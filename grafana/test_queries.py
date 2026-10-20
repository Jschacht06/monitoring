"""Run dashboard queries against real Prometheus using targets without group.

From the repository root:
  python -B grafana/test_queries.py --docker
or supply a local binary with --promtool /path/to/promtool.
Expressions are read from the shipped dashboards, so fixtures cannot drift.
"""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def labels(**values):
    return "{" + ",".join(f"{key}={json.dumps(value)}" for key, value in sorted(values.items())) + "}"


def sample(value, **values):
    return {"labels": labels(**values), "value": value}


def suite():
    catalogue = load("dashboard-template.json")
    health = load("service-health-dashboard-template.json")
    for dashboard in (catalogue, health):
        assert all(v["name"] != "group" for v in dashboard["templating"]["list"])
        for panel in dashboard["panels"]:
            for target in panel.get("targets", []):
                assert not re.search(r"\bgroup\b", target.get("expr", ""))
    service = next(v for v in health["templating"]["list"] if v["name"] == "service")
    assert service["query"]["query"] == 'label_values(up{job="blackbox",service!=""}, service)'

    def expr(dashboard, title, selected=".*"):
        panel = next(p for p in dashboard["panels"] if p["title"] == title)
        result = panel["targets"][0]["expr"]
        for key, value in {"$__range_s": "120", "$__range": "2m", "$probe_interval_s": "30", "$probe_freshness_s": "90", "$service": selected}.items():
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
    return dict(rule_files=[], evaluation_interval="30s", tests=tests)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--docker", action="store_true")
    choice.add_argument("--promtool")
    args = parser.parse_args()
    fixture = suite()
    with tempfile.TemporaryDirectory(prefix="dashboard-queries-") as directory:
        path = Path(directory) / "queries.json"
        # JSON is a YAML subset accepted by promtool; no YAML dependency needed.
        path.write_text(json.dumps(fixture), encoding="utf-8")
        if args.docker:
            command = ["docker", "run", "--rm", "--network", "none", "-v", f"{directory}:/tests:ro", "--entrypoint", "/bin/promtool", "prom/prometheus:v3.13.3", "test", "rules", "/tests/queries.json"]
        else:
            command = [args.promtool, "test", "rules", str(path)]
        subprocess.run(command, check=True)
    print(f"Passed {len(fixture['tests'])} dashboard scenarios using shipped queries.")


if __name__ == "__main__":
    main()
