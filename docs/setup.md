# Setup from scratch

This guide takes you from an empty Proxmox host to a running noc-core stack that probes services and sends alert emails. Each step ends with a check that tells you what you should see before you continue.

Placeholders used in this guide:

| Placeholder | Meaning |
|---|---|
| `<noc-core-ip>` | IP address of the noc-core LXC on your LAN |
| `<vmid>` | Proxmox container ID of the LXC |
| `<your-gmail-address>` | The Gmail account that sends the alerts |
| `<your-gmail-app-password>` | A Gmail app password (not your normal password) |
| `<alert-recipient>` | Inbox that receives alerts |

> **Never commit real values.** `compose.yaml` and `alertmanager/alertmanager.yml` are in `.gitignore` for that reason.

---

## 1. Prerequisites

### Proxmox LXC

| LXC | vCPU | RAM | Swap | Root disk |
|---|---|---|---|---|
| noc-core | 2 | 2–4 GB | 512 MB | 30 GB |

Why these numbers: Prometheus keeps recent data in memory and writes everything to disk. Retention is capped at 45 days or 10 GB (whichever comes first, see `compose.yaml`), so 30 GB leaves room for Docker images, Grafana and the OS.

Docker inside an LXC needs **nesting** enabled. On the Proxmox host:

```bash
pct set <vmid> --features nesting=1,keyctl=1
pct reboot <vmid>
```

`keyctl=1` is usually also needed when the LXC is unprivileged. You can set both in the web UI too: *Container → Options → Features*.

### Software inside the LXC

Everything below runs as root inside noc-core.

```bash
apt update && apt upgrade -y
apt install -y git curl
bash <(wget -qO- https://get.docker.com)
```

The last line is Docker's official convenience script. It installs Docker Engine and the Compose plugin (`docker compose`, with a space).

**Check:**

```bash
docker --version
docker compose version
docker run --rm hello-world
```

You should see version numbers for both, and `hello-world` should print "Hello from Docker!". If `hello-world` fails with a permission or `keyctl` error, go back and check the LXC features.

---

## 2. Clone the repo

The rest of the docs assume the stack lives in `/opt/monitoring`. `/opt` is the standard Linux location for self-contained software. Unlike a home folder such as `/root`, it isn't tied to one user, so the same path works on an LXC, a VM or bare metal.

```bash
git clone https://github.com/Jschacht06/monitoring.git /opt/monitoring
cd /opt/monitoring
```

**Check:** `ls` shows `compose-template.yaml`, `alertmanager/`, `blackbox/` and `prometheus/`.

---

## 3. Create `compose.yaml`

The tracked file is a template. The real `compose.yaml` is ignored by Git because it holds your host address.

```bash
cp compose-template.yaml compose.yaml
nano compose.yaml
```

Change one line in the `alertmanager` service:

```yaml
      - --web.external-url=http://<noc-core-ip>:9093
```

Why: Alertmanager puts this URL into emails ("View in Alertmanager") and uses it for links in its UI. Without it, the links point to the container's internal hostname and do not work from your browser.

**Check:**

```bash
docker compose config --quiet && echo OK
```

You should see `OK`. A YAML error here (for example `volumes must be a mapping`) usually means a missing colon or wrong indentation. See [operations-and-troubleshooting.md](operations-and-troubleshooting.md#troubleshooting).

---

## 4. Create `alertmanager.yml` and add the SMTP app password

```bash
cp alertmanager/template.yml alertmanager/alertmanager.yml
nano alertmanager/alertmanager.yml
```

Fill in the `global:` block. For Gmail:

```yaml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: '<your-gmail-address>'
  smtp_auth_username: '<your-gmail-address>'
  smtp_auth_password: '<your-gmail-app-password>'
```

- **The app password goes in `smtp_auth_password`.** Create it in your Google account under *Security → 2-Step Verification → App passwords*. Gmail does not accept your normal password over SMTP.
- Port 587 uses STARTTLS. Alertmanager requires TLS by default (`smtp_require_tls` defaults to `true`), so the password is never sent in plain text.

Then replace every `to: 'you@example.com'` under `receivers:` with `<alert-recipient>`. There are four receivers: `default`, `email-critical`, `email-warning` and `email-escalation`. In real use, `email-escalation` should go to a second person.

> The password is stored in plain text in this file. That is acceptable for a first test, because the file is ignored by Git. To move it into a separate secret file, see [how-to-guides.md](how-to-guides.md#move-the-smtp-password-into-a-secret-file).

**Check:**

```bash
git status --short
```

`alertmanager/alertmanager.yml` and `compose.yaml` must **not** be listed. If they are, stop and fix `.gitignore` before you do anything else.

---

## 5. Add your first targets

Prometheus reads probe targets from `prometheus/targets/*.yml`. The template file is all comments, so it adds nothing. Create a real file for the NOC itself. Prometheus and Grafana are probed through their health endpoints on the Docker network:

```bash
cat > prometheus/targets/noc.yml <<'EOF'
# One block per (module, host/service). Add targets to a block, or copy a block.
- targets:
    - http://prometheus:9090/-/healthy
    - http://grafana:3000/api/health
  labels:
    module: http_2xx
    group: noc
    service: noc-selftest
    host: noc-core
EOF
```

Real target files are ignored by Git, because they contain internal addresses. To add other services, see [adding-targets.md](adding-targets.md).

---

## 6. Start the stack

```bash
docker compose up -d
```

`-d` runs the containers in the background. Compose creates the five services and three named volumes:

| Service | Image | Port on noc-core |
|---|---|---|
| prometheus | `prom/prometheus:v3.13.3` | 9090 |
| grafana | `grafana/grafana:13.2.2` | 3000 |
| blackbox | `prom/blackbox-exporter:v0.28.0` | none (internal, 9115) |
| alertmanager | `prom/alertmanager:v0.34.1` | 9093 |
| node-exporter | `prom/node-exporter:v1.12.1` | none (internal, 9100) |

**Check:**

```bash
docker compose ps
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose exec prometheus promtool check rules /etc/prometheus/rules/alerts.yml
docker compose exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
```

- `ps`: all five services have the status `Up` (not `Restarting`).
- `promtool check config`: `SUCCESS`, and it finds 1 rule file.
- `promtool check rules`: `SUCCESS: 5 rules found`.
- `amtool check-config`: `SUCCESS`, and it lists 4 receivers and 1 inhibit rule.

If a container keeps restarting, read its log: `docker compose logs --tail=50 <service>`.

---

## 7. Open each UI

### Prometheus: `http://<noc-core-ip>:9090`

**Check:**

- *Status → Target health* (called *Targets* in older versions) shows three jobs: `prometheus`, `node` and `blackbox`. All should be **UP**.
- In the query box, run `probe_success`. Each blackbox target should return `1`.
- *Alerts* lists the five rules in three groups (`availability`, `capacity`, `monitoring-health`), all **inactive**.
- `http://<noc-core-ip>:9090/api/v1/alertmanagers` lists `alertmanager:9093` under `activeAlertmanagers`. That proves Prometheus can reach Alertmanager.

> `UP` on a blackbox target only means Prometheus could reach the Blackbox Exporter. Whether the service itself is healthy is in `probe_success`. See [adding-targets.md](adding-targets.md#up-vs-probe_success).

### Alertmanager: `http://<noc-core-ip>:9093`

**Check:** the UI loads with no alerts. *Status* shows your loaded config. The Alertmanager UI has **no login**, so keep port 9093 on the LAN.

### Grafana: `http://<noc-core-ip>:3000`

First login is `admin` / `admin`. Grafana makes you set a new password right away.

**Check:** you get to the Grafana home page.

---

## 8. Add the Prometheus data source in Grafana

1. Go to *Connections → Data sources → Add data source → Prometheus*.
2. Set the URL to `http://prometheus:9090`.
   Use the service name, not `localhost` or the LXC IP. Grafana runs in its own container and reaches Prometheus over the Docker network.
3. Click **Save & test**.

**Check:**

- Grafana reports that it successfully queried the Prometheus API.
- In *Explore*, select the Prometheus data source and run `up`. You should see one series per target, with the value `1`.

Dashboards are not stored in this repo yet (dashboards as code is planned). Anything you build in the UI lives in the `grafana_data` volume.

---

## 9. Test the email path

Send a fake alert straight to Alertmanager, so you don't need to switch anything off:

```bash
docker compose exec alertmanager amtool alert add alertname=TestAlert host=test severity=critical \
  --annotation=summary="Test alert" --alertmanager.url=http://localhost:9093
```

**Check:**

- The alert appears in the Alertmanager UI.
- After about 30 seconds (`group_wait` of the critical route), an email arrives with a subject like `[CRITICAL] FIRING: TestAlert on test`.
- If nothing arrives, run `docker compose logs alertmanager` and look for SMTP errors (wrong app password, wrong `smtp_smarthost`).

Fake alerts expire on their own after a few minutes. You then also get a `RESOLVED` email, because `send_resolved: true` is set.

Because the alert is critical, it also matches the escalation route. That route waits 15 minutes, so the `[ESCALATED]` email only arrives if the alert is still active by then. To test escalation, see [how-to-guides.md](how-to-guides.md#add-or-change-the-escalation).

---

## 10. Test a real alert (optional but recommended)

1. Add a target for a service you control (see [adding-targets.md](adding-targets.md)) and wait until `probe_success` is `1`.
2. Switch the service off.
3. Expected timeline:
   - `probe_success` drops to `0` within about 30 s (the scrape interval).
   - `ServiceDown` is **Pending** in Prometheus *Alerts*.
   - About 2 minutes later (`for: 2m`) it becomes **Firing** and shows up in Alertmanager.
   - About 30 s later (`group_wait`), the `[CRITICAL]` email arrives. That is roughly 3 minutes in total.
4. Switch the service back on. The alert clears and a `RESOLVED` email arrives.

You are done. Next steps:

- [adding-targets.md](adding-targets.md): monitor your services
- [operations-and-troubleshooting.md](operations-and-troubleshooting.md): day-to-day commands
