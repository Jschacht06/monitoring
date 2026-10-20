# Service catalogue in Grafana

This guide continues the installation in [setup.md](../../docs/setup.md), adding a Grafana dashboard that lists currently discovered scrape targets by service, with their owner, dependencies and contact person. Each step ends with a check that tells you what you should see before you continue.

**Status — 16 October 2026:** catalogue and health behaviour were verified in the homelab, and the operator confirmed successful dashboard export/restore on a separate Grafana in approximately 10 minutes. See the [Grafana documentation index](README.md) and [test report](service-health-tests.md). School service coverage and owner agreements still need deployment-specific evidence. The dashboard JSON does not install the monitoring stack.

All commands run as root inside the Debian 13 LXC, from the stack folder:

```bash
cd /opt/monitoring
```

The supplied setup uses `/opt/monitoring` for both home and school. If the recipient uses another stack folder, substitute that folder in the commands. Docker-in-LXC configuration belongs to the supporting base setup and must be working before continuing here.

Placeholders used in this guide:

| Placeholder | Meaning |
|---|---|
| `<noc-core-ip>` | IP address of the monitoring LXC you are using |
| `<owner>` | Person or team responsible for the service |
| `<contact-person>` | Named person to contact when the service has a problem |
| `<contact-address>` | That person's agreed school email address or other contact channel |
| `<dependencies>` | Other service IDs or external infrastructure the service needs |
| `<school-host>` | Reachable IP address or hostname of a school server |

---

## Agree the monitored services

Before configuring school targets, record an intake with at least three project groups. Homelab categories such as gaming or monitoring do not demonstrate those school-group agreements. Keep the signed-off list with the project evidence.

| Record per service | What to agree |
|---|---|
| Identity | Project group, service name and stable host identity |
| Responsibility | Owner, real contact role/channel and escalation contact |
| Dependencies | Monitored service IDs as group/service@host; otherwise external:name |
| Reachability | Permitted URL/port/protocol and the network location of the probe |
| Application health | Endpoint and expected status/body or function, approved by the owner |
| SLI and threshold | What is measured, acceptable response time and agreed detection/notification time |
| Maintenance | Timezone, planned window, owner and existing silence procedure |
| Access | Approval for probes and any optional host/agent/API metrics; least-privilege credentials |

Use the same identity and metadata on every check for one service. Keep maintenance and SLI explanations in the intake record rather than long metric labels. A success count alone cannot detect a service that was never configured; reconcile the target list against this agreement.

## 1. Prerequisites

On a new installation, use [setup.md](../../docs/setup.md) through step 8 as the supplied stack context, and verify a working Compose stack and Prometheus data source before continuing. On an existing installation, reuse its working configuration. You need permission to change the Prometheus configuration and create/save Grafana dashboards (and permission to create a data source if one is missing). The catalogue guide assumes sufficient resources and does not repeat the server installation.

The base setup also copies `prometheus/template.yml` to `prometheus/prometheus.yml`. The latter is now an ignored local configuration file. On an existing installation, keep your current copy and integrate new template settings into it; copy the template only when creating a configuration for the first time.

| Component | Address |
|---|---|
| Grafana in your browser | `http://<noc-core-ip>:3000` |
| Prometheus in your browser | `http://<noc-core-ip>:9090` |
| Prometheus data source inside Grafana | `http://prometheus:9090` |

Use the Prometheus data source created during that base installation. A clean Grafana volume starts without the source or dashboards from the previous installation; there is no extra Grafana plugin to install for the catalogue.

**Check:**

```bash
docker compose ps
```

Every service enabled in your actual `compose.yaml` should be running without a restart loop. The supporting configuration describes five base services and an optional `pve-exporter`; count the services actually enabled rather than expecting a fixed total. Grafana opens at `http://<noc-core-ip>:3000` if that port is published as described.

Verify the active `blackbox` job in `prometheus/prometheus.yml` before adding target files. It must discover the mounted target folder, pass the destination and module to Blackbox, and preserve `instance` as the destination. The supplied configuration reference describes this pattern; adjust paths/service names to the actual stack and update an existing job rather than duplicating it:

```yaml
  - job_name: blackbox
    metrics_path: /probe
    scrape_interval: 30s
    scrape_timeout: 10s
    file_sd_configs:
      - files: ['/etc/prometheus/targets/*.yml']
        refresh_interval: 1m
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [module]
        target_label: __param_module
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox:9115
```

This requires the host `prometheus` folder to be mounted at `/etc/prometheus` in the Prometheus container. Keep existing rules, other jobs and any intentional additional relabeling. Every module referenced by an enabled target must exist in the active `blackbox/blackbox.yml`. Reuse `http_2xx` for ordinary HTTP checks and `tcp_connect` for TCP. ICMP is optional and requires its own configured module; the current tracked Blackbox configuration does not define `icmp`. An unknown module makes the probe scrape fail even when the destination works. A module name is a local recipe name; its behavior depends on that recipe. The supplied reference describes HTTP/TCP/ICMP probers with 5-second timeouts, leaving time within the 10-second scrape timeout. See [the Blackbox exporter scrape pattern](https://github.com/prometheus/blackbox_exporter#prometheus-configuration) and [file discovery configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#file_sd_config).

If you change the main job, validate and reload it as in steps 4–5. File discovery only applies automatically when this job is active and can read the matching files.

---

## 2. Add the first targets and their catalogue labels

A catalogue entry starts with the labels on a monitored target. `group`, `service` and `host` define the service identity used by this package. Add three more labels: `owner`, `contact` and `dependencies`. Two independent applications on the same host need distinct `service` values. Several checks of one application use the same identity labels and exactly the same metadata.

| Label | What it does | Where it is used |
|---|---|---|
| `group` | Owning group or team, for example `noc` or `group-a` | Catalogue column and filters; alert use depends on the active rules |
| `service` | Service name, for example `grafana`, `wiki` or `ssh` | Catalogue column; alert use depends on the active rules |
| `host` | Stable machine identity for this service | Catalogue column; keep identical values across checks on one machine when active alert grouping/inhibition uses `host` |
| `owner` | Responsible team or person | Owner column |
| `contact` | Named person and contact channel | Contact person column |
| `dependencies` | Services or infrastructure this service requires | Dependencies column |
| `module` | Existing probe type: `http_2xx`, `tcp_connect` or `icmp` | Selects the Blackbox probe; not part of the service identity |

This guide's dependency notation is `group/service@host`; it is a readable-text convention, not built-in Grafana dependency resolution. For infrastructure that is not monitored, use `external:<name>`. Separate several values with `; `, for example `external:docker; noc/prometheus@noc-core`. Use `none` only when you have confirmed that there are no dependencies to record. Record `noc/prometheus@noc-core` for Grafana only if it is the dependency you intend to describe (for example this dashboard's data source); Grafana's own process/database health does not inherently depend on Prometheus.

Why: a contact and dependency list tells the person reading the dashboard whom to call and what else to check. These labels document relationships; they do not automatically change alert routing or mute alerts.

Save a copy before editing the configuration:

```bash
CATALOGUE_BACKUP="/opt/monitoring-catalogue-backup-$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$CATALOGUE_BACKUP"
cp -a prometheus "$CATALOGUE_BACKUP/"
```

For a first target file:

```bash
nano prometheus/targets/noc.yml
```

Replace the placeholders below before saving:

```yaml
- targets:
    - http://prometheus:9090/-/ready
  labels:
    module: http_2xx
    group: noc
    service: prometheus
    host: noc-core
    owner: '<owner>'
    contact: '<contact-person> (<contact-address>)'
    dependencies: 'external:docker'

- targets:
    - http://grafana:3000/api/health
  labels:
    module: http_2xx
    group: noc
    service: grafana
    host: noc-core
    owner: '<owner>'
    contact: '<contact-person> (<contact-address>)'
    dependencies: 'external:docker; noc/prometheus@noc-core'
```

If you already followed setup.md, its `noc.yml` puts both endpoints in one `noc-selftest` block. Replace that block with the two above. They are separate services and should become separate catalogue rows. If the self-checks are already in another target file, update that file instead of adding duplicate probes.

Keep `noc` and `noc-core` consistent with the existing internal target labels. The URLs use Compose service names because Blackbox probes them over the Docker network. Your browser still uses the LXC IP. These names resolve when the containers share the relevant [Compose network](https://docs.docker.com/compose/how-tos/networking/).

The Prometheus example uses `/-/ready`: it returns success when Prometheus can serve queries. `/-/healthy`, used in the supporting setup example, is a liveness endpoint that always returns HTTP 200 while the server can answer it; it does not test readiness. Choose the endpoint matching your check's purpose. Grafana's `/api/health` checks the Grafana API/database health response; it does not test every configured data source. See [Prometheus management endpoints](https://prometheus.io/docs/prometheus/latest/management_api/) and [Grafana health API](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/other/#health-api).

Real target files are ignored by Git, as explained in [adding-targets.md](../../docs/adding-targets.md). Leave the tracked `template.yml` as a template. The target/config files and their parent directories must be readable/traversable by the Prometheus process inside its container; a root-only target file can silently prevent discovery. Keep credentials out of these catalogue labels.

**Check:** in Grafana *Explore* or the Prometheus query box, run:

```promql
probe_success{group="noc", service=~"prometheus|grafana"}
```

After discovery and a few scrape cycles, both targets should return `1` when their selected health endpoints pass. Expand a result and check that the owner, contact and dependencies are present. Target-file edits need no Prometheus restart with the active file-discovery job verified above. Keep credentials out of endpoint URLs and label values: labels are stored with metrics and displayed in the catalogue.

---

## 3. Add the school services

Use one file per group, as in [adding-targets.md](../../docs/adding-targets.md#how-to-organise-the-files):

```bash
cp prometheus/targets/template.yml prometheus/targets/group-a.yml
nano prometheus/targets/group-a.yml
```

Only copy the template when creating a new file. Edit an existing file directly so its targets are preserved. Replace the commented examples with populated blocks. Each service needs its real endpoint and all six catalogue labels.

### Web service

```yaml
- targets:
    - http://<school-host>:8080/health
  labels:
    module: http_2xx
    group: group-a
    service: wiki
    host: '<school-host>'
    owner: '<owner>'
    contact: '<contact-person> (<contact-address>)'
    dependencies: '<dependencies>'
```

Use the service's actual port and path. For HTTPS, use `https://` and the correct hostname. Prefer a health endpoint when the service has one.

### TCP service

```yaml
- targets:
    - '<school-host>:22'
  labels:
    module: tcp_connect
    group: group-a
    service: ssh
    host: '<school-host>'
    owner: '<owner>'
    contact: '<contact-person> (<contact-address>)'
    dependencies: '<dependencies>'
```

With the basic `tcp_connect` recipe shown in the supporting reference, this proves that the TCP port accepts a connection. It does not test a login or the whole application protocol. HTTP recipes can also follow redirects; a 2xx login page can pass a simple HTTP probe, so verify what the final response actually checks. See [Blackbox module settings](https://github.com/prometheus/blackbox_exporter/blob/master/CONFIGURATION.md).

### Agreed application-content checks

The basic http_2xx module is sufficient for HTTP reachability. It does not require a new module for Grafana unless the agreed check also validates its response body. A login page returning HTTP 200 can pass a reachability probe while useful application functions are broken.

The tracked Blackbox configuration includes http_grafana_health, which checks HTTP 200 and a body matching "database": "ok". Use it only when it is present in the running exporter and this is the intended Grafana health contract. The homelab used http_2xx for its baseline Grafana check after encountering a missing custom module. A recipe being present in Git does not prove it is loaded on the destination machine.

For another service, agree its health response with the owner and reuse a matching module or add a dedicated HTTP recipe. For example, an application whose documented healthy response includes "status": "ok" could use:

```yaml
  http_app_health:
    prober: http
    timeout: 5s
    http:
      valid_status_codes: [200]
      fail_if_body_not_matches_regexp:
        - '"status":\s*"ok"'
```

Add that recipe under the existing modules mapping, preserve other recipes, and point only the matching application target at it. A response-content check is not a complete synthetic user transaction. Validate the live configuration before applying a module change:

```bash
docker compose exec blackbox blackbox_exporter --config.check --config.file=/etc/blackbox/blackbox.yml
```

Only after validation succeeds, apply the change using the [existing operations procedure](../../docs/operations-and-troubleshooting.md#how-to-apply-a-change). Target-file-only changes need no restart. The [HTTPS test and IPv4 routing fix](../../docs/adding-targets.md#temporary-public-https-test) remain in the target guide; do not disable TLS verification just to work around a routing fault.

### Host with ICMP

```yaml
- targets:
    - '<school-host>'
  labels:
    module: icmp
    group: group-a
    service: ping
    host: '<school-host>'
    owner: '<owner>'
    contact: '<contact-person> (<contact-address>)'
    dependencies: '<dependencies>'
```

> **Only add ICMP for hosts that reliably answer ping and have a configured ICMP module.** If the loaded Alertmanager configuration includes ICMP/HTTP inhibition, it can suppress HTTP ServiceDown alerts while the same host's ICMP ServiceDown alert is firing. Check the active rule and ping result before relying on it. See [multiple checks for one machine](../../docs/adding-targets.md#several-checks-for-one-machine).

That inhibition behavior is described by the supplied reference; it depends on the Alertmanager configuration actually loaded. ICMP also needs appropriate privileges in the exporter environment. On Linux this can be an allowed ping group, `CAP_NET_RAW` or root; nested LXC/container restrictions can still prevent probing. Confirm an ICMP result of `1` before using it for inhibition. See [Blackbox ICMP permissions](https://github.com/prometheus/blackbox_exporter#permissions).

Probes run from Blackbox, so the endpoints must be reachable from the monitoring LXC. `localhost` in a probe target means Blackbox itself.

**Check:**

```promql
probe_success{group="group-a"}
```

Every configured probe should appear with its labels. `1` means the destination check passed; `0` means it failed. Confirm that every service on the intended school-service list has a target, not just that the targets you added work.

---

## 4. Label the existing internal scrape targets

The `prometheus` and `node` jobs are also monitored targets. They need catalogue labels, otherwise the dashboard's completeness check reports them as unfinished.

```bash
nano prometheus/prometheus.yml
```

Update these two existing entries under `scrape_configs`. Keep the rest of the file, including the `blackbox` job. Replace the owner/contact placeholders, using exactly the same values as the corresponding service probes. Put these labels in the targets' `labels` blocks; `global.external_labels` are for communication with external systems and do not populate the local `up` series used by this dashboard.

Apply the examples below as label updates to your existing `static_configs` entries. Preserve additional host targets and the `node` job's `metric_relabel_configs` from the current template: that block drops shared Proxmox hardware and ZFS metrics from `noc-core` when it runs in an LXC. Replacing the entire job with the shorter example would lose that filtering.

```yaml
  - job_name: prometheus
    static_configs:
      - targets:
          - localhost:9090
        labels:
          group: noc
          service: prometheus
          host: noc-core
          owner: '<owner>'
          contact: '<contact-person> (<contact-address>)'
          dependencies: 'external:docker'

  - job_name: node
    static_configs:
      - targets: ['node-exporter:9100']
        labels:
          group: noc
          service: node-exporter
          host: noc-core
          owner: '<owner>'
          contact: '<contact-person> (<contact-address>)'
          dependencies: 'external:docker'
```

Why: the dashboard uses all `up` series so an unlabeled internal job is not silently omitted. The Prometheus self-scrape and its health probe share one service identity and become one row with two checks.

`localhost:9090` is correct for Prometheus's self-scrape: that request runs inside Prometheus. It is different from a destination probed by Blackbox.

For another host's Node Exporter, add the same catalogue labels to its static target block too. Keep its `host` value equal to that host's probes, as described in [how-to-guides.md](../../docs/how-to-guides.md#add-node_exporter-for-another-host).

### Optional drive-health exporter

If you enabled the Prometheus template's optional `smartctl` job, add all six catalogue labels to each of its existing static target entries as well. Its `up` series is included in the same dashboard completeness check. Keep the exporter address and its existing `host` and `group` values, and add the missing fields:

```yaml
  - job_name: smartctl
    static_configs:
      - targets: ['<school-host>:9633']
        labels:
          group: noc
          service: smartctl-exporter
          host: '<school-host>'
          owner: '<owner>'
          contact: '<contact-person> (<contact-address>)'
          dependencies: 'external:docker'
```

Replace the placeholders and set dependencies to match how the exporter is actually installed. Use the same `host` label as that machine's Node Exporter so the drive and host alerts stay aligned. Update an enabled job rather than creating a duplicate; leave the optional job commented out if you are not collecting drive health. The installation steps are in [how-to-guides.md](../../docs/how-to-guides.md#add-smartctl_exporter-for-drive-health).

### Existing Proxmox API scrape or any other job

If `job="pve"` is enabled, its scrape is also included in this catalogue. Add the missing labels to the **existing** `static_configs` target blocks of that job. Preserve its `metrics_path: /pve`, parameters and relabeling to `pve-exporter:9221`; a plain scrape of a Proxmox host is not a substitute. For example, the label portion can be:

```yaml
        labels:
          group: noc
          service: pve-exporter
          host: '<existing-proxmox-host-label>'
          owner: '<owner>'
          contact: '<contact-person> (<contact-address>)'
          dependencies: 'external:docker; external:proxmox-api'
```

Keep the actual `group` and `host` values already used by that job, and replace the other placeholders. This row describes the API collection check, not one row for every VM/LXC returned by the exporter. No new exporter or second `pve` job is needed just to add catalogue metadata. The supporting [Proxmox exporter guide](../../docs/how-to-guides.md#monitor-proxmox-guests-with-pve-exporter) describes its existing integration; Smith guest resource data is handled separately in [smith-resource-metrics.md](smith-resource-metrics.md).

Apply all six catalogue labels to every other enabled scrape job too, including any direct scrape of an exporter's own `/metrics` endpoint. The dashboard intentionally uses all current `up` series; adding a new integration can therefore reveal incomplete metadata.

**Check:**

```bash
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
```

You should see `SUCCESS`. If validation fails, fix the reported YAML/configuration error before continuing.

---

## 5. Apply the main configuration change

Target files are discovered automatically. The internal labels are in `prometheus.yml`, which needs to be loaded again:

```bash
docker compose kill -s SIGHUP prometheus
docker compose logs --since 2m prometheus
```

`SIGHUP` reloads the configuration and configured rule files without restarting the container. It does not need `--web.enable-lifecycle`; that flag is required for the HTTP reload endpoint. This also applies to later rule changes even if a supporting guide describes restarting. See [Prometheus configuration reloads](https://prometheus.io/docs/prometheus/latest/configuration/configuration/). A restart is another option after validation.

**Check:** after a few 30-second scrape cycles, in grafana (in the explore tab), query:

```promql
up
```

Every target should now carry `group`, `service`, `host`, `owner`, `contact` and `dependencies`. Check the logs and *Status → Target health* for discovery errors too; main-config validation alone does not prove every target file loaded. Check `prometheus_config_last_reload_successful` is `1` and `prometheus_config_last_reload_success_timestamp_seconds` advanced after your command; the signal command itself does not prove the new configuration was accepted. These metrics are defined in the [Prometheus server source](https://github.com/prometheus/prometheus/blob/main/cmd/prometheus/main.go).

---

## 6. Open Grafana and select the Prometheus data source

1. Open `http://<noc-core-ip>:3000` and sign in.
2. Go to *Connections → Data sources* and select the Prometheus source created during setup.
3. Its URL is `http://prometheus:9090`. If it has not been created on this fresh installation, choose *Add data source → Prometheus* and set that URL.
4. Click **Save & test**.
5. Open *Explore*, select that source and query `up`.

Why the service name: Grafana reaches Prometheus over the Docker network. `localhost:9090` would point to Grafana's own container.

**Check:** Explore returns the target series and the labels from steps 2–4. Keep this source; you do not need a second one for the catalogue.

---

## 7. Create or reuse the catalogue dashboard

If you do not have a catalogue dashboard yet, start with [service-catalogue-dashboard.md](service-catalogue-dashboard.md#1-choose-how-to-create-the-dashboard). It explains how to create the dashboard definition before importing it. The ready-made definition is in [dashboard-template.json](../dashboard-template.json), a separate file you can copy and edit.

Follow this sequence in the dashboard guide:

1. On your local computer, copy `dashboard-template.json` to your own `service-catalogue-dashboard.json` file. This JSON file does not need to be on the LXC.
2. Replace the dashboard title, description and environment-tag placeholders using the code excerpts and explanations in the guide. The panel queries and data-source mapping are already configured.
3. Upload the finished local file through Grafana's web interface and select the existing Prometheus source. **Import creates the dashboard in Grafana.**
4. Keep the time range ending at **now** and save any dashboard changes.

The same guide also explains how to create the panels manually in Grafana and export an existing dashboard for another LXC. If the catalogue already exists on this instance, open it and verify the panels below.

**Check:** the dashboard opens with four full-width panels, from top to bottom. The template includes the status query, column headings and coloured mappings; no manual formatting is needed:

| Panel | What it shows | Expected result |
|---|---|---|
| Current service probe status | Group, service, host, check, target, owner, contact, dependencies and Up/Down/Unknown status | One row per configured destination probe; healthy checks are green |
| Every monitored service | Group, service, host, owner, contact person, dependencies and check count | One row per service instance |
| Services with incomplete catalogue metadata | Number of service instances with at least one incomplete check | `0` after the labels are complete |
| Services missing catalogue metadata | Affected service instances and their incomplete-check counts | One row per affected service; empty when the counter is 0 |

With only the two NOC probes and the two original internal scrapes, the status table shows two probe rows. The inventory table should show three service rows: `prometheus` with 2 checks, `grafana` with 1, and `node-exporter` with 1. School targets add their own rows. The missing-metadata counter counts each affected `(group, service, host)` once, and its value matches the number of rows in the bottom table. An empty bottom table is expected when all labels are complete.

---

## 8. Check what the catalogue query means

The service table uses:

```promql
count by (group, service, host, owner, contact, dependencies) (up)
```

| Part | What it does | Why |
|---|---|---|
| `up` | One series per scrape target, including a failing scrape with value 0 | Failing checks stay in the inventory while Prometheus keeps scraping them. |
| `count by (...)` | Counts checks that share all six labels | Several checks of the same service become one row when their metadata agrees. |
| Checks column | The resulting count | It counts current `up` series, including failures; it does not count healthy checks or services absent from discovery. |

`up` is generated for each scrape target; see [Prometheus jobs and instances](https://prometheus.io/docs/concepts/jobs_instances/). A newly discovered target may not appear until its first scrape. Removed targets leave current results after discovery/staleness processing. A row is not proof that a service has been configured in every intended environment.

For destination health, use `probe_success`, as explained in [up vs probe_success](../../docs/adding-targets.md#up-vs-probe_success). A blackbox check can have `up=1` and `probe_success=0`.

If you build or adjust the table manually, use these [query options](https://grafana.com/docs/grafana/latest/datasources/prometheus/query-editor/):

| Setting | Value | Why |
|---|---|---|
| Visualisation | Table | Displays the labels as columns |
| Query format | Table | Returns tabular results |
| Query type | Instant | One current result per series, not one row per scrape time |
| Transformation | Organize fields by name | Hide Time, rename fields and put the columns in order |
| Columns | Group, Service, Host, Owner, Contact person, Dependencies, Checks | The required catalogue information |
| Refresh | 30s | Matches the scrape interval |

The template applies these settings. If your Grafana generates a different numeric field name, rename that field to **Checks**.

**Check:** after all identity labels are complete and metadata agrees, the table has one row per `(group, service, host)`. Until then it has one row per distinct combination of all six labels, so conflicting metadata can split a service into multiple rows. Contact and dependency text is readable, and changing the range while keeping its end at now does not produce a row for every scrape. An Instant query evaluates at the selected range's end; an end in the past shows the catalogue at that time.

---

## 9. Verify completeness, consistency and persistence

### Missing labels

In Explore, run:

```promql
up{group=""} or up{service=""} or up{host=""}
or up{owner=""} or up{contact=""} or up{dependencies=""}
```

**Check:** no results. An empty matcher also finds a label that is absent, as specified in [Prometheus label matching](https://prometheus.io/docs/prometheus/latest/querying/basics/#instant-vector-selectors). Review the text manually too: whitespace, placeholders such as `<owner>` and incorrect dependency/contact values are present labels but unfinished entries.

Fix missing `group`, `service` or `host` before interpreting the counter as a number of services. Without complete identity labels, unrelated checks can collapse into the same partial/blank tuple. The red counter still flags incomplete metadata, but it can undercount the real affected services. Inspect individual `job`, `instance` and `module` labels in Explore to identify each unfinished check. The bottom table and counter agree on tuples; that agreement alone does not prove identity completeness.

### Conflicting metadata

```promql
count by (group, service, host) (
  count by (group, service, host, owner, contact, dependencies) (up)
) > 1
```

**Check:** no results. A returned service has different metadata on its checks. Correct its labels instead of hiding one row in Grafana.

### Coverage

Compare the intended school-service list with *Status → Target health* and the catalogue. The **Checks** values in the **Every monitored service** inventory table should add up to the number of series returned by:

```promql
count(up)
```

**Check:** every intended service has a configured check and a catalogue row. A missing-metadata query cannot find a service you never added to monitoring.

### Failure behaviour (optional)

Use an existing failed target, or switch off a home-test service you control and restore it afterwards. The existing alerts may send emails, so coordinate this test with your partner.

**Check:** its catalogue row stays visible when `probe_success` becomes 0. If the exporter cannot be scraped, an `up=0` series still contributes to the inventory. A Prometheus outage produces an error or no current data; that is not a successful empty catalogue.

### Saved dashboard

Save the dashboard, [export its JSON](service-catalogue-dashboard.md#5-export-a-dashboard-you-already-created), then test a restart during a home-test window:

```bash
docker compose restart grafana
```

**Check:** after Grafana starts, the saved dashboard is still available. In the supplied Compose configuration, `grafana_data` is mounted at `/var/lib/grafana`; that persistent storage retains Grafana's database, including saved dashboards and data sources. Verify the mount in your actual configuration. Another database/storage arrangement must preserve its own data instead. See [Grafana Docker persistent storage](https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/). Keep the JSON export and screenshots as project evidence.

Record the actual check results with the evidence:

| Check | Actual result | Evidence |
|---|---|---|
| Probe results | To fill in | Explore result |
| Catalogue fields and coverage | To fill in | Filled table screenshot |
| Missing/conflicting metadata | To fill in | Query results |
| Failed target remains listed | To fill in, if tested | Before/after screenshots |
| Saved dashboard survives restart | To fill in | Dashboard URL and result |

---

## Day-to-day changes

| Task | What to change | How to apply it |
|---|---|---|
| Add a service | Add a complete block in `prometheus/targets/<group>.yml` | No restart; file_sd discovers it |
| Change owner, contact or dependencies | Change the labels on every check for that service | Target files: automatic. Static jobs in `prometheus.yml`: validate and reload. |
| Add a second check for a service | Keep all six catalogue labels identical; change endpoint/module as needed | Automatic discovery; the Checks count increases |
| Remove a check | Delete its block | Automatic discovery; use `[]` if the file should remain with no targets |
| Change table layout | Edit the Grafana panel and save the dashboard | Immediate in the UI |
| Reuse the dashboard | Export/import its JSON and choose the destination source | No container restart |

Changes to metadata create new time series, because labels are part of a series' identity. Keep values short and stable. Removing a target removes it from the current catalogue after discovery/staleness processing; this dashboard is not an archive of retired services. See [Prometheus staleness](https://prometheus.io/docs/prometheus/latest/querying/basics/#staleness).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| New service does not appear | File does not match `targets/*.yml`, YAML is invalid, or discovery has not completed | Check filename and logs: `docker compose logs --since 5m prometheus`. Verify the active target list. |
| Probe is listed but fails | Wrong endpoint/module, destination issue or network access | Check `probe_success` and follow [adding-targets.md](../../docs/adding-targets.md#after-saving). |
| Missing-metadata count is greater than 0 | At least one probe/static target lacks a required label | Run the missing-label query from step 9 and complete that target's labels. |
| Same service appears twice | Owner/contact/dependencies differ between its checks | Run the conflict query and align all six labels. |
| Lots of rows for the same check | Query is Range or Both instead of Instant | Set Type to Instant and Format to Table. |
| Checks is 2 for Prometheus | It has a self-scrape and a health probe | Expected; both belong to one service row. |
| Static labels still show the old values | Main configuration was not loaded again | Validate and send SIGHUP as in step 5. |
| No data or a query error | Wrong source, Prometheus unavailable, or no current matching series | Query `up` in Explore and check the source/container. Do not treat this as a successful zero. |
| Dashboard/source missing on another LXC | It has a fresh Grafana volume | Create/select the source and import the saved template/export. |

To undo a main-config edit, restore the saved file, validate it, then reload. With `CATALOGUE_BACKUP` still set to the path from step 2:

```bash
cp -a "$CATALOGUE_BACKUP/prometheus/prometheus.yml" prometheus/prometheus.yml
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose kill -s SIGHUP prometheus
```

Only run the reload after validation succeeds. Restore specific edited target files from the same backup if needed; move a newly added target file outside `prometheus/targets/` to undo it. Preserve any later changes your partner made.

Next steps:

- [service-catalogue-dashboard.md](service-catalogue-dashboard.md): create, edit, export and import the dashboard
- [dashboard-template.json](../dashboard-template.json): ready-made dashboard definition to copy and customise
- [adding-targets.md](../../docs/adding-targets.md): probe formats, diagnosis and ICMP/HTTP inhibition
- [operations-and-troubleshooting.md](../../docs/operations-and-troubleshooting.md): stack operations and applying configuration changes
