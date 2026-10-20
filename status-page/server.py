"""Publish approved aliases and binary status; keep all source labels private."""

import html
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen


POLL_SECONDS = 30
SNAPSHOT_TTL = 45
SAMPLE_TTL = 90  # Three scrapes at the repository's 30-second interval.
IDENTITY = {"service", "host", "module", "instance"}
PROBE = 'probe_success{job="blackbox"}'
SCRAPE = 'up{job="blackbox"}'
QUERY = (
    f'({PROBE} == 1) and ({SCRAPE} == 1) '
    f'and (time() - timestamp({PROBE}) < {SAMPLE_TTL}) '
    f'and (time() - timestamp({SCRAPE}) < {SAMPLE_TTL})'
)


def load_services(filename):
    """Require explicit check identities; no discovery-based publication."""
    config = json.loads(Path(filename).read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) != {"services"}:
        raise ValueError("Expected services configuration")
    services = config["services"]
    if not isinstance(services, list) or not 1 <= len(services) <= 100:
        raise ValueError("Configure between 1 and 100 services")
    names = set()
    for service in services:
        if not isinstance(service, dict) or set(service) != {"name", "checks"}:
            raise ValueError("Expected name and checks")
        name = service["name"]
        if (not isinstance(name, str) or not 1 <= len(name) <= 80
                or name != name.strip() or not name.isprintable() or name in names):
            raise ValueError("Public names must be unique printable text")
        names.add(name)
        checks = service["checks"]
        if not isinstance(checks, list) or not 1 <= len(checks) <= 10:
            raise ValueError("Configure between 1 and 10 checks per service")
        for check in checks:
            if (not isinstance(check, dict) or not IDENTITY <= check.keys()
                    or check.keys() - IDENTITY - {"group"}
                    or any(not isinstance(v, str) or not v.strip() or "<" in v
                           for v in check.values())):
                raise ValueError("Replace check placeholders with exact target labels")
    return services


def read_healthy(prometheus_url):
    url = prometheus_url.rstrip("/") + "/api/v1/query?" + urlencode(
        {"query": QUERY, "timeout": "4s"}
    )
    try:
        with urlopen(url, timeout=5) as response:
            payload = response.read(2_000_001)
    except HTTPError as error:
        error.close()
        raise ValueError("Source HTTP error") from None
    if len(payload) > 2_000_000:
        raise ValueError("Source response too large")
    result = json.loads(payload)
    if (result.get("status") != "success" or result.get("warnings")
            or result.get("data", {}).get("resultType") != "vector"):
        raise ValueError("Source query failed")
    series = result["data"]["result"]
    if not isinstance(series, list):
        raise ValueError("Invalid source vector")
    # Keep these labels inside the collector; never copy them into public output.
    healthy = []
    for item in series:
        labels, value = item["metric"], item["value"]
        if (not isinstance(labels, dict)
                or any(not isinstance(k, str) or not isinstance(v, str)
                       for k, v in labels.items())
                or not isinstance(value, list) or len(value) != 2):
            raise ValueError("Invalid source series")
        if float(value[1]) == 1:
            healthy.append(labels)
    return healthy


def public_services(services, healthy):
    def passed(check):
        matches = [labels for labels in healthy
                   if all(labels.get(key) == value for key, value in check.items())]
        return len(matches) == 1

    return [{"name": service["name"],
             "status": "Up" if all(passed(c) for c in service["checks"]) else "Down"}
            for service in services]


class StatusStore:
    def __init__(self, services, prometheus_url, clock=time.monotonic):
        self.services = services
        self.prometheus_url = prometheus_url
        self.clock = clock
        self.lock = threading.Lock()
        self.snapshot = public_services(services, [])
        self.updated = None

    def refresh(self):
        try:
            healthy = read_healthy(self.prometheus_url)
        except Exception:
            # Source errors may contain private URLs or labels. Do not log them.
            logging.warning("Status source unavailable; publishing Down")
            healthy = []
        snapshot = public_services(self.services, healthy)
        with self.lock:
            self.snapshot = snapshot
            self.updated = self.clock()

    def get(self):
        with self.lock:
            if self.updated is None or self.clock() - self.updated >= SNAPSHOT_TTL:
                return public_services(self.services, [])
            return self.snapshot

    def poll(self, stop):
        while not stop.is_set():
            self.refresh()
            stop.wait(POLL_SECONDS)


def render_page(services):
    rows = "".join(
        '<li><span class="name">' + html.escape(s["name"]) + '</span>'
        '<span class="status ' + s["status"].lower() + '">' + s["status"] + '</span></li>'
        for s in services
    )
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta http-equiv="refresh" content="30"><title>Service status</title>'
            '<link rel="stylesheet" href="/style.css"></head><body><main>'
            '<header><h1>Service status</h1><p>Current service availability</p></header>'
            '<ul aria-label="Service availability">' + rows + '</ul>'
            '<footer>Refreshes automatically every 30 seconds.</footer>'
            '</main></body></html>').encode("utf-8")


def make_handler(store):
    stylesheet = Path(__file__).with_name("style.css").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not retain visitor addresses, query strings or request headers.

        def respond(self, code, content_type, body, head=False):
            self.send_response_only(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'self'; "
                             "base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def send_error(self, code, message=None, explain=None):
            self.respond(code, "text/plain; charset=utf-8", b"Request unavailable\n",
                         self.command == "HEAD")

        def do_GET(self, head=False):
            # Exact routes only: no query forwarding, files, debug pages or proxy.
            if self.path == "/":
                self.respond(200, "text/html; charset=utf-8", render_page(store.get()), head)
            elif self.path == "/api/status":
                body = json.dumps({"services": store.get()}, ensure_ascii=True).encode("utf-8")
                self.respond(200, "application/json; charset=utf-8", body, head)
            elif self.path == "/style.css":
                self.respond(200, "text/css; charset=utf-8", stylesheet, head)
            else:
                self.send_error(404)

        def do_HEAD(self):
            self.do_GET(head=True)

    return Handler


class StatusServer(ThreadingHTTPServer):
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(10)
        return connection, address

    def handle_error(self, request, client_address):
        pass  # Keep request contents and visitor addresses out of tracebacks.


def main():
    try:
        services = load_services(os.environ.get("STATUS_CONFIG", "/config/services.json"))
    except Exception:
        raise SystemExit("Invalid status configuration; check the private services file") from None
    store = StatusStore(services, os.environ.get("PROMETHEUS_URL", "http://prometheus:9090"))
    stop = threading.Event()
    worker = threading.Thread(target=store.poll, args=(stop,), daemon=True)
    worker.start()
    server = StatusServer(("0.0.0.0", 8080), make_handler(store))
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        worker.join(timeout=6)


if __name__ == "__main__":
    main()
