# Documentation

Guides for the noc-core monitoring stack and the Grafana service catalogue.

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
| [service-catalogue.md](service-catalogue.md) | Add targets and catalogue labels, build the Grafana list, verify it and apply it. |
| [service-catalogue-dashboard.md](service-catalogue-dashboard.md) | Create a dashboard from the template or Grafana's editor, edit it, then export/import it. |
| [dashboard-template.json](dashboard-template.json) | Local JSON template with title, description and environment-tag placeholders; upload the edited copy through Grafana's web interface. |
