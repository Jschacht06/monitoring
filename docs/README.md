# Documentation

Guides for the noc-core monitoring stack, Grafana service catalogue, health dashboards and Smith resource budgets.

## Monitoring stack

| Guide | What it covers |
|---|---|
| [setup.md](setup.md) | Set up Prometheus, Grafana, Blackbox Exporter, Node Exporter and Alertmanager. |
| [adding-targets.md](adding-targets.md) | Add HTTP, TCP and ICMP probes; verify the results. |
| [configuration-reference.md](configuration-reference.md) | What each configuration setting does and why it is set that way. |
| [how-to-guides.md](how-to-guides.md) | Change alerts, routing, inhibition, receivers and exporters. |
| [operations-and-troubleshooting.md](operations-and-troubleshooting.md) | Daily commands, applying changes and diagnosing problems. |

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
| [smith-resource-metrics.md](../grafana/docs/smith-resource-metrics.md) | Proposed read-only Proxmox API integration, guest/group mapping, approved budgets, complete allocation totals and validation. |
| [service-health-dashboard-template.json](../grafana/service-health-dashboard-template.json) | Importable health, status-history, latency, observed-availability and sample-coverage panels. |
| [smith-resources-dashboard-template.json](../grafana/smith-resources-dashboard-template.json) | Importable allocation/budget bars, CPU/memory/disk trends, guest inventory and missing-data indicators. |
| [smith-resource-rules-template.yml](../grafana/docs/smith-resource-rules-template.yml) | Placeholder rules to copy, customize and validate; not loaded from the docs folders. |

**Deployment status:** the new guides/templates have not been validated on the running Grafana/Smith environment. Keep pending API access and acceptance checks visible; these files do not deploy the dashboards or collector automatically.
