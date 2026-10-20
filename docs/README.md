# Documentation

Guides for the noc-core monitoring stack, Grafana service catalogue, health dashboards and Smith resource budgets.

## Monitoring stack

| Guide | What it covers |
|---|---|
| [setup.md](setup.md) | Set up Prometheus, Grafana, Blackbox Exporter, Node Exporter and Alertmanager. |
| [adding-targets.md](adding-targets.md) | Add HTTP and TCP probes; verify the results. |
| [configuration-reference.md](configuration-reference.md) | What each configuration setting does and why it is set that way. |
| [how-to-guides.md](how-to-guides.md) | Change alerts, routing, inhibition, receivers and exporters. |
| [operations-and-troubleshooting.md](operations-and-troubleshooting.md) | Daily commands, applying changes and diagnosing problems. |

## Grafana documentation

Start with the [Grafana documentation index](../grafana/docs/README.md) for the complete service-list/health setup route, validated tests, operator access, backup and restore.

## Service catalogue

| Guide | What it covers |
|---|---|
| [service-catalogue.md](../grafana/docs/service-catalogue.md) | Add targets and catalogue labels, build the Grafana list, verify it and apply it. |
| [service-catalogue-dashboard.md](../grafana/docs/service-catalogue-dashboard.md) | Create a dashboard from the template or Grafana's editor, edit it, then export/import it. |
| [dashboard-template.json](../grafana/dashboard-template.json) | Local JSON template with title, description and environment-tag placeholders; upload the edited copy through Grafana's web interface. |

## Health, resource usage and trends

Continue here after the service catalogue works. The health dashboard uses existing probes; Smith live resource panels require the additional approved API integration.

| Guide or template | What it covers |
|---|---|
| [health-and-usage-dashboards.md](../grafana/docs/health-and-usage-dashboards.md) | Numbered dashboard setup, filters, panel queries/settings, interpretation, acceptance evidence, export and troubleshooting. |
| [service-health-tests.md](../grafana/docs/service-health-tests.md) | Homelab test report, Viewer verification, approximately 10-minute dashboard restore and teacher-requirements review. |
| [smith-resource-metrics.md](../grafana/docs/smith-resource-metrics.md) | Proposed read-only Proxmox API integration, guest/group mapping, approved budgets, complete allocation totals and validation. |
| [service-health-dashboard-template.json](../grafana/service-health-dashboard-template.json) | Importable health, status-history, latency, observed-availability, sample-coverage, HTTPS certificate-expiry and host disk SMART-health panels. |
| [smith-resources-dashboard-template.json](../grafana/smith-resources-dashboard-template.json) | Importable allocation/budget bars, CPU/memory/disk trends, guest inventory and missing-data indicators. |
| [smith-resource-rules-template.yml](../grafana/docs/smith-resource-rules-template.yml) | Placeholder rules to copy, customize and validate; not loaded from the docs folders. |

**Deployment status — 16 October 2026:** the service-list and health-dashboard homelab checks and Viewer access passed; separate-Grafana dashboard restore was operator-confirmed in approximately 10 minutes, without screenshots. Repository templates are structurally checked, while a fresh live import of those placeholder templates and school coverage remain separate. Smith API/resource acceptance and full-stack configuration/rule/catalogue restore remain pending. See the [report](../grafana/docs/service-health-tests.md).
