# How-to guides

Practical recipes. Each one shows the YAML to change, the command to apply it and how to check it worked. All commands run on noc-core from the stack folder:

```bash
cd /opt/monitoring
```

Most `amtool` commands need the Alertmanager address. Inside the container, that is always `--alertmanager.url=http://localhost:9093`.

Contents:

- [Change an alert threshold or "for" duration](#change-an-alert-threshold-or-for-duration)
- [Add a new alert rule](#add-a-new-alert-rule)
- [Change routing and timings per severity](#change-routing-and-timings-per-severity)
- [Add or change an inhibit rule](#add-or-change-an-inhibit-rule)
- [Silence alerts for maintenance](#silence-alerts-for-maintenance)
- [Add or change the escalation](#add-or-change-the-escalation)
- [Add another email receiver or change the recipients](#add-another-email-receiver-or-change-the-recipients)
- [Add node_exporter for another host](#add-node_exporter-for-another-host)
- [Add smartctl_exporter for drive health](#add-smartctl_exporter-for-drive-health)
- [Monitor Proxmox guests with pve-exporter](#monitor-proxmox-guests-with-pve-exporter)
- [Test an alert by flipping its condition](#test-an-alert-by-flipping-its-condition)
- [Move the SMTP password into a secret file](#move-the-smtp-password-into-a-secret-file)

Status of the recipes on this setup:

| Recipe | Status |
|---|---|
| Change an alert threshold or "for" duration | Tested (test values for `ServiceSlow` and `DiskSpaceLow`) |
| Add a new alert rule | Structure tested through the existing rules; the certificate example is **untested** |
| Change routing and timings per severity | Routing by severity tested; the two examples (1 m warning wait, `info` route) are **untested** |
| Add or change an inhibit rule | No rules by default; the example is **untested** |
| Silence alerts for maintenance | Tested |
| Add or change the escalation | Tested, including the resolved email |
| Add another email receiver or change the recipients | A second recipient is tested; the per-owner route is **untested** |
| Add node_exporter for another host | Debian package on the Proxmox host: tested. Docker on another host and the firewall steps: **untested** |
| Add smartctl_exporter for drive health | Tested on the Proxmox host (Debian 13 package from backports) |
| Monitor Proxmox guests with pve-exporter | Tested on the Proxmox host (read-only token, exporter, job UP, both tag alerts fired and resolved) |
| Test an alert by flipping its condition | Tested (used for the drive, ZFS and temperature alerts) |
| Move the SMTP password into a secret file | **Untested** |

---

## Change an alert threshold or "for" duration

Example: make `ServiceSlow` fire at 2 seconds instead of 1, after 10 minutes instead of 5.

**1. Edit** `prometheus/rules/alerts.yml`:

```yaml
      - alert: ServiceSlow
        expr: probe_duration_seconds{module="http_2xx"} > 2 and on(instance, module) probe_success == 1
        for: 10m
```

Only change the number and `for:`. Leave the `and on(instance, module) probe_success == 1` part alone, because it keeps slow and down apart.

Other common knobs:

| Alert | Threshold | Default `for` |
|---|---|---|
| ServiceDown | – (any failure) | `2m` |
| ServiceSlow | `> 1` (seconds) | `5m` |
| DiskSpaceLow | `< 0.15` (fraction free) | `10m` |
| DiskWillFillSoon | `[6h]` history, `24 * 3600` s ahead | `30m` |
| MonitoringCheckFailed | – (`up == 0`) | `2m` |

**2. Check and apply:**

```bash
docker compose exec prometheus promtool check rules /etc/prometheus/rules/alerts.yml
docker compose restart prometheus
```

Prometheus reads rule files only at startup, so the restart is needed.

**3. Verify:** open `http://<noc-core-ip>:9090/alerts` and expand the rule. The expression and `for` value shown there should be your new ones.

**Testing a threshold:** to see an alert fire without breaking anything, temporarily make it very sensitive, for example `> 0.001` and `for: 1m` for `ServiceSlow`, or `< 0.99` and `for: 1m` for `DiskSpaceLow`. Restart, wait for Pending → Firing and the email, then **put the real values back** and restart again. Test values left in place make the alert fire constantly and turn it into noise.

---

## Add a new alert rule

Copy this template into `prometheus/rules/alerts.yml`, either into an existing group or as a new group. Indentation matters: a new group starts at the same level as `- name: availability`.

```yaml
  - name: <group-name>
    rules:
      - alert: <AlertName>               # CamelCase, shows up in emails and inhibit rules
        expr: <PromQL that returns series only when something is wrong>
        for: 5m                          # how long it must stay true
        labels:
          severity: warning              # critical or warning: decides the route
        annotations:
          summary: "<short text with {{ $labels.host }}>"
          description: "<details, can use {{ $value }} and {{ $labels.owner }}>"
          runbook: "<AlertName>: 1) first check, 2) second check, 3) contact the owner."
```

**Example** (not in the repo yet, **untested**): warn when a TLS certificate expires within 14 days. It uses a metric that HTTPS probes already produce.

```yaml
  - name: certificates
    rules:
      - alert: CertificateExpiringSoon
        expr: (probe_ssl_earliest_cert_expiry - time()) / 86400 < 14
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Certificate of {{ $labels.service }} on {{ $labels.host }} expires soon"
          description: "The TLS certificate of {{ $labels.instance }} expires in {{ $value | humanize }} days (owner: {{ $labels.owner }})."
          runbook: "CertificateExpiringSoon: 1) check the certificate renewal (e.g. certbot), 2) renew or replace the certificate, 3) contact the owner."
```

Rules of thumb:

- Every alert needs a `severity` that matches a route (`critical` or `warning`). Otherwise it goes to the `default` receiver.
- Every alert needs a runbook line, so the receiver knows what to do.
- Keep `host` and `owner` on the result. Avoid aggregations like `sum(...)` without `by (host, owner)`, because they drop labels that grouping, inhibition and the email text rely on.
- Try the expression in the Prometheus query box first. It should return nothing while everything is fine.

**Apply and verify:**

```bash
docker compose exec prometheus promtool check rules /etc/prometheus/rules/alerts.yml
docker compose restart prometheus
```

`promtool` prints the number of rules found. The new rule should appear on `http://<noc-core-ip>:9090/alerts`, **inactive**.

---

## Change routing and timings per severity

Routing lives in `alertmanager/alertmanager.yml` under `route.routes`. Each route matches on labels and sets its own timing. See the [routing table](configuration-reference.md#route-the-routing-tree) for the current values.

**Example:** make warnings arrive faster (1 minute wait) and remind every 6 hours instead of 12.

```yaml
    - matchers:
        - severity="warning"
      receiver: email-warning
      group_wait: 1m
      group_interval: 15m
      repeat_interval: 6h
```

**Example:** add an `info` severity that goes to the default receiver once a day. Add it at the end of `routes:`:

```yaml
    - matchers:
        - severity="info"
      receiver: default
      group_wait: 5m
      group_interval: 1h
      repeat_interval: 24h
```

What the timings mean:

| Key | Lower value | Higher value |
|---|---|---|
| `group_wait` | Faster first email, less bundling | More alerts bundled in the first email |
| `group_interval` | Faster updates when a group changes (including resolved emails) | Fewer update emails |
| `repeat_interval` | More reminders for alerts that stay active | Fewer reminders |

Remember: routes are checked from **top to bottom** and the first match wins, unless it has `continue: true`. Put specific routes above general ones.

**Check and apply:**

```bash
docker compose exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
docker compose restart alertmanager
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  config routes show
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  config routes test severity=warning host=x alertname=Test
```

`routes show` prints the routing tree. `routes test` prints which receiver(s) an alert with these labels would go to. Here that is `email-warning`.

---

## Add or change an inhibit rule

**Inhibition** mutes alerts (the *targets*) while another alert (the *source*) is firing, if both have the same value for the labels in `equal`. Muted alerts still show in Prometheus and in Alertmanager (marked as inhibited), but no email goes out for them. Use it to report a **cause** once instead of all its **symptoms**.

> **Untested.** No inhibit rules are configured by default, so nothing here has been tried on this setup yet. Grouping by `alertname` and `host` already puts all alerts of the same kind for one machine into one email. Add a rule only for a cause and a symptom that really arrive as separate emails.

### Template

```yaml
inhibit_rules:
  - source_matchers:          # the alert that does the muting
      - alertname="<CauseAlert>"
    target_matchers:          # the alerts that get muted
      - alertname="<SymptomAlert>"
    equal: [host]             # labels that must have the same value on both
```

Every label in `equal` must exist on both alerts with exactly the same spelling. If one alert lacks the label, the rule never matches and you get both emails, without an error.

### Example: a critical temperature alert mutes its warning

Above 95 °C, `HostTemperatureHigh` (above 90 °C) and `HostTemperatureCritical` both fire for the same sensor. Report the critical one only:

```yaml
inhibit_rules:
  - source_matchers:
      - alertname="HostTemperatureCritical"
    target_matchers:
      - alertname="HostTemperatureHigh"
    equal: [host, chip, sensor]
```

**Apply:**

```bash
docker compose exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
docker compose restart alertmanager
```

`check-config` should now report `1 inhibit rules`.

**Verify with fake alerts.** No sensor has to get hot:

```bash
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  alert add alertname=HostTemperatureCritical host=inhibit-test chip=test sensor=test severity=critical
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  alert add alertname=HostTemperatureHigh host=inhibit-test chip=test sensor=test severity=warning
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  alert query host=inhibit-test
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  alert query --inhibited host=inhibit-test
```

Without a state flag, `alert query` shows only active alerts. The first query should show only `HostTemperatureCritical`. The second (`--inhibited`) shows only inhibited alerts and should list `HostTemperatureHigh`. You should get one `[CRITICAL]` email and no `[WARNING]` email. Both fake alerts expire on their own after about 5 minutes (`resolve_timeout`).

---

## Silence alerts for maintenance

A **silence** mutes notifications for alerts that match a set of labels, for a set time.

What a silence **does**:

- It stops all emails for matching alerts on every route, including escalation. It acts as an "acknowledge": silence a critical alert within 15 minutes and the escalation should never be sent (expected behaviour, not tested).
- It persists across restarts, because it is stored in the `alertmanager_data` volume.
- It can be created in advance with a start time, for planned maintenance.

What a silence does **not** do:

- It does not stop Prometheus. Probes, metrics and alert evaluation continue. Alerts still show as firing on the Prometheus *Alerts* page and as silenced in Alertmanager.
- It does not affect alerts that don't match **all** of its matchers.
- If an alert fires and resolves entirely inside the silence, you get **no** emails for it, not even a resolved one. That is expected.
- If the alert is still firing when the silence ends, the notification is sent then.

### In the UI

Button names can differ slightly between Alertmanager versions.

1. Open `http://<noc-core-ip>:9093` and click **New Silence**. Or click **Silence** next to a firing alert, which pre-fills its labels.
2. Matchers: for maintenance on a host, use one matcher, `host` = `server-a`. That covers every alert of that host.
3. Set the start and the duration (for example `2h`), your name as **Creator**, and a **Comment** with the reason.
4. Click **Preview Alerts** to see which current alerts would match, then **Create**.

To end early: open *Silences*, select it and click **Expire**.

### With amtool

```bash
# Silence everything on one host for 2 hours, starting now
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  silence add host=server-a --duration=2h \
  --author="<your-name>" --comment="Planned maintenance: kernel update"

# List active silences (shows their IDs)
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  silence query

# End a silence early
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  silence expire <silence-id>
```

To schedule maintenance in advance, use `--start` with an RFC 3339 time instead of starting now, for example `--start=2026-10-10T20:00:00+02:00 --duration=2h`.

Matchers can be narrower: `alertname=ServiceSlow host=server-a` only mutes slowness on that host and keeps outage alerts active.

**Verify:** the silence is listed in *Silences* (UI) or `silence query`, and matching alerts show as silenced on the Alertmanager *Alerts* page.

---

## Add or change the escalation

Alertmanager has no built-in "notify the next person after X minutes". The escalation is built from two routes that match the **same** critical alerts:

```yaml
  routes:
    - matchers:
        - severity="critical"
      receiver: email-critical
      continue: true              # also check the next route
      group_wait: 30s
      group_interval: 5m
      repeat_interval: 1h
    - matchers:
        - severity="critical"
      receiver: email-escalation
      group_wait: 15m             # only sends if the alert is still firing after 15 minutes
      group_interval: 5m
      repeat_interval: 4h
```

How it works:

1. `continue: true` on the first route makes Alertmanager also check the second route. Without it, matching stops at the first route and the escalation never happens.
2. The second route starts its own group with a 15-minute `group_wait`. If the alert resolved within those 15 minutes, there is nothing left to send and the escalation stays quiet. If it is still firing, `email-escalation` gets it.
3. A silence created within the 15 minutes stops the escalation too (expected behaviour, not tested).

The receiver:

```yaml
  - name: email-escalation
    email_configs:
      - to: '<escalation-contact>'
        send_resolved: true
        headers:
          Subject: '[ESCALATED] {{ .Status | toUpper }}: {{ .GroupLabels.alertname }} on {{ .GroupLabels.host }}'
```

`send_resolved: true` makes sure the escalated person also hears when the problem is over. The `[ESCALATED]` prefix keeps it distinguishable, even if everything goes to one mailbox during testing. In real use, `to:` should be a second person (the owning group's contact or a teacher).

**To change the delay**, edit `group_wait` on the second route (for example `30m`).

**To add a third level**, add `continue: true` to the escalation route and add another route after it with a longer `group_wait` (for example `1h`) and a new receiver.

**Apply and check:**

```bash
docker compose exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
docker compose restart alertmanager
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  config routes test --verify.receivers=email-critical,email-escalation severity=critical host=x alertname=Test
```

The last command must print both receivers. If it prints only one, `continue: true` is missing.

**Test end to end:** temporarily set the escalation `group_wait` to `2m`, restart Alertmanager and fire a critical alert that stays active for 10 minutes:

```bash
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  alert add EscalationTest severity=critical host=control-host \
  --annotation=summary="Escalation test" --end=$(date -d '+10 minutes' -Iseconds)
```

`$(date ...)` runs on noc-core (GNU date) before the command goes into the container. Expected:

- a `[CRITICAL] FIRING` email after about 30 s
- an `[ESCALATED] FIRING` email after about 2 minutes
- `RESOLVED` emails from both receivers after the 10 minutes, plus up to `group_interval` (5 min)

Then set `group_wait` back to `15m` and restart Alertmanager.

---

## Add another email receiver or change the recipients

### Change or add recipients

Edit `to:` in `alertmanager/alertmanager.yml`. Separate several addresses with commas inside one string:

```yaml
  - name: email-critical
    email_configs:
      - to: 'oncall@example.org, teacher@example.org'
        send_resolved: true
        headers:
          Subject: '[CRITICAL] {{ .Status | toUpper }}: {{ .GroupLabels.alertname }} on {{ .GroupLabels.host }}'
```

### Add a receiver for one owner

> **Untested.** Not tried on this setup yet.

Every target carries an `owner` label. To also notify the owner directly, add a receiver:

```yaml
  - name: email-team-a
    email_configs:
      - to: '<team-a-contact>'
        send_resolved: true
        headers:
          Subject: '[TEAM-A] {{ .Status | toUpper }}: {{ .GroupLabels.alertname }} on {{ .GroupLabels.host }}'
```

Then add a route at the **top** of `routes:`, with `continue: true` so the alert still reaches the critical/warning/escalation routes below. The matcher must use the exact `owner` value from the target file:

```yaml
  routes:
    - matchers:
        - owner="team-a"
      receiver: email-team-a
      continue: true
    - matchers:
        - severity="critical"
      receiver: email-critical
      # ... existing routes stay as they are
```

Without `continue: true`, team-a alerts would **only** go to the team, and the NOC would stop seeing them. An alert only matches if it still has the `owner` label, so aggregations such as `sum(...)` need `by (host, owner)`.

**Apply and check:**

```bash
docker compose exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
docker compose restart alertmanager
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  config routes test owner=team-a severity=critical host=x alertname=Test
```

Expected receivers: `email-team-a,email-critical,email-escalation`.

---

## Add node_exporter for another host

Only do this on hosts where you are **allowed** to install software. For everything else, stay with black-box probes.

> **Status.** Option A (Debian package) is **tested** on the Proxmox host (PVE 9, Debian 13, package 1.9.0). Option B (Docker) is tested on noc-core only; on a second host it is **untested**. The firewall steps for ufw and the Proxmox firewall are **untested**.

Pick one of the two ways to run it:

| | Option A: Debian package | Option B: Docker |
|---|---|---|
| Best for | Hosts without Docker, such as a Proxmox host or a plain VM | Hosts that already run Docker, such as noc-core |
| Version | The distro's version (Debian 13 / PVE 9: 1.9.0; Debian 12 / PVE 8: 1.5.0) | Same as the NOC (v1.12.1) |
| Updates | With `apt upgrade` | Change the image tag |
| Tested | Proxmox host | noc-core |

The Debian version is older, but for this project it exposes everything needed: filesystems (including ZFS), temperatures (`hwmon`), memory, CPU, network and the apt update status. On Proxmox 8 (Debian 12) the package is much older (1.5.0); there, prefer the release binary or Docker.

### 1A. Install the Debian package

Run on the monitored host as root:

```bash
apt update
apt install -y prometheus-node-exporter
```

By default the package listens on **all** interfaces. Bind it to the host's LAN address only (the one you use to reach the host, for example the Proxmox web UI address). Edit `/etc/default/prometheus-node-exporter` and set the `ARGS` line (edit the existing one, don't add a second):

```bash
ARGS="--web.listen-address=<host-ip>:9100"
```

```bash
systemctl restart prometheus-node-exporter
systemctl status prometheus-node-exporter --no-pager
ss -tlnp | grep 9100
```

The status should be `active (running)`, and `ss` should show `<host-ip>:9100`, not `*:9100` or `0.0.0.0:9100`.

### 1B. Or run it with Docker

Use the same version as the NOC:

```bash
docker run -d --name node-exporter --restart unless-stopped \
  --net host --pid host \
  -v /:/host:ro,rslave \
  prom/node-exporter:v1.12.1 --path.rootfs=/host
```

`--net host` (instead of `-p 9100:9100`) matters for the firewall step. Ports published with `-p` are handled by Docker's own iptables rules and **bypass ufw**.

### 2. Restrict port 9100 to the NOC

node_exporter has no authentication. Anyone who can reach port 9100 can read hardware details, mount points and network configuration of the host. Only noc-core needs it. Which control works depends on where you can apply it:

| Where | What it covers | Limit |
|---|---|---|
| Firewall on the monitored host (ufw, or the Proxmox firewall) | Every source, including devices in the same VLAN | Needs access to the host; a wrong rule can lock you out |
| Network firewall (for example UniFi zone policies: allow noc-core, block the rest, both with destination `<host-ip>` port 9100) | Traffic **between** VLANs | Does **not** see traffic inside one VLAN, because that never reaches the gateway |

With ufw on the monitored host:

```bash
ufw allow from <noc-core-ip> to any port 9100 proto tcp
ufw deny 9100/tcp
ufw status numbered
```

The `allow` rule must come before the `deny` (ufw evaluates rules in order).

On a Proxmox host, use **Datacenter → Firewall** instead: add accept rules for noc-core (tcp 9100), the web UI (tcp 8006) and SSH (tcp 22). Do this **before** setting *Input Policy* to `DROP` and *Firewall* to `Yes`, and keep console access ready: a missing rule locks you out of the web UI. `pve-firewall stop` on the console switches it off again.

**Check from noc-core** (it should work):

```bash
docker compose exec prometheus wget -qO- http://<host-ip>:9100/metrics | head -5
```

From a machine the firewall should block, `curl http://<host-ip>:9100/metrics` should time out.

### 3. Add the host to the `node` job

In `prometheus/prometheus.yml`, add a second entry under `static_configs` of the `node` job:

```yaml
  - job_name: node
    static_configs:
      - targets: ['node-exporter:9100']
        labels:
          host: noc-core
          service: node-exporter
          owner: '<owner>'
          contact: '<contact-person> (<contact-address>)'
          dependencies: 'external:docker'
      - targets: ['<host-ip>:9100']
        labels:
          host: <host-name>
          service: node-exporter
          owner: '<owner>'
          contact: '<contact-person> (<contact-address>)'
          dependencies: '<dependencies>'
```

Use **exactly the same `host` value** as this host's targets in `prometheus/targets/*.yml`. Grouping and silences depend on it. Choose a readable machine name (for example `server-a`), not the IP address: the address is already in the `instance` label.

### 4. Apply and verify

```bash
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose restart prometheus
```

- *Status → Target health*: the `node` job shows the new target as **UP**.
- Query `node_filesystem_avail_bytes{host="<host-name>"}`: it returns values.
- `DiskSpaceLow`, `DiskWillFillSoon` and `MonitoringCheckFailed` now cover this host automatically.
- Check the collectors: `node_scrape_collector_success{host="<host-name>"}`. The ones you need should be `1`. Collectors for hardware the host doesn't have (for example `infiniband`, `fibrechannel`, `ipvs`, `nfsd`) show `0`. That is normal and not a problem.

### Extra checks for a Proxmox host

These worked on the Proxmox host (PVE 9, ZFS):

```promql
node_hwmon_temp_celsius{host="<host-name>"}                        # CPU, NVMe and NIC temperatures
node_filesystem_avail_bytes{host="<host-name>", fstype="zfs"}      # ZFS pools and one entry per LXC volume
node_zfs_zpool_state{host="<host-name>"}                           # pool health: state="online" is 1 when healthy
```

Notes:

- `DiskSpaceLow` includes `zfs`, so it also covers every LXC volume. Several alerts for the same pool still arrive as one email, because alerts are grouped by `host`.
- VM disks are ZFS volumes, not filesystems, so they don't show up in `node_filesystem_*`.
- Temperatures only exist on real hardware. They are not available inside an LXC or most VMs.
- An exporter that runs inside an LXC (such as the one on noc-core) reports the **host's** ZFS pools and CPU sensors, because an LXC shares the host's kernel. Left alone, every such alert arrives twice, once for the host and once for the LXC. `prometheus.yml` drops these metrics for `noc-core` with `metric_relabel_configs`; do the same for any other LXC you scrape.

---

## Add smartctl_exporter for drive health

> **Status.** Tested on the Proxmox host (Proxmox 9, Debian 13, package 0.14.0). Only for hosts where you are **allowed** to install software and that have physical drives. It is no use inside an LXC or most VMs, because virtual disks have no SMART data.

smartctl_exporter reads the SMART data of each drive (the drive's own health report) with `smartctl` and turns it into metrics. Prometheus can then alert on a drive that reports failure, a drive that stops answering, and drive temperature. See the [alert reference](configuration-reference.md#drives) for the rules.

### 1. Check that the host can read its drives

```bash
smartctl --scan
smartctl -H /dev/<drive>
```

Every physical drive should be listed, and `-H` should say `PASSED`. If `smartctl` cannot read a drive, the exporter cannot either. Drives behind a RAID controller or a USB bridge may need extra options.

### 2. Install the package

On Debian 13 (Proxmox 9) the package `prometheus-smartctl-exporter` is **not** in the normal repository, only in `trixie-backports`:

```bash
echo "deb http://deb.debian.org/debian trixie-backports main" > /etc/apt/sources.list.d/trixie-backports.list
apt update
apt install -t trixie-backports prometheus-smartctl-exporter
```

Packages from backports are only installed when you ask for them with `-t`, so the rest of the system is unchanged. The service is called `smartctl_exporter` (with an underscore), not after the package.

### 3. Listen on the host's LAN address only

The package starts the exporter on **all** interfaces (port 9633) and has no settings file. Set the address and some basic sandboxing with a systemd override:

```bash
systemctl edit smartctl_exporter
```

```ini
[Service]
ExecStart=
ExecStart=/usr/bin/smartctl_exporter --web.listen-address=<host-ip>:9633
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
```

The empty `ExecStart=` line is required: it clears the original command so yours replaces it instead of being added to it. The other four lines limit what the process can do. The package runs the exporter as `root`, which it needs for raw disk access, so the sandboxing matters.

```bash
systemctl restart smartctl_exporter
systemctl status smartctl_exporter --no-pager -l
ss -tlnp | grep 9633
curl -s http://<host-ip>:9633/metrics | grep smartctl_device_smart_status
```

- `ss` should show `<host-ip>:9633`, not `*:9633`.
- `curl` should print one line per readable drive. `1` means the drive passed its health check.
- The log shows `Found device` for every drive. A line like `Smartctl open device: /dev/sdX failed` means that drive has **no metrics**. The `DriveNotReadable` alert exists for exactly that case.

### 4. Add the job to Prometheus

Uncomment the `smartctl` job in your `prometheus/prometheus.yml` (the template has it commented out) and fill in the IP:

```yaml
  - job_name: smartctl
    static_configs:
      - targets: ['<host-ip>:9633']
        labels:
          host: <host-name>
          service: smartctl-exporter
          owner: '<owner>'
          contact: '<contact-person> (<contact-address>)'
          dependencies: '<dependencies>'
```

```bash
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose restart prometheus
```

Use the **same** `host` value as the node job and the probes for this machine: `DriveNotReadable` compares the two exporters by `host`.

Verify:

- *Status → Target health*: the `smartctl` job shows **UP**.
- `smartctl_device_smart_status{host="<host-name>"}` returns one series per drive.
- `smartctl_device_temperature{host="<host-name>"}` returns the temperatures (label `temperature_type="current"`).

`MonitoringCheckFailed` already covers this job, so you are alerted if the exporter stops answering.

### 5. Restrict the port

The exporter has no authentication, like node_exporter. Restrict port 9633 to noc-core in the same way as port 9100, see [step 2 of the node_exporter recipe](#2-restrict-port-9100-to-the-noc). The same limits apply.

---

## Monitor Proxmox guests with pve-exporter

pve-exporter reads the Proxmox API with a **read-only token** and exposes the status of every VM and LXC (running or stopped, CPU, memory, storage). node_exporter cannot see this, because VMs and other LXCs are invisible from inside noc-core.

You choose which guests to watch with **tags in Proxmox**, so there is no list file to maintain:

| Tag | Meaning | Alert |
|---|---|---|
| `monitored-critical` | Must always run (remote access, databases, game server) | `PveCriticalGuestNotRunning`: critical email after 2 minutes |
| `monitored-warning` | Matters, but is not urgent | `PveGuestNotRunning`: warning email after 5 minutes |

Give a guest only one of the two tags. Guests without a tag are never alerted on, so a VM you stop on purpose causes no email.

### 1. Create a read-only user and token

On the Proxmox host shell:

```bash
pveum user add prometheus@pve --comment "Read-only monitoring"
pveum aclmod / --users prometheus@pve --roles PVEAuditor
pveum user token add prometheus@pve exporter --privsep 0
```

Or in the web UI (Datacenter): *Permissions → Users → Add* (realm *Proxmox VE authentication server*, no password needed), then *Permissions → Add → User Permission* (path `/`, role `PVEAuditor`), then *Permissions → API Tokens → Add* (user `prometheus@pve`, Token ID `exporter`, **untick Privilege Separation**).

- `PVEAuditor` is the built-in read-only role: it can look at everything and change nothing.
- The user has no password on purpose. It only exists to own the token, so nobody can log in with it.
- The token **secret is shown only once**. Store it in a password manager. Never paste it in chat, a screenshot or Git.

### 2. Test the token

On the Proxmox host. `read -rs` waits silently: type the command, press Enter, then paste the secret and press Enter again.

```bash
read -rs PVE_SECRET
curl -sk -H 'Authorization: PVEAPIToken=prometheus@pve!exporter='"$PVE_SECRET" \
  https://<proxmox-ip>:8006/api2/json/version; echo
unset PVE_SECRET
```

Expected: `{"data":{"version":"9.x.x",...}}`. `401` means a wrong secret or token name. Use single quotes around the header: in double quotes bash treats the `!` as history expansion and prints `event not found`.

### 3. Create `pve/pve.yml`

```bash
mkdir -p pve
cp pve/template.yml pve/pve.yml
nano pve/pve.yml                 # fill in user, token name and the token secret
```

With the commands above the values are `prometheus@pve`, `exporter` and the secret. `pve/pve.yml` is ignored by Git, because it holds the secret. `verify_ssl: false` is needed while Proxmox uses its self-signed certificate.

### 4. Start the exporter

The `pve-exporter` service is part of `compose-template.yaml`. If your `compose.yaml` was copied before it was added, copy the service block over. Create `pve/pve.yml` **before** starting it: if the file is missing, Docker creates a folder with that name and the exporter fails. Then:

```bash
docker compose up -d pve-exporter
docker compose logs --tail 20 pve-exporter
```

If the log says `permission denied` for `pve.yml`, the container user cannot read the file: run `chmod 644 pve/pve.yml` (the file only exists on noc-core). If you do not use Proxmox, delete the `pve-exporter` service from your `compose.yaml`.

### 5. Test the exporter

```bash
curl -s 'http://127.0.0.1:9221/pve?target=<proxmox-ip>&cluster=1&node=1' | grep -E '^pve_(up|guest_info)' | head
```

You should see one `pve_up` and one `pve_guest_info` line per guest. The published port is bound to `127.0.0.1`, so it is only reachable from noc-core itself.

### 6. Add the job to Prometheus

Uncomment the `pve` job in your `prometheus/prometheus.yml` (it is in `prometheus/template.yml`) and fill in the Proxmox IP, then:

```bash
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose restart prometheus
```

Under *Status → Targets* the `pve` job should be UP. It works like the Blackbox job: the target is the Proxmox host, and the `relabel_configs` send the scrape to `pve-exporter:9221` instead. `MonitoringCheckFailed` already covers the `pve` job, so you get an alert if the exporter loses access (deleted token, stopped container, host unreachable).

### 7. Tag the guests

In the Proxmox web UI, select a guest and click the tag pencil next to its name, then add `monitored-critical` or `monitored-warning`. Tags are read on the next scrape (up to 30 seconds). Check which guests are picked up:

```promql
pve_guest_info{tags=~"(.*;)?monitored-critical(;.*)?"}
pve_guest_info{tags=~"(.*;)?monitored-warning(;.*)?"}
```

A guest with several tags has them joined with `;` in the `tags` label, which the regex handles.

### 8. Test the alerts

Give a **stopped** guest the tag and wait: `PveCriticalGuestNotRunning` fires after about 3 minutes, `PveGuestNotRunning` after about 7 to 8 minutes. Remove the tag and wait for the resolved email (up to 5 minutes for critical, up to 15 for warning, because of `group_interval`). Both were tested this way.

### Limits

- A guest you **delete** disappears from the API, so it does not alert. Remove its tag first if you decommission it on purpose.
- The tags cover guests only. The Proxmox host itself is covered by node_exporter and `MonitoringCheckFailed`.
- `verify_ssl: false` accepts any certificate on the way to Proxmox. That is acceptable on a trusted LAN. Install a real certificate on Proxmox and set `verify_ssl: true` to harden it..

---

## Test an alert by flipping its condition

> **Status.** Tested. Used for all drive, ZFS and temperature alerts, including the resolved emails.

A healthy system fires no alerts, so you cannot see the whole path (rule, Alertmanager, email) work. The trick is to **temporarily flip the condition** so it is true right now, and then put it back. You test the real rule with the real routing, without breaking anything.

| Rule | Normal condition | Temporary flip |
|---|---|---|
| `SmartStatusFailed`, `ZfsPoolNotOnline`, `ServiceDown` | `== 0` | `== 1` |
| A temperature rule, for example `HostTemperatureHigh` | `> 90` | `> 10` |
| `DiskSpaceLow` | `< 0.15` | `< 0.99` |

### 1. Flip, validate and restart

Edit `expr:` in `prometheus/rules/alerts.yml`, then:

```bash
docker compose exec prometheus promtool check rules /etc/prometheus/rules/alerts.yml
docker compose restart prometheus
```

You can flip several rules at once. The alert then fires for **every** matching series, for example one per sensor, per drive and per host, so expect several alerts in one email.

### 2. Wait for the FIRING emails

The delay is `for:` plus up to 1 minute for the rule evaluation plus the group wait of the route: 30 s for critical and 2 minutes for warning (see [routing](configuration-reference.md#route-the-routing-tree)).

### 3. Put everything back, then restart again

Restore **every** flipped `expr`, validate and restart. Check the result with `git diff prometheus/rules/alerts.yml`: only intended changes should show. A flipped rule that is left in place keeps sending false critical emails.

### 4. Wait for the RESOLVED emails

Resolved notifications follow the route's `group_interval`: up to **5 minutes** for critical and up to **15 minutes** for warning. If a resolved email seems missing, wait for that time before you look for a problem.

### 5. Check the Alerts page

Open *Alerts* in Prometheus. Everything should be **Inactive** again, except alerts that are really firing.

Tell the people who receive the emails before you test. A flip test sends real critical emails.

---

## Move the SMTP password into a secret file

> **Untested.** Not tried on this setup yet. If Alertmanager cannot read the file, check its owner and mode first.

Instead of `smtp_auth_password` in `alertmanager.yml`, Alertmanager can read the password from a separate file. This keeps the password out of the config: you can show, diff or share `alertmanager.yml` without leaking it, and give the file stricter permissions.

### 1. Create the secret file

Type the password instead of putting it on the command line, so it doesn't end up in your shell history:

```bash
cd /opt/monitoring
read -rsp 'Gmail app password: ' PW; echo
printf '%s' "$PW" > alertmanager/smtp_password
unset PW
chown 65534:65534 alertmanager/smtp_password   # 65534 = nobody, the user Alertmanager runs as in the container
chmod 400 alertmanager/smtp_password
```

The `./alertmanager` folder is already mounted into the container, so the file is visible at `/etc/alertmanager/smtp_password`. `.gitignore` ignores everything in `alertmanager/` except `template.yml`, so the file is not committed.

### 2. Point Alertmanager at the file

In `alertmanager/alertmanager.yml`, **replace** the `smtp_auth_password` line (you can't set both):

```yaml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: '<your-gmail-address>'
  smtp_auth_username: '<your-gmail-address>'
  smtp_auth_password_file: '/etc/alertmanager/smtp_password'
```

### 3. Apply and verify

```bash
git status --short                      # smtp_password must NOT be listed
docker compose exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
docker compose restart alertmanager
docker compose logs --tail=20 alertmanager
docker compose exec alertmanager amtool alert add alertname=TestAlert host=test severity=critical \
  --annotation=summary="Secret file test" --alertmanager.url=http://localhost:9093
```

A `[CRITICAL]` test email should arrive within about 30 s. If the log shows a "permission denied" error for the file, check the owner and mode from step 1 (`ls -l alertmanager/smtp_password`). If it shows an authentication error, the file probably has a typo or a trailing newline. Recreate it with `printf` as shown above.
