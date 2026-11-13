"""Poll Proxmox's structured journal API; push selected units through the Loki gateway.

No third-party Python dependencies. Progress advances only after HTTP 204 from
Loki. A crash after acceptance but before checkpointing can replay the last batch
(at-least-once delivery). Source rotation/expiry can still remove unread records.
"""

import argparse
import base64
import gzip
import io
import json
import logging
import os
from pathlib import Path
import signal
import ssl
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import (
    build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request,
)


UNITS = ("ssh", "pveproxy", "pvedaemon")
LEVELS = ("emerg", "alert", "crit", "err", "warning", "notice", "info", "debug")
MAX_RESPONSE = 16 * 1024 * 1024
MAX_ENTRIES = 10000
BATCH_ENTRIES = 100
BATCH_BYTES = 256 * 1024
STATE_FILE = Path(os.environ.get("STATE_DIR", "/var/lib/collector")) / "state.json"


class CollectorError(Exception):
    """A diagnostic safe to print without log contents or credentials."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CollectorError("HTTP redirect refused; configure the final HTTPS address")


def tls_context(target, verify_pve):
    if target == "pve" and not verify_pve:
        # Explicit opt-in, equivalent to curl --insecure for Proxmox only.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.set_alpn_protocols(["http/1.1"])
        return context
    ca = {"pve": "/etc/collector/certs/proxmox-ca.crt",
          "loki": "/etc/collector/certs/logging-root.crt"}[target]
    return ssl.create_default_context(cafile=ca)


def secret(path):
    value = Path(path).read_text(encoding="utf-8")
    if not value or any(c in value for c in "\r\n\x00"):
        raise CollectorError("Secret file is empty or contains a newline/control character")
    return value


def https_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise CollectorError("Configure an HTTPS base URL without credentials, query or path")
    return value.rstrip("/")


def read_json_response(response):
    # Proxmox's journal endpoint may gzip even without Accept-Encoding.
    data = response.read(MAX_RESPONSE + 1)
    if len(data) > MAX_RESPONSE:
        raise CollectorError("API response too large; reduce INITIAL_LOOKBACK_SECONDS")
    if response.headers.get("Content-Encoding", "").lower() == "gzip":
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            data = stream.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise CollectorError("Expanded API response too large; reduce INITIAL_LOOKBACK_SECONDS")
    return json.loads(data)


class Client:
    def __init__(self):
        self.pve_url = https_url(os.environ["PVE_URL"])
        self.logging_url = https_url(os.environ["LOGGING_URL"])
        self.node = os.environ["PVE_NODE"]
        self.host = os.environ["LOG_HOST"]
        self.owner = os.environ["LOG_OWNER"]
        if not all((self.node, self.host, self.owner)) or any(
                "<" in v for v in (self.node, self.host, self.owner)):
            raise CollectorError("Set PVE_NODE, LOG_HOST and LOG_OWNER")
        token = secret("/run/secrets/pve-token")
        if not token.startswith("PVEAPIToken=") or "!" not in token:
            raise CollectorError("pve-token must contain PVEAPIToken=user@realm!token=secret")
        self.pve_auth = token
        pw = secret("/run/secrets/logging-password")
        self.loki_auth = "Basic " + base64.b64encode(("infra:" + pw).encode()).decode()
        self.openers = {}
        verify_value = os.environ.get("PVE_TLS_VERIFY", "true").strip().lower()
        if verify_value not in ("true", "false"):
            raise CollectorError("PVE_TLS_VERIFY must be exactly true or false")
        verify_pve = verify_value == "true"
        self.pve_tls_mode = ("CA and hostname verification" if verify_pve else
                             "verification DISABLED; HTTPS encryption only")
        for name in ("pve", "loki"):
            handler = HTTPSHandler(context=tls_context(name, verify_pve))
            # Explicit direct connection; never send API credentials through an env proxy.
            self.openers[name] = build_opener(
                ProxyHandler({}), handler, NoRedirect())

    def request(self, target, path, params=None, payload=None):
        base = self.pve_url if target == "pve" else self.logging_url
        auth = self.pve_auth if target == "pve" else self.loki_auth
        url = base + path + ("?" + urlencode(params) if params else "")
        headers = {"Authorization": auth, "Accept": "application/json"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, separators=(",", ":")).encode()
        request = Request(url, data=body, headers=headers)
        try:
            with self.openers[target].open(request, timeout=30) as response:
                expected = 204 if payload is not None else 200
                if response.status != expected:
                    raise CollectorError(f"{target} returned HTTP {response.status}; expected {expected}")
                return None if payload is not None else read_json_response(response)
        except HTTPError as error:
            code = error.code
            error.close()
            hints = {400: "check journal structured/unit support or Loki age/ingestion limits",
                     401: "check the credential file", 403: "check user AND token ACLs"}
            raise CollectorError(f"{target} HTTP {code}: " + hints.get(code, "request failed")) from None
        except (URLError, TimeoutError, OSError):
            raise CollectorError(f"{target} connection/TLS failure; check routing, CA and certificate hostname") from None

    def journal(self, unit, params):
        return self.request("pve", "/api2/json/nodes/" + quote(self.node, safe="") + "/journal",
                            dict(params, structured=1, unit=unit))

    def push(self, payload):
        self.request("loki", "/loki/api/v1/push", payload=payload)


def parse_journal(payload, unit, host, owner):
    """Read the Proxmox -J schema: cursor {ty,c}, entries {t,id,msg,p}.

    't' is integer microseconds since epoch, as used by Proxmox JournalView.
    The API applies the systemd-unit filter; arbitrary other units aren't fetched.
    """
    if not isinstance(payload, dict) or payload.get("success") in (0, False):
        raise CollectorError("Journal request did not succeed")
    records = payload.get("data")
    if not isinstance(records, list):
        raise CollectorError("Unexpected journal response: data must be an array")
    if len(records) > MAX_ENTRIES:
        raise CollectorError("Too many entries; reduce INITIAL_LOOKBACK_SECONDS")
    cursor = None
    groups = {}
    for record in records:
        if not isinstance(record, dict):
            raise CollectorError("Structured journal unavailable; response contains text instead of objects")
        kind = record.get("ty")
        if kind == "cursor":
            if not isinstance(record.get("c"), str) or not record["c"]:
                raise CollectorError("Invalid journal cursor")
            cursor = record["c"]
        elif kind in ("host", "reboot", "identifiers", "units"):
            continue
        else:
            timestamp = record.get("t")
            message = record.get("msg")
            priority = record.get("p", 6)
            if (type(timestamp) is not int or timestamp <= 0
                    or not isinstance(message, str) or type(priority) is not int
                    or not 0 <= priority <= 7):
                raise CollectorError("Unexpected structured journal entry; checkpoint not advanced")
            # A supplied unit field must agree with the requested filter.
            if record.get("unit", unit + ".service").removesuffix(".service") != unit:
                raise CollectorError("API returned a different unit; checkpoint not advanced")
            groups.setdefault(LEVELS[priority], []).append([str(timestamp * 1000), message])
    if groups and cursor is None:
        raise CollectorError("Entries lack an end cursor; checkpoint not advanced")
    streams = []
    for level, values in groups.items():
        values.sort(key=lambda value: int(value[0]))
        streams.append({"stream": {"host": host, "owner": owner, "service": unit, "level": level},
                        "values": values})
    return cursor, {"streams": streams}


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(state, output, separators=(",", ":"))
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)
    if os.name != "nt":
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def make_batches(payload):
    """Keep individual pushes small; reject oversized lines without dropping them."""
    batches = []
    for stream in payload["streams"]:
        values = []
        size = len(json.dumps({"streams": [{"stream": stream["stream"], "values": []}]}).encode())
        overhead = size
        for value in stream["values"]:
            added = len(json.dumps(value).encode()) + 2
            if overhead + added > BATCH_BYTES:
                raise CollectorError("A journal line exceeds the batch limit; progress retained")
            if values and (len(values) >= BATCH_ENTRIES or size + added > BATCH_BYTES):
                batches.append({"streams": [{"stream": stream["stream"], "values": values}]})
                values, size = [], overhead
            values.append(value)
            size += added
        if values:
            batches.append({"streams": [{"stream": stream["stream"], "values": values}]})
    return batches


class Collector:
    def __init__(self, client, path=STATE_FILE, lookback=43200):
        self.client, self.path = client, path
        identity = {"url": client.pve_url, "node": client.node,
                    "host": client.host, "owner": client.owner, "logging_url": client.logging_url}
        if path.exists():
            self.state = json.loads(path.read_text(encoding="utf-8"))
            if self.state.get("identity") != identity:
                raise CollectorError("Source/labels/gateway changed; review existing state before using a new state volume")
        else:
            self.state = {"identity": identity, "since": int(time.time()) - lookback,
                          "cursors": {}, "pending": None, "last_success": 0}
            save_state(path, self.state)

    def deliver_pending(self):
        pending = self.state["pending"]
        if pending is None:
            return
        while pending["next"] < len(pending["batches"]):
            self.client.push(pending["batches"][pending["next"]])
            pending["next"] += 1
            save_state(self.path, self.state)
        # Never checkpoint before Loki confirms receipt.
        self.state["cursors"][pending["unit"]] = pending["cursor"]
        self.state["pending"] = None
        save_state(self.path, self.state)

    def poll(self):
        self.deliver_pending()
        sent = 0
        for unit in UNITS:
            cursor = self.state["cursors"].get(unit)
            # Fixed upper bound keeps a finite snapshot if the node is busy.
            params = {"until": int(time.time()) - 2}
            params.update({"startcursor": cursor} if cursor else {"since": self.state["since"]})
            payload = self.client.journal(unit, params)
            next_cursor, batch = parse_journal(payload, unit, self.client.host, self.client.owner)
            count = sum(len(stream["values"]) for stream in batch["streams"])
            if count:
                self.state["pending"] = {"unit": unit, "cursor": next_cursor,
                                         "batches": make_batches(batch), "next": 0}
                save_state(self.path, self.state)
                self.deliver_pending()
                sent += count
            elif next_cursor:
                self.state["cursors"][unit] = next_cursor
                save_state(self.path, self.state)
        self.state["last_success"] = int(time.time())
        save_state(self.path, self.state)
        logging.info("poll OK; delivered=%d", sent)


def preflight(client):
    logging.info("Proxmox TLS trust: %s", client.pve_tls_mode)
    for unit in UNITS:
        _, batch = parse_journal(client.journal(unit, {"lastentries": 3}), unit, client.host, client.owner)
        logging.info("API check OK: %s; sample_entries=%d", unit,
                     sum(len(stream["values"]) for stream in batch["streams"]))
    result = client.request("loki", "/loki/api/v1/labels")
    if result.get("status") != "success":
        raise CollectorError("Loki login check did not succeed")
    logging.info("infra login and certificate check OK; no logs sent; no progress changed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="read-only API, schema, CA and infra login test")
    mode.add_argument("--once", action="store_true", help="one fetch/send cycle; saves progress")
    mode.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.healthcheck:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return 0 if time.time() - state["last_success"] < 180 else 1
        client = Client()
        if args.check:
            preflight(client)
            return 0
        logging.info("Proxmox TLS trust: %s", client.pve_tls_mode)
        interval = int(os.environ.get("POLL_SECONDS", "15"))
        lookback = int(os.environ.get("INITIAL_LOOKBACK_SECONDS", "43200"))
        if not 5 <= interval <= 300 or not 1 <= lookback <= 86400:
            raise CollectorError("POLL_SECONDS must be 5..300; INITIAL_LOOKBACK_SECONDS 1..86400")
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Refuse two pollers sharing a checkpoint (preflight is read-only).
        import fcntl
        with (STATE_FILE.parent / "collector.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CollectorError("Another collector is using this state volume") from None
            collector = Collector(client, lookback=lookback)
            if args.once:
                collector.poll()
                return 0
            stop = threading.Event()
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: stop.set())
            while not stop.is_set():
                try:
                    collector.poll()
                except Exception as error:
                    # No API response bodies, URLs with secrets, or raw log lines.
                    message = str(error) if isinstance(error, CollectorError) else type(error).__name__
                    logging.error("cycle failed; progress retained: %s", message)
                stop.wait(interval)
        return 0
    except Exception as error:
        message = str(error) if isinstance(error, CollectorError) else type(error).__name__
        logging.error("collector stopped: %s", message)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
