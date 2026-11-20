# Documentation

Guides for the noc-core monitoring stack and the two final Grafana dashboards for physical hosts and Proxmox guests.

## Monitoring stack

| Guide | What it covers |
|---|---|
| [public-status-page.md](public-status-page.md) | Sanitized Up/Down page: private allowlist, Compose deployment, privacy checks, live acceptance, publication and rollback. |
| [setup.md](setup.md) | Set up Prometheus, Grafana, Blackbox Exporter, Node Exporter and Alertmanager. |
| [adding-targets.md](adding-targets.md) | Add HTTP and TCP probes; verify the results. |
| [configuration-reference.md](configuration-reference.md) | What each configuration setting does and why it is set that way. |
| [how-to-guides.md](how-to-guides.md) | Change alerts, routing, inhibition, receivers and exporters. |
| [operations-and-troubleshooting.md](operations-and-troubleshooting.md) | Daily commands, applying changes and diagnosing problems. |

## Final Grafana dashboards

The operator confirmed **Host Systems and Disk Health** and **Proxmox VM and LXC Monitoring** as final on 20 November 2026. Start with the [Grafana guide](../grafana/README.md).

| Guide or template | What it covers |
|---|---|
| [Host Systems and Disk Health](../grafana/host-systems-and-disk-health.json) | Physical-host metrics and SMART disk health. |
| [Proxmox VM and LXC Monitoring](../grafana/proxmox-resources-and-group-budgets.json) | Automatic VM/LXC inventory, state, guest resources and summaries by actual Proxmox node. |
| [Grafana documentation index](../grafana/docs/README.md) | Current setup and handover route. |
| [Operations and troubleshooting](../grafana/docs/operations-and-troubleshooting.md) | Daily use, operator access, export, restore and common issues for the final pair. |
| [Validation and acceptance](../grafana/docs/validation-and-acceptance.md) | Final status, live Proxmox screenshots and local structural/query checks. |

Blackbox service checks and manual group budgets are outside the final dashboard scope. Earlier procedures and October test results remain in the [Grafana documentation archive](../grafana/docs/archive/README.md), with their older JSON files in [old templates](../grafana/old%20templates/). They are not additional setup requirements for the final dashboards.
