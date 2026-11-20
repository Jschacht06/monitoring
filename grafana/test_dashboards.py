"""Validate dashboard archives, import references and source feature preservation.

Run from the monitoring repository: python -B -m unittest discover -s grafana -p test_dashboards.py
Pass --sources to run this file directly and compare against supplied JSON files.
"""
import argparse
import copy
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = None


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def panels(items):
    for panel in items:
        yield panel
        yield from panels(panel.get('panels', []))


def normalized(panel):
    panel = copy.deepcopy(panel)
    panel.pop('id', None)
    panel.pop('gridPos', None)
    panel.pop('scopedVars', None)
    return panel


class DashboardTests(unittest.TestCase):
    def test_original_archives_are_byte_identical(self):
        manifest = read(ROOT / 'docs/dashboard-sources.json')
        for name, digest in manifest['archived'].items():
            self.assertFalse((ROOT / name).exists())
            self.assertEqual(hashlib.sha256((ROOT / 'old templates' / name).read_bytes()).hexdigest(), digest)

    def test_import_identity_and_variables(self):
        paths = list(ROOT.glob('*.json'))
        expected={'host-systems-and-disk-health.json', 'proxmox-resources-and-group-budgets.json'}
        if (ROOT / 'service-health-and-catalogue.json').exists():
            expected.add('service-health-and-catalogue.json')
        self.assertEqual({p.name for p in paths}, expected)
        for path in paths:
            with self.subTest(path=path.name):
                dashboard = read(path)
                self.assertIsNone(dashboard['uid'])
                self.assertIsNone(dashboard['id'])
                self.assertIn('noc-monitoring', dashboard['tags'])
                items = list(panels(dashboard['panels']))
                ids = [p['id'] for p in items]
                self.assertEqual(len(ids), len(set(ids)))
                variables = [v['name'] for v in dashboard['templating']['list']]
                self.assertEqual(len(variables), len(set(variables)))
                inputs = [v['name'] for v in dashboard.get('__inputs', [])]
                text = json.dumps(dashboard)
                self.assertNotIn('<your ', text)
                for name in re.findall(r'\$(?:\{([a-zA-Z_][\w]*)(?::[^}]+)?\}|([a-zA-Z_][\w]*))', text):
                    name = name[0] or name[1]
                    if not name.startswith('__'):
                        self.assertIn(name, variables + inputs, name)
                for p in items:
                    self.assertNotIn(p['type'], ('graph', 'singlestat', 'table-old'))
                    self.assertLessEqual(p['gridPos']['x'] + p['gridPos']['w'], 24)
                    refs = [t['refId'] for t in p.get('targets', [])]
                    self.assertEqual(len(refs), len(set(refs)))
                for v in dashboard['templating']['list']:
                    if v['type'] == 'constant':
                        self.assertEqual(v['current']['value'], v['query'])
                        self.assertEqual(v['options'][0]['value'], v['query'])

    def test_automatic_guest_monitoring_without_budget_rules(self):
        dashboard = read(ROOT / 'proxmox-resources-and-group-budgets.json')
        items = list(panels(dashboard['panels']))
        titles = [p.get('title') for p in items if p['type'] != 'row']
        self.assertEqual(len(titles), 13)
        self.assertEqual(titles.count('VM and LXC inventory'), 1)
        self.assertIn('Guests and allocated capacity by node', titles)
        self.assertIn('Unknown guest state', titles)
        self.assertNotIn('group', [v['name'] for v in dashboard['templating']['list']])
        expressions = '\n'.join(t['expr'] for p in items for t in p.get('targets', []))
        self.assertNotRegex(expressions, r'\b(?:noc_|probe_|node_)\w+')
        inventory = next(p for p in items if p['title'] == 'VM and LXC inventory' and p['type'] == 'table')
        columns = inventory['transformations'][1]['options']['renameByName']
        self.assertEqual(columns['node'], 'Node')
        self.assertNotIn('host', columns)

    def test_physical_host_and_guest_dashboards_do_not_overlap(self):
        guests = read(ROOT / 'proxmox-resources-and-group-budgets.json')
        hosts = read(ROOT / 'host-systems-and-disk-health.json')
        guest_queries = '\n'.join(t.get('expr', '') for p in panels(guests['panels']) for t in p.get('targets', []))
        host_queries = '\n'.join(t.get('expr', '') for p in panels(hosts['panels']) for t in p.get('targets', []))
        self.assertNotRegex(guest_queries, r'\b(?:node_|smartctl_|pve_node_info|pve_storage_info)\w*')
        self.assertNotIn('pve_', host_queries)
        retired = {'Resource allocation summary', 'CPU history', 'Current CPU', 'Host CPU capacity',
                   'Memory history', 'Current memory', 'Host memory used and capacity', 'Storage usage', 'Space allocation'}
        self.assertFalse(retired & {p.get('title') for p in panels(guests['panels'])})
        # Resource selectors in the guest dashboard may not include physical nodes/storage.
        for name, selector in re.findall(r'(pve_\w+)\{([^}]*)\}', guest_queries):
            if name != 'pve_guest_info':
                self.assertIn('id=~"qemu/.+|lxc/.+"', selector)

    def test_service_health_queries_and_catalogue_survive(self):
        if not (ROOT / 'service-health-and-catalogue.json').exists():
            self.skipTest('Individual service monitoring has been retired')
        before = read(ROOT / 'old templates/service-health-dashboard-template.json')
        after = read(ROOT / 'service-health-and-catalogue.json')
        actual = {p['title']: p for p in panels(after['panels'])}
        for panel in before['panels']:
            expressions = [t['expr'].replace('job="blackbox"','job=~"$job",instance=~"$instance"') for t in panel['targets']]
            # Additional inventory scoping excludes unrelated scrape jobs when All
            # is selected, without changing the archived state/freshness logic.
            guard=' and on(job) (count by(job) (probe_success) or count by(job) (up{job="blackbox"}))'
            current=[t['expr'].replace(guard,'') for t in actual[panel['title']]['targets']]
            current=[re.sub(r'0 \* \((up\{[^}]+\})\)',r'0 * \1',q) for q in current]
            self.assertEqual(expressions,current)
        catalogue = read(ROOT / 'old templates/dashboard-template.json')
        for panel in catalogue['panels'][1:]:
            self.assertEqual(panel['targets'], actual[panel['title']]['targets'])

    def test_host_disk_health_survives(self):
        service = read(ROOT / 'old templates/service-health-dashboard-template.json')
        host = read(ROOT / 'host-systems-and-disk-health.json')
        service_disk = next(p for p in panels(service['panels']) if p['title'] == 'Host disk SMART health')
        host_disk = next(p for p in panels(host['panels']) if p['title'] == 'Host disk SMART health')
        self.assertEqual(service_disk['targets'][0]['expr'], host_disk['targets'][0]['expr'])
        self.assertEqual(len([p for p in panels(host['panels']) if p['type'] != 'row']), 125)

    def test_supplied_dashboards_preserved(self):
        if SOURCES is None:
            self.skipTest('Supply --sources to compare with the original downloaded dashboards')
        manifest = read(ROOT / 'docs/dashboard-sources.json')
        if not all((SOURCES / name).exists() for name in manifest['supplied']):
            self.skipTest('Original downloaded files are not available')
        for name, digest in manifest['supplied'].items():
            self.assertEqual(hashlib.sha256((SOURCES / name).read_bytes()).hexdigest(), digest)
        original = read(SOURCES / 'node-exporter-full_rev46.json')
        host = read(ROOT / 'host-systems-and-disk-health.json')
        actual = [normalized(p) for p in panels(host['panels']) if p['type'] != 'row']
        for panel in panels(original['panels']):
            if panel['type'] != 'row': self.assertIn(normalized(panel), actual)
        original = read(SOURCES / 'proxmox-via-prometheus_rev5.json')
        resources = read(ROOT / 'proxmox-resources-and-group-budgets.json')
        titles = [p.get('title') for p in panels(resources['panels'])]
        for title in ['Guests CPU usage', 'Guests memory usage', 'LXC guests Disk usage', 'Network IO/s', 'Disk IO/s']:
            self.assertIn(title, titles)
        # Every metric family used by either supplied service/PVE dashboard remains.
        comparisons=[('proxmox-via-prometheus_rev5.json',resources,'pve_')]
        if (ROOT / 'service-health-and-catalogue.json').exists():
            comparisons.append(('blackbox-exporter-http-prober_rev1.json',read(ROOT / 'service-health-and-catalogue.json'),'probe_'))
        for filename, dashboard, prefix in comparisons:
            before = read(SOURCES / filename)
            def metrics(d):
                return set(re.findall(r'\b'+prefix+r'\w+', ' '.join(t.get('expr','') for p in panels(d['panels']) for t in p.get('targets',[]))))
            intentionally_retired = {'pve_node_info', 'pve_storage_info'} if prefix == 'pve_' else set()
            self.assertFalse(metrics(before) - metrics(dashboard) - intentionally_retired)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', type=Path)
    args, rest = parser.parse_known_args()
    SOURCES = args.sources
    unittest.main(argv=[__file__] + rest)
