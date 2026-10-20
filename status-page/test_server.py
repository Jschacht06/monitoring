import copy
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

import server

CHECK = dict(service='private-service', host='secret-host', module='http_2xx',
             instance='http://192.0.2.7:9000/private?token=secret')
SERVICES = [dict(name='Community website', checks=[CHECK])]
LABELS = dict(CHECK, job='blackbox', owner='Secret Owner', contact='private@example.invalid',
              dependencies='secret-database')


def vector(labels=None):
    return dict(status='success', data=dict(resultType='vector', result=[
        dict(metric=labels or LABELS, value=[time.time(), '1'])]))


class StatusTests(unittest.TestCase):
    def test_allowlist_aggregation_and_ambiguity(self):
        self.assertEqual(server.public_services(SERVICES, [LABELS]),
                         [dict(name='Community website', status='Up')])
        for labels in [[], [dict(LABELS, instance='other')], [LABELS, LABELS]]:
            self.assertEqual(server.public_services(SERVICES, labels)[0]['status'], 'Down')
        combined = copy.deepcopy(SERVICES)
        combined[0]['checks'].append(dict(CHECK, module='tcp_connect'))
        self.assertEqual(server.public_services(combined, [LABELS])[0]['status'], 'Down')
        self.assertEqual(server.public_services(combined, [LABELS, dict(LABELS, module='tcp_connect')])[0]['status'], 'Up')
        grouped = copy.deepcopy(SERVICES)
        grouped[0]['checks'][0]['group'] = 'selected'
        self.assertEqual(server.public_services(grouped, [dict(LABELS, group='other')])[0]['status'], 'Down')

    def test_startup_expiry_failure_and_recovery(self):
        clock = [100.0]
        store = server.StatusStore(SERVICES, 'http://private-source', clock=lambda: clock[0])
        self.assertEqual(store.get()[0]['status'], 'Down')
        with patch.object(server, 'read_healthy', return_value=[LABELS]):
            store.refresh()
        self.assertEqual(store.get()[0]['status'], 'Up')
        clock[0] += server.SNAPSHOT_TTL
        self.assertEqual(store.get()[0]['status'], 'Down')
        with patch.object(server, 'read_healthy', side_effect=ValueError('secret error')):
            store.refresh()
        self.assertEqual(store.get()[0]['status'], 'Down')
        with patch.object(server, 'read_healthy', return_value=[LABELS]):
            store.refresh()
        self.assertEqual(store.get()[0]['status'], 'Up')

    def test_configuration_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            filename = Path(temp) / 'services.json'
            for value in [dict(services=SERVICES), dict(services=[]),
                          dict(services=SERVICES * 2),
                          dict(services=[dict(name='A', checks=[dict(service='x')])]),
                          dict(services=[dict(name='A', checks=[dict(CHECK, instance='<replace>')])])]:
                filename.write_text(json.dumps(value), encoding='utf-8')
                if value == dict(services=SERVICES):
                    self.assertEqual(server.load_services(filename), SERVICES)
                else:
                    with self.assertRaises(ValueError):
                        server.load_services(filename)

    def test_promql_fixture_matches_runtime_query(self):
        fixture = Path(__file__).with_name("query-tests.yml").read_text(encoding="utf-8")
        self.assertEqual(fixture.count("expr: " + json.dumps(server.QUERY)), 6)

    def test_html_escapes_public_names(self):
        page = server.render_page([dict(name='<script>alert(1)</script>', status='Down')])
        self.assertNotIn(b'<script>', page)
        self.assertIn(b'&lt;script&gt;', page)

    def test_real_http_source_and_public_boundary(self):
        state = dict(payload=vector(), code=200, queries=[])

        class Source(BaseHTTPRequestHandler):
            def do_GET(self):
                state['queries'].append(parse_qs(urlsplit(self.path).query))
                self.send_response(state['code'])
                self.end_headers()
                self.wfile.write(json.dumps(state['payload']).encode())

            def log_message(self, *args):
                pass

        upstream = ThreadingHTTPServer(('127.0.0.1', 0), Source)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        store = server.StatusStore(SERVICES, 'http://127.0.0.1:' + str(upstream.server_port))
        public = server.StatusServer(('127.0.0.1', 0), server.make_handler(store))
        worker = threading.Thread(target=public.serve_forever, daemon=True)
        worker.start()
        origin = 'http://127.0.0.1:' + str(public.server_port)
        try:
            store.refresh()
            self.assertEqual(store.get()[0]['status'], 'Up')
            self.assertEqual(state['queries'][0]['query'], [server.QUERY])
            self.assertIn('timestamp(probe_success', server.QUERY)
            self.assertIn('timestamp(up', server.QUERY)
            for route in ['/', '/api/status', '/style.css', '/config/services.json',
                          '/api/v1/query?query=up', '/?query=up', '/../../server.py', '/metrics']:
                try:
                    response = urlopen(origin + route)
                except HTTPError as error:
                    response = error
                body = response.read().decode()
                visible = str(response.headers) + body
                for secret in ['secret-host', '192.0.2.7', 'private-service', 'private@example.invalid',
                               'secret-database', 'Secret Owner', 'Python/', 'private-source']:
                    self.assertNotIn(secret, visible)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertIsNone(response.headers['Server'])
                if route == '/api/status':
                    self.assertEqual(json.loads(body), dict(services=[dict(name='Community website', status='Up')]))
                elif route not in ['/', '/style.css']:
                    self.assertEqual(response.status, 404)
                response.close()
            response = urlopen(Request(origin + '/api/status', method='HEAD'))
            self.assertEqual(response.read(), b'')
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(origin + '/', method='POST', data=b'secret'))
            self.assertEqual(error.exception.code, 501)
            error.exception.close()
            # Public visitor requests only read the cached snapshot.
            self.assertEqual(len(state['queries']), 1)
            for payload, code in [(dict(status='error', error='secret-host'), 200),
                                  (dict(status='success', data=dict(resultType='vector', result=[])), 200),
                                  (vector(), 500),
                                  (dict(status='success', data=dict(resultType='vector', result=[dict(metric=[], value=[0, '1'])])), 200), (dict(vector(), warnings=['partial data']), 200),
                                  (dict(status='success', data=dict(resultType='matrix', result=[])), 200)]:
                state.update(payload=payload, code=code)
                store.refresh()
                self.assertEqual(store.get()[0]['status'], 'Down')
                self.assertNotIn('secret-host', urlopen(origin + '/api/status').read().decode())
            state.update(payload=vector(), code=200)
            store.refresh()
            self.assertEqual(store.get()[0]['status'], 'Up')
        finally:
            public.shutdown()
            upstream.shutdown()
            public.server_close()
            upstream.server_close()
            worker.join(timeout=2)
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
