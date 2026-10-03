# Configuration reference

This page explains every config file in the repo: what each setting does and **why** it is set that way, so you can adjust it yourself. For step-by-step changes, see [how-to-guides.md](how-to-guides.md). For how to apply a change (restart or not), see [operations-and-troubleshooting.md](operations-and-troubleshooting.md#how-to-apply-a-change).

| File | Read by | In Git? |
|---|---|---|
| `compose.yaml` (from `compose-template.yaml`) | Docker Compose | Template only |
| `prometheus/prometheus.yml` | Prometheus | Yes |
| `prometheus/rules/alerts.yml` | Prometheus | Yes |
| `prometheus/targets/*.yml` | Prometheus (file_sd) | Template only |
| `blackbox/blackbox.yml` | Blackbox Exporter | Yes |
| `alertmanager/alertmanager.yml` (from `alertmanager/template.yml`) | Alertmanager | Template only (holds the SMTP password) |

---

## prometheus/prometheus.yml

```yaml
global:
  scrape_interval: 30s

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093
rule_files:
  - /etc/prometheus/rules/*.yml
scrape_configs:
  - job_name: prometheus   # details below
  - job_name: node         # details below
  - job_name: blackbox     # details below
```

### `global`

| Key | Value | Why |
|---|---|---|
| `scrape_interval` | `30s` | How often every target is scraped, and so how often each probe runs. 30 s is fast enough to detect an outage within a minute and light on the services we probe. Lower it for faster detection at the cost of more load and more stored data. |

Not set, so Prometheus defaults apply:

- `evaluation_interval: 1m`: alert rules are evaluated once per minute. A rule with `for: 2m` can therefore take up to about 3 minutes to fire.
- `scrape_timeout: 10s`: longer than the Blackbox module timeout (5 s), so a slow service shows up as `probe_success 0`, not as a failed scrape.

### `alerting`

Tells Prometheus where to send firing alerts. `alertmanager:9093` is the Compose service name and port on the internal Docker network. Prometheus only **evaluates** alerts. Grouping, routing, silences and email are Alertmanager's job.

Check: `http://<noc-core-ip>:9090/api/v1/alertmanagers` should list it under `activeAlertmanagers`.

### `rule_files`

`/etc/prometheus/rules/*.yml` loads every rule file in `prometheus/rules/`. That works because Compose mounts the whole `./prometheus` folder at `/etc/prometheus`. You can split rules over several files and they are all loaded. Rule files are only read at startup, so a change needs `docker compose restart prometheus`.

### `scrape_configs`

#### Job `prometheus`

```yaml
  - job_name: prometheus
    static_configs:
      - targets:
          - localhost:9090
```

Prometheus scrapes its own metrics. This gives you `up{job="prometheus"}` and internal metrics such as TSDB size. It has no `host` label and is not part of `MonitoringCheckFailed`. If Prometheus is down, nothing can alert on that anyway.

#### Job `node`

```yaml
  - job_name: node
    static_configs:
      - targets: ['node-exporter:9100']
        labels:
          host: noc-core
          group: noc
```

Scrapes node_exporter on noc-core over the Docker network (no published port). The `host` and `group` labels are added to every metric of this target, so disk alerts carry the same labels as probe alerts (`host: noc-core`). That keeps grouping and inhibition working across both. To add more hosts, see [how-to-guides.md](how-to-guides.md#add-node_exporter-for-another-host).

#### Job `blackbox`

```yaml
  # Probes: do not add targets here. Add them in targets/*.yml
  - job_name: blackbox
    metrics_path: /probe
    file_sd_configs:
      - files:
          - /etc/prometheus/targets/*.yml
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

The Blackbox Exporter works differently from a normal exporter. Prometheus does not scrape the service itself. It asks Blackbox to probe the service: `http://blackbox:9115/probe?target=<service>&module=<module>`. The relabeling builds that request from each entry in the target files.

| Line | What it does |
|---|---|
| `metrics_path: /probe` | Scrape the `/probe` endpoint of Blackbox instead of `/metrics`. |
| `file_sd_configs` / `files` | Read targets from every `*.yml` in `prometheus/targets/`. Each entry becomes a target whose `__address__` is the value under `targets:` and whose labels come from `labels:`. |
| `refresh_interval: 1m` | Re-read the files at least once per minute. Prometheus also watches the files for changes, so edits usually apply within seconds. You never need a restart for target changes. |
| `source_labels: [__address__]` → `target_label: __param_target` | Copy the target (for example `http://192.168.1.150:8080/`) into the URL parameter `?target=`. Labels that start with `__param_` become query parameters. |
| `source_labels: [module]` → `target_label: __param_module` | Copy the `module` label from the target file into `?module=`, so each target picks its own probe type. |
| `source_labels: [__param_target]` → `target_label: instance` | Set `instance` to the probed address. Without this, every probe would get `instance="blackbox:9115"` and you could not tell them apart. |
| `target_label: __address__`, `replacement: blackbox:9115` | Replace the address Prometheus actually connects to with the Blackbox Exporter. The original target is now only in the parameter. |

Labels without `__` (`module`, `group`, `service`, `host`) stay on every metric of that probe. Alerts and dashboards use them.

### Retention is not in this file

How long data is kept is set with **command-line flags** in `compose.yaml`, not in `prometheus.yml`:

```yaml
      - --storage.tsdb.retention.time=45d
      - --storage.tsdb.retention.size=10GB
```

Whichever limit is reached first wins. Changing flags requires `docker compose up -d`. See [compose.yaml](#composeyaml).

---

## blackbox/blackbox.yml

```yaml
modules:
  http_2xx:
    prober: http
    timeout: 5s

  tcp_connect:
    prober: tcp
    timeout: 5s

  icmp:
    prober: icmp
    timeout: 5s
```

A **module** is a named probe recipe. Targets choose one with their `module` label.

| Module | Prober | Passes when | Use for |
|---|---|---|---|
| `http_2xx` | `http` | The URL returns a 2xx status (redirects are followed) within 5 s. For `https://` URLs, the TLS certificate must also be valid. | Websites, APIs, health endpoints |
| `tcp_connect` | `tcp` | A TCP connection to `host:port` opens within 5 s | SSH, databases, any non-HTTP port |
| `icmp` | `icmp` | The host answers ping within 5 s | Is the host/network reachable at all |

`timeout: 5s` is also the boundary between **slow** and **down**. A probe that takes longer than 5 s fails (`probe_success 0` → `ServiceDown`). A probe that succeeds but takes over 1 s is slow (`ServiceSlow`). Keep the timeout below the Prometheus `scrape_timeout` (10 s).

All other settings use Blackbox defaults. For example, the HTTP prober does not skip TLS verification and prefers IPv6 when a hostname resolves to both IPv4 and IPv6.

### Adding a module

Add a module under `modules:`, then restart Blackbox (see [operations](operations-and-troubleshooting.md#how-to-apply-a-change)). Two examples (not in the repo yet):

**HTTPS check that requires exactly 200 and a valid certificate:**

```yaml
  https_200:
    prober: http
    timeout: 5s
    http:
      valid_status_codes: [200]      # only 200 counts (after redirects); e.g. 204 now fails
      fail_if_not_ssl: true          # fail if the final URL is plain HTTP
      preferred_ip_protocol: ip4     # avoid IPv6 surprises in a v4-only LAN
      tls_config:
        insecure_skip_verify: false  # the default, written out: an invalid certificate fails the probe
```

**TCP check with TLS** (for example LDAPS on 636 or IMAPS on 993). It checks that the port is open and the certificate is valid:

```yaml
  tcp_tls:
    prober: tcp
    timeout: 5s
    tcp:
      tls: true
      preferred_ip_protocol: ip4
```

Then use `module: https_200` or `module: tcp_tls` in a target file. Note that `ServiceSlow` only watches `module="http_2xx"`. If you want slowness alerts for a new HTTP module too, change its expression (see [how-to-guides.md](how-to-guides.md#change-an-alert-threshold-or-for-duration)).

Validate before restarting:

```bash
docker compose exec blackbox blackbox_exporter --config.check --config.file=/etc/blackbox/blackbox.yml
```

---

## prometheus/rules/alerts.yml

All rules are in one file, in three groups. Every alert has:

- `labels.severity`: what Alertmanager routes on (`critical` or `warning`).
- `annotations.summary` / `description`: the text in the email. `{{ $labels.x }}` inserts a label of the failing series, and `{{ $value }}` the value of the expression.
- `annotations.runbook`: short first steps, so no alert arrives without an action.

`for:` is how long the condition must stay true before the alert fires. Until then it is **Pending**. This filters out a single dropped probe. Rules are evaluated every minute (default `evaluation_interval`), so the real delay is `for` plus up to 1 minute.

| Alert | Group | Severity | `for` | Status |
|---|---|---|---|---|
| ServiceDown | availability | critical | 2m | Tested |
| ServiceSlow | availability | warning | 5m | Tested |
| DiskSpaceLow | capacity | warning | 10m | Tested |
| DiskWillFillSoon | capacity | warning | 30m | **Written, not tested** |
| MonitoringCheckFailed | monitoring-health | critical | 2m | Tested |

### ServiceDown

```yaml
expr: probe_success == 0
for: 2m
```

- **Detects:** a Blackbox probe that fails: no answer, a wrong status code, a connection refused, ping lost or more than 5 s.
- **In plain language:** "any probe that is currently failing".
- **Why 2m:** about four failed probes in a row (30 s interval). One lost packet does not page anyone.
- **What to change:** `for:` for faster or calmer alerting. To exclude a module, for example `probe_success{module!="icmp"} == 0`.

### ServiceSlow

```yaml
expr: probe_duration_seconds{module="http_2xx"} > 1 and on(instance, module) probe_success == 1
for: 5m
```

- **Detects:** an HTTP service that works but responds slowly.
- **In plain language:** "HTTP probes that took longer than 1 second **and** succeeded". `and on(instance, module)` pairs each duration with the success value of the same probe. Failed probes are dropped, so `ServiceSlow` and `ServiceDown` never fire for the same probe. The duration is on the left side on purpose: `$value` in the description is then the measured time and not `1`.
- **Why only `http_2xx`:** ICMP and TCP connect times are not a useful latency signal for users.
- **Why 5m:** short slowdowns are normal. Only sustained slowness is worth a warning.
- **What to change:** the `1` (seconds) is a placeholder. The real threshold should come from each group's SLI. If different services need different thresholds, copy the rule and filter by label, for example `{module="http_2xx", group="group-a"}`.

| Probe result | Meaning | Alert |
|---|---|---|
| `probe_success == 0` (failed or over 5 s) | Down | ServiceDown, critical, after 2 min |
| `probe_success == 1` and duration over 1 s | Slow | ServiceSlow, warning, after 5 min |

### DiskSpaceLow

```yaml
expr: |
  node_filesystem_avail_bytes{fstype=~"ext4|xfs|zfs|btrfs"}
    / node_filesystem_size_bytes{fstype=~"ext4|xfs|zfs|btrfs"} < 0.15
for: 10m
```

- **Detects:** a real filesystem with less than 15 % free space.
- **In plain language:** "available bytes divided by total size, per filesystem, is below 0.15". The `fstype` filter keeps Docker's overlay, tmpfs and other virtual mounts out, because they would cause noise.
- **Why 10m:** disks don't change in seconds. 10 minutes skips short spikes from temporary files.
- **What to change:** `0.15` for the threshold. Add a filesystem type to the regex if a host uses another one (both sides of the division). `$value | humanizePercentage` shows the free fraction as a percentage in the email.

### DiskWillFillSoon

```yaml
expr: |
  predict_linear(node_filesystem_avail_bytes{fstype=~"ext4|xfs|zfs|btrfs"}[6h], 24 * 3600) < 0
for: 30m
```

- **Detects:** a disk that will run out of space within 24 hours at the current growth rate.
- **In plain language:** "draw a straight line through the free space of the last 6 hours, extend it 24 hours (`24 * 3600` seconds) into the future: does it go below zero?".
- **Why 30m:** a forecast jumps around more than a measured value. Requiring it for 30 minutes avoids alerts on one big temporary file.
- **What to change:** `[6h]` is how much history the trend uses (longer means calmer but slower to react). `24 * 3600` is how far ahead it looks.
- **Status: written, not tested.** It needs hours of real disk growth to fire. Directly after a restart there is less than 6 h of data, and the forecast is less reliable.

### MonitoringCheckFailed

```yaml
expr: up{job=~"node|blackbox"} == 0
for: 2m
```

- **Detects:** Prometheus cannot scrape node_exporter or the Blackbox Exporter. The monitoring is blind: probe and disk metrics stop, so `ServiceDown` and `DiskSpaceLow` **cannot** fire.
- **In plain language:** "a scrape of the `node` or `blackbox` job failed". For `blackbox`, there is one `up` series per target. If the Blackbox container dies, it fires for every target.
- **Note:** `up{job="blackbox"} == 1` while the website is down is normal. See [up vs probe_success](adding-targets.md#up-vs-probe_success).
- **What to change:** add more jobs to the regex when you add exporters (for example `node|blackbox|proxmox`). For a remote node_exporter host, a powered-off host also triggers this alert. You can suppress that with an inhibit rule, see [how-to-guides.md](how-to-guides.md#add-or-change-an-inhibit-rule).

---

## alertmanager/alertmanager.yml (template)

The real file is created from `alertmanager/template.yml` and ignored by Git, because it holds the SMTP password. The order of top-level blocks (`route`, `global`, `receivers`, `inhibit_rules`) doesn't matter.

### `global`

```yaml
global:
  smtp_smarthost: 'smtp.example.com:587'
  smtp_from: 'noc-alerts@example.com'
  smtp_auth_username: 'your-smtp-user'
  smtp_auth_password: 'your-smtp-password'
```

| Key | Meaning |
|---|---|
| `smtp_smarthost` | Mail server and port. For Gmail: `smtp.gmail.com:587` (STARTTLS). |
| `smtp_from` | Sender address of alert emails. With Gmail, this must be the account itself (or an alias of it). |
| `smtp_auth_username` | SMTP login. With Gmail, the full address. |
| `smtp_auth_password` | SMTP password. With Gmail, an **app password**. Better: use `smtp_auth_password_file`, see [how-to-guides.md](how-to-guides.md#move-the-smtp-password-into-a-secret-file). |

Defaults that apply because they are not set: `smtp_require_tls: true` (it refuses to send if the connection can't be encrypted) and `resolve_timeout: 5m` (only used for alerts that come without an end time, such as ones added with `amtool alert add`).

### `route`: the routing tree

```yaml
route:
  receiver: default
  group_by: [alertname, host]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - severity="critical"
      receiver: email-critical
      continue: true
      group_wait: 30s
      group_interval: 5m
      repeat_interval: 1h
    - matchers:
        - severity="critical"
      receiver: email-escalation
      group_wait: 15m
      group_interval: 5m
      repeat_interval: 4h
    - matchers:
        - severity="warning"
      receiver: email-warning
      group_wait: 2m
      group_interval: 15m
      repeat_interval: 12h
```

The top-level `route` is the **root**. Every alert enters here and is checked against the child `routes:` **from top to bottom**. The first match wins and stops the search, unless that route has `continue: true`. An alert that matches no child route uses the root's receiver.

| Key | Meaning | Why this value |
|---|---|---|
| `receiver` | Where alerts go if no child route matches | `default` catches anything without a known severity (for example a test alert). |
| `group_by` | Alerts with the same values for these labels are bundled into one email | `[alertname, host]`: one email per problem type per machine. This prevents a notification storm when a host with five services goes down. Child routes inherit it. |
| `group_wait` | How long to wait after the first alert of a new group before sending, to collect related alerts | 30 s: fast, but long enough to bundle alerts that fire together. |
| `group_interval` | Minimum time before sending an update when a group changes (new alert added, alert resolved) | 5 m |
| `repeat_interval` | How often a still-firing group is re-sent unchanged | 4 h on the root, overridden per route |
| `routes` | Child routes | See below |
| `matchers` | Conditions on alert labels, for example `severity="critical"`. Supports `=`, `!=`, `=~`, `!~` | We route only on `severity`. |
| `continue` | `true` means that after this route matches, the next routes are also checked | Needed for escalation |

The three child routes:

| # | Matches | Receiver | `group_wait` | `group_interval` | `repeat_interval` | `continue` | Why |
|---|---|---|---|---|---|---|---|
| 1 | `severity="critical"` | `email-critical` | 30s | 5m | 1h | `true` | Critical needs attention fast and a reminder every hour. `continue` passes the alert on to route 2. |
| 2 | `severity="critical"` | `email-escalation` | 15m | 5m | 4h | – | Same alerts, separate group. The long `group_wait` means the first email only goes out if the alert is **still firing after 15 minutes**. If it resolved earlier, nothing is sent. |
| 3 | `severity="warning"` | `email-warning` | 2m | 15m | 12h | – | Warnings are not urgent. Wait longer to bundle them and remind only twice a day. |

Alertmanager has no "acknowledge" button. A **silence** acts as acknowledgement: if someone silences the alert within 15 minutes, the escalation never fires.

### `receivers`

```yaml
receivers:
  - name: email-critical
    email_configs:
      - to: 'you@example.com'
        send_resolved: true
        headers:
          Subject: '[CRITICAL] {{ .Status | toUpper }}: {{ .GroupLabels.alertname }} on {{ .GroupLabels.host }}'
```

| Key | Meaning |
|---|---|
| `name` | Referenced by `receiver:` in routes. Must be unique. |
| `email_configs` | List of email destinations. A receiver can have several. |
| `to` | Recipient. Several addresses go comma-separated in one string: `'a@example.org, b@example.org'`. |
| `send_resolved` | `true` also sends an email when the alert clears. All four receivers have it on, including escalation, so the escalated person knows when it's over. |
| `headers.Subject` | Custom subject. `{{ .Status | toUpper }}` becomes `FIRING` or `RESOLVED`. `.GroupLabels` are the `group_by` labels, so the subject reads, for example, `[CRITICAL] FIRING: ServiceDown on 192.168.1.150`. The prefix makes critical, warning and escalated mails easy to tell apart and filter, even in a single mailbox. |

| Receiver | Subject prefix | Used by |
|---|---|---|
| `default` | (Alertmanager default subject) | Alerts without `severity=critical/warning` |
| `email-critical` | `[CRITICAL]` | Route 1 |
| `email-escalation` | `[ESCALATED]` | Route 2 |
| `email-warning` | `[WARNING]` | Route 3 |

### `inhibit_rules`

```yaml
inhibit_rules:
  - source_matchers:
      - alertname="ServiceDown"
      - module="icmp"
    target_matchers:
      - alertname="ServiceDown"
      - module="http_2xx"
    equal: [host]
```

**Inhibition** mutes some alerts while another alert is firing. Muted alerts still show in Prometheus and in the Alertmanager UI (as inhibited), but no email is sent for them.

| Key | Meaning |
|---|---|
| `source_matchers` | The alert that does the muting: a failing ICMP probe. |
| `target_matchers` | The alerts that get muted: failing HTTP probes. |
| `equal` | Source and target must have the **same value** for these labels. `[host]` means that a ping failure on host A only mutes HTTP alerts of host A. |

Why: for a host that normally answers ping, a failing ping means the host or the network path is gone, so its web services are unreachable too. One email about the host is then more useful than one per service. This only works if the ICMP and HTTP targets have an identical `host` label. See [adding-targets.md](adding-targets.md#combining-icmp-and-http-for-one-host).

> **Only add an ICMP target for hosts that reliably answer ping.** If a host or firewall blocks ICMP, the ICMP alert fires permanently and this rule mutes every HTTP outage on that host, without any warning. Before you add the ICMP target, check that `probe_success{module="icmp"}` is `1`.

---

## compose.yaml

The repo tracks `compose-template.yaml`. Copy it to `compose.yaml` (ignored by Git) and replace `<your-host>`.

### Pinned versions

| Service | Image |
|---|---|
| prometheus | `prom/prometheus:v3.13.3` |
| grafana | `grafana/grafana:13.2.2` |
| blackbox | `prom/blackbox-exporter:v0.28.0` |
| alertmanager | `prom/alertmanager:v0.34.1` |
| node-exporter | `prom/node-exporter:v1.12.1` |

Why pinned, not `latest`: a rebuild or a new host gets exactly the versions that were tested. Upgrades become a deliberate change you can review and roll back. To upgrade, change the tag, read the release notes and run `docker compose pull && docker compose up -d`.

### Common settings

- `restart: unless-stopped`: containers come back after a crash or a reboot of the LXC, but not if you stopped them on purpose.
- Services reach each other by **service name** on the default Compose network (`prometheus`, `grafana`, `blackbox`, `alertmanager`, `node-exporter`). That's why configs use `blackbox:9115` and `alertmanager:9093` instead of IPs.

### prometheus

```yaml
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.path=/prometheus
      - --storage.tsdb.retention.time=45d
      - --storage.tsdb.retention.size=10GB
    volumes:
      - ./prometheus:/etc/prometheus:ro
      - prometheus_data:/prometheus
```

- `command` replaces the image's default arguments, so the config file and data path are listed explicitly.
- `retention.time=45d` / `retention.size=10GB`: keep 45 days of history, but never more than 10 GB. This fits the 30 GB disk.
- `./prometheus:/etc/prometheus:ro`: the **whole folder** is mounted, so `prometheus.yml`, `rules/` and `targets/` are all visible. `:ro` (read-only) means the container cannot change your config.
- `prometheus_data`: named volume for the time-series database. It survives `docker compose down` and image upgrades.
- Port `9090` is published for the UI and API.
- Not set: `--web.external-url` and `--web.enable-lifecycle`. Without the first, the "Source" links on alerts in Alertmanager point to the container's hostname. Without the second, config changes need a restart instead of a reload.

### grafana

```yaml
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
```

`grafana_data` holds users, the admin password, data sources and dashboards. Nothing is provisioned from files yet (planned), so this volume is the only copy of your dashboards.

### blackbox

```yaml
    command:
      - --config.file=/etc/blackbox/blackbox.yml
    volumes:
      - ./blackbox/blackbox.yml:/etc/blackbox/blackbox.yml:ro
```

No published port: only Prometheus needs to reach it, on `blackbox:9115`. Keeping it internal means nobody else on the LAN can use the NOC to probe arbitrary addresses. The service **must** be named `blackbox`, because `prometheus.yml` points to `blackbox:9115`.

### alertmanager

```yaml
    command:
      - --config.file=/etc/alertmanager/alertmanager.yml
      - --storage.path=/alertmanager
      - --web.external-url=http://<your-host>:9093
    volumes:
      - ./alertmanager:/etc/alertmanager:ro
      - alertmanager_data:/alertmanager
```

- `--storage.path` + `alertmanager_data`: stores silences and the notification log. A maintenance silence survives a restart, and Alertmanager remembers what it already sent, so a restart doesn't trigger duplicate emails.
- `--web.external-url`: the address you use in a browser. It is used for the "View in Alertmanager" link in emails and for links in the UI. Set `<your-host>` to the noc-core IP.
- The whole `./alertmanager` folder is mounted, so a secret file placed there (for example `smtp_password`) is visible at `/etc/alertmanager/`.
- Port `9093`: the web UI has **no login**. Keep it on the LAN.

### node-exporter

```yaml
    command:
      - --path.rootfs=/host
    pid: host
    volumes:
      - /:/host:ro,rslave
```

- `/:/host:ro,rslave` mounts the root filesystem of noc-core read-only at `/host`. `--path.rootfs=/host` tells node_exporter to report filesystems from there. That way disk metrics are about noc-core, not about the container. `rslave` makes mounts added later on the host visible too.
- `pid: host` lets it see the processes of noc-core, not just its own.
- Read-only and no published port: least privilege. Prometheus reaches it on `node-exporter:9100`.
- Inside an LXC, "host" means the **noc-core LXC**, not the Proxmox host. Memory figures may show the Proxmox host's values instead of the LXC limit. See [known limitations](operations-and-troubleshooting.md#troubleshooting).

### volumes

```yaml
volumes:
  prometheus_data:
  grafana_data:
  alertmanager_data:
```

Named volumes managed by Docker. They survive `docker compose down`. **`docker compose down -v` deletes them**, together with all metrics, dashboards and silences. Backup and restore is planned, not built.
