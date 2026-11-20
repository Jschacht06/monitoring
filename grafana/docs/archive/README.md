# Archived Grafana documentation

These files preserve the earlier Blackbox service-catalogue/health work, its October test record, and the proposed Smith group-budget integration. They are historical references, not the installation route for the two dashboards finalized on 20 November 2026.

Use the [current dashboard guide](../../README.md), [current operations guide](../operations-and-troubleshooting.md) and [final acceptance record](../validation-and-acceptance.md) for Host Systems and Disk Health and Proxmox VM and LXC Monitoring.

| Archived file | Historical scope |
|---|---|
| [service-catalogue.md](service-catalogue.md) | Target labels, owners, contacts and dependencies for individual service checks. |
| [service-catalogue-dashboard.md](service-catalogue-dashboard.md) | Standalone catalogue creation, original service-dashboard operator setup and restore procedure. |
| [health-and-usage-dashboards.md](health-and-usage-dashboards.md) | Blackbox health/history/availability and the earlier budget-dashboard setup. |
| [service-health-tests.md](service-health-tests.md) | October homelab results and requirements assessment for the earlier service dashboards. |
| [smith-resource-metrics.md](smith-resource-metrics.md) | Proposed API scope, guest-to-group mapping and approved-budget integration. |
| [smith-resource-rules-template.yml](smith-resource-rules-template.yml) | Unfilled historical `noc_*` recording-rule recipe. Not loaded by the final dashboard setup. |

Terms such as proposed, deferred or pending inside these dated records describe that earlier scope. They do not change the final status of the current two dashboards. Example budgets and placeholder rules in this archive are not live configuration.

The archived dashboard JSON files are kept separately in [old templates](../../old%20templates/). Historical commands or GUI instructions may refer to earlier versions and dashboard names; current operations use the final names and procedures linked above.
