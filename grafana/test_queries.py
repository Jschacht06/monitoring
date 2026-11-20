"""Check merged dashboard PromQL and behaviour with real Prometheus.

From the repository root:
  python -B grafana/test_queries.py --docker
or supply a local binary with --promtool /path/to/promtool.
Expressions are read from the shipped dashboards, so fixtures cannot drift.
"""
import argparse
import json
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IMAGE = 'quay.io/prometheus/prometheus:v3.7.3'


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def labels(**values):
    return "{" + ",".join(f"{key}={json.dumps(value)}" for key, value in sorted(values.items())) + "}"


def sample(value, **values):
    return {"labels": labels(**values), "value": value}


def service_suite():
    catalogue = health = load("service-health-and-catalogue.json")
    for dashboard in (catalogue, health):
        assert all(v["name"] != "group" for v in dashboard["templating"]["list"])
        for panel in dashboard["panels"]:
            for target in panel.get("targets", []):
                assert not re.search(r"\bgroup\b", target.get("expr", ""))
    service = next(v for v in health["templating"]["list"] if v["name"] == "service")
    assert service["query"]["query"] == 'label_values(up{job=~"$job",service!=""}, service)'

    def expr(dashboard, title, selected=".*"):
        panel = next(p for p in dashboard["panels"] if p["title"] == title)
        result = panel["targets"][0]["expr"]
        for key, value in {"$__range_s": "120", "$__range": "2m", "$probe_interval_s": "30", "$probe_freshness_s": "90", "$service": selected, "$job": "blackbox", "$instance": ".*"}.items():
            result = result.replace(key, value)
        return result

    wiki = dict(job="blackbox", instance="http://wiki.invalid", module="http_2xx", service="wiki", host="host-a", owner="team-a", contact="operator@example.invalid", dependencies="none")
    ssh = dict(wiki, instance="ssh.invalid:22", module="tcp_connect", service="ssh", host="host-b")
    tests = []

    def add(name, series, checks):
        tests.append(dict(name=name, interval="30s", input_series=series,
                          promql_expr_test=[dict(expr=query, eval_time="2m", exp_samples=expected) for query, expected in checks]))

    def metric(name, identity, values="1+0x4"):
        return dict(series=name + labels(**identity), values=values)

    counter = expr(catalogue, "Services with incomplete catalogue metadata")
    detail = expr(catalogue, "Services missing catalogue metadata")
    inventory = expr(catalogue, "Every monitored service")
    add("complete-five-label-catalogue-without-group", [metric("up", wiki), metric("up", ssh)],
        [(counter, [sample(0)]), (detail, []), (inventory, [sample(1, **{k: wiki[k] for k in ("service", "host", "owner", "contact", "dependencies")}), sample(1, **{k: ssh[k] for k in ("service", "host", "owner", "contact", "dependencies")})])])
    incomplete = {k: v for k, v in wiki.items() if k != "owner"}
    add("missing-owner-counts-service-once-and-both-checks", [metric("up", incomplete), metric("up", dict(incomplete, instance="http://wiki.invalid/second"), "0+0x4")],
        [(counter, [sample(1)]), (detail, [sample(2, service="wiki", host="host-a")])])
    incomplete = dict(wiki, contact="")
    add("empty-contact-is-incomplete", [metric("up", incomplete)], [(counter, [sample(1)]), (detail, [sample(1, service="wiki", host="host-a")])])
    incomplete = {k: v for k, v in wiki.items() if k != "service"}
    add("missing-service-identity-still-flagged", [metric("up", incomplete)], [(counter, [sample(1)]), (detail, [sample(1, host="host-a")])])
    add("absent-inventory-is-not-a-healthy-zero", [], [(counter, []), (detail, []), (inventory, [])])

    for name, probe_values, up_values, failed, unknown in [
        ("healthy", "1+0x4", "1+0x4", 0, 0),
        ("destination-down", "0+0x4", "1+0x4", 1, 0),
        ("scrape-failed", "1+0x4", "0+0x4", 0, 1),
        ("probe-stale", "1 _ _ _ _", "1+0x4", 0, 1),
        ("scrape-stale", "1+0x4", "1 _ _ _ _", 0, 1),
        ("probe-missing", None, "1+0x4", 0, 1),
    ]:
        series = [metric("up", wiki, up_values), metric("up", ssh), metric("probe_success", ssh)]
        if probe_values is not None:
            series.append(metric("probe_success", wiki, probe_values))
        checks = []
        for selected, count in [(".*", 2), ("wiki", 1)]:
            current = [sample(-1 if unknown else (0 if failed else 1), **(wiki if unknown else dict(wiki, __name__="probe_success")))]
            if selected == ".*":
                current.append(sample(1, __name__="probe_success", **ssh))
            checks.extend([(expr(health, "Visible probe checks", selected), [sample(count)]),
                           (expr(health, "Failed destination checks", selected), [sample(failed)]),
                           (expr(health, "Unknown probe checks", selected), [sample(unknown)]),
                           (expr(health, "Current probe checks", selected), current)])
        add("health-without-group-" + name, series, checks)

    unrelated=dict(job='prometheus',instance='localhost:9090')
    add('non-probe-scrapes-never-become-probe-inventory',[metric('up',unrelated)],
        [(expr(health,'Visible probe checks').replace('job=~"blackbox"','job=~".*"'),[]),
         (expr(health,'Current probe checks').replace('job=~"blackbox"','job=~".*"'),[])])

    def panel_expr(dashboard, title, ref='A'):
        panel = next(p for p in dashboard['panels'] if p.get('title') == title and p.get('type') != 'row')
        return next(t['expr'] for t in panel['targets'] if t['refId'] == ref)

    # Two different checks at the same destination must remain separate rows.
    second = dict(wiki, module='http_grafana_health')
    def check_key(identity):
        return ' | '.join(identity.get(k, '') for k in ('job','instance','module','service','host','owner','contact','dependencies'))

    overview = expr(health, 'HTTP Probe Overview')
    add('http-overview-distinct-checks-on-one-destination',
        [metric('up', wiki), metric('up', second), metric('probe_success', wiki), metric('probe_success', second,'0+0x4')],
        [(overview,[sample(1,__name__='probe_success',check_key=check_key(wiki),**wiki),sample(0,__name__='probe_success',check_key=check_key(second),**second)])])
    ssl_expr = panel_expr(health, 'HTTP Probe Overview', 'B')
    for key,value in {'$job':'blackbox','$instance':'.*','$service':'.*','$probe_freshness_s':'90'}.items(): ssl_expr=ssl_expr.replace(key,value)
    add('http-without-tls-is-zero-not-missing', [metric('up',wiki),metric('probe_http_ssl',wiki,'0+0x4')],
        [(ssl_expr,[sample(0,check_key=check_key(wiki))])])
    add('old-http-diagnostics-hidden', [metric('up',wiki),metric('probe_http_ssl',wiki,'1 _ _ _ _')],[(ssl_expr,[])])

    disk_id=dict(job='smartctl',host='host-a',instance='host-a:9633',device='/dev/sda')
    disk_expr=expr(health,'Host disk SMART health').replace('$disk_host','.*').replace('$disk_freshness_s','90')
    for name,up_values,status_values,expected in [('passed','1+0x4','1+0x4',1),('failed','1+0x4','0+0x4',0),('scrape-failed','0+0x4','1+0x4',-1),('stale','1+0x4','1 _ _ _ _',-1),('invalid','1+0x4','2+0x4',-1)]:
        add('smart-'+name,[metric('up', {k:v for k,v in disk_id.items() if k!='device'},up_values),metric('smartctl_device',disk_id),metric('smartctl_device_smart_status',disk_id,status_values)],
            [(disk_expr,[sample(expected,**{k:disk_id[k] for k in ('host','instance','device')})])])

    return tests


def suite():
    tests = service_suite() if (ROOT / 'service-health-and-catalogue.json').exists() else []

    def add(name, series, checks):
        tests.append(dict(name=name, interval='30s', input_series=series,
                          promql_expr_test=[dict(expr=query, eval_time='2m', exp_samples=expected) for query, expected in checks]))

    def metric(name, identity, values='1+0x4'):
        return dict(series=name + labels(**identity), values=values)

    def panel_expr(dashboard, title, ref='A'):
        panel=next(p for p in dashboard['panels'] if p.get('title')==title and p.get('type')!='row')
        return next(t['expr'] for t in panel['targets'] if t['refId']==ref)

    resources=load('proxmox-resources-and-group-budgets.json')

    def guest_expr(title, ref='A', node='.*', kind='.*'):
        result=panel_expr(resources,title,ref)
        for key,value in {'$instance':'cluster-a','$guest_node':node,'$guest_type':kind,'$pve_freshness_s':'90','$__rate_interval':'2m'}.items():
            result=result.replace(key,value)
        return result

    # The scrape-level host label is deliberately the same for guests on different nodes.
    guest_specs=[('qemu/101','tank','vm-a','qemu','0',1,4,1000,500,1000,0),
                 ('lxc/102','mouse','ct-b','lxc','0',0,2,500,0,400,20),
                 ('lxc/103','tank','ct-c','lxc','0',None,2,500,100,600,150),
                 ('qemu/104','mouse','golden','qemu','1',0,1,250,0,100,0)]

    def guest_fixture(source_values='1+0x4', overrides=None, omit=()):
        overrides=overrides or {}
        series=[metric('up',dict(job='pve',instance='cluster-a'),source_values)]
        for guest_id,node,name,kind,template,state,cpu,ram,used,disk,disk_used in guest_specs:
            base=dict(job='pve',instance='cluster-a',id=guest_id,host='Smith')
            info=dict(base,node=node,name=name,type=kind,template=template,tags='service')
            values={'pve_guest_info':1,'pve_up':state,'pve_cpu_usage_limit':cpu,'pve_cpu_usage_ratio':0.5,
                    'pve_memory_size_bytes':ram,'pve_memory_usage_bytes':used,'pve_disk_size_bytes':disk,'pve_disk_usage_bytes':disk_used}
            for name,value in values.items():
                if (guest_id,name) in omit: continue
                value=overrides.get((guest_id,name),value)
                if value is not None:
                    series.append(metric(name,info if name=='pve_guest_info' else base,
                                         value if isinstance(value,str) else f'{value}+0x4'))
        # Neither a physical host nor another cluster may inflate the guest totals.
        series += [metric('pve_cpu_usage_limit',dict(job='pve',instance='cluster-a',id='node/tank'),'64+0x4'),
                   metric('pve_guest_info',dict(job='pve',instance='cluster-b',id='qemu/101',node='neo',name='other',type='qemu',template='0')),
                   metric('pve_cpu_usage_limit',dict(job='pve',instance='cluster-b',id='qemu/101'),'32+0x4')]
        return series

    def guest_metadata(index):
        guest_id,node,name,kind,template,*_=guest_specs[index]
        return dict(job='pve',instance='cluster-a',id=guest_id,node=node,name=name,type=kind,template=template,tags='service')

    def guest_key(index):
        info=guest_metadata(index)
        return ' | '.join(info[k] for k in ('job','instance','id','node','name','type','template','tags'))

    summary='Guests and allocated capacity by node'
    add('automatic-guests-without-blackbox-or-noc-rules',guest_fixture(),[
        (guest_expr('Discovered VMs and LXCs'),[sample(4)]),
        (guest_expr('Running guests'),[sample(1)]),(guest_expr('Stopped guests'),[sample(2)]),
        (guest_expr('Unknown guest state'),[sample(1)]),(guest_expr('Templates'),[sample(1)]),
        (guest_expr(summary,'TOTAL'),[sample(2,node='tank'),sample(2,node='mouse')]),
        (guest_expr(summary,'CPU'),[sample(6,node='tank'),sample(3,node='mouse')]),
        (guest_expr(summary,'RAM'),[sample(1500,node='tank'),sample(750,node='mouse')]),
        (guest_expr(summary,'DISK'),[sample(1600,node='tank'),sample(500,node='mouse')]),
        (guest_expr('Guests CPU usage'),[sample(0.5,**guest_metadata(0))]),
        (guest_expr('VM and LXC inventory','CPU_PERCENT'),[sample(50,guest_key=guest_key(0))]),
        (guest_expr('VM and LXC inventory','STATE'),[sample(state,guest_key=guest_key(i),**guest_metadata(i)) for i,state in enumerate([1,0,-1,0])]),
        (guest_expr('VM and LXC inventory','DISK_USED'),[])])
    add('guest-node-filter-uses-node-not-common-host-label',guest_fixture(),[
        (guest_expr('Discovered VMs and LXCs',node='tank'),[sample(2)]),
        (guest_expr('Stopped guests',node='tank'),[sample(0)]),
        (guest_expr(summary,'CPU',node='tank'),[sample(6,node='tank')])])
    add('guest-type-filter-and-templates',guest_fixture(),[
        (guest_expr('Discovered VMs and LXCs',kind='qemu'),[sample(2)]),
        (guest_expr('Templates',kind='qemu'),[sample(1)])])
    add('lxc-filesystem-usage-does-not-infer-vm-filesystem-usage',guest_fixture(overrides={('lxc/103','pve_up'):1}),[
        (guest_expr('VM and LXC inventory','DISK_USED'),[sample(150,guest_key=guest_key(2))]),
        (guest_expr('LXC guests Disk usage'),[sample(0.25,**guest_metadata(2))])])
    add('failed-pve-scrape-is-unknown-not-stopped',guest_fixture(source_values='0+0x4'),[
        (guest_expr('Proxmox scrape health'),[sample(0)]),(guest_expr('Unknown guest state'),[sample(4)]),
        (guest_expr('Stopped guests'),[sample(0)]),(guest_expr('Guests CPU usage'),[])])
    for name,values in [('stale','1 _ _ _ _'),('invalid','2+0x4')]:
        add('guest-state-'+name,guest_fixture(overrides={('qemu/101','pve_up'):values}),[
            (guest_expr('Unknown guest state'),[sample(2)]),(guest_expr('Running guests'),[sample(0)])])
    add('incomplete-node-capacity-is-not-a-partial-total',guest_fixture(omit=[('lxc/103','pve_cpu_usage_limit')]),[
        (guest_expr(summary,'CPU'),[sample(3,node='mouse')]),
        (guest_expr('Discovered VMs and LXCs'),[sample(4)])])
    add('empty-guest-inventory-stays-unknown',[metric('up',dict(job='pve',instance='cluster-a'))],[
        (guest_expr('Proxmox scrape health'),[sample(1)]),(guest_expr('Discovered VMs and LXCs'),[]),
        (guest_expr('Stopped guests'),[])])
    return dict(rule_files=[], evaluation_interval="30s", tests=tests)


def all_expressions():
    def panels(items):
        for panel in items:
            yield panel
            yield from panels(panel.get('panels',[]))
    replacements={'$__rate_interval':'2m','$__interval_ms':'30000','$__interval':'30s','$__range_s':'120','$__range':'2m',
                  '$probe_interval_s':'30','$probe_freshness_s':'90','$disk_freshness_s':'180','$disk_host':'.*',
                  '$instance':'cluster-a','$service':'.*','$group':'.*','$nodename':'host-a','$node':'host-a:9100','$job':'blackbox',
                  '$guest_node':'.*','$guest_type':'.*','$pve_freshness_s':'90'}
    expressions=[]
    for path in sorted(ROOT.glob('*.json')):
        for panel in panels(load(path.name)['panels']):
            for target in panel.get('targets',[]):
                expression=target.get('expr','')
                if not expression: continue
                for key,value in replacements.items(): expression=expression.replace(key,value)
                assert '$' not in expression, (path.name,panel.get('title'),expression)
                expressions.append(expression)
    return list(dict.fromkeys(expressions))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--docker", action="store_true")
    choice.add_argument("--promtool")
    args = parser.parse_args()
    fixture = suite()
    expressions = all_expressions()
    with tempfile.TemporaryDirectory(prefix="dashboard-queries-") as directory:
        path = Path(directory) / "queries.json"
        # JSON is a YAML subset accepted by promtool; no YAML dependency needed.
        path.write_text(json.dumps(fixture), encoding="utf-8")
        if args.docker:
            script=Path(directory)/'check-queries.sh'
            script.write_text('set -eu\n'+'\n'.join('/bin/promtool --experimental promql format '+shlex.quote(e)+' > /dev/null' for e in expressions)+'\n/bin/promtool test rules /tests/queries.json\n',encoding='utf-8',newline='\n')
            command = ["docker", "run", "--rm", "--network", "none", "-v", f"{directory}:/tests:ro", "--entrypoint", "/bin/sh", IMAGE, '/tests/check-queries.sh']
        else:
            for expression in expressions:
                subprocess.run([args.promtool,'--experimental','promql','format',expression],check=True,stdout=subprocess.DEVNULL)
            command = [args.promtool, "test", "rules", str(path)]
        subprocess.run(command, check=True)
    print(f"Checked {len(expressions)} unique PromQL expressions; passed {len(fixture['tests'])} dashboard scenarios using shipped queries.")


if __name__ == "__main__":
    main()
