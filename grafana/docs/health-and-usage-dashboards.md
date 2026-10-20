# Grafana health, resource usage and trends

This guide continues from the working [service catalogue](service-catalogue.md). Keep that dashboard as the ownership and dependency list. Add two dashboards for the next project milestone: service health over time, and Smith resource usage compared with approved budgets. Each step ends with a check before you continue.

**Status — 16 October 2026:** the service-list and service-health implementation is complete for the tested homelab scope. Down/recovery, Unknown, slow-response display and Viewer access were verified with supplied evidence; dashboard restore to a separate Grafana was operator-confirmed in approximately 10 minutes, without restore screenshots. See the [test report](service-health-tests.md) and [setup route](README.md). School coverage, agreed application checks and full-stack restore remain separate requirements. Smith metrics, quotas and resource trends are deferred. The supplied setup already describes pve-exporter; the Smith guide extends that integration without requiring another collector.

| Dashboard | Questions it answers | Data needed |
|---|---|---|
| Service catalogue (existing) | What is monitored, who owns it, what does it depend on? | Target labels on `up` |
| Service health and trends (new) | Which check fails, is the check itself working, how has health/latency changed? | Existing Blackbox probes and `up` |
| Smith resources and budgets (new) | How much is allocated, how much is used, how close is each group to its approved budget? | Approved Proxmox API metrics, guest inventory and group budgets |

The health dashboard can be built once the existing stack and Blackbox targets pass step 1. Its certificate panel also needs at least one HTTPS target; HTTP-only checks have no certificate metrics. The Smith dashboard needs additional data. `node_exporter` inside noc-core can expose host-wide CPU/memory information: do not use it as proof of the LXC's quota or usage. The repo already documents this [LXC limitation](../../docs/operations-and-troubleshooting.md#problems-seen-in-this-project).

Commands in this guide run inside noc-core from `/opt/monitoring`. Dashboard JSON files are edited on your own computer and uploaded through Grafana, just like the catalogue template. They do not need to be stored on the LXC.

**Choose your route:** importing the template in step 3 creates all nine health panels, including their queries and display settings. After checking the filters in step 4, use steps 5 and 6 as reference and complete only their final **Check** paragraphs. Follow their panel-creation instructions only if you are building manually or correcting a missing/incorrect panel. For service-health work, skip the deferred Smith sections 7–9 and continue to step 10 for acceptance, operator access and restore. Resume step 7 when Smith resource work is authorized.

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
probe_duration_seconds{job="blackbox",module=~"http_.*"}
```

`up=1` means Prometheus successfully scraped the Blackbox `/probe` response for that target; it does not prove the destination is healthy. `probe_success=1` means the configured probe passed from the exporter’s network location. A fresh `up=1, probe_success=0` means the configured check failed; this can reflect the destination, network, DNS, TLS or an incorrect check definition. `up=0`, a missing success metric or old samples means destination health is Unknown. A passed TCP connection or ping alone does not verify the application’s full function. See [Prometheus scrape metrics](https://prometheus.io/docs/concepts/jobs_instances/) and [Blackbox probe results](https://github.com/prometheus/blackbox_exporter#checking-the-results).

The supplied configuration reference describes **30-second** scrapes and retention flags **45d / 10GB**. Verify the actual loaded configuration and flags on the destination: these values are not measurements of a running instance. A per-job `scrape_interval` can override the global value. If both retention flags are enabled, the first policy reached applies; the size setting is a TSDB retention policy, not a hard cap on all disk use. A newly monitored target has history only from its first scrape. See [scrape configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config) and [retention behavior](https://prometheus.io/docs/prometheus/latest/storage/#operational-aspects).

In Prometheus, check *Status → Configuration*, *Command-line flags* and *Target health* (names differ by version). Confirm the Blackbox scrape interval, last scrape and scrape errors. In Grafana’s Prometheus data-source settings, set **Scrape interval** to the same value. `http://prometheus:9090` is correct only when Grafana and Prometheus share the Compose network described in the supporting setup guide; otherwise use the address reachable from the Grafana server.

The health template has two hidden **Constant** variables: `probe_interval_s=30` (coverage denominator) and `probe_freshness_s=90` (maximum accepted sample age, exclusive). Set the first to the verified interval in seconds; choose the second longer than normal scrape completion and jitter, typically three intervals for this stack. Also update the status-history **Min interval** separately if collection is not every 30s. One coverage constant assumes every selected check uses the same interval; split dashboards or adapt the coverage calculation if intervals differ. These display settings do not change Prometheus collection. See [Constant variables](https://grafana.com/docs/grafana/latest/visualizations/dashboards/variables/add-template-variables/#add-a-constant-variable).

**Check:** compare current `up{job="blackbox"}` with the agreed service/check list and the target files; no metric query can find a target that was never configured. Each expected probe needs `group`, `service`, `host`, `module`, `owner`, `contact` and `dependencies`. Confirm the `module` label matches the actual `?module=` relabeling and that `instance` is the destination, not `blackbox:9115`. The supplied [target guide](../../docs/adding-targets.md) describes this layout. An empty HTTP-duration query is expected if there are no HTTP checks with module names starting `http_`, or all are failing. The current template includes all `http_.*` modules; other naming conventions require explicitly updating the panel selector.

The joins below use `job,instance,module,group,service,host,owner,contact,dependencies`. Run this current query; it must return no rows:

```promql
count by (job,instance,module,group,service,host,owner,contact,dependencies) (
  up{job="blackbox"}
) > 1
```

If there are duplicates distinguished by another label, include that label consistently in every health join. Confirm `probe_success` and `up` carry the same target labels. Record existing faults rather than requiring every probe to pass before displaying it.

---

## 2. Preserve the catalogue and current configuration

Export both the service list and health dashboard using [the existing export procedure](service-catalogue-dashboard.md#5-export-a-dashboard-you-already-created). Keep an original-UID copy for restoration and a portable copy for destination datasource mapping. Record their names/UIDs and the Prometheus datasource URL/UID. Keep complete exports private; a sanitized reusable template is a different artifact.

Before editing the existing collector configuration or adding rules, take a local configuration backup:

```bash
cd /opt/monitoring
umask 077
DASHBOARD_BACKUP="/opt/monitoring-dashboards-backup-$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$DASHBOARD_BACKUP"
cp -a compose.yaml prometheus "$DASHBOARD_BACKUP/"
if [ -d pve ]; then cp -a pve "$DASHBOARD_BACKUP/"; fi
if [ -d blackbox ]; then cp -a blackbox "$DASHBOARD_BACKUP/"; fi
if [ -d alertmanager ]; then cp -a alertmanager "$DASHBOARD_BACKUP/"; fi
if [ -f .env ]; then cp -a .env "$DASHBOARD_BACKUP/"; fi
```

This backup includes the actual ignored target files and configuration, not just Git templates. It can include credentials; keep it access-controlled and outside Git, with a separate protected copy off the monitored machine. A local folder alone does not protect against losing that machine. It is a configuration backup, not a Grafana database/volume or Prometheus data backup. No full configuration/rule/catalogue restore is claimed by the dashboard test.

For dashboard backup and handover, record the owner, storage location, access controls, retention/cleanup policy, backup date and datasource mapping. Export after accepted dashboard changes. Agree the permitted loss of configuration changes (RPO) and recovery target (RTO); the observed approximately 10-minute homelab restore is a measurement, not an owner-approved RTO. Follow the [separate-instance restore procedure](service-catalogue-dashboard.md#9-verify-dashboard-restore-on-a-separate-grafana); see the [restore result](service-health-tests.md#dashboard-backup-and-restore).

**Check:** you have the exported catalogue JSON and the backup folder. On an existing installation, edit your actual `compose.yaml` and `prometheus/prometheus.yml`; do not replace them with clean templates.

---

## 3. Import the health dashboard

Use [service-health-dashboard-template.json](../service-health-dashboard-template.json), which already contains the variables, queries and panel settings described below.

Before importing, keep these settings on the **Probe status history** panel. They are already present in the current template:

| Setting | Value | JSON field on the panel |
|---|---|---|
| Max data points | **200**, entered explicitly rather than left on Auto | `"maxDataPoints": 200` |
| Min interval | **30s**, matching the existing scrape interval | `"interval": "30s"` |
| Query type / format | Range / Time series | `"range": true`, `"instant": false`, `"format": "time_series"` on query A |
| Panel width | Full dashboard width | `"w": 24` in `gridPos` |

Status history uses separate cells. An explicit point setting requests a coarser query step for longer periods and helps avoid a **Too many points to visualize properly** error. With Prometheus this affects query resolution rather than providing an exact 200-row cutoff. It does not change the collection interval or stored history; 200 is a suggested starting value, not a guaranteed rendering limit. See [Grafana's query options](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/query-transform-data/#query-options).

1. Save a local copy named `service-health-dashboard.json`.
2. Replace `<your dashboard title here>`, `<your description here>` and `<your environment tag here>`. Suggested title: **Service health and trends**; environment tag: `school` or `home-test`.
3. Confirm the four variables are group, service, probe_interval_s and probe_freshness_s, with each name defined once. The current template is already cleaned up; remove duplicate definitions only from an older copy. Keep `id: null`, `uid: null` and every `${DS_PROMETHEUS}` reference. These create a new dashboard and let the import form select the destination source. Check the hidden Constant variables in the JSON against step 1 before import; edit their `query`, `current.text`, `current.value` and `options` value consistently, or adjust them afterward in Variables.
4. In Grafana, go to *Dashboards → New → Import dashboard* and upload the complete local JSON file.
5. Choose the project folder and the existing Prometheus source. Use a new UID; leave the catalogue's UID alone.
6. Click **Import**, choose **All** for the filters, and set the time range to **Last 6 hours**, ending at **now**, with **30s** refresh.

Import follows [Grafana's documented upload workflow](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/import-dashboards/). Keep the imported dashboard saved in Grafana. Saving it there does not update the local JSON file; export a new copy after later edits.

**Check before continuing:** the dashboard shows three summary counters, a current-check table, a status history, latency, observed availability, sample coverage and the HTTPS certificate table. The certificate table may show No data when no HTTPS targets exist; investigate missing results for expected HTTPS targets. Confirm the history displays colored cells without a point-limit error at **Last 6 hours**, then **Last 24 hours** and **Last 7 days**; a new installation will only show the history collected so far. Return to Last 6 hours and save the dashboard. No container restart is needed for an import.

If you already imported an earlier copy, update the existing panel during this setup check:

1. Hover over **Probe status history**, open its **⋮** panel menu and choose **Edit**.
2. In **Queries**, expand **Query options** beside the data-source selector. If the newer query editor is enabled, Query options is in the editor's footer instead.
3. Enter **Max data points = 200** and **Min interval = 30s**. Keep query A as **Range**, format **Time series**, and keep its existing PromQL expression.
4. Run the query. Apply the panel changes, or return using **Back to dashboard** if that is the button shown, then **Save** the dashboard and **Exit edit**.
5. Repeat the three time-range checks above in the normal dashboard view. Keep this panel full width. If a narrow screen still causes the error, lower Max data points to **100** and save again.

Long periods show sampled status at a wider time step and can miss short outages. Use **Last 15 minutes** with a 30s query step to inspect 30-second checks; verify the actual returned step in Query inspector. The current-status table, fault counters and alert rules do not depend on this history-panel resolution.

---

## 4. Configure the filters (also used when building manually)

The template already supplies `group` and `service`; importing it does not require adding them again. Step 4 is a check of those filters, or their setup when building manually.

The supplied setup guide lists Grafana **13.2.2**; verify the running version. Current Grafana documentation describes the following editor paths; menu names and preview features vary by version:

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

Set refresh to **On dashboard load**. Changing `group` refreshes the dependent `service` variable; use All again if a previously selected service does not exist in the new group. After target changes, reload the dashboard to refresh options. Label-value queries can include historical series, so an old dropdown value can legitimately produce No data in the current table. For older/classic editors, the equivalent queries are:

```text
label_values(up{job="blackbox",group!=""}, group)
label_values(up{job="blackbox",group=~"$group",service!=""}, service)
```

These are **Grafana variable queries**, not PromQL to paste into Prometheus. Multi-value variables require regex matchers such as `group=~"$group"`; see [Grafana's Prometheus variable documentation](https://grafana.com/docs/grafana/latest/datasources/prometheus/template-variables/).

Check hidden Constant variables `probe_interval_s` and `probe_freshness_s` here too. For a manual build, create those variables with the values verified in step 1. Save the dashboard after variable edits, then **Exit edit**. If the imported filters already match the table and work correctly, continue without changing them.

**Check:** selecting one group narrows every health panel and the service dropdown. The catalogue still lists scrape-only services too; this dashboard deliberately shows destination probes. A service with no agreed probe has no measured destination health.

---

## 5. Understand or build the current-health panels

**If you imported the template:** the three counters and current-check table already exist. Read their meaning and complete the **Check** at the end. For a manual build, add each visualization, select Prometheus, use **Code** mode, apply the settings below and save.

Current queries use **Instant**, end at **now**, and require the two Constant variables from step 1. The three counters use **Stat**, **Time series** format, calculation **Last**, 0 decimals, graph mode **None**, No value **Unknown**. A historical end time makes them statuses at that time rather than current statuses.

### Current probe checks

Use this expression for the table and the status-history panel. Known states require fresh `probe_success`, `up=1` and a fresh `up` sample. The fallback retains a visible check as `-1` when its state cannot be trusted.

```promql
(
  probe_success{job="blackbox",group=~"$group",service=~"$service"}
  and on(job,instance,module,group,service,host,owner,contact,dependencies) (up{job="blackbox",group=~"$group",service=~"$service"} == 1)
  and on(job,instance,module,group,service,host,owner,contact,dependencies) (time() - timestamp(up{job="blackbox",group=~"$group",service=~"$service"}) < $probe_freshness_s)
  and on(job,instance,module,group,service,host,owner,contact,dependencies)
  (time() - timestamp(probe_success{job="blackbox",group=~"$group",service=~"$service"}) < $probe_freshness_s)
)
or on(job,instance,module,group,service,host,owner,contact,dependencies)
(-1 + 0 * up{job="blackbox",group=~"$group",service=~"$service"})
```

| Setting | Value |
|---|---|
| Title / visualization | Current probe checks / Table |
| Query | Instant; Format Table |
| Transformation | Organize fields by name; hide Time and job |
| Column order | group, service, host, module, instance, owner, contact, dependencies, Value |
| Display names | Group, Service, Host, Check, Target, Owner, Contact, Dependencies, Status |
| Value mappings on Status only | `1` → Up (green); `0` → Down (red); `-1` → Unknown (gray) |
| Status cell type | Colored background |
| No value | Unknown |

One row is one visible destination check. **Up** means that check passed; it is not evidence that every function of a service works. HTTP and TCP probes for the same service count as two checks. Ownership columns give the operator a contact for investigation.

The default freshness tolerance is **less than 90 seconds**, assuming 30s collection. Samples exactly 90s old are Unknown. Prometheus can otherwise reuse recent samples within its lookback window (normally 5 minutes). These gates reduce that stale-green window, but a fault between two scrapes remains undetected until collection or the freshness tolerance expires. If Prometheus/Grafana itself is unreachable, the panel can show a query error instead of an Unknown value. See [Prometheus staleness](https://prometheus.io/docs/prometheus/latest/querying/basics/#staleness) and [time/timestamp functions](https://prometheus.io/docs/prometheus/latest/querying/functions/#timestamp).

Once a target is removed or its `up` series becomes stale, it disappears from current inventory; the fallback cannot preserve a target whose `up` is absent. Compare with the agreed list after target edits. An entirely absent job must read **Unknown/No data**, not healthy zero.

### Summary counters

**Visible probe checks:**

```promql
count(up{job="blackbox",group=~"$group",service=~"$service"})
```

This counts currently queryable `up` series, including failed scrapes. It does not prove that all intended checks have been configured.

**Failed destination checks:**

```promql
count((
  probe_success{job="blackbox",group=~"$group",service=~"$service"}
  and on(job,instance,module,group,service,host,owner,contact,dependencies) (up{job="blackbox",group=~"$group",service=~"$service"} == 1)
  and on(job,instance,module,group,service,host,owner,contact,dependencies) (time() - timestamp(up{job="blackbox",group=~"$group",service=~"$service"}) < $probe_freshness_s)
  and on(job,instance,module,group,service,host,owner,contact,dependencies)
  (time() - timestamp(probe_success{job="blackbox",group=~"$group",service=~"$service"}) < $probe_freshness_s)
) == 0)
or (0 * count(up{job="blackbox",group=~"$group",service=~"$service"}))
```

**Unknown probe checks:**

```promql
count(((
  probe_success{job="blackbox",group=~"$group",service=~"$service"}
  and on(job,instance,module,group,service,host,owner,contact,dependencies) (up{job="blackbox",group=~"$group",service=~"$service"} == 1)
  and on(job,instance,module,group,service,host,owner,contact,dependencies) (time() - timestamp(up{job="blackbox",group=~"$group",service=~"$service"}) < $probe_freshness_s)
  and on(job,instance,module,group,service,host,owner,contact,dependencies)
  (time() - timestamp(probe_success{job="blackbox",group=~"$group",service=~"$service"}) < $probe_freshness_s)
)
or on(job,instance,module,group,service,host,owner,contact,dependencies)
(-1 + 0 * up{job="blackbox",group=~"$group",service=~"$service"})) == -1)
or (0 * count(up{job="blackbox",group=~"$group",service=~"$service"}))
```

For both fault counters, use absolute thresholds **base green, 1 red**. The Unknown counter includes failed scrapes, missing `probe_success` and old samples while `up` remains visible. Both fallbacks produce zero only while selected inventory exists. Read all three counters together; zero failed checks with unknown checks is inconclusive.

**Check:** the visible counter equals the number of table rows. Compare one check with its `up`, `probe_success` and sample ages in Explore. Fresh passing/failed probes give 1/0; a failed scrape, missing success metric or old sample gives Unknown. Empty inventory gives No data. A failing exporter must not leave a green row after the next failed scrape or freshness deadline.

---

## 6. Understand or build the trend panels

**If you imported the template:** status history, HTTP duration, availability and sample coverage already exist with the queries and settings below. Complete the final time-range **Check**; the remaining instructions are reference or manual-build instructions. For an older import, apply the status-history resolution fix in step 3 if you have not done so yet.

The status-history and HTTP-duration panels use query type **Range**, format **Time series**, and the dashboard time range. The availability and coverage Stats use **Instant** queries over that period. Leave **Connect null values** at **Never** where available. Do not replace gaps with zero or carry the last healthy state through a gap.

| Panel | Visualisation | Unit / options |
|---|---|---|
| Probe status history | Status history | Same 1/0/-1 mappings as the current table; legend `{{service}}` |
| Successful HTTP probe duration | Time series | Seconds (`s`); min 0; legend `{{service}}` |
| Observed probe availability | Stat (Instant query) | Percent (0–100); 2 decimals; No value Unknown; legend `{{service}}` |
| Probe sample coverage | Stat (Instant query) | Percent (0–100); 1 decimal; No value Unknown; legend `{{service}}` |

All four panels display only the `service` label from the Prometheus target file (for example `jellyfin`), using the query legend `{{service}}`. This changes names only: each probe remains a separate series with its original labels and query. Multiple checks or historical label changes can therefore produce repeated service names; use the group/service filters and **Current probe checks** table to inspect the host, module and destination.

To update an existing dashboard without re-importing it:

1. Edit each of the four panels listed above and select its Prometheus query **A**.
2. Under the query's **Legend** option, choose **Custom** and enter `{{service}}`. In editors with a single legend text field, enter it there. Keep the PromQL expression and query type unchanged.
3. Run the query and confirm the history row labels, duration legend and Stat names show only the service value. Return to the dashboard and save after applying all four panels.

A fresh template import already contains these legends. For an edited export of an existing dashboard, preserve its UID and datasource mapping when importing it over that dashboard.

For **Probe status history**, paste the complete current-check expression from step 5. Before applying or saving this panel, configure:

| Setting | Value |
|---|---|
| Query type / format | Range / Time series |
| Query options → Max data points | **200**, entered explicitly |
| Query options → Min interval | **30s** |
| Value mappings | `1` → Up (green); `0` → Down (red); `-1` → Unknown (gray) |
| No value / Connect null values | Unknown / Never |
| Panel width | Full dashboard width |

Open Query options in the **Queries** area beside the data-source selector, or in the footer if the newer query editor is enabled. The fixed point setting helps keep a consistent query resolution when the panel is resized. A status-history error depends on the returned data and visible width, so use **100** on narrow screens if needed; the acceptance check remains required. Verify the preview, apply the changes, save and check the normal dashboard view before adding the next panel. Step 3 includes the same settings in the import template.

Status history displays sampled values as colored cells; see [Grafana's status history documentation](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/status-history/). A long time range with this resolution can omit brief failures between evaluation points. Zoom to **Last 15 minutes** for 30-second detail; use the current table and fault counters for current faults.

For **Successful HTTP probe duration**:

To edit the query on a dashboard that was imported earlier:

1. Open the **Service health** dashboard.
2. Find **Successful HTTP probe duration**.
3. Hover over that panel, open its **⋮** menu and choose **Edit**. This opens the panel editor, rather than dashboard settings.
4. In the query area, open **Queries** and select query **A**. In the newer editor, select the **A** card under **Queries & expressions**.
5. Switch the Prometheus query editor from **Builder** to **Code**.
6. In that query, replace all four occurrences of `module="http_2xx"` with `module=~"http_.*"`. Keep every success, scrape-health and freshness condition.
7. Click **Run queries** or **Refresh**. Keep query type **Range**, result format **Time series**, unit seconds and the existing group/service filters.
8. Return to the dashboard using **Back to dashboard** or **Apply**, then **Save** the dashboard.

The current import template already has this query; a fresh import needs no manual query change. The selector matches HTTP modules named with the `http_` prefix, including `http_2xx`, `http_2xx_insecure` and `http_grafana_health`. If all current probes use `http_2xx`, the displayed results should stay the same. Other naming conventions require an explicit selector update.

```promql
(
  probe_duration_seconds{job="blackbox",group=~"$group",service=~"$service",module=~"http_.*"}
  and on(job,instance,module,group,service,host,owner,contact,dependencies) (probe_success{job="blackbox",group=~"$group",service=~"$service",module=~"http_.*"} == 1)
  and on(job,instance,module,group,service,host,owner,contact,dependencies) (up{job="blackbox",group=~"$group",service=~"$service"} == 1)
  and on(job,instance,module,group,service,host,owner,contact,dependencies) (time() - timestamp(up{job="blackbox",group=~"$group",service=~"$service"}) < $probe_freshness_s)
  and on(job,instance,module,group,service,host,owner,contact,dependencies)
  (time() - timestamp(probe_success{job="blackbox",group=~"$group",service=~"$service",module=~"http_.*"}) < $probe_freshness_s)
  and on(job,instance,module,group,service,host,owner,contact,dependencies)
  (time() - timestamp(probe_duration_seconds{job="blackbox",group=~"$group",service=~"$service",module=~"http_.*"}) < $probe_freshness_s)
)
```

The template already has a visible reference line at **1 second**. Match it to the agreed threshold and verify the actual loaded `ServiceSlow` rule before claiming chart and alert alignment. The repository rule already includes `http_.*` modules; follow [the alert coverage check](../../docs/how-to-guides.md#keep-http-latency-charts-and-alerts-aligned) only when verifying or updating the deployed configuration. This is total successful probe duration, including connection and TLS work, not an application response-time histogram. Failed, missing and old probe samples leave gaps.

For **Observed probe availability**, use an Instant query with one result per check:

```promql
(100 * avg_over_time(probe_success{job="blackbox",group=~"$group",service=~"$service"}[$__range]))
or on(job,instance,module,group,service,host,owner,contact,dependencies) (-1 + 0 * up{job="blackbox",group=~"$group",service=~"$service"})
```

Add a value mapping `-1 → Unknown` (gray). The sentinel covers a visible check with no recorded `probe_success` samples in the selected range; it is not a negative percentage.

For **Probe sample coverage**, also use Instant:

```promql
clamp_max(
  100 * count_over_time(probe_success{job="blackbox",group=~"$group",service=~"$service"}[$__range]) / ($__range_s / $probe_interval_s),
  100
)
or on(job,instance,module,group,service,host,owner,contact,dependencies) (0 * up{job="blackbox",group=~"$group",service=~"$service"})
```

Use legend `{{service}}` for both. `$__range` and `$__range_s` are Grafana time-range variables. Coverage uses `probe_interval_s` from step 1. The estimate is approximate at boundaries and with timing jitter and is clamped at 100%; use a range substantially longer than one scrape interval.

Availability is the **fraction of recorded samples that succeeded**, with each sample weighted equally. Missing samples are excluded. A visible check with no samples has Unknown availability and 0% coverage. A monitoring outage can therefore leave 100% availability with poor coverage; that is inconclusive. New targets, label changes, retention and monitoring gaps lower coverage for a longer view. Historical series with samples can remain in these period summaries after the target is removed. Neither panel is a verified monthly SLO or combined service SLI. See [Prometheus over-time functions](https://prometheus.io/docs/prometheus/latest/querying/functions/#aggregation_over_time).

**Check:** change Last 6 hours to Last 24 hours and Last 7 days. Status history must render without a point-limit error in the normal dashboard view. The selected period changes the graphs and the availability window. Coverage exposes missing history. Metadata changes create separate series, so period summaries can show more than one line with the same displayed check name; do not combine their percentages as a service availability measure. Wait for real history before claiming a seven-day trend.

---

### HTTPS certificate expiry

The health template includes **HTTPS certificate days remaining**, with its query, column order, days unit, one decimal and coloured numeric cells already configured. A fresh import requires no manual panel creation. For an older live dashboard, use **Edit → Add new element → Panel → Configure visualization**, choose the existing Prometheus data source and Table, then use the reference below.

```promql
(
  (probe_ssl_earliest_cert_expiry{job="blackbox",group=~"$group",service=~"$service"} - time()) / 86400
)
and on(job,instance,module,group,service,host,owner,contact,dependencies)
(probe_ssl_earliest_cert_expiry{job="blackbox",group=~"$group",service=~"$service"} > 0)
and on(job,instance,module,group,service,host,owner,contact,dependencies)
(up{job="blackbox",group=~"$group",service=~"$service"} == 1)
and on(job,instance,module,group,service,host,owner,contact,dependencies)
(time() - timestamp(up{job="blackbox",group=~"$group",service=~"$service"}) < $probe_freshness_s)
and on(job,instance,module,group,service,host,owner,contact,dependencies)
(time() - timestamp(probe_ssl_earliest_cert_expiry{job="blackbox",group=~"$group",service=~"$service"}) < $probe_freshness_s)
```

| Setting | Value |
|---|---|
| Query type / format | Instant / Table |
| Visible fields | group, service, host, module, instance, Value |
| Display names | Group, Service, Host, Check, Target, Days remaining |
| Hidden fields, if present | Time, job, __name__, owner, contact, dependencies |
| Override matcher | Fields with name: Days remaining |
| Unit / decimals | Days / 1 |
| No value / null mapping | Unknown / grey |
| Thresholds on Days remaining only | Absolute: base red, 3 orange, 14 green |
| Cell type on Days remaining only | Colored background |

Keep negative values visible: they indicate an expired certificate. The query needs a fresh successful scrape and a recent positive expiry timestamp; it deliberately does not require `probe_success=1`, because an application check may fail while the exporter still observes its certificate.

The table displays reported certificate metrics, not every expected HTTPS target. HTTP-only checks have no certificate expiry. An expected HTTPS target missing from the table needs investigation; an empty table does not establish healthy certificates. Compare the rows with the agreed HTTPS inventory. The 3/14-day colour boundaries correspond to the existing critical/warning rule thresholds, but panel colours do not implement the rules' waiting periods or send notifications.

For a homelab without HTTPS services, use the [temporary public HTTPS example](../../docs/adding-targets.md#temporary-public-https-test). If its debug output reports an IPv6 `network is unreachable` error, follow the documented IP-family setting there.

**Homelab confirmation — 16 October 2026:** the operator confirmed the manually configured certificate panel works after changing the existing `http_2xx` module to prefer IPv4. The original probe had selected an IPv6 destination with no working route. This confirms that live configuration and display; fresh import of the updated complete template, school deployment and critical-certificate notification testing remain separate checks.

**Check:** select the HTTPS target's group/service and compare the panel's days remaining with the same query in Explore. Confirm the numeric cells have the expected colour and HTTP-only services are absent. Preserve evidence of the working display.

---

## 7. Prepare Smith resource metrics

Follow [smith-resource-metrics.md](smith-resource-metrics.md) in order before importing the resource dashboard. That guide covers approved read-only API access, an exporter inside noc-core, the scrape job, guest ownership, budget rules and coverage checks.

Use the existing physical-host Node Exporter only where its installation is authorized. Blackbox probes cannot measure allocated RAM, vCPU or group disk budgets. Adding a Grafana panel does not create those metrics.

| Quantity | Source | Meaning |
|---|---|---|
| CPU capacity | Proxmox API | API-reported `maxcpu`; reconcile it with the approved charging policy. For LXC it may fall back from configured cores to CPU limit to host CPU count; see the [Proxmox LXC implementation](https://github.com/proxmox/pve-container/blob/master/src/PVE/LXC.pm). It is not a reservation or a verified quota. |
| Memory capacity | Proxmox API | API-reported maximum memory per VM/LXC, including stopped guests when exposed |
| CPU and memory used | Proxmox API | Hypervisor-reported current usage; compare with the same Proxmox summary |
| Allocated disk | Reviewed guest disk inventory | All provisioned disks charged under the agreed policy |
| Approved group budget | Approved resourcebudget document | Constant reference values; updated when the allocation decision changes |
| Filesystem free space | Node Exporter on an approved guest | Space available inside that filesystem, distinct from storage allocation |

The budget bars show allocation divided by the approved budget. They do not enforce quotas in Proxmox. Runtime CPU usage and memory consumption have their own trends. For example, a group charged 6 CPU units against an approved budget of 8 is at **75% of its CPU budget**, even when its machines are idle. That interpretation requires the API CPU-capacity values to match the approved charging policy.

**Check:** the resource guide's acceptance checks pass for the intended scope. If school API access is pending, keep the health dashboard as the completed part and record the resource dashboard as pending; a home exporter is not evidence of Smith coverage.

---

## 8. Import and verify the Smith dashboard

1. Complete [smith-resource-metrics.md](smith-resource-metrics.md), using the existing exporter and single `pve` scrape where present. Load the reviewed inventory, budgets and recording rules before importing.
2. Copy [smith-resources-dashboard-template.json](../smith-resources-dashboard-template.json) to a local `smith-resources-dashboard.json`.
3. Replace the title/description/environment placeholders. Suggested title: **Smith resources and budgets**. Describe the agreed scope, CPU charging policy and reviewed disk inventory.
4. Import using the new-dashboard procedure in step 3, choose the intended Prometheus source and keep the catalogue UID unchanged.
5. Select `group`. Its options include reviewed inventory groups and approved budget groups. **All** keeps separate series per group instead of averaging percentages.
6. Use Last 6 hours ending at now and 30s refresh. The resource recording group is configured to evaluate every minute; verify it is loaded and healthy.

The JSON is the panel/query reference. The resource guide defines each normalized metric and the exact source, inventory and budget acceptance checks. Interpret the panels as follows:

| Panel category | Meaning / required check |
|---|---|
| Proxmox scrape health | Source readiness requires exactly one configured PVE target, a successful scrape and an `up` sample younger than 90s. Unknown, absent or failed readiness prevents trusting live CPU/memory totals. Adjust the rule tolerance when collection differs from 30s. |
| Missing resource metrics | Inventoried guests missing a required normalized CPU/memory value; detail rows identify them. An affected group’s relevant live total is hidden instead of showing a partial sum. |
| Unmapped visible Smith guests | Global scope: API-visible Smith guests with no reviewed mapping; an unmapped guest cannot be reliably assigned to a group filter. The detail table supports reconciliation. |
| Missing/invalid budgets | Groups without all three positive approved budgets. Missing or zero budgets must not create meaningful percentages. |
| Duplicate guest IDs | Global API/inventory identity conflicts. Resolve the source or mapping; duplicates are filtered before joins so they cannot silently double-count totals. A detail table identifies conflicts. |
| CPU/memory budget bars and trends | API capacity and reported use compared with approved group reference values. Reconcile CPU API capacity with the charging policy, particularly for LXC. Capacity is not CPU busy time and is not a guaranteed reservation. |
| Reviewed disk bar/trend | Provisioned disk amounts from the reviewed inventory, not physical storage consumption. This static data can remain visible while the API fails. |
| Guest utilization | Hypervisor-reported usage relative to the corresponding API capacity. Compare like-for-like with the Proxmox summary and inspect collector semantics before treating it as guest-internal usage. |
| Resource inventory | Reviewed mapping, not proof of automatic discovery, running state or complete API permissions. |

Budget display thresholds are proposed **80 yellow / 95 red**; obtain the budget owner’s agreement. Bar maximum 100 visually fills at an exceeded budget, so retain the numeric label above 100. These display thresholds neither enforce Proxmox quotas nor create email alerts.

A fresh PVE scrape does not prove that the underlying Proxmox host statistics are fresh; compare the API readings with node health and the Proxmox summary at similar times. Use **Unknown** for missing values. Keep used/capacity/budget trend lines unstacked and gaps disconnected: these are comparisons, not additive amounts. A budget line records the reference configured at that time; it is not evidence of approval by itself.

**Check:** source readiness is Up, all diagnostic counters have the expected results, and every detail table has been reconciled against the approved scope. Empty tables or zero counters cannot prove ACL coverage: the API may hide guests the token cannot see. Compare the approved list independently. Compare at least one guest and group with Proxmox and approved budgets. Verify one LXC CPU value against its cores/CPU limit if the scope includes LXC; verify every provisioned disk charged by policy. Test missing metrics/source/duplicate IDs in a separate test setup. CPU/memory totals must become Unknown/No data for incomplete or invalid live data, while static disk values remain explicitly marked as reviewed inventory.

---

## 9. Add an existing filesystem-capacity trend (optional)

The supplied stack describes Node Exporter filesystem metrics; confirm they exist and represent the intended mounts. Add this Time series panel to the resource dashboard if you want to show noc-core's real disk-space trend:

```promql
100 * (
  1 - node_filesystem_avail_bytes{job="node",host="noc-core",fstype=~"ext4|xfs|zfs|btrfs"}
    / node_filesystem_size_bytes{job="node",host="noc-core",fstype=~"ext4|xfs|zfs|btrfs"}
)
```

Title it **noc-core filesystem space unavailable (%)**, unit percent (0–100), legend `{{mountpoint}} / {{device}}`, thresholds 80 yellow and **85 red**, corresponding to the supplied reference’s less-than-15%-available disk condition (equality at 85% is a display threshold; the rule’s comparison is strict). Verify the loaded alert threshold and collector mounts first. This uses `avail`, so reserved filesystem space counts as unavailable to normal users. It does not measure the group's provisioned disk allocation.

For an approved VM/guest exporter, replace `noc-core` with its exact `host` label. Confirm the intended mounts against `df -h` on that guest before adding them. Do not sum duplicated mount views or use a VM's zero Proxmox disk-usage value as proof that its filesystem is empty.

**Check:** the selected mount's available and total bytes agree with the guest's filesystem report. This optional panel uses a fixed host and does not follow the resource dashboard's group filter; make that explicit in its description.

---

## 10. Run the acceptance checks and collect evidence

The [service-health dashboard test report](service-health-tests.md) records the completed homelab tests, Grafana observations and outcomes for Down/recovery, Unknown status, slow successful responses and HTTPS display. Notification routing and maintenance procedures remain in the [monitoring how-to guide](../../docs/how-to-guides.md).

For the Viewer login and permission checks, follow [Verify the operator account](service-catalogue-dashboard.md#8-verify-the-operator-account). For dashboard export and a separate-instance restore test, follow [the Grafana restore procedure](service-catalogue-dashboard.md#9-verify-dashboard-restore-on-a-separate-grafana).

Use a disposable service you control for failure tests. Agree the test window with its owner; the existing alert rules can send real emails. Stopping a production service or the shared exporter is unnecessary.

| Scenario | Procedure | Expected result / evidence |
|---|---|---|
| Persistence | Save both dashboards, close/reopen Grafana | Both are under Dashboards; the catalogue still opens |
| Group filter | Select one group, then All | Every health panel follows the selection; resource totals remain separate per group |
| Failed destination | Stop the disposable service while its scrape remains healthy, then restore it | Table Down, failed-check count increases, red history segment, then Up/green; record detection/recovery times |
| Failed monitoring | In a home/test stack, add a temporary probe with an invalid module name, wait for discovery, then remove it | Its `/probe` scrape fails: row Unknown, Unknown-check count increases; verify `up=0` in Explore |
| Alert timing | Observe the disposable failure for long enough if testing alerting too | Dashboard changes on the first failed scrape; `ServiceDown` follows its loaded `for` duration (the supplied reference says 2m) plus rule-evaluation timing; email adds Alertmanager routing/group delays |
| Latency | Compare the chart with successful HTTP duration in Explore | Seconds and 1-second reference line agree; failures are gaps, not zero latency |
| Resource allocation | Compare an inventoried guest and its group with Proxmox and approved budgets | Allocated vCPU/RAM, disk inventory and percentages have a traceable source |
| Missing guest | On a home/test setup, use a nonexistent ID in a temporary inventory entry and remove it afterward | Missing-metrics count increases; the affected group's live total becomes Unknown/No data |
| Missing API | On a home/test setup, stop only `pve-exporter`, then start it | API health fails; live CPU/memory panels lose data after the failed scrape and next successful rule evaluation (or the source freshness deadline if scraping stops); disk inventory stays explicitly reviewed/static |
| History | Review 6h, 24h and 7d as data accumulates; zoom to 15m for short failure tests | No point-limit error; sampled changes, gaps and coverage are visible; brief failures are checked at 30-second resolution; no claim of history before collection began |
| Transfer/restore | Export Classic JSON with the external-sharing option, import on a test Grafana and select its source | The imported dashboards work with the destination's metrics; record result, duration and screenshots/logs when available |

For the invalid-module test, copy one complete disposable target block to a separate temporary target file, give it unique service/host labels and set `module: dashboard_test_invalid`. Do not edit `blackbox.yml` or existing targets. Remove that file after the test and verify discovery, counters and alerts return to their prior state. This exercises a failed probe scrape without interrupting every service check.

Add two query-level checks: a visible target with no `probe_success` must be Unknown in the table, Unknown in availability and 0% in coverage; entirely absent `up` must produce No data/Unknown, never healthy zero. A test fixture or disposable test scrape can exercise these without stopping shared monitoring. Confirm the freshness boundary in a test source: retained samples at or above the configured age are Unknown.

Capture the dashboard name, selected filters, visible time range, timestamp, expected/actual result and tester for each scenario. Keep a record of pending checks and identify operator-confirmed results when screenshots/logs were not collected. Save sanitized screenshots with the project evidence; review internal addresses, contacts and dependency names before sharing outside the group.

**Check:** the tested homelab service-list and health-dashboard scope can be marked complete with the evidence in the report. School sign-off still requires the approved service coverage and application checks; Smith remains explicitly deferred. The teacher's broader milestone also requires configuration/rule/catalogue restore and the other NOC deliverables. Local template validation or restoring exported dashboard definitions alone does not prove those requirements.

---

## 11. Export, maintain and troubleshoot

Export each saved dashboard as **Classic JSON** with **Share dashboard with another instance** enabled, using [the catalogue export/import procedure](service-catalogue-dashboard.md#5-export-a-dashboard-you-already-created). Keep a sanitized copy with project documentation and an access-controlled complete export for recovery. To update an existing dashboard by import, use that dashboard's current UID and confirm the intended replacement.

| Change | Apply it |
|---|---|
| Grafana panel or variable | Save dashboard; export a fresh JSON copy |
| Probe target file | Automatic file discovery; no restart if the existing `file_sd_configs` glob includes the file; verify target health afterward |
| Proxmox scrape job or resource rules | Validate with `promtool`, then send Prometheus SIGHUP |
| Exporter flags/mounts/image in Compose | Validate Compose, then `docker compose up -d pve-exporter` |
| Exporter credential file | Recreate `pve-exporter` so a single-file mount reads the current file |
| Approved budget or guest mapping | Update the ignored rule copy, record the decision, validate and reload; do not change only the panel title |

| Symptom | Likely cause | Next check |
|---|---|---|
| Many repeated table rows | Range/Both query | Use Instant + Table for current inventory/status |
| Green count but blank status panels | Empty/mismatched filters, metric missing, wrong source | Query `up` and `probe_success`; reset filters to All; Unknown is not healthy |
| Latency is empty while TCP checks work | No matching HTTP probes or every HTTP probe is failing | Verify module names start with `http_` and successful samples exist |
| Availability 100% with poor coverage | Missing scrape samples or a recently added target | Read status history and sample coverage before interpreting availability |
| Smith panels say No data | Resource guide not applied, rules invalid, wrong case-sensitive node or missing rights | Query `up{job="pve"}`, `noc_pve_source_ready`, `pve_guest_info`, `noc_guest_info` and `noc_guest_scope` in order; then inspect diagnostic panels |
| Resource totals too low | Unmapped/hidden guests, wrong scope or missing per-guest values | Check both coverage counters and compare the authorized API inventory with the agreed guest list |
| Memory differs from `free` inside the guest | Hypervisor versus guest accounting, cache/ballooning, or LXC Node Exporter limitation | Compare like-for-like with Proxmox; describe the source rather than mixing the figures |
| Budget percentage is infinite/absent | Zero/missing budget, unit mismatch or wrong group | Use positive approved values; convert GiB to bytes and align group labels |
| No older trends | New series or retention size limit | Check first collection date, label changes and retained history |
| Rules fail with duplicate-series matching | Cluster scraped repeatedly or duplicate inventory ID | Keep one cluster scrape and one inventory entry per ID; do not hide the mismatch with an arbitrary aggregation |

To undo a dashboard import, remove only the new dashboard from Grafana or reimport its previous export using the same UID. To undo configuration changes, restore only the affected files from step 2's backup, preserving your partner's later work, validate, then reload/recreate the affected service. Never remove data volumes to undo a dashboard edit.

Next guide: [smith-resource-metrics.md](smith-resource-metrics.md) supplies the additional data for step 7.
