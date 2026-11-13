import gzip
import io
import json
import os
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import HTTPSHandler

from collector import (
    Client, Collector, CollectorError, NoRedirect, UNITS, https_url,
    tls_context,
    make_batches, parse_journal, read_json_response, secret,
)


STAMP = 1793367009123456


def journal(cursor="end", message="login accepted", priority=6):
    return {"success": 1, "data": [
        {"ty": "cursor", "c": "begin"}, {"ty": "host", "h": "smith"},
        {"t": STAMP, "id": "sshd", "pid": 123, "msg": message, "p": priority},
        {"ty": "cursor", "c": cursor},
    ]}


class FakeClient:
    pve_url = "https://pve.example:8006"
    logging_url = "https://logs.example"
    node = host = "smith"
    owner = "test-owner"

    def __init__(self):
        self.calls, self.sent = [], []
        self.fail = False
        self.bad_unit = None

    def journal(self, unit, params):
        self.calls.append((unit, params))
        if unit == self.bad_unit:
            return {"data": ["legacy text"]}
        if "startcursor" in params:
            return {"success": 1, "data": []}
        return journal("end-" + unit, message="message-" + unit)

    def push(self, payload):
        if self.fail:
            raise CollectorError("loki HTTP 503")
        self.sent.append(payload)


class ParsingTests(unittest.TestCase):
    def test_fields_timestamp_priority_and_multiline(self):
        cursor, batch = parse_journal(journal(message="line1\nline2", priority=0), "ssh", "smith", "Vives")
        self.assertEqual(cursor, "end")
        self.assertEqual(batch["streams"], [{"stream": {
            "host": "smith", "owner": "Vives", "service": "ssh", "level": "emerg"},
            "values": [[str(STAMP * 1000), "line1\nline2"]]}])

    def test_empty_response_is_valid(self):
        self.assertEqual(parse_journal({"data": []}, "ssh", "h", "o"), (None, {"streams": []}))

    def test_bad_responses_fail_without_skipping(self):
        cases = [{"success": 0, "data": []}, {"data": ["legacy text"]},
                 {"data": [{"t": STAMP, "msg": "no cursor"}]},
                 {"data": [{"t": "not an integer", "msg": "secret log content"}]},
                 {"data": [{"t": STAMP, "msg": "x", "p": 9}]},
                 {"data": [{"ty": "cursor", "c": ""}]},
                 {"data": [{"t": STAMP, "msg": "x", "unit": "other.service"}]}]
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(CollectorError) as caught:
                parse_journal(payload, "ssh", "h", "o")
            self.assertNotIn("secret log content", str(caught.exception))

    def test_streams_sorted_by_numeric_timestamp(self):
        data = journal()
        data["data"].insert(2, {"t": STAMP + 3, "msg": "later", "p": 6})
        _, batch = parse_journal(data, "ssh", "h", "o")
        self.assertEqual([v[1] for v in batch["streams"][0]["values"]], ["login accepted", "later"])


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.json"
        self.client = FakeClient()

    def tearDown(self):
        self.temp.cleanup()

    def test_three_units_and_restart_resume_without_replay(self):
        Collector(self.client, self.path).poll()
        state = json.loads(self.path.read_text())
        self.assertEqual(set(state["cursors"]), set(UNITS))
        self.assertEqual(len(self.client.sent), 3)
        Collector(self.client, self.path).poll()
        self.assertEqual(len(self.client.sent), 3)
        for unit, params in self.client.calls[3:]:
            self.assertEqual(params["startcursor"], "end-" + unit)
            self.assertNotIn("since", params)

    def test_delivery_failure_spools_and_does_not_advance(self):
        self.client.fail = True
        with self.assertRaises(CollectorError):
            Collector(self.client, self.path).poll()
        state = json.loads(self.path.read_text())
        self.assertEqual(state["cursors"], {})
        self.assertEqual(state["pending"]["unit"], "ssh")
        expected = state["pending"]["batches"][0]
        self.client.fail = False
        Collector(self.client, self.path).poll()
        self.assertEqual(self.client.sent[0], expected)
        self.assertEqual(json.loads(self.path.read_text())["pending"], None)

    def test_malformed_second_unit_preserves_first_only(self):
        self.client.bad_unit = "pveproxy"
        with self.assertRaises(CollectorError):
            Collector(self.client, self.path).poll()
        self.assertEqual(json.loads(self.path.read_text())["cursors"], {"ssh": "end-ssh"})

    def test_initial_since_survives_restart_and_failure(self):
        with patch("collector.time.time", return_value=10000):
            Collector(self.client, self.path, lookback=3600)
        with patch("collector.time.time", return_value=20000):
            resumed = Collector(self.client, self.path, lookback=100)
        self.assertEqual(resumed.state["since"], 6400)

    def test_source_change_refused(self):
        Collector(self.client, self.path)
        self.client.node = "different-node"
        with self.assertRaises(CollectorError):
            Collector(self.client, self.path)

    def test_corrupt_state_is_not_reset(self):
        self.path.write_text("damaged")
        with self.assertRaises(json.JSONDecodeError):
            Collector(self.client, self.path)
        self.assertEqual(self.path.read_text(), "damaged")

    def test_partial_delivery_resumes_from_saved_batch(self):
        source = journal()
        source["data"].insert(3, {"t": STAMP + 1, "msg": "second", "p": 6})
        original_push = self.client.push
        def fail_second(payload):
            if len(self.client.sent) == 1:
                raise CollectorError("loki HTTP 503")
            original_push(payload)
        self.client.push = fail_second
        self.client.journal = lambda unit, params: source if "startcursor" not in params else {"data": []}
        with patch("collector.BATCH_ENTRIES", 1), self.assertRaises(CollectorError):
            Collector(self.client, self.path).poll()
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved["pending"]["next"], 1)
        self.assertEqual(saved["cursors"], {})
        self.client.push = original_push
        with patch("collector.BATCH_ENTRIES", 1):
            Collector(self.client, self.path).poll()
        self.assertEqual(self.client.sent[1]["streams"][0]["values"][0][1], "second")

    def test_batch_limits_and_oversize_rejection(self):
        _, payload = parse_journal(journal(), "ssh", "h", "o")
        with patch("collector.BATCH_BYTES", 20), self.assertRaises(CollectorError):
            make_batches(payload)


class TransportTests(unittest.TestCase):
    def test_gzip_api_envelope(self):
        response = io.BytesIO(gzip.compress(json.dumps(journal()).encode()))
        response.headers = {"Content-Encoding": "gzip"}
        self.assertEqual(read_json_response(response), journal())

    def test_decompression_bound(self):
        response = io.BytesIO(gzip.compress(b"x" * 100))
        response.headers = {"Content-Encoding": "gzip"}
        with patch("collector.MAX_RESPONSE", 60), self.assertRaises(CollectorError):
            read_json_response(response)

    def test_redirect_refused(self):
        with self.assertRaises(CollectorError):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example")

    def test_https_only_and_no_url_credentials(self):
        for url in ("http://pve.example", "https://user:pw@pve.example", "https://pve.example/path"):
            with self.subTest(url=url), self.assertRaises(CollectorError):
                https_url(url)
        self.assertEqual(https_url("https://pve.example:8006/"), "https://pve.example:8006")

    def test_secret_newline_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "password"
            path.write_text("password\n")
            with self.assertRaises(CollectorError):
                secret(path)

    def test_http_error_body_not_exposed(self):
        client = object.__new__(Client)
        client.pve_url, client.pve_auth = "https://pve.example:8006", "secret-token"
        from unittest.mock import Mock
        opener = Mock()
        opener.open.side_effect = HTTPError("https://pve.example", 403, "raw private detail", {},
                                            io.BytesIO(b"private logs"))
        client.openers = {"pve": opener}
        with self.assertRaises(CollectorError) as caught:
            client.request("pve", "/api2/json/nodes/smith/journal")
        self.assertNotIn("private", str(caught.exception))
        self.assertIn("403", str(caught.exception))

    def test_api_filter_is_always_sent(self):
        client = object.__new__(Client)
        client.node = "smith"
        with patch.object(client, "request", return_value=journal()) as request:
            client.journal("ssh", {"startcursor": "saved"})
        self.assertEqual(request.call_args.args, (
            "pve", "/api2/json/nodes/smith/journal",
            {"startcursor": "saved", "structured": 1, "unit": "ssh"}))


class TLSModeTests(unittest.TestCase):
    def test_disabled_pve_mode_needs_no_ca_file(self):
        with patch("collector.ssl.create_default_context") as load_ca:
            context = tls_context("pve", False)
        load_ca.assert_not_called()
        self.assertFalse(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)

    def test_disabled_pve_mode_keeps_loki_verified(self):
        verified = ssl.create_default_context()
        with patch("collector.ssl.create_default_context", return_value=verified) as load_ca:
            context = tls_context("loki", False)
        load_ca.assert_called_once_with(cafile="/etc/collector/certs/logging-root.crt")
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_verified_pve_mode_loads_ca(self):
        verified = ssl.create_default_context()
        with patch("collector.ssl.create_default_context", return_value=verified) as load_ca:
            context = tls_context("pve", True)
        load_ca.assert_called_once_with(cafile="/etc/collector/certs/proxmox-ca.crt")
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def client_context(self, value):
        from contextlib import ExitStack
        env = {"PVE_URL": "https://pve.example:8006", "PVE_NODE": "smith",
               "LOGGING_URL": "https://logs.example", "LOG_HOST": "smith", "LOG_OWNER": "test"}
        if value is not None:
            env["PVE_TLS_VERIFY"] = value
        with ExitStack() as stack:
            stack.enter_context(patch.dict("collector.os.environ", env))
            if value is None:
                os.environ.pop("PVE_TLS_VERIFY", None)
            stack.enter_context(patch("collector.secret", side_effect=["PVEAPIToken=test@pve!test=secret", "password"]))
            load_ca = stack.enter_context(patch("collector.ssl.create_default_context", side_effect=lambda **_: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)))
            client = Client()
            return client, load_ca.call_args_list

    def test_real_client_in_no_ca_mode_only_loads_gateway_ca(self):
        client, calls = self.client_context("false")
        self.assertEqual([call.kwargs for call in calls], [{"cafile": "/etc/collector/certs/logging-root.crt"}])
        contexts = {name: next(handler._context for handler in opener.handlers if isinstance(handler, HTTPSHandler))
                    for name, opener in client.openers.items()}
        self.assertEqual(contexts["pve"].verify_mode, ssl.CERT_NONE)
        self.assertEqual(contexts["loki"].verify_mode, ssl.CERT_REQUIRED)

    def test_default_client_mode_is_verified(self):
        _, calls = self.client_context(None)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].kwargs["cafile"], "/etc/collector/certs/proxmox-ca.crt")

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(CollectorError):
            self.client_context("flase")


if __name__ == "__main__":
    unittest.main()
