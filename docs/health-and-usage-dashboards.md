# Grafana health, resource usage and trends

This guide continues from the working [service catalogue](service-catalogue.md). Keep that dashboard as the ownership and dependency list. Add two dashboards for the next project milestone: service health over time, and Smith resource usage compared with approved budgets. Each step ends with a check before you continue.

**Status:** these instructions and dashboard templates were prepared from the repository configuration and checked structurally. An initial health-dashboard import exposed a status-history point-limit error; the template now includes explicit query-resolution settings, which still need verification on the running instance. The Proxmox integration remains a proposed installation until the checks in [smith-resource-metrics.md](smith-resource-metrics.md) pass. Exporting JSON manually is covered here; automatic Grafana provisioning remains a later task.

| Dashboard | Questions it answers | Data needed |
|---|---|---|
| Service catalogue (existing) | What is monitored, who owns it, what does it depend on? | Target labels on `up` |
| Service health and trends (new) | Which check fails, is the check itself working, how has health/latency changed? | Existing Blackbox probes and `up` |
| Smith resources and budgets (new) | How much is allocated, how much is used, how close is each group to its approved budget? | Approved Proxmox API metrics, guest inventory and group budgets |

The health dashboard can be built immediately using the existing stack. The Smith dashboard needs additional data. `node_exporter` inside noc-core can expose host-wide CPU/memory information: do not use it as proof of the LXC's quota or usage. The repo already documents this [LXC limitation](operations-and-troubleshooting.md#problems-seen-in-this-project).

Commands in this guide run inside noc-core from `/opt/monitoring`. Dashboard JSON files are edited on your own computer and uploaded through Grafana, just like the catalogue template. They do not need to be stored on the LXC.

---

## 1. Check the starting point

1. Open Grafana at `http://<noc-core-ip>:3000`.
2. Open the saved catalogue. Confirm the metadata counter is **0**, the ownership fields are correct, and all intended services appear.
3. In *Explore*, choose the working Prometheus source (`http://prometheus:9090`) and run the following queries separately:

```promql
up
```

```promql
probe_success{job="blackbox"}
```

```promql
probe_duration_seconds{job="blackbox",module="http_2xx"}
```

`up=1` for a Blackbox target means the exporter answered Prometheus. `probe_success=1` means the destination passed the check. `up=1, probe_success=0` is a real failed destination check. `up=0` means its health is unknown because the monitoring failed.

The configuration currently scrapes every **30 seconds**. Prometheus retention is **45 days or 10 GB, whichever limit removes old data first**. A newly monitored target has history only from its first scrape; keeping 45 days does not create past data.

**Check:** each expected probe has `group`, `service`, `host`, `module`, `owner`, `contact` and `dependencies`. An empty HTTP-duration query is expected if there are no HTTP checks yet; add an agreed HTTP check before building that panel. Record existing faults rather than requiring everything to be healthy before you can display it.

---

## 2. Preserve the catalogue and current configuration

Export the catalogue using [the existing export procedure](service-catalogue-dashboard.md#5-export-a-dashboard-you-already-created). Keep its name and UID so you can restore that dashboard if needed.

Before adding the resource collector or rules later, take a local configuration backup:

```bash
cd /opt/monitoring
DASHBOARD_BACKUP="/opt/monitoring-dashboards-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DASHBOARD_BACKUP"
cp -a compose.yaml prometheus "$DASHBOARD_BACKUP/"
```

This backup contains private configuration and target labels. Keep it on the server with restricted access, outside Git. It is a configuration backup; a complete Grafana-volume restore remains a separate project task.

**Check:** you have the exported catalogue JSON and the backup folder. On an existing installation, edit your actual `compose.yaml` and `prometheus/prometheus.yml`; do not replace them with clean templates.

---

## 3. Import the health dashboard

Use [service-health-dashboard-template.json](service-health-dashboard-template.json), which already contains the variables, queries and panel settings described below.

Before importing, keep these settings on the **Probe status history** panel. They are already present in the current template:

| Setting | Value | JSON field on the panel |
|---|---|---|
| Max data points | **200**, entered explicitly rather than left on Auto | `"maxDataPoints": 200` |
| Min interval | **30s**, matching the existing scrape interval | `"interval": "30s"` |
| Query type / format | Range / Time series | `"range": true`, `"instant": false`, `"format": "time_series"` on query A |
| Panel width | Full dashboard width | `"w": 24` in `gridPos` |

Status history needs space between its cells. The automatic resolution can request more points than the panel can draw and produce **Too many points to visualize properly**. The explicit point setting makes Grafana request a coarser time step for longer periods. With Prometheus it controls query resolution, rather than imposing an exact 200-row cutoff. It does not change the 30-second collection interval or the stored history. See [Grafana's query options](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/query-transform-data/#query-options).

1. Save a local copy named `service-health-dashboard.json`.
2. Replace `<your dashboard title here>`, `<your description here>` and `<your environment tag here>`. Suggested title: **Service health and trends**; environment tag: `school` or `home-test`.
3. Keep `id: null`, `uid: null` and every `${DS_PROMETHEUS}` reference. These create a new dashboard and let the import form select the destination source.
4. In Grafana, go to *Dashboards → New → Import dashboard* and upload the complete local JSON file.
5. Choose the project folder and the existing Prometheus source. Use a new UID; leave the catalogue's UID alone.
6. Click **Import**, choose **All** for the filters, and set the time range to **Last 6 hours**, ending at **now**, with **30s** refresh.

Import follows [Grafana's documented upload workflow](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/import-dashboards/). Keep the imported dashboard saved in Grafana. Saving it there does not update the local JSON file; export a new copy after later edits.

**Check before continuing:** the dashboard shows three summary counters, a current-check table, a status history, latency, observed availability and sample coverage. Confirm the history displays colored cells without a point-limit error at **Last 6 hours**, then **Last 24 hours** and **Last 7 days**; a new installation will only show the history collected so far. Return to Last 6 hours and save the dashboard. No container restart is needed for an import.

If you already imported an earlier copy, update the existing panel during this setup check:

1. Hover over **Probe status history**, open its **⋮** panel menu and choose **Edit**.
2. In **Queries**, expand **Query options** beside the data-source selector. If the newer query editor is enabled, Query options is in the editor's footer instead.
3. Enter **Max data points = 200** and **Min interval = 30s**. Keep query A as **Range**, format **Time series**, and keep its existing PromQL expression.
4. Run the query. Apply the panel changes, or return using **Back to dashboard** if that is the button shown, then **Save** the dashboard and **Exit edit**.
5. Repeat the three time-range checks above in the normal dashboard view. Keep this panel full width. If a narrow screen still causes the error, lower Max data points to **100** and save again.

Long periods now show sampled status at a wider time step and can miss short outages. Use **Last 15 minutes** to inspect individual 30-second checks. The current-status table, fault counters and alert rules do not depend on this history-panel resolution.

---

## 4. Configure the filters (also used when building manually)

The template already supplies `group` and `service`; importing it does not require adding them again. Step 4 is a check of those filters, or their setup when building manually.

The Compose template lists Grafana **13.2.2**. In its current dashboard editor, settings and variables have separate paths:

1. Open the dashboard and click **Edit** in the upper-right toolbar.
2. Click the **Dashboard options** icon to open its sidebar. Hover over the toolbar icons to find the one with that name.
3. For general dashboard settings, click **View all settings** in the sidebar. This is where the title, time options and JSON model are located.
4. For the existing filters, stay in Dashboard options, expand **Variables** and click the edit icon beside `group` or `service`. Variables are managed in this sidebar rather than in the general settings page.
5. To create a missing variable during a manual build, click the blue **Add new element (+)** button, choose **Variable**, then **Query**. Select the Prometheus source and use **Label values** with the table below.

These paths follow Grafana's [dashboard settings](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/modify-dashboard-settings/) and [dashboard controls](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/create-dashboard/dashboard-controls/) documentation. If your running instance uses the older dashboard editor, open the **Settings/gear** icon (sometimes available after clicking Edit), then **Variables** to edit the imported variables or add a missing one.

| Name | Label | Metric selector | Options |
|---|---|---|---|
| `group` | `group` | `up{job="blackbox",group!=""}` | Multi-value, Include All, Custom all value `.*` |
| `service` | `service` | `up{job="blackbox",group=~"$group",service!=""}` | Multi-value, Include All, Custom all value `.*` |

Set refresh to **On dashboard load**. Changing `group` refreshes the dependent `service` variable; use All again if a previously selected service does not exist in the new group. For older/classic editors, the equivalent queries are:

```text
label_values(up{job="blackbox",group!=""}, group)
label_values(up{job="blackbox",group=~"$group",service!=""}, service)
```

These are **Grafana variable queries**, not PromQL to paste into Prometheus. Multi-value variables require regex matchers such as `group=~"$group"`; see [Grafana's Prometheus variable documentation](https://grafana.com/docs/grafana/latest/datasources/prometheus/template-variables/).

Save the dashboard after variable edits, then **Exit edit**. If the imported filters already match the table and work correctly, continue without changing them.

**Check:** selecting one group narrows every health panel and the service dropdown. The catalogue still lists scrape-only services too; this dashboard deliberately shows destination probes. A service with no agreed probe has no measured destination health.

---

## 5. Understand or build the current-health panels

For a manual build, go to *Dashboards → New → New dashboard → Add visualization*. Select Prometheus, switch the query editor to **Code**, paste the relevant expression, choose the settings below, then apply the panel and save the dashboard. Menu names can differ slightly between Grafana versions.

### Summary counters

Each counter uses **Stat**, **Instant**, **Time series** format, calculation **Last**, 0 decimals, graph mode **None**, and No value **Unknown**. Current status queries must end at `now`.

**Configured probe checks:**

```promql
count(up{job="blackbox",group=~"$group",service=~"$service"})
```

**Failed destination checks:**

```promql
count(
  (probe_success{job="blackbox",group=~"$group",service=~"$service"} == 0)
  and on(job,instance,module,group,service,host)
  (up{job="blackbox",group=~"$group",service=~"$service"} == 1)
)
or (0 * count(up{job="blackbox",group=~"$group",service=~"$service"}))
```

**Probe scrape failures:**

```promql
count(up{job="blackbox",group=~"$group",service=~"$service"} == 0)
or (0 * count(up{job="blackbox",group=~"$group",service=~"$service"}))
```

For the two fault counters, use absolute thresholds: base green, **1 red**. The fallback yields zero only while the selected inventory exists. No matching inventory produces **Unknown/No data**. These counters count checks, not service instances: HTTP and TCP for one service are two checks. A missing `probe_success` despite `up=1` is covered by the **Unknown** status below, not by the scrape-failure counter.

### Current probe checks

Use this expression to retain an unknown state while a configured scrape fails or its success metric is absent:

```promql
(
  probe_success{job="blackbox",group=~"$group",service=~"$service"}
  and on(job,instance,module,group,service,host)
  (up{job="blackbox",group=~"$group",service=~"$service"} == 1)
)
or on(job,instance,module,group,service,host)
(
  -1 + 0 * up{job="blackbox",group=~"$group",service=~"$service"}
)
```

| Setting | Value |
|---|---|
| Title / visualisation | Current probe checks / Table |
| Query | Instant; Format Table |
| Transformation | Organize fields by name; hide Time and job |
| Column order | group, service, host, module, instance, owner, contact, dependencies, Value |
| Display names | Group, Service, Host, Check, Target, Owner, Contact, Dependencies, Status |
| Value mappings on Status only | `1` → Up (green); `0` → Down (red); `-1` → Unknown (gray) |
| Status cell type | Colored background |
| No value | Unknown |

One row is one configured check. This keeps the endpoint visible when a service has several checks and only one fails. Keep the ownership columns, because the operator needs a contact when a row turns red.

`Unknown` is a monitoring problem to investigate. Once a target is removed from discovery, it eventually disappears from current `up` too; this query does not preserve retired targets. Compare the dashboard with the agreed service list after target edits.

**Check:** the configured counter equals the number of table rows. Select a check in Explore and compare its displayed state with `up` and `probe_success`. A failing exporter must never create a green Up row.

---

## 6. Understand or build the trend panels

The status-history and HTTP-duration panels use query type **Range**, format **Time series**, and the dashboard time range. The availability and coverage Stats use **Instant** queries over that period. Leave **Connect null values** at **Never** where available. Do not replace gaps with zero or carry the last healthy state through a gap.

| Panel | Visualisation | Unit / options |
|---|---|---|
| Probe status history | Status history | Same 1/0/-1 mappings as the current table; legend `{{group}} / {{service}} @ {{host}} / {{module}} / {{instance}}` |
| Successful HTTP probe duration | Time series | Seconds (`s`); min 0; legend includes service, host and target |
| Observed probe availability | Stat (Instant query) | Percent (0–100); 2 decimals; No value Unknown |
| Probe sample coverage | Stat (Instant query) | Percent (0–100); 1 decimal; No value Unknown |

For **Probe status history**, paste the complete current-check expression from step 5. Before applying or saving this panel, configure:

| Setting | Value |
|---|---|
| Query type / format | Range / Time series |
| Query options → Max data points | **200**, entered explicitly |
| Query options → Min interval | **30s** |
| Value mappings | `1` → Up (green); `0` → Down (red); `-1` → Unknown (gray) |
| No value / Connect null values | Unknown / Never |
| Panel width | Full dashboard width |

Open Query options in the **Queries** area beside the data-source selector, or in the footer if the newer query editor is enabled. The point setting is required during panel creation: leaving it on Auto can cause the **1,441 points received** display error. The exact limit depends on the panel's visible width, so use **100** on narrow screens if necessary. Verify the preview, apply the changes, save and check the normal dashboard view before adding the next panel. Step 3 includes the same settings in the import template.

Status history displays sampled values as colored cells; see [Grafana's status history documentation](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/status-history/). A long time range with this resolution can omit brief failures between evaluation points. Zoom to **Last 15 minutes** for 30-second detail; use the current table and fault counters for current faults.

For **Successful HTTP probe duration**:

```promql
(
  probe_duration_seconds{job="blackbox",module="http_2xx",group=~"$group",service=~"$service"}
  and on(job,instance,module,group,service,host)
  (probe_success{job="blackbox",module="http_2xx",group=~"$group",service=~"$service"} == 1)
)
and on(job,instance,module,group,service,host)
(up{job="blackbox",group=~"$group",service=~"$service"} == 1)
```

Set a visible threshold at **1 second**, matching the current `ServiceSlow` condition. The chart displays the total successful probe duration, including connection and TLS work. It is not an application's internal response-time histogram. Failures leave gaps and are visible in the history panel above.

For **Observed probe availability**, use an Instant query with one result per check:

```promql
100 * avg_over_time(
  probe_success{job="blackbox",group=~"$group",service=~"$service"}[$__range]
)
```

For **Probe sample coverage**, also use Instant:

```promql
clamp_max(
  100 * count_over_time(
    probe_success{job="blackbox",group=~"$group",service=~"$service"}[$__range]
  ) / ($__range_s / 30),
  100
)
```

Use the same legend for both: `{{service}} @ {{host}} / {{module}} / {{instance}}`. `$__range` and `$__range_s` are Grafana time-range variables. The coverage estimate assumes the repo's 30-second scrape interval; change the denominator if you change that interval. It is approximate at range boundaries and during timing jitter.

Availability means **the fraction of recorded samples that succeeded**. An exporter outage creates missing samples, not failed destination samples, so 100% availability with low coverage is inconclusive. A target added an hour ago has low coverage for a six-hour view. Changing target labels starts a new series. Neither panel is a verified monthly SLO or a combined multi-check service SLI. Agree those semantics separately. See [Prometheus's over-time functions](https://prometheus.io/docs/prometheus/latest/querying/functions/#aggregation_over_time).

**Check:** change Last 6 hours to Last 24 hours and Last 7 days. Status history must render without a point-limit error in the normal dashboard view. The selected period changes the graphs and the availability window. Coverage exposes missing history. Wait for real history before claiming a seven-day trend.

---

## 7. Prepare Smith resource metrics

Follow [smith-resource-metrics.md](smith-resource-metrics.md) in order before importing the resource dashboard. That guide covers approved read-only API access, an exporter inside noc-core, the scrape job, guest ownership, budget rules and coverage checks.

Use the existing physical-host Node Exporter only where its installation is authorized. Blackbox probes cannot measure allocated RAM, vCPU or group disk budgets. Adding a Grafana panel does not create those metrics.

| Quantity | Source | Meaning |
|---|---|---|
| Allocated vCPU and memory | Proxmox API | Configured capacity per VM/LXC, including stopped guests |
| CPU and memory used | Proxmox API | Hypervisor-reported current usage; compare with the same Proxmox summary |
| Allocated disk | Reviewed guest disk inventory | All provisioned disks charged under the agreed policy |
| Approved group budget | Approved resourcebudget document | Constant reference values; updated when the allocation decision changes |
| Filesystem free space | Node Exporter on an approved guest | Space available inside that filesystem, distinct from storage allocation |

The budget bars show allocation divided by the approved budget. They do not enforce quotas in Proxmox. Runtime CPU usage and memory consumption have their own trends. For example, a group allocated 6 of 8 vCPU is at **75% of its allocation budget**, even when its machines are idle.

**Check:** the resource guide's acceptance checks pass for the intended scope. If school API access is pending, keep the health dashboard as the completed part and record the resource dashboard as pending; a home exporter is not evidence of Smith coverage.

---

## 8. Import and verify the Smith dashboard

1. Copy [smith-resources-dashboard-template.json](smith-resources-dashboard-template.json) to a local `smith-resources-dashboard.json`.
2. Replace the three title/description/environment placeholders. Suggested title: **Smith resources and budgets**. Explain the agreed scope and that disk allocation is reviewed inventory.
3. Import it using the same new-dashboard procedure as step 3 and select the school's Prometheus source.
4. Select the `group` filter. It comes from `noc_guest_info`; **All** displays separate series per group, rather than averaging percentages across groups.
5. Use Last 6 hours and 30s refresh. Recording rules update once per minute.

The template's panels use the normalized metrics from the resource guide:

| Panel | Query | Type / unit |
|---|---|---|
| Proxmox scrape health | `min(up{job="pve"})` | Stat; Instant; 1 Up green, 0 Failed red; No value Unknown |
| Guests missing resource metrics | See expression below | Stat; Instant; base green, 1 red |
| Unmapped visible Smith guests | `count(noc_smith_unmapped_guest_info) or (0 * count(noc_guest_scope))` | Stat; Instant; base green, 1 red; global scope |
| vCPU allocation / approved budget | `100 * noc_group_cpu_allocated_cores{group=~"$group"} / on(group) noc_group_cpu_budget_cores{group=~"$group"}` | Bar gauge; Instant; percent |
| Memory allocation / approved budget | `100 * noc_group_memory_allocated_bytes{group=~"$group"} / on(group) noc_group_memory_budget_bytes{group=~"$group"}` | Bar gauge; Instant; percent |
| Reviewed disk allocation / approved budget | `100 * noc_group_disk_allocated_bytes{group=~"$group"} / on(group) noc_group_disk_budget_bytes{group=~"$group"}` | Bar gauge; Instant; percent |
| Group vCPU: used, allocated, budget | The three corresponding `noc_group_cpu_*` metrics with `{group=~"$group"}` | Time series; Range; cores |
| Group memory: used, allocated, budget | The three corresponding `noc_group_memory_*` metrics with `{group=~"$group"}` | Time series; Range; bytes (IEC) |
| Reviewed group disk: allocated, budget | `noc_group_disk_allocated_bytes` and `noc_group_disk_budget_bytes` with the group filter | Time series; Range; bytes (IEC) |
| Guest CPU / allocated vCPU | `100 * noc_guest_cpu_used_cores{group=~"$group"} / noc_guest_cpu_allocated_cores{group=~"$group"}` | Time series; Range; percent |
| Guest memory / allocated memory | `100 * noc_guest_memory_used_bytes{group=~"$group"} / noc_guest_memory_allocated_bytes{group=~"$group"}` | Time series; Range; percent |
| Resource inventory | `noc_guest_info{group=~"$group"}` | Table; Instant; Group, Host and Guest ID |

The missing-metrics counter checks all four live resource metrics:

```promql
count(
  noc_guest_info{group=~"$group"}
  unless on(id) (
    noc_guest_cpu_allocated_cores
    and on(id) noc_guest_cpu_used_cores
    and on(id) noc_guest_memory_allocated_bytes
    and on(id) noc_guest_memory_used_bytes
  )
)
or (0 * count(noc_guest_info{group=~"$group"}))
```

Set budget bar thresholds to absolute **base green, 80 yellow, 95 red**. Use percent (0–100), min 0, max 100, decimals 1; disable automatic min/max in the bar gauge. Values above 100 must retain their numeric label so an exceeded budget is visible. These are proposed display thresholds; agree them with the budget owner. They do not create email alerts.

Set No value to **Unknown**. Use legend `{{group}} used`, `{{group}} allocated` and `{{group}} budget` for group trends; guest legends include `{{host}} / {{id}}`. Do not stack the three quantities: usage, allocation and budget are comparisons, not additive amounts. Keep gaps disconnected.

The unmapped-guest counter is intentionally global: an unmapped VM has no reliable group to filter by. The disk bar and disk trend remain available from reviewed inventory even when the API fails; their titles make that distinction explicit. A budget line is a historical record of the configured approved reference, not automatic evidence of approval.

**Check:** verify both fault counters are 0, the API scrape is Up, and the selected inventory matches the approved list. Compare at least one guest's vCPU/RAM and one group's totals with Proxmox and the resourcebudget. CPU/RAM totals disappear for a group missing an inventoried guest's relevant metrics; they must not show a falsely low total.

---

## 9. Add an existing filesystem-capacity trend (optional)

The current stack already has node filesystem metrics. Add this Time series panel to the resource dashboard if you want to show noc-core's real disk-space trend:

```promql
100 * (
  1 - node_filesystem_avail_bytes{job="node",host="noc-core",fstype=~"ext4|xfs|zfs|btrfs"}
    / node_filesystem_size_bytes{job="node",host="noc-core",fstype=~"ext4|xfs|zfs|btrfs"}
)
```

Title it **noc-core filesystem space unavailable (%)**, unit percent (0–100), legend `{{mountpoint}} / {{device}}`, thresholds 80 yellow and **85 red** to match the existing less-than-15%-available disk alert. This uses `avail`, so reserved filesystem space counts as unavailable to normal users. It does not measure the group's provisioned disk allocation.

For an approved VM/guest exporter, replace `noc-core` with its exact `host` label. Confirm the intended mounts against `df -h` on that guest before adding them. Do not sum duplicated mount views or use a VM's zero Proxmox disk-usage value as proof that its filesystem is empty.

**Check:** the selected mount's available and total bytes agree with the guest's filesystem report. This optional panel uses a fixed host and does not follow the resource dashboard's group filter; make that explicit in its description.

---

## 10. Run the acceptance checks and collect evidence

Use a disposable service you control for failure tests. Agree the test window with its owner; the existing alert rules can send real emails. Stopping a production service or the shared exporter is unnecessary.

| Scenario | Procedure | Expected result / evidence |
|---|---|---|
| Persistence | Save both dashboards, close/reopen Grafana | Both are under Dashboards; the catalogue still opens |
| Group filter | Select one group, then All | Every health panel follows the selection; resource totals remain separate per group |
| Failed destination | Stop the disposable service while its scrape remains healthy, then restore it | Table Down, failed-check count increases, red history segment, then Up/green; record detection/recovery times |
| Failed monitoring | In a home/test stack, add a temporary probe with an invalid module name, wait for discovery, then remove it | Its `/probe` scrape fails: row Unknown, scrape-failure count increases; verify `up=0` in Explore |
| Alert timing | Observe the disposable failure for long enough if testing alerting too | Dashboard changes on the first failed scrape; `ServiceDown` fires only after its existing 2-minute hold plus evaluation delay |
| Latency | Compare the chart with successful HTTP duration in Explore | Seconds and 1-second reference line agree; failures are gaps, not zero latency |
| Resource allocation | Compare an inventoried guest and its group with Proxmox and approved budgets | Allocated vCPU/RAM, disk inventory and percentages have a traceable source |
| Missing guest | On a home/test setup, use a nonexistent ID in a temporary inventory entry and remove it afterward | Missing-metrics count increases; the affected group's live total becomes Unknown/No data |
| Missing API | On a home/test setup, stop only `pve-exporter`, then start it | API health fails; live resource panels lose data after the next rule evaluation; disk inventory stays explicitly reviewed/static |
| History | Review 6h, 24h and 7d as data accumulates; zoom to 15m for short failure tests | No point-limit error; sampled changes, gaps and coverage are visible; brief failures are checked at 30-second resolution; no claim of history before collection began |
| Transfer/restore | Export Classic JSON with the external-sharing option, import on a test Grafana and select its source | The imported dashboards work with the destination's metrics; retain restore screenshots |

For the invalid-module test, copy one complete disposable target block to a separate temporary target file, give it unique service/host labels and set `module: dashboard_test_invalid`. Do not edit `blackbox.yml` or existing targets. Remove that file after the test and verify discovery, counters and alerts return to their prior state. This exercises a failed probe scrape without interrupting every service check.

Capture the dashboard name, selected filters, visible time range, timestamp, expected/actual result and tester for each scenario. Keep a record of pending checks. Save sanitized screenshots with the project evidence; review internal addresses, contacts and dependency names before sharing outside the group.

**Check:** mark the dashboard milestone complete only after school service coverage, approved Smith resource scope, comparisons and restore checks pass. Local file validation alone does not prove deployment.

---

## 11. Export, maintain and troubleshoot

Export each saved dashboard as **Classic JSON** with **Share dashboard with another instance** enabled, using [the catalogue export/import procedure](service-catalogue-dashboard.md#5-export-a-dashboard-you-already-created). Keep a sanitized copy with project documentation and an access-controlled complete export for recovery. To update an existing dashboard by import, use that dashboard's current UID and confirm the intended replacement.

| Change | Apply it |
|---|---|
| Grafana panel or variable | Save dashboard; export a fresh JSON copy |
| Probe target file | Automatic file discovery; no restart |
| Proxmox scrape job or resource rules | Validate with `promtool`, then send Prometheus SIGHUP |
| Exporter flags/mounts/image in Compose | Validate Compose, then `docker compose up -d pve-exporter` |
| Exporter credential file | Recreate `pve-exporter` so a single-file mount reads the current file |
| Approved budget or guest mapping | Update the ignored rule copy, record the decision, validate and reload; do not change only the panel title |

| Symptom | Likely cause | Next check |
|---|---|---|
| Many repeated table rows | Range/Both query | Use Instant + Table for current inventory/status |
| Green count but blank status panels | Empty/mismatched filters, metric missing, wrong source | Query `up` and `probe_success`; reset filters to All; Unknown is not healthy |
| Latency is empty while TCP checks work | No HTTP probes or every HTTP probe is failing | Verify `module="http_2xx"` and successful samples |
| Availability 100% with poor coverage | Missing scrape samples or a recently added target | Read status history and sample coverage before interpreting availability |
| Smith panels say No data | Resource guide not applied, rules invalid, wrong case-sensitive node or missing rights | Query `up{job="pve"}`, `pve_guest_info`, `noc_guest_info` and `noc_guest_scope` in order |
| Resource totals too low | Unmapped/hidden guests, wrong scope or missing per-guest values | Check both coverage counters and compare the authorized API inventory with the agreed guest list |
| Memory differs from `free` inside the guest | Hypervisor versus guest accounting, cache/ballooning, or LXC Node Exporter limitation | Compare like-for-like with Proxmox; describe the source rather than mixing the figures |
| Budget percentage is infinite/absent | Zero/missing budget, unit mismatch or wrong group | Use positive approved values; convert GiB to bytes and align group labels |
| No older trends | New series or retention size limit | Check first collection date, label changes and retained history |
| Rules fail with duplicate-series matching | Cluster scraped repeatedly or duplicate inventory ID | Keep one cluster scrape and one inventory entry per ID; do not hide the mismatch with an arbitrary aggregation |

To undo a dashboard import, remove only the new dashboard from Grafana or reimport its previous export using the same UID. To undo configuration changes, restore only the affected files from step 2's backup, preserving your partner's later work, validate, then reload/recreate the affected service. Never remove data volumes to undo a dashboard edit.

Next guide: [smith-resource-metrics.md](smith-resource-metrics.md) supplies the additional data for step 7.
