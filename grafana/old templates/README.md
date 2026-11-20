# Archived dashboard templates

These JSON files are previous versions, retained for history and comparison. The two final import files are in the [parent Grafana folder](../README.md): Host Systems and Disk Health, and Proxmox VM and LXC Monitoring.

| Archived file | Earlier purpose |
|---|---|
| [dashboard-template.json](dashboard-template.json) | Standalone service catalogue and metadata checks. |
| [service-health-dashboard-template.json](service-health-dashboard-template.json) | Blackbox service health, history, availability, certificates and SMART health. |
| [smith-resources-dashboard-template.json](smith-resources-dashboard-template.json) | Reviewed guest-to-group mappings, approved budgets and resource-rule checks. |
| [service-health-and-catalogue.json](service-health-and-catalogue.json) | Merged individual-service catalogue, health and HTTP diagnostics; retired from the final scope. |
| [proxmox-resources-and-group-budgets_rev1.json](proxmox-resources-and-group-budgets_rev1.json) | Earlier Proxmox merge with physical-node views and manual group budgets; replaced by the final guest-only dashboard. |

Use the [documentation archive](../docs/archive/README.md) for the corresponding earlier procedures and test records. These templates are not the operator's saved live exports; use the [current export/restore guide](../docs/operations-and-troubleshooting.md) for restoring an accepted live dashboard.
