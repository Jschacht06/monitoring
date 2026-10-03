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
- [Move the SMTP password into a secret file](#move-the-smtp-password-into-a-secret-file)

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
          description: "<details, can use {{ $value }} and {{ $labels.group }}>"
          runbook: "<AlertName>: 1) first check, 2) second check, 3) contact the owning group."
```

**Example** (not in the repo yet): warn when a TLS certificate expires within 14 days. It uses a metric that HTTPS probes already produce.

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
          description: "The TLS certificate of {{ $labels.instance }} expires in {{ $value | humanize }} days (group: {{ $labels.group }})."
          runbook: "CertificateExpiringSoon: 1) check the certificate renewal (e.g. certbot), 2) renew or replace the certificate, 3) contact the owning group."
```

Rules of thumb:

- Every alert needs a `severity` that matches a route (`critical` or `warning`). Otherwise it goes to the `default` receiver.
- Every alert needs a runbook line, so the receiver knows what to do.
- Keep `host` and `group` on the result. Avoid aggregations like `sum(...)` without `by (host, group)`, because they drop labels that grouping, inhibition and the email text rely on.
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

### Existing rule: ICMP down suppresses HTTP down

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

For a host that normally answers ping, a failing ping means the host or the network path is gone, so its websites are unreachable too. You get one email about ping instead of one per website.

> **Only use this for hosts that reliably answer ping.** If ICMP is blocked, the ICMP alert fires permanently and mutes every HTTP outage on that host. Use `tcp_connect` instead of `icmp` for such hosts. The same applies to the rule below.

### New rule: a down host suppresses MonitoringCheckFailed

When a remote host with node_exporter is powered off, two alerts fire: `ServiceDown` for its ICMP probe, and `MonitoringCheckFailed` because the `node` job can't scrape it. The second is a symptom. Add this entry to the `inhibit_rules:` list:

```yaml
  - source_matchers:
      - alertname="ServiceDown"
      - module="icmp"
    target_matchers:
      - alertname="MonitoringCheckFailed"
    equal: [host]
```

This only works if the `host` label is **identical** in both places:

- the ICMP target in `prometheus/targets/*.yml` (`host: 192.168.1.150`)
- the node_exporter target in the `node` job of `prometheus.yml` (`host: 192.168.1.150`)

A different spelling (`192.168.1.150` and `server-a`) means no match. You get both emails and no error.

This rule does not hide a broken Blackbox Exporter. If Blackbox dies, there are no probe results, so `ServiceDown` cannot fire as a source, and `MonitoringCheckFailed` still reaches you.

The full section then looks like this:

```yaml
inhibit_rules:
  - source_matchers:
      - alertname="ServiceDown"
      - module="icmp"
    target_matchers:
      - alertname="ServiceDown"
      - module="http_2xx"
    equal: [host]
  - source_matchers:
      - alertname="ServiceDown"
      - module="icmp"
    target_matchers:
      - alertname="MonitoringCheckFailed"
    equal: [host]
```

**Apply:**

```bash
docker compose exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
docker compose restart alertmanager
```

`check-config` should now report `2 inhibit rules`.

**Verify with fake alerts.** No host has to go down:

```bash
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  alert add alertname=ServiceDown module=icmp host=inhibit-test severity=critical
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  alert add alertname=MonitoringCheckFailed job=node host=inhibit-test severity=critical
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  alert query host=inhibit-test
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  alert query --inhibited host=inhibit-test
```

Without a state flag, `alert query` shows only active alerts. The first query should show only `ServiceDown`. The second (`--inhibited`) shows only inhibited alerts and should list `MonitoringCheckFailed`. You should get one `[CRITICAL]` email for `ServiceDown` only. Both fake alerts expire on their own after about 5 minutes (`resolve_timeout`).

---

## Silence alerts for maintenance

A **silence** mutes notifications for alerts that match a set of labels, for a set time.

What a silence **does**:

- It stops all emails for matching alerts on every route, including escalation. It acts as an "acknowledge": silence a critical alert within 15 minutes and the escalation is never sent.
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
2. Matchers: for maintenance on a host, use one matcher, `host` = `192.168.1.150`. That covers every alert of that host.
3. Set the start and the duration (for example `2h`), your name as **Creator**, and a **Comment** with the reason.
4. Click **Preview Alerts** to see which current alerts would match, then **Create**.

To end early: open *Silences*, select it and click **Expire**.

### With amtool

```bash
# Silence everything on one host for 2 hours, starting now
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  silence add host=192.168.1.150 --duration=2h \
  --author="<your-name>" --comment="Planned maintenance: kernel update"

# List active silences (shows their IDs)
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  silence query

# End a silence early
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  silence expire <silence-id>
```

To schedule maintenance in advance, use `--start` with an RFC 3339 time instead of starting now, for example `--start=2026-10-10T20:00:00+02:00 --duration=2h`.

Matchers can be narrower: `alertname=ServiceSlow host=192.168.1.150` only mutes slowness on that host and keeps outage alerts active.

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
3. A silence created within the 15 minutes stops the escalation too.

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

### Add a receiver for one group

Every alert carries the `group` label from its target. To also notify the owning group directly, add a receiver:

```yaml
  - name: email-group-a
    email_configs:
      - to: '<group-a-contact>'
        send_resolved: true
        headers:
          Subject: '[GROUP-A] {{ .Status | toUpper }}: {{ .GroupLabels.alertname }} on {{ .GroupLabels.host }}'
```

Then add a route at the **top** of `routes:`, with `continue: true` so the alert still reaches the critical/warning/escalation routes below:

```yaml
  routes:
    - matchers:
        - group="group-a"
      receiver: email-group-a
      continue: true
    - matchers:
        - severity="critical"
      receiver: email-critical
      # ... existing routes stay as they are
```

Without `continue: true`, group-a alerts would **only** go to the group, and the NOC would stop seeing them.

**Apply and check:**

```bash
docker compose exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
docker compose restart alertmanager
docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  config routes test group=group-a severity=critical host=x alertname=Test
```

Expected receivers: `email-group-a,email-critical,email-escalation`.

---

## Add node_exporter for another host

Only do this on hosts where you are **allowed** to install software. For everything else, stay with black-box probes.

### 1. Run node_exporter on the host

With Docker, use the same version as the NOC:

```bash
docker run -d --name node-exporter --restart unless-stopped \
  --net host --pid host \
  -v /:/host:ro,rslave \
  prom/node-exporter:v1.12.1 --path.rootfs=/host
```

`--net host` (instead of `-p 9100:9100`) matters for the firewall step. Ports published with `-p` are handled by Docker's own iptables rules and **bypass ufw**.

### 2. Restrict port 9100 to the NOC

node_exporter has no authentication. Anyone who can reach port 9100 can read hardware details, mount points and network configuration of the host. Only noc-core needs it. With ufw on the monitored host:

```bash
ufw allow from <noc-core-ip> to any port 9100 proto tcp
ufw deny 9100/tcp
ufw status numbered
```

The `allow` rule must come before the `deny` (ufw evaluates rules in order).

**Check from noc-core** (it should work):

```bash
docker compose exec prometheus wget -qO- http://<host-ip>:9100/metrics | head -5
```

From any other machine, `curl http://<host-ip>:9100/metrics` should time out.

### 3. Add the host to the `node` job

In `prometheus/prometheus.yml`, add a second entry under `static_configs` of the `node` job:

```yaml
  - job_name: node
    static_configs:
      - targets: ['node-exporter:9100']
        labels:
          host: noc-core
          group: noc
      - targets: ['<host-ip>:9100']
        labels:
          host: <host-ip>
          group: group-a
```

Use **exactly the same `host` value** as this host's targets in `prometheus/targets/*.yml`. Grouping and the inhibit rules depend on it.

### 4. Apply and verify

```bash
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose restart prometheus
```

- *Status → Target health*: the `node` job shows the new target as **UP**.
- Query `node_filesystem_avail_bytes{host="<host-ip>"}`: it returns values.
- `DiskSpaceLow`, `DiskWillFillSoon` and `MonitoringCheckFailed` now cover this host automatically.

---

## Move the SMTP password into a secret file

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
