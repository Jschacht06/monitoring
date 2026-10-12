# Service catalogue in Grafana

This guide continues the clean installation in [setup.md](setup.md), adding a Grafana dashboard that lists every monitored service, its owner, dependencies and contact person. Each step ends with a check that tells you what you should see before you continue.

All commands run as root inside the Debian 13 LXC, from the stack folder:

```bash
cd /opt/monitoring
```

Use `/opt/monitoring` for both the clean home installation and the clean school installation. This is the same path used throughout the monitoring guides. Enable nesting as part of the base setup.

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

## 1. Prerequisites

On each clean Debian 13 LXC, first follow [setup.md](setup.md) through step 8. That installs the tools, clones the repo into `/opt/monitoring`, prepares the Compose and Alertmanager configuration, starts the stack and creates the Prometheus data source. Continue here after those checks pass. The catalogue guide assumes sufficient resources and does not repeat the server installation.

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

The five services should be `Up`. Grafana opens at `http://<noc-core-ip>:3000`.

---

## 2. Add the first targets and their catalogue labels

A catalogue entry starts with the labels on a monitored target. `group`, `service` and `host` identify it. Add three more labels: `owner`, `contact` and `dependencies`.

| Label | What it does | Where it is used |
|---|---|---|
| `group` | Owning group or team, for example `noc` or `group-a` | Catalogue column, filters and the existing alert descriptions |
| `service` | Service name, for example `grafana`, `wiki` or `ssh` | Catalogue column and the existing alert summaries |
| `host` | Machine the service runs on | Catalogue column, existing email grouping and inhibition. Use the same value for all checks on one machine. |
| `owner` | Responsible team or person | Owner column |
| `contact` | Named person and contact channel | Contact person column |
| `dependencies` | Services or infrastructure this service requires | Dependencies column |
| `module` | Existing probe type: `http_2xx`, `tcp_connect` or `icmp` | Selects the Blackbox probe; not part of the service identity |

Dependencies are written as `group/service@host`. For infrastructure that is not monitored, use `external:<name>`. Separate several values with `; `, for example `external:docker; noc/prometheus@noc-core`. Use `none` only when you have confirmed that there are no dependencies to record.

Why: a contact and dependency list tells the person reading the dashboard whom to call and what else to check. These labels document relationships; they do not automatically change alert routing or mute alerts.

Save a copy before editing the configuration:

```bash
CATALOGUE_BACKUP="/opt/monitoring-catalogue-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$CATALOGUE_BACKUP"
cp -a prometheus "$CATALOGUE_BACKUP/"
```

For a first target file:

```bash
nano prometheus/targets/noc.yml
```

Replace the placeholders below before saving:

```yaml
- targets:
    - http://prometheus:9090/-/healthy
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

Keep `noc` and `noc-core` consistent with the existing internal target labels. The URLs use Compose service names because Blackbox probes them over the Docker network. Your browser still uses the LXC IP.

Real target files are ignored by Git, as explained in [adding-targets.md](adding-targets.md). Leave the tracked `template.yml` as a template.

**Check:** in Grafana *Explore* or the Prometheus query box, run:

```promql
probe_success{group="noc", service=~"prometheus|grafana"}
```

After discovery and a few scrape cycles, both targets should return `1`. Expand a result and check that the owner, contact and dependencies are present. No restart is needed for target-file changes.

---

## 3. Add the school services

Use one file per group, as in [adding-targets.md](adding-targets.md#how-to-organise-the-files):

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

This proves that the TCP port accepts a connection. It does not test a login or the whole application protocol.

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

> **Only add ICMP for hosts that reliably answer ping.** The existing inhibit rule suppresses HTTP ServiceDown alerts while the same host's ICMP ServiceDown alert is firing. Check the ping result before relying on it. See [combining ICMP and HTTP](adding-targets.md#combining-icmp-and-http-for-one-host).

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

Update these two existing entries under `scrape_configs`. Keep the rest of the file, including the `blackbox` job. Replace the owner/contact placeholders, using exactly the same values as the corresponding service probes:

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

For another host's Node Exporter, add the same catalogue labels to its static target block too. Keep its `host` value equal to that host's probes, as described in [how-to-guides.md](how-to-guides.md#add-node_exporter-for-another-host).

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

Replace the placeholders and set dependencies to match how the exporter is actually installed. Use the same `host` label as that machine's Node Exporter so the drive and host alerts stay aligned. Update an enabled job rather than creating a duplicate; leave the optional job commented out if you are not collecting drive health. The installation steps are in [how-to-guides.md](how-to-guides.md#add-smartctl_exporter-for-drive-health).

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

`SIGHUP` reloads the configuration without restarting the container. It does not need `--web.enable-lifecycle`. The restart procedure in [operations-and-troubleshooting.md](operations-and-troubleshooting.md#how-to-apply-a-change) is also an option after validation.

**Check:** after a few 30-second scrape cycles, in grafana (in the explore tab), query:

```promql
up
```

Every target should now carry `group`, `service`, `host`, `owner`, `contact` and `dependencies`. Check the logs and *Status → Target health* for discovery errors too; main-config validation alone does not prove every target file loaded.

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

If you do not have a catalogue dashboard yet, start with [service-catalogue-dashboard.md](service-catalogue-dashboard.md#1-choose-how-to-create-the-dashboard). It explains how to create the dashboard definition before importing it. The ready-made definition is in [dashboard-template.json](dashboard-template.json), a separate file you can copy and edit.

Follow this sequence in the dashboard guide:

1. On your local computer, copy `dashboard-template.json` to your own `service-catalogue-dashboard.json` file. This JSON file does not need to be on the LXC.
2. Replace the dashboard title, description and environment-tag placeholders using the code excerpts and explanations in the guide. The panel queries and data-source mapping are already configured.
3. Upload the finished local file through Grafana's web interface and select the existing Prometheus source. **Import creates the dashboard in Grafana.**
4. Keep the time range ending at **now** and save any dashboard changes.

The same guide also explains how to create the panels manually in Grafana and export an existing dashboard for another LXC. If the catalogue already exists on this instance, open it and verify the panels below.

**Check:** the dashboard opens with three full-width panels, from top to bottom:

| Panel | What it shows | Expected result |
|---|---|---|
| Every monitored service | Group, service, host, owner, contact person, dependencies and check count | One row per service instance |
| Services with incomplete catalogue metadata | Number of service instances with at least one incomplete check | `0` after the labels are complete |
| Services missing catalogue metadata | Affected service instances and their incomplete-check counts | One row per affected service; empty when the counter is 0 |

With only the two NOC probes and the two original internal scrapes, you should see three service rows: `prometheus` with 2 checks, `grafana` with 1, and `node-exporter` with 1. School targets add their own rows. The missing-metadata counter counts each affected `(group, service, host)` once, and its value matches the number of rows in the bottom table. An empty bottom table is expected when all labels are complete.

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
| Checks column | The resulting count | It counts configured checks, not healthy checks. |

For destination health, use `probe_success`, as explained in [up vs probe_success](adding-targets.md#up-vs-probe_success). A blackbox check can have `up=1` and `probe_success=0`.

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

**Check:** the table has one row per `(group, service, host)`. Contact and dependency text is readable, and changing the time range does not produce a row for every scrape.

---

## 9. Verify completeness, consistency and persistence

### Missing labels

In Explore, run:

```promql
up{group=""} or up{service=""} or up{host=""}
or up{owner=""} or up{contact=""} or up{dependencies=""}
```

**Check:** no results. An empty matcher also finds a label that is absent. Review the text manually too: a placeholder such as `<owner>` is present, but is not a finished entry.

### Conflicting metadata

```promql
count by (group, service, host) (
  count by (group, service, host, owner, contact, dependencies) (up)
) > 1
```

**Check:** no results. A returned service has different metadata on its checks. Correct its labels instead of hiding one row in Grafana.

### Coverage

Compare the intended school-service list with *Status → Target health* and the catalogue. The **Checks** values in the top **Every monitored service** table should add up to the number of series returned by:

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

**Check:** after Grafana starts, the saved dashboard is still available. It is stored in `grafana_data`, together with the data source. Keep the JSON export and screenshots as project evidence.

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

Changes to metadata create new time series, because labels are part of a series' identity. Keep values short and stable. Removing a target removes it from the current catalogue after discovery/staleness processing; this dashboard is not an archive of retired services.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| New service does not appear | File does not match `targets/*.yml`, YAML is invalid, or discovery has not completed | Check filename and logs: `docker compose logs --since 5m prometheus`. Verify the active target list. |
| Probe is listed but fails | Wrong endpoint/module, destination issue or network access | Check `probe_success` and follow [adding-targets.md](adding-targets.md#after-saving). |
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
- [dashboard-template.json](dashboard-template.json): ready-made dashboard definition to copy and customise
- [adding-targets.md](adding-targets.md): probe formats, diagnosis and ICMP/HTTP inhibition
- [operations-and-troubleshooting.md](operations-and-troubleshooting.md): stack operations and applying configuration changes
