# Grafana documentation

Documentation and teacher-requirements review completed on 20 October 2026. The homelab test results below were reported on 16 October 2026.

Start here for the service list and service-health dashboards. They share the existing Prometheus source: the service list provides current probe status, ownership and dependencies; the health dashboard adds history, latency, availability, sample coverage, HTTPS certificate expiry and host disk SMART health. Keeping two dashboards is an organizational choice, not a requirement to duplicate every panel.

**Status — 16 October 2026:** the service-list and service-health work is complete for the tested homelab scope. Down/recovery, Unknown, slow-response display and Viewer access were checked with screenshots and operator confirmation. A separate Grafana restore was operator-confirmed in approximately 10 minutes; no restore screenshots were taken. See the [test report and requirements review](service-health-tests.md). Smith resource quotas and resource trends remain deferred. Homelab completion does not establish school deployment or completion of the entire NOC assignment.

## Setup and handover

Use the following route for a new installation or transfer to school. Each topic has one maintained procedure; imported templates already contain their panel settings.

| Order | Task | Documentation |
|---|---|---|
| 1 | Agree the school services, owners, SLIs, application checks and maintenance windows with at least three project groups | [Service intake](service-catalogue.md#agree-the-monitored-services) |
| 2 | Preserve the current configuration and dashboard exports | [Backup scope and procedure](health-and-usage-dashboards.md#2-preserve-the-catalogue-and-current-configuration) |
| 3 | Configure target labels, matching probe modules and internal-scrape metadata | [Service catalogue setup](service-catalogue.md#1-prerequisites) |
| 4 | Import the health dashboard and verify its interval/freshness constants | [Health template import](health-and-usage-dashboards.md#3-import-the-health-dashboard) |
| 5 | Import the service-list template with its current-status table and metadata checks | [Service-list creation/import](service-catalogue-dashboard.md#1-choose-how-to-create-the-dashboard) |
| 6 | Check successful HTTP latency, including custom http_ modules | [Latency query and existing-import updates](health-and-usage-dashboards.md#6-understand-or-build-the-trend-panels) |
| 7 | Verify HTTPS certificate days and physical-host disk health; investigate missing expected results | [Certificate panel](health-and-usage-dashboards.md#https-certificate-expiry) and [SMART table](health-and-usage-dashboards.md#host-disk-smart-health) |
| 8 | Compare the dashboard with source metrics during controlled failures | [Acceptance checks](health-and-usage-dashboards.md#10-run-the-acceptance-checks-and-collect-evidence) and [completed tests](service-health-tests.md) |
| 9 | Configure and test a read-only operator | [Viewer setup and verification](service-catalogue-dashboard.md#8-verify-the-operator-account) |
| 10 | Export both dashboards and restore them in a separate Grafana | [Detailed export/restore procedure](service-catalogue-dashboard.md#9-verify-dashboard-restore-on-a-separate-grafana) |

The stack must already work; use the [base installation guide](../../docs/setup.md) when needed. Target/configuration edits run on the monitoring machine. Dashboard JSON is prepared on the operator's computer and uploaded through Grafana. Saving a live dashboard does not update a repository template; exporting it does not back up users, permissions or Prometheus data.

## Templates

| Template | Included behaviour |
|---|---|
| [dashboard-template.json](../dashboard-template.json) | Four panels: current destination-probe status, service inventory, missing-metadata count and missing-metadata detail |
| [service-health-dashboard-template.json](../service-health-dashboard-template.json) | Ten panels: three counters, current status, history, successful HTTP latency, observed availability, sample coverage, certificate days and host disk SMART health |

Copy the template, replace its title/description/environment placeholders and map the existing Prometheus source during import. Do not manually recreate panels that already exist. A live imported dashboard can have a different UID from the template; export it before deliberately replacing it.

## Deferred Smith work

The [Smith metric integration](smith-resource-metrics.md), [resource dashboard template](../smith-resources-dashboard-template.json) and [recording-rule template](smith-resource-rules-template.yml) are prepared references. Their approved API scope, budgets, measurements and live acceptance are not signed off by the service-health tests. When resuming this work, follow [health guide steps 7–9](health-and-usage-dashboards.md#7-prepare-smith-resource-metrics).

## Completion boundary

The [teacher-requirements review](service-health-tests.md#comparison-with-the-teachers-requirements) separates completed dashboard work from school intake/coverage, application contracts, full configuration/rule/catalogue restore and the team's other NOC deliverables. Prometheus/Alertmanager authentication is known pending work owned by the stack team; planned Authentik integration is not counted as implemented protection.
