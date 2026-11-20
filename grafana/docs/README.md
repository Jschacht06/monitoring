# Grafana documentation

**Final — 20 November 2026.** The accepted pair is Host Systems and Disk Health and Proxmox VM and LXC Monitoring. Start with the [dashboard guide](../README.md) for the current files, import/replacement, filters, data requirements and interpretation.

A simple [Logs template](../logs.json) is also available: log volume and messages with Loki source, host and service filters. See the [Logs import guide](../README.md#logs). This new template has not yet been verified in live Grafana.

| Final dashboard | What it covers |
|---|---|
| [Host Systems and Disk Health](../host-systems-and-disk-health.json) | 125 panels: complete Node Exporter Full host metrics plus SMART disk health. |
| [Proxmox VM and LXC Monitoring](../proxmox-resources-and-group-budgets.json) | 13 panels: automatic guest inventory/state, guest allocations/usage and summaries by actual Proxmox node. |

A compact [All Nodes Overview](../all-nodes-overview.json) is also available for CPU, RAM, disk-space and network comparisons across all configured Node Exporter targets. See the [overview guide](../README.md#all-nodes-overview) for automatic discovery and network-interface selection. This additional template is locally checked and awaiting its first live import; the accepted host and guest dashboards are unchanged.

## Current guides

| Guide | Use it for |
|---|---|
| [Dashboard guide](../README.md) | Scope, import, source selection, filters, units, freshness and avoiding duplicate host/guest views. |
| [Operations and troubleshooting](operations-and-troubleshooting.md) | Daily use, read-only operator access, exports, restore and common display/data issues for the final pair. |
| [Validation and acceptance](../README.md#validation-and-maintenance) | Final status, live Proxmox screenshots/operator confirmation and the local structural/query checks. |
| [Monitoring setup](../../docs/setup.md) | Underlying stack configuration. Individual Blackbox checks are not required by the final dashboards. |
| [Exporter recipes](../../docs/how-to-guides.md) | Existing Node Exporter, smartctl and PVE collector setup. |

The dashboards have separate responsibilities: physical hosts in Host Systems, virtual guests in Proxmox. Neither final template needs the archived `noc_*` group-budget rules, guest-to-group mappings or Blackbox service probes.

## Historical references

Earlier service-catalogue/Blackbox procedures, the October test report and the proposed Smith-budget integration are in [docs/archive](archive/README.md). Older JSON definitions remain in [old templates](../old%20templates/). These are retained for history and rollback, not as additional dashboards or setup prerequisites.

Dashboard exports contain definitions; users, permissions, metric history and the rest of the monitoring stack use their own configuration and backups.
