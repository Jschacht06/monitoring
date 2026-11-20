# Grafana documentation

**Final — 20 November 2026.** The accepted pair is Host Systems and Disk Health and Proxmox VM and LXC Monitoring. Start with the [dashboard guide](../README.md) for the current files, import/replacement, filters, data requirements and interpretation.

| Final dashboard | What it covers |
|---|---|
| [Host Systems and Disk Health](../host-systems-and-disk-health.json) | 125 panels: complete Node Exporter Full host metrics plus SMART disk health. |
| [Proxmox VM and LXC Monitoring](../proxmox-resources-and-group-budgets.json) | 13 panels: automatic guest inventory/state, guest allocations/usage and summaries by actual Proxmox node. |

## Current guides

| Guide | Use it for |
|---|---|
| [Dashboard guide](../README.md) | Scope, import, source selection, filters, units, freshness and avoiding duplicate host/guest views. |
| [Operations and troubleshooting](operations-and-troubleshooting.md) | Daily use, read-only operator access, exports, restore and common display/data issues for the final pair. |
| [Validation and acceptance](validation-and-acceptance.md) | Final status, live Proxmox screenshots/operator confirmation and the local structural/query checks. |
| [Monitoring setup](../../docs/setup.md) | Underlying stack configuration. Individual Blackbox checks are not required by the final dashboards. |
| [Exporter recipes](../../docs/how-to-guides.md) | Existing Node Exporter, smartctl and PVE collector setup. |

The dashboards have separate responsibilities: physical hosts in Host Systems, virtual guests in Proxmox. Neither final template needs the archived `noc_*` group-budget rules, guest-to-group mappings or Blackbox service probes.

## Historical references

Earlier service-catalogue/Blackbox procedures, the October test report and the proposed Smith-budget integration are in [docs/archive](archive/README.md). Older JSON definitions remain in [old templates](../old%20templates/). These are retained for history and rollback, not as additional dashboards or setup prerequisites.

[dashboard-sources.json](dashboard-sources.json) records source-file and original-template fingerprints. Dashboard exports contain definitions; users, permissions, metric history and the rest of the monitoring stack use their own configuration and backups.
