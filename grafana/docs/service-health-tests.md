# Service-health dashboard test report

**Date:** 16 October 2026. **Environment:** homelab, using Crafty and temporary probe targets. The tests checked how Grafana displayed destination failures, monitoring failures and slow successful responses. Smith resource dashboards were outside this test scope.

## How the dashboard was checked

The Service health dashboard was observed alongside Grafana Explore using the same Prometheus data source. Current status, summary counters, probe history and HTTP duration were compared with the underlying metrics. Screenshots captured the dashboard and Explore results; detailed evidence remains outside the repository.

## Destination outage and recovery

Crafty was made unreachable and then restored. Grafana initially showed six visible checks, no failed destinations and no Unknown checks. During the outage, Crafty's row turned red and **Failed destination checks** increased to 1; **Unknown probe checks** remained 0 and unrelated services stayed green.

In Explore, up for Crafty's Blackbox check remained 1 while probe_success became 0. This showed that the exporter was responding successfully and the destination check was failing.

After Crafty recovered, probe_success returned to 1, its current row became green and the failure counter returned to 0. **Probe status history** retained the red outage segment.

**Outcome:** passed. Grafana distinguished a failed destination from a failed monitoring check and showed recovery without losing the outage history.

## Monitoring failure / Unknown

A temporary target named crafty-monitoring-test used the running Crafty destination with the deliberately nonexistent module dashboard_test_invalid. The shared exporter and real Crafty service remained running.

Grafana showed seven visible checks, **Unknown probe checks = 1** and **Failed destination checks = 0**. The temporary check was grey and labelled Unknown; the original Crafty check stayed Up. Explore showed up=0 for the temporary check and no probe_success data.

After the temporary target was removed, its row disappeared from the current table and the Unknown counter returned to 0. The historical grey row remained visible within the test period.

**Outcome:** passed. Missing probe results appeared as Unknown rather than being presented as a destination outage or a healthy result. Target removal demonstrated cleanup, rather than a successful probe using the invalid module.

## Slow successful response

A separate temporary HTTP endpoint ran inside Crafty's guest, leaving the real Crafty application running. It was monitored as crafty-lab-test using http_2xx. The endpoint first responded quickly, then introduced an approximately 2-second delay while continuing to return HTTP 200. Its URL and labels stayed unchanged.

**Successful HTTP probe duration** rose above the dashboard's 1-second reference to approximately 2 seconds. The check remained Up, with no failed destinations or Unknown checks. Explore showed probe_duration_seconds of approximately 2.00275 and probe_success=1, agreeing with the chart.

**Outcome:** slow-response display passed. A successful but slow response remained green in the status view while its degradation appeared in the latency graph. The operator reported successful completion; a separate screenshot of the return to fast responses was not supplied.

## HTTPS certificate display

A public HTTPS target initially failed because the probe selected an IPv6 address without a working network route. The existing http_2xx module was changed to prefer IPv4. The operator then confirmed successful probing and a working **HTTPS certificate days remaining** panel.

**Outcome:** operator-confirmed. The incident and configuration fix are documented with the [certificate panel](health-and-usage-dashboards.md#https-certificate-expiry) and [target configuration](../../docs/adding-targets.md).

## Operator-account verification

A separate noc-operator account was tested in an Incognito browser session. The administrator's user-details view showed **Main Org.: Viewer** and **Grafana Admin: No**. The health dashboard's permission view granted the Viewer role View access, with editing reserved for the Editor/Admin roles.

The supplied screenshots showed the health dashboard loading six current probes with no failed or Unknown checks. Selecting group monitoring reduced the visible count to 2; selecting service scrutiny reduced it to 1, and the table/history followed the selections. Dashboard editing/settings controls were absent. The operator confirmed both dashboard permissions were correct and shared dashboards could not be edited. Both dashboards appeared in the operator's recent-dashboard list; a separate catalogue-panel screenshot was not supplied in this batch.

Opening the restricted Users URL returned the operator to Grafana's homepage, with redirectTo pointing to /admin/users. This screenshot supports the reported restriction of administrative pages; the data-source page restriction was operator-reported rather than separately captured here.

The operator reported that dashboard export remained available. Export downloads a copy of the dashboard definition; it does not grant permission to save changes to the running dashboard. This was recorded as compatible with the intended read-only role.

**Outcome:** Grafana operator access passed based on the supplied screenshots and operator confirmation. Viewer identity, non-admin status, health-dashboard filters, absent edit controls and the restricted Users-page redirect were visible in the evidence.

**Separate access boundary:** the operator reported Prometheus and Alertmanager are reachable without password login. The stack owner is aware and plans Authentik integration. This remains planned work, not a completed authentication control; the Grafana permission result does not establish protection of those direct interfaces. School-network access and Proxmox permissions were not established by this evidence.

## Dashboard backup and restore

**Date:** 16 October 2026. **Duration:** approximately 10 minutes, reported by the operator. **Evidence type:** written operator confirmation; no restore screenshots were taken.

The operator followed the [separate-instance procedure](service-catalogue-dashboard.md#9-verify-dashboard-restore-on-a-separate-grafana): exported the live service list and health dashboards, used a separate Grafana with its own data volume, connected the existing Prometheus and imported the exports. The operator reported that everything worked as expected and both restored dashboards matched the originals, with no dashboard differences observed. Completion of the procedure, including its persistence/live checks, is operator-confirmed rather than independently captured per step.

**Outcome:** dashboard export/restore passed on operator confirmation. Approximate elapsed time is a useful observed baseline, not an agreed RTO or a precisely timed benchmark. Data loss for dashboard definitions was not observed by the operator; metric-history recovery was not tested because the existing Prometheus supplied the data. No operating users, permissions, rules, credentials or real target files were restored by the dashboard JSON.

The report is the current written restore record. Screenshots/logs can strengthen a teacher demonstration, but their absence is stated rather than treated as proof that the test failed. The broader teacher restore scenario includes rules and the actual service catalogue on a test instance; that remains separate from this dashboard-only restore.

## Result and scope

| Grafana behaviour | Result |
|---|---|
| Destination failure shown as Down, with the correct failure counter | Passed |
| Recovery shown as Up, with outage retained in history | Passed |
| Monitoring failure shown as Unknown, with the correct Unknown counter | Passed |
| Successful slow response shown in the latency chart while status stays Up | Passed |
| HTTPS certificate-days display after the IPv4 fix | Operator-confirmed |
| Grafana Viewer access, filtering and restricted administration | Passed; screenshot evidence and operator confirmation |
| Dashboard export/import and separate-Grafana restore, approximately 10 minutes | Passed on operator confirmation; no restore screenshots |

The evidence supports these homelab dashboard results. It does not establish school deployment, a fresh live import of the repository placeholder templates, school-network access controls, full configuration/rule/catalogue restore or long-term history coverage. Maintenance was explicitly skipped, and application-content failure was not tested in this session. Notification verification is retained in private evidence and is outside this dashboard report.

## Repository verification

**SMART table extension — 20 October 2026:** the updated health template contains ten panels and adds the independent `disk_host` filter and `disk_freshness_s` constant. The new table maps overall SMART status to Passed/Failed and uses Unknown for missing, invalid or stale data and failed scrapes, retaining observed disk inventory for 24 hours. The previous nine panels and their service-only legends are preserved. JSON parsing, matching queries across both export formats, non-overlapping layout, unchanged original panels/settings and local documentation links were checked. The source queried on 20 October returned no `smartctl` target or SMART metrics, so collector setup is pending. This extension requires its own [live acceptance checks](health-and-usage-dashboards.md#host-disk-smart-health); the earlier screenshots do not verify it.

Before the SMART extension, the service-list and health templates were parsed as JSON and checked locally: four catalogue panels and nine health panels, unique panel IDs and variable names, portable Prometheus source mappings, the HTTP-module latency selector, and the certificate query's freshness checks. The health constants occur once each. Local Grafana documentation links were checked after integration.

These checks support the reusable files; the live screenshots and operator statements support the homelab results. Local structural checks do not execute PromQL against the school source or prove a fresh live import of the placeholder templates. The successful restore used exports of the working dashboards.

## Comparison with the teacher's requirements

Reviewed on 20 October 2026 against [Project 4 — Network Operations Center](https://github.com/JollyJones101/network-experience-2627/blob/main/projecten/04-network-operations-center.md), [backup/restore guidance](https://github.com/JollyJones101/network-experience-2627/blob/main/docs/07-backup-en-restore.md), [monitoring/logging guidance](https://github.com/JollyJones101/network-experience-2627/blob/main/docs/08-monitoring-en-logging.md) and the [backup-test record](https://github.com/JollyJones101/network-experience-2627/blob/main/docs/templates/backup-test-template.md). The locally available assignment files were the review source; the homelab observations above were reported on 16 October 2026. This is an assessment of the monitoring repository and supplied homelab evidence, not a claim about unreviewed work owned by other teammates.

### Must requirements

| Teacher requirement | Current position | Remaining evidence or work |
|---|---|---|
| Intake with at least three project groups: service, owner, SLI and maintenance window | Procedure integrated in the catalogue guide; homelab labels/services exist | Signed-off intake with three actual project groups and agreed timing/maintenance; homelab categories do not prove this |
| Service catalogue with status, dependencies and contact role | Implemented in the four-panel service-list template and live homelab dashboard | Populate and reconcile the actual school catalogue; verify named contact roles and real dependencies |
| Reachability, latency, certificates and agreed application checks | Reachability, slow-success display and HTTPS expiry verified; an application-body recipe exists in Blackbox and earlier stack documentation reports tests | Owner-approved checks for the school applications, with their agreed healthy/failure responses; not newly evidenced by this homelab session |
| Host/agent metrics only with permission and least-privilege credentials | Guides require approval and document a read-only API design | Keep actual scope/permission evidence with the deployment; dashboard access is not permission to collect another group's host data |
| Service-health, Smith-resource quotas and trends dashboards | Service health and its probe history/latency trends complete for homelab | Smith quotas/resource trends explicitly deferred; school source/budget validation pending |
| Four usable alerts: outage, degradation, capacity and backup/check failure | ServiceDown, ServiceSlow, DiskSpaceLow and MonitoringCheckFailed exist with severity and runbook annotations; README records earlier capacity tests; current session confirmed outage/slow/check-failure delivery | Reconcile the loaded alert matrix and approved thresholds with the stack owner; keep that team's test evidence, without requiring duplicate notification work here |
| Severity, deduplication, quiet maintenance and escalation | Stack configuration/documentation covers routing/grouping/escalation; operator states maintenance works and declined a repeat | Retain the stack owner's maintenance/escalation records and an agreed school maintenance window; no new maintenance evidence claimed here |
| Central/federated log trial for at least two services, retention and access control | Main README lists logging as planned; no such implementation/test was found in the reviewed monitoring repo | Team deliverable; confirm any separate work and its retention/access evidence |
| Status page without internal details or sensitive metadata | Separate sanitized component installed in the homelab; three Up rows confirmed by operator and screenshot | Complete live failure/recovery and external disclosure checks using the [status-page guide](../../docs/public-status-page.md); keep detailed Grafana private |
| At least two simulated incidents from detection through post-mortem | Crafty outage and controlled slow response provide two technical scenarios | Incident timelines, impact, response and post-mortems; a two-project-group game day is not established by these homelab tests |
| Backup/restore of configuration, dashboards and catalogue | Dashboard-only export/restore operator-confirmed in approximately 10 minutes; configuration backup procedure documented | Restore actual configuration/target catalogue and rules on a test instance; record outcome, duration, data loss and evidence. A Git clone contains templates, not the ignored real targets/secrets |

### Teacher acceptance scenarios

| Scenario | Assessment |
|---|---|
| Service down: agreed detection/notification time, no notification storm | Functional detection, dashboard recovery and firing/resolved delivery verified; no owner-agreed timing or complete storm analysis supplied |
| Slow service distinguished from unreachable | Passed in homelab: approximately 2-second successful HTTP response remained Up and appeared in latency |
| Maintenance suppresses only intended alerts and is traceable | Operator-confirmed existing functionality; repeat explicitly skipped, so reuse the stack owner's records |
| Disk warns before failure with the right runbook | Rule and runbook present; README records prior stack-owner testing, not a new test in this Grafana session |
| Operator sees dashboards but cannot manage source credentials/other VMs | Grafana read-only behaviour passed; direct Prometheus/Alertmanager lack authentication with Authentik only planned. School-network and Proxmox access boundaries remain separate checks |
| Dashboards, rules and catalogue restored on test instance | Dashboard portion passed on operator confirmation; rules and real catalogue/configuration restore not demonstrated by the separate Grafana test |

### Optional requirements and handover

The Should items are distinct from the completed dashboard scope: per-service SLI/SLO and monthly error-budget reports require agreed objectives and reporting; file-based target discovery exists but is not an approved inventory integration by itself; a true synthetic user transaction is not the same as a JSON body check; DiskWillFillSoon exists but its measured-growth validation is still listed as pending in the main README. The Could items (n8n integration, on-call/handover dashboard and anonymized wallboard) were not part of these changes.

**Sign-off:** the requested service-list/health-dashboard implementation, accompanying documentation, homelab checks, Viewer setup and dashboard restore can be marked complete for this scope. Smith remains deferred. The entire teacher NOC assignment cannot be marked complete from this evidence; the remaining school agreements, application contracts, access boundary, full restore, logs, sanitized status page and incident documents must be completed or linked from their owners' work. No notifications, access changes or Smith metrics were changed by this documentation integration.

## Public status-page implementation update — 20 October 2026

A separate [public status component](../../docs/public-status-page.md) now implements the sanitized page requirement: approved aliases plus Up/Down, with the source connection and check identities retained server-side. Local automated verification covers status aggregation, failures/recovery, cache expiry and the HTTP privacy boundary. The existing Grafana tests above do not establish live acceptance for this new component. The operator subsequently confirmed a working homelab installation with a screenshot of Jellyfin, Scrutiny and Uptime Kuma in three separate Up rows; a private terminal check also confirmed successful source querying. The [live baseline and configuration repair](../../docs/public-status-page.md#live-baseline-and-configuration-repair--20-october-2026) are recorded in the status guide. Controlled live failures, API/source disclosure inspection and the approved public HTTPS route remain pending; the whole teacher requirement must not yet be marked verified.
