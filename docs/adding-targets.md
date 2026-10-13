# Adding targets

A **target** is something the NOC probes from the outside: a URL, a TCP port or a host that answers ping. Probes run through the Blackbox Exporter, so the monitored machine needs no agent and we need no management rights on it.

Targets are **not** listed in `prometheus.yml`. They live in `prometheus/targets/*.yml` and Prometheus reads them through file-based service discovery (`file_sd`). You add a target by editing or creating a file. No restart needed.

## How to organise the files

All files that match `prometheus/targets/*.yml` are loaded. You can use:

- **one file per group** (for example `group-a.yml`, `noc.yml`). This is recommended, because it matches the `group` label and keeps ownership clear.
- **one file per target**, which can be handy in a small homelab.
- one big file with everything.

For a new target file, start from the template:

```bash
cd /opt/monitoring
cp prometheus/targets/template.yml prometheus/targets/group-a.yml
nano prometheus/targets/group-a.yml
```

Only copy the template when creating a new file. For existing targets, edit their current file; updating `template.yml` does not change files you copied earlier.

The active target files must be on the running LXC, under `/opt/monitoring/prometheus/targets/`. If you edit a local computer's copy, transfer the edited target file to that LXC. The dashboard JSON is different: it stays on your computer for upload through Grafana.

Don't add real targets to `template.yml` itself. It is tracked in Git and its blocks are commented out on purpose. All other files in `prometheus/targets/` are ignored by Git, because they contain internal addresses.

## The fields

Each file is a YAML list of **blocks**. One block holds one or more targets that share the same labels:

```yaml
- targets:
    - http://192.168.1.150:8080/health
  labels:
    module: http_2xx
    group: group-a
    service: wiki
    host: 192.168.1.150
    owner: '<owner>'
    contact: '<contact-person> (<contact-address>)'
    dependencies: '<dependencies>'
```

| Field | Required | What it does | Where it is used |
|---|---|---|---|
| `targets` | yes | What to probe. The format depends on the module: a full URL for `http_2xx`, `host:port` for `tcp_connect`, a bare host or IP for `icmp`. | Becomes the `instance` label (see the relabeling in [configuration-reference.md](configuration-reference.md#job-blackbox)). Shown in alert descriptions ("Probe ... to `<instance>`"). |
| `module` | yes | Which Blackbox module runs the probe. Must exist in `blackbox/blackbox.yml`: `http_2xx`, `tcp_connect` or `icmp`. | Passed to Blackbox as `?module=`. `ServiceSlow` only looks at `module="http_2xx"`. The inhibit rule uses it (`icmp` suppresses `http_2xx`). |
| `group` | yes (catalogue) | The owning group or team. | Shown in alert descriptions, so the receiver knows whom to contact. Useful for filtering in Grafana and silences. Not used for routing at the moment. |
| `service` | yes (catalogue) | Human-readable service name, such as `wiki`, `ssh` or `ping`. | Alert summary: "`<service>` on `<host>` is unreachable". |
| `host` | yes (catalogue) | The machine the service runs on. Use the **same value for every target on the same machine**. | Alertmanager groups emails by `alertname` and `host`. The inhibit rule matches on `host`. The email subject shows it. |
| `owner` | yes (catalogue) | Person or team responsible for the service. | Owner column in the service catalogue. |
| `contact` | yes (catalogue) | Named contact person and an agreed contact channel, for example a school email address. | Contact person column in the service catalogue. |
| `dependencies` | yes (catalogue) | Services or infrastructure this service needs. | Dependencies column in the service catalogue. |
| `instance` | do not set | Set automatically to the target address by relabeling. | Identifies the individual probe in alerts, `up` and `probe_success`. |

Replace `<owner>`, `<contact-person>`, `<contact-address>` and `<dependencies>` in every example before saving. The six catalogue labels (`group`, `service`, `host`, `owner`, `contact`, `dependencies`) are required by this project's dashboard; Prometheus itself can scrape a target without them.

Use consistent lowercase IDs for `group`, `service` and `host`, with dashes where appropriate (for example `group-a`). Owner and contact values can contain names, spaces and punctuation; quote these values as shown. A typo in `host` breaks grouping and inhibition without any error.

Write monitored dependencies as `group/service@host`, and unmonitored infrastructure as `external:<name>`. Separate several entries with `; `, for example `external:docker; noc/prometheus@noc-core`. Use `none` only when you have confirmed that there are no dependencies to record. Keep the dependency list as one quoted string, not a YAML list.

Checks for the same service instance must share all six catalogue labels so they become one row. These labels document ownership and dependencies; they do not automatically change alert routing or inhibition. See [service-catalogue.md](../grafana/docs/service-catalogue.md#2-add-the-first-targets-and-their-catalogue-labels) for the catalogue setup.

## Examples

### Web service (`http_2xx`)

Passes when the URL answers with a 2xx status within 5 s. Redirects are followed.

```yaml
- targets:
    - http://192.168.1.150:8080/
  labels:
    module: http_2xx
    group: group-a
    service: wiki
    host: 192.168.1.150
    owner: '<owner>'
    contact: '<contact-person> (<contact-address>)'
    dependencies: '<dependencies>'
```

Point it at a health endpoint if the service has one (for example `/health` or `/api/health`). That is a better signal than the start page.

### Host with ICMP (`icmp`)

Passes when the host answers ping. The target is a bare IP or hostname, without a scheme or port.

```yaml
- targets:
    - 192.168.1.144
  labels:
    module: icmp
    group: group-a
    service: ping
    host: 192.168.1.144
    owner: '<owner>'
    contact: '<contact-person> (<contact-address>)'
    dependencies: '<dependencies>'
```

If ping always fails while the host is up, the host or a firewall drops ICMP. **Don't add an ICMP target for that host**: it would fire permanently and, through the inhibit rule, mute that host's HTTP alerts. Use `tcp_connect` instead.

### TCP port (`tcp_connect`)

Passes when a TCP connection to `host:port` can be opened. Use it for services without HTTP, such as SSH, databases or mail.

```yaml
- targets:
    - 192.168.1.144:22
  labels:
    module: tcp_connect
    group: group-a
    service: ssh
    host: 192.168.1.144
    owner: '<owner>'
    contact: '<contact-person> (<contact-address>)'
    dependencies: '<dependencies>'
```

It only proves the port is open. It does not prove the service behind it works.

### HTTPS service

Use the same `http_2xx` module with an `https://` URL. The HTTP prober checks the TLS certificate by default: an expired certificate, an untrusted one or a hostname mismatch makes the probe fail (`probe_success 0`). The certificate expiry date is exported as `probe_ssl_earliest_cert_expiry`.

```yaml
- targets:
    - https://wiki.example.org/
  labels:
    module: http_2xx
    group: group-a
    service: wiki-https
    host: wiki.example.org
    owner: '<owner>'
    contact: '<contact-person> (<contact-address>)'
    dependencies: '<dependencies>'
```

To require exactly HTTP 200, or to make sure plain HTTP is never accepted, add a stricter module. See [configuration-reference.md](configuration-reference.md#adding-a-module).

## Combining ICMP and HTTP for one host

Probe the host with ICMP and the service with HTTP, and give both blocks **exactly the same `host` value**:

```yaml
- targets:
    - 192.168.1.150
  labels:
    module: icmp
    group: group-a
    service: ping
    host: 192.168.1.150
    owner: '<owner>'
    contact: '<contact-person> (<contact-address>)'
    dependencies: '<dependencies>'

- targets:
    - http://192.168.1.150:8080/
  labels:
    module: http_2xx
    group: group-a
    service: wiki
    host: 192.168.1.150
    owner: '<owner>'
    contact: '<contact-person> (<contact-address>)'
    dependencies: '<dependencies>'
```

Why this matters:

- **Diagnosis**: for a host that normally answers ping, ICMP down and HTTP down means the host or network is gone. ICMP up and HTTP down means the service failed on a running host.
- **Inhibition**: Alertmanager has an inhibit rule. While `ServiceDown` for the `icmp` probe is firing, it suppresses `ServiceDown` for `http_2xx` probes **with an equal `host` label**. You get one email that says "the host is down" instead of one per service. If the `host` values differ (for example `192.168.1.150` and `wiki-server`), the rule does not match and you get both emails.
  **Only combine them for hosts that reliably answer ping.** If ICMP is blocked, the ICMP alert fires permanently and mutes every HTTP outage on that host. Check that `probe_success{module="icmp"}` is `1` before you rely on it.
- **Grouping**: emails are grouped by `alertname` and `host`, so all `ServiceDown` alerts of one host land in the same email.

## After saving

Prometheus automatically discovers target-file changes; a restart is unnecessary. This stack checks the files every minute as a fallback to its file watch and scrapes every 30 seconds, so allow about 1–2 minutes for new samples. Only valid target groups are applied; a malformed file can leave the last valid version active. See [Prometheus file discovery](https://github.com/prometheus/prometheus/blob/main/docs/configuration/configuration.md#file_sd_config).

### 1. Check the file inside the running container

All commands below run inside the LXC. The examples use `group-a.yml`; replace that filename with the file containing your two targets.

```bash
cd /opt/monitoring
cat prometheus/targets/group-a.yml
docker compose exec prometheus cat /etc/prometheus/targets/group-a.yml
```

Why both copies: the first is the file you edited; the second is what the running Prometheus container can read through its mount.

**Check:** both outputs contain your updated labels. If the container's copy is different or missing, check which folder it mounts:

```bash
docker inspect --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}' "$(docker compose ps -q prometheus)"
```

The source mounted at `/etc/prometheus` should be `/opt/monitoring/prometheus`. A stack still running from another clone, such as `/root/monitoring`, reads that clone's files instead. Confirm the active stack location before editing further; do not start a second stack just to apply target labels.

### 2. Check that Prometheus loaded the labels

Open `http://<noc-core-ip>:9090`, go to *Status → Target health* and expand the relevant target in the `blackbox` job. Check its final labels for `owner`, `contact` and `dependencies`.

For the same check in the terminal:

```bash
curl -fsS 'http://localhost:9090/api/v1/targets?state=active'
```

Find your target in `data.activeTargets`. `discoveredLabels` shows what discovery read; `labels` shows the result after relabeling. `__meta_filepath` identifies the source target file in the discovered labels. See the [targets API](https://prometheus.io/docs/prometheus/latest/querying/api/#targets) and [file-discovery format](https://github.com/prometheus/prometheus/blob/main/docs/configuration/configuration.md#file_sd_config).

**Check:** the final `labels` object contains your three new values. If it does not, check for discovery or YAML errors:

```bash
docker compose logs --since 5m prometheus
```

Check the reported filename, indentation, and that every label value is text. A config-validation success alone does not prove the target file was discovered correctly.

### 3. Check a current `up` result

In Prometheus's query page, run the following as a current table query:

```promql
up{job="blackbox"}
```

You can narrow it to one service, replacing `wiki` with your own service label:

```promql
up{job="blackbox", service="wiki"}
```

For a current query from the LXC terminal:

```bash
curl -fsSG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=up{job="blackbox"}'
```

**Check:** find each changed target in `data.result`; its `metric` object contains the labels. The [instant-query API](https://prometheus.io/docs/prometheus/latest/querying/api/#instant-queries) uses the current time when no `time` is supplied.

To find Blackbox checks still missing one of the three values:

```promql
up{job="blackbox", owner=""}
or up{job="blackbox", contact=""}
or up{job="blackbox", dependencies=""}
```

**Check:** no results once all Blackbox targets have complete metadata and the old series have gone stale. An empty matcher also finds an absent label.

Adding labels creates new time series; it does not rewrite earlier samples. A range query can still show the old series before the change. Old series disappear from current queries after staleness processing. See the [Prometheus data model](https://prometheus.io/docs/concepts/data_model/#metric-names-and-labels) and [staleness behaviour](https://prometheus.io/docs/prometheus/latest/querying/basics/#staleness).

A plain `up` also includes the `prometheus` and `node` jobs. Editing a Blackbox target file does not label those static targets. Follow [the internal-target step](../grafana/docs/service-catalogue.md#4-label-the-existing-internal-scrape-targets) for them; that main-configuration edit needs validation and a reload as described in [step 5](../grafana/docs/service-catalogue.md#5-apply-the-main-configuration-change).

### 4. Refresh Grafana and the catalogue

Once the current Prometheus result contains the labels:

1. In Grafana *Explore*, select the source whose URL is `http://prometheus:9090`.
2. Set the time range to end at **now**, use query type **Instant**, and run `up{job="blackbox"}`.
3. Inspect the table/raw data for each target. If using a time-series legend, choose **Verbose**: **Auto** can hide labels shared by all returned series. See [Grafana's query options](https://grafana.com/docs/grafana/latest/datasources/prometheus/query-editor/).
4. Open the catalogue dashboard and click **Refresh**, with its time range ending at **now**.

**Check:** the catalogue displays the new owner, contact and dependency values. Target-label changes are read through Prometheus; no Grafana restart or dashboard re-import is needed.

If Explore has the labels but the catalogue columns are missing, edit **Every monitored service**. Its query must include all six labels:

```promql
count by (group, service, host, owner, contact, dependencies) (up)
```

Use **Instant**, **Table** format and a Table visualisation. In **Organize fields by name**, make `owner`, `contact` and `dependencies` visible and name them **Owner**, **Contact person** and **Dependencies**. Save any panel changes. The [dashboard guide](../grafana/docs/service-catalogue-dashboard.md#4-create-the-dashboard-manually-in-grafana-alternative) explains the full panel settings.

### If labels still do not appear

| What you see | What to check next |
|---|---|
| LXC file has the labels; container file does not | The running container's mount points to another clone or directory. Check step 1. |
| Container file has the labels; active target does not | File-discovery/YAML errors, a filename outside `targets/*.yml`, or another target block/file still holding the old entry. Use logs and `__meta_filepath` to find the active source. |
| `discoveredLabels` has the labels; final `labels` does not | Main-config relabel rules are removing or replacing them. Check the active `blackbox` job's relabeling. |
| Active target has the labels; current `up` does not yet | Allow the next scrape, then query the exact job/instance at the current time. Check its `lastScrape` and `lastError`. |
| Prometheus has the labels; Grafana does not | Check the selected source, evaluation time and raw data. Shared labels can be hidden in an Auto legend. |
| Explore has the labels; dashboard does not | Check its query, Instant setting and column transformation in step 4. |
| Only `prometheus` or `node` lacks the labels | Update those static jobs in `prometheus.yml`, validate and reload using the catalogue guide. |

### Verify with `probe_success`

In Prometheus (or Grafana *Explore*), run:

```promql
probe_success{service="wiki"}
```

- `1`: the probe passes. The service is healthy from the NOC's point of view.
- `0`: the probe fails. If it stays `0` for 2 minutes, `ServiceDown` fires.

Useful extra queries:

```promql
probe_duration_seconds{service="wiki"}              # how long the probe took
probe_http_status_code{service="wiki"}              # HTTP status code (http probes only)
(probe_ssl_earliest_cert_expiry - time()) / 86400   # days until the certificate expires (https only)
```

To see why a probe fails, ask Blackbox directly with debug output. Blackbox has no published port, so run it from inside the Prometheus container:

```bash
docker compose exec prometheus wget -qO- \
  'http://blackbox:9115/probe?module=http_2xx&target=http://192.168.1.150:8080/&debug=true'
```

## `up` vs `probe_success`

These two are easy to mix up, and mixing them up hides real outages.

| Metric | What it means for a blackbox target | Example |
|---|---|---|
| `up` | Prometheus could scrape **the Blackbox Exporter** for this target. It says nothing about the service. | `up=1` while the website is down: Blackbox answered "I probed it and it failed". |
| `probe_success` | **The probed service** passed the check. | `probe_success=0`: the website is down, slow beyond the 5 s timeout, or returned a non-2xx status. |

So:

- Alert on `probe_success` for service health. `ServiceDown` does exactly that.
- `up == 0` on the `blackbox` or `node` job means the **monitoring** is broken: the exporter container is down or unreachable. In that case `probe_success` is missing entirely, so `ServiceDown` cannot fire. That is why `MonitoringCheckFailed` watches `up`.
