# Configuration reference

This page explains every config file in the repo: what each setting does and **why** it is set that way, so you can adjust it yourself. For step-by-step changes, see [how-to-guides.md](how-to-guides.md). For how to apply a change (restart or not), see [operations-and-troubleshooting.md](operations-and-troubleshooting.md#how-to-apply-a-change).

| File | Read by | In Git? |
|---|---|---|
| `compose.yaml` (from `compose-template.yaml`) | Docker Compose | Template only |
| `prometheus/prometheus.yml` (from `prometheus/template.yml`) | Prometheus | Template only (holds the IP addresses of your hosts) |
| `pve/pve.yml` (from `pve/template.yml`) | pve-exporter | Template only (holds the Proxmox API token secret) |
| `prometheus/rules/alerts.yml` | Prometheus | Yes |
| `prometheus/targets/*.yml` | Prometheus (file_sd) | Template only |
| `blackbox/blackbox.yml` | Blackbox Exporter | Yes |
| `alertmanager/alertmanager.yml` (from `alertmanager/template.yml`) | Alertmanager | Template only (holds the SMTP password) |

---

## prometheus/prometheus.yml (template)

The repo contains `prometheus/template.yml`. Copy it to `prometheus/prometheus.yml` and edit the copy. Your own file is ignored by Git, because adding hosts puts their IP addresses in it. Everything below describes the template and what you add to it.

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
  - job_name: smartctl     # optional, details below
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

```yaml
    metric_relabel_configs:
      - source_labels: [host, __name__]
        regex: 'noc-core;(node_hwmon_.*|node_zfs_.*|node_thermal_zone_.*)'
        action: drop
```

noc-core is an LXC and shares the Proxmox host's kernel, so its node_exporter also sees the host's ZFS pools and CPU/NVMe sensors. Without this block, one hardware problem would be reported twice (once as `host=noc-core`, once as the real host) and every such alert would arrive twice. The rule joins the `host` label and the metric name with a `;` and drops the hardware metrics only for `noc-core`. Disk and filesystem metrics of noc-core are untouched, because those are its own volumes. Remove the block if noc-core is not an LXC, and add a similar one for any other LXC you scrape.

#### Job `smartctl` (optional)

```yaml
  # - job_name: smartctl
  #   static_configs:
  #     - targets: ['<host-ip>:9633']
  #       labels:
  #         host: <host-ip>
  #         group: noc
```

Scrapes smartctl_exporter on a physical host, for drive health and drive temperature. It is commented out in the template because it needs a host with real drives. Use the same `host` value as the `node` job for the same machine: `DriveNotReadable` compares both exporters by `host`. Setup: [how-to-guides.md](how-to-guides.md#add-smartctl_exporter-for-drive-health).

#### Job `pve` (optional)

```yaml
  # - job_name: pve
  #   metrics_path: /pve
  #   params:
  #     module: [default]
  #     cluster: ['1']
  #     node: ['1']
  #   static_configs:
  #     - targets: ['<proxmox-ip>']
  #       labels:
  #         host: <proxmox-ip>
  #         group: noc
  #   relabel_configs:
  #     - source_labels: [__address__]
  #       target_label: __param_target
  #     - source_labels: [__param_target]
  #       target_label: instance
  #     - target_label: __address__
  #       replacement: pve-exporter:9221
```

Scrapes the Proxmox API through pve-exporter, for the status of every VM and LXC. It works like the `blackbox` job: the target is the Proxmox host, and the relabeling sends the scrape to `pve-exporter:9221` with the host as `?target=`. `module: [default]` selects the credentials block in `pve/pve.yml`, and `cluster` and `node` switch on the cluster and node collectors. Use the same `host` value as the `node` job, so alerts for the same machine are grouped together. Setup: [how-to-guides.md](how-to-guides.md#monitor-proxmox-guests-with-pve-exporter).

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

Add a module under `modules:`, then restart Blackbox (see [operations](operations-and-troubleshooting.md#how-to-apply-a-change)). Two examples (not in the repo yet, **untested**):

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

All rules are in one file, in seven groups. Every alert has:

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
| SmartStatusFailed | drives | critical | 2m | Tested (firing and resolved) |
| DriveNotReadable | drives | critical | 5m | Firing tested on a real faulted drive; resolved email not shown yet |
| DriveDisappeared | drives | critical | 5m | **Written, not tested** (only "returns no results" checked) |
| ZfsPoolNotOnline | storage | critical | 2m | Tested (firing and resolved) |
| HostTemperatureHigh | hardware | warning | 5m | Tested (firing and resolved) |
| HostTemperatureCritical | hardware | critical | 2m | Tested (firing and resolved) |
| NvmeTemperatureHigh | hardware | warning | 5m | Tested (firing and resolved) |
| DriveTemperatureHigh | hardware | warning | 5m | Tested (firing and resolved) |
| DriveTemperatureCritical | hardware | critical | 2m | Tested (firing and resolved) |
| MonitoringCheckFailed | monitoring-health | critical | 2m | Tested |
| PveCriticalGuestNotRunning | proxmox | critical | 2m | Tested (firing and resolved) |
| PveGuestNotRunning | proxmox | warning | 5m | Tested (firing and resolved) |

The drive, ZFS and temperature rules only produce results where the matching exporter exists (smartctl_exporter, or node_exporter on a host with ZFS or sensors). Without them they stay inactive and do no harm. They were tested by [flipping their condition](how-to-guides.md#test-an-alert-by-flipping-its-condition).

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
expr: up{job=~"node|blackbox|smartctl|pve"} == 0
for: 2m
```

- **Detects:** Prometheus cannot scrape node_exporter, smartctl_exporter, pve-exporter or the Blackbox Exporter. The monitoring is blind: probe and disk metrics stop, so `ServiceDown` and `DiskSpaceLow` **cannot** fire.
- **In plain language:** "a scrape of the `node`, `blackbox`, `smartctl` or `pve` job failed". For `blackbox`, there is one `up` series per target. If the Blackbox container dies, it fires for every target.
- **Note:** `up{job="blackbox"} == 1` while the website is down is normal. See [up vs probe_success](adding-targets.md#up-vs-probe_success).
- **What to change:** add more jobs to the regex when you add exporters (for example `node|blackbox|smartctl|pve|loki`). For a remote node_exporter host, a powered-off host also triggers this alert. You can suppress that with an inhibit rule, see [how-to-guides.md](how-to-guides.md#add-or-change-an-inhibit-rule).

### Drives

#### SmartStatusFailed

```yaml
expr: smartctl_device_smart_status == 0
for: 2m
```

- **Detects:** a drive whose own SMART health check reports failure.
- **In plain language:** "any drive whose SMART status is 0 (failed)". `1` means passed.
- **Why critical:** a drive that says it is failing puts its data at risk.
- **Why 2m:** the status does not flap, and a hiccup of the exporter produces a *missing* series, not a `0`. Two minutes only filters out a single odd evaluation. Waiting longer would not change what you do about it.

#### DriveNotReadable

```yaml
expr: node_disk_info{device=~"sd[a-z]"} and on(host) (up{job="smartctl"} == 1) unless on(device, host) smartctl_device_smart_status
for: 5m
```

- **Detects:** a disk that the operating system lists, but for which the smartctl exporter returns no data. This is what a drive that stops answering looks like: `SmartStatusFailed` cannot fire for it, because there is no value to evaluate.
- **In plain language:** "the disks node_exporter knows about, on hosts whose smartctl exporter works, minus the disks that have SMART data".
- **Why `and on(host) (up{job="smartctl"} == 1)`:** it limits the rule to hosts that really have a working smartctl exporter. Without it, noc-core (an LXC that sees the host's disks but has no smartctl exporter) fired a false alert for every disk. If the exporter itself is down, the rule stays quiet and `MonitoringCheckFailed` reports the real problem, instead of every drive looking unreadable at once.
- **Limit:** only `sd*` drives. An NVMe drive has a different name in each exporter (`nvme0n1` vs `nvme0`), so it would need a name mapping.
- **Seen in practice:** it fired for a faulted WD Red drive that returned `INQUIRY failed` to `smartctl` and `DID_BAD_TARGET` I/O errors in `dmesg`. The email carried the model and serial number.

#### DriveDisappeared

```yaml
expr: (smartctl_device_smart_status offset 1d) unless on(device, host) smartctl_device_smart_status
for: 5m
```

- **Detects:** a drive that reported SMART data 24 hours ago and does not now, including a drive that disappeared from the system completely (the kernel removes it from the list, so `DriveNotReadable` can no longer see it).
- **In plain language:** "drives that existed a day ago and are gone now".
- **Limits:** it resolves by itself 24 hours after the drive disappeared, even if the drive is still missing. Silence it during a planned drive replacement. A drive that never reported (for example one that was already broken when the exporter started) is covered by `DriveNotReadable`, not by this rule.
- **Status: written, not tested.** A real test would mean unplugging a drive. Only the check that the expression returns no results on a healthy system was done.

### Storage

#### ZfsPoolNotOnline

```yaml
expr: node_zfs_zpool_state{state="online"} == 0
for: 2m
```

- **Detects:** a ZFS pool that left the `online` state: degraded, faulted, offline, removed, suspended or unavailable.
- **In plain language:** node_exporter exports one series per pool and state. The `online` series is `1` while the pool is healthy. Any problem flips it to `0`, so one rule covers every bad state.
- **Note:** an exporter running inside an LXC also reports the host's pools. The `metric_relabel_configs` block in the `node` job removes that duplicate for noc-core.

### Hardware

#### HostTemperatureHigh and HostTemperatureCritical

```yaml
expr: node_hwmon_temp_celsius{chip=~"platform_coretemp_.*"} > 90   # High, warning, for 5m
expr: node_hwmon_temp_celsius{chip=~"platform_coretemp_.*"} > 95   # Critical, for 2m
```

- **Detects:** a CPU core or package sensor above the limit. There is one series per sensor.
- **Why 90 and 95:** the numbers come from this host, not from a guess. Its CPU peaked at 88 °C over 24 hours, and the chip reports a "high" mark of 82 °C and a critical limit of 100 °C. A limit below the normal peak would fire every day, so the warning sits just above the peak and the critical alert leaves a 5 °C margin below the chip's critical limit. Choose your own numbers with the queries below.
- **Why `for:` 5m and 2m:** short heat spikes under load are normal and the CPU throttles itself. Only sustained heat is worth an email. The critical alert is already close to damage, so it waits less.

#### NvmeTemperatureHigh

```yaml
expr: node_hwmon_temp_celsius{chip=~"nvme_.*"} > 70
for: 5m
```

- **Detects:** an NVMe sensor above 70 °C.
- **Why a fixed number:** the drive reports a critical limit of about 87 °C for its main sensor. The two secondary sensors report `65261.85` as their limit, which is an "unset" value, so the limits the hardware reports cannot be used for them.

#### DriveTemperatureHigh and DriveTemperatureCritical

```yaml
expr: smartctl_device_temperature{temperature_type="current", device!~"nvme.*"} > 50   # High, warning, for 5m
expr: smartctl_device_temperature{temperature_type="current", device!~"nvme.*"} > 60   # Critical, for 2m
```

- **Detects:** a SATA drive that is too hot. NVMe drives are left out on purpose, because `NvmeTemperatureHigh` already covers them.
- **Why 50 and 60:** the drives here run at 26-34 °C. Many hard-disk datasheets list 55-65 °C as the maximum operating temperature, so 50 °C is an early warning and 60 °C is close to the limit. Check the datasheet of your own drives.

#### Choosing the temperature thresholds

Look at what the hardware really does and what it reports about itself before you pick a number:

```promql
max_over_time(node_hwmon_temp_celsius{host="<host-ip>", chip=~"platform_coretemp_.*"}[24h])   # highest value in a day
node_hwmon_temp_crit_celsius{host="<host-ip>"}   # critical limit reported by the chip
node_hwmon_temp_max_celsius{host="<host-ip>"}    # "high" mark reported by the chip
smartctl_device_temperature{host="<host-ip>"}    # drive temperatures
```

Set the warning above your normal peak and the critical alert a few degrees below the chip's critical limit. Ignore limits that look absurd (such as `65261.85`): they mean "not set".

---

### Proxmox guests

#### PveCriticalGuestNotRunning and PveGuestNotRunning

```yaml
expr: pve_guest_info{tags=~"(.*;)?monitored-critical(;.*)?"} and on(id) (pve_up == 0)   # critical, for: 2m
expr: pve_guest_info{tags=~"(.*;)?monitored-warning(;.*)?"} and on(id) (pve_up == 0)    # warning, for: 5m
```

- **Detects:** a VM or LXC that carries the Proxmox tag `monitored-critical` (or `monitored-warning`) but is not running.
- **In plain language:** "take the guests with this tag, keep those that Proxmox reports as stopped". `pve_guest_info` has the guest's name, ID and tags and is always 1. `pve_up` is 1 for a running guest and 0 for a stopped one. `and on(id)` joins them by guest ID, so the alert keeps the `name` label for the email.
- **Why tags:** the list of guests to watch lives in Proxmox, next to the guest. Tag a guest and it is monitored on the next scrape, with no file to edit and no Prometheus restart. Guests you stop on purpose and never tagged cause no alerts.
- **The regex:** Proxmox joins several tags with `;` in the `tags` label. `(.*;)?monitored-critical(;.*)?` matches the exact tag at the start, middle or end, and does not match a tag that only starts with the same letters.
- **When the exporter is down:** `pve_up` disappears, so these alerts stay quiet and `MonitoringCheckFailed` fires instead (job `pve`).
- **Limits:** a guest deleted from Proxmox disappears from the API and does not alert. A guest tagged with both tags fires both alerts. A typo in the tag means no monitoring: check with `pve_guest_info{tags=~".*monitored.*"}`.
- **Status:** tested (firing and resolved emails for both alerts, on a stopped LXC).

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

Alertmanager has no "acknowledge" button. A **silence** acts as acknowledgement: if someone silences the alert within 15 minutes, the escalation never fires (expected behaviour, not tested).

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

The repo tracks `compose-template.yaml`. Copy it to `compose.yaml` (ignored by Git) and replace `<your-host>` (twice: in `prometheus` and in `alertmanager`).

### Pinned versions

| Service | Image |
|---|---|
| prometheus | `prom/prometheus:v3.13.3` |
| grafana | `grafana/grafana:13.2.2` |
| blackbox | `prom/blackbox-exporter:v0.28.0` |
| alertmanager | `prom/alertmanager:v0.34.1` |
| node-exporter | `prom/node-exporter:v1.12.1` |
| pve-exporter | `prompve/prometheus-pve-exporter:3.10.1` |

Why pinned, not `latest`: a rebuild or a new host gets exactly the versions that were tested. Upgrades become a deliberate change you can review and roll back. To upgrade, change the tag, read the release notes and run `docker compose pull && docker compose up -d`.

### Common settings

- `restart: unless-stopped`: containers come back after a crash or a reboot of the LXC, but not if you stopped them on purpose.
- Services reach each other by **service name** on the default Compose network (`prometheus`, `grafana`, `blackbox`, `alertmanager`, `node-exporter`, `pve-exporter`). That's why configs use `blackbox:9115` and `alertmanager:9093` instead of IPs.

### prometheus

```yaml
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.path=/prometheus
      - --storage.tsdb.retention.time=45d
      - --storage.tsdb.retention.size=10GB
      - --web.external-url=http://<your-host>:9090
    volumes:
      - ./prometheus:/etc/prometheus:ro
      - prometheus_data:/prometheus
```

- `command` replaces the image's default arguments, so the config file and data path are listed explicitly.
- `retention.time=45d` / `retention.size=10GB`: keep 45 days of history, but never more than 10 GB. This fits the 30 GB disk.
- `./prometheus:/etc/prometheus:ro`: the **whole folder** is mounted, so `prometheus.yml`, `rules/` and `targets/` are all visible. `:ro` (read-only) means the container cannot change your config.
- `prometheus_data`: named volume for the time-series database. It survives `docker compose down` and image upgrades.
- Port `9090` is published for the UI and API.
- `--web.external-url`: the address you use in a browser. Prometheus puts it in the "Source" link of each alert, so the link in Alertmanager and in emails opens the right query. Set `<your-host>` to the noc-core IP. Without it, those links point to the container's hostname.
- Not set: `--web.enable-lifecycle`. Without it, config changes need a restart (or a `SIGHUP`) instead of an HTTP reload.

### grafana

```yaml
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
```

`grafana_data` holds users, the admin password, data sources and dashboards. Automatic file provisioning is still planned. Manual-import templates are available for the [catalogue](service-catalogue-dashboard.md) and [health/resource dashboards](health-and-usage-dashboards.md); export saved UI changes separately, because Grafana does not update those template files.

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

### pve-exporter

```yaml
  pve-exporter:
    image: prompve/prometheus-pve-exporter:3.10.1
    restart: unless-stopped
    ports:
      - "127.0.0.1:9221:9221"
    volumes:
      - ./pve/pve.yml:/etc/prometheus/pve.yml:ro
```

- Needs a Proxmox API token first ([how-to](how-to-guides.md#monitor-proxmox-guests-with-pve-exporter)). Create `pve/pve.yml` **before** the first `docker compose up -d`: if the file is missing, Docker creates a folder with that name and the exporter fails. If you do not use Proxmox, delete this service from your `compose.yaml`.
- `./pve/pve.yml` holds the token secret. It is mounted read-only and ignored by Git. If the log says `permission denied`, make the file readable for the container (`chmod 644`).
- Port `127.0.0.1:9221` is only for testing from noc-core. Prometheus reaches the exporter on `pve-exporter:9221` over the Compose network, so the port is not exposed to the LAN.

### volumes

```yaml
volumes:
  prometheus_data:
  grafana_data:
  alertmanager_data:
```

Named volumes managed by Docker. They survive `docker compose down`. **`docker compose down -v` deletes them**, together with all metrics, dashboards and silences. Backup and restore is planned, not built.
