# Operations and troubleshooting

All commands run on noc-core from the stack folder:

```bash
cd /opt/monitoring
```

## Daily commands

| Task | Command |
|---|---|
| Status of all containers | `docker compose ps` |
| Logs of one service (last 50 lines, follow) | `docker compose logs --tail=50 -f prometheus` |
| Errors of the last hour, all services | `docker compose logs --since 1h \| grep -i -E "error\|fail"` |
| Validate `prometheus.yml` (and the rule files it loads) | `docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml` |
| Validate only the alert rules | `docker compose exec prometheus promtool check rules /etc/prometheus/rules/alerts.yml` |
| Validate `alertmanager.yml` | `docker compose exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml` |
| Validate `blackbox.yml` | `docker compose exec blackbox blackbox_exporter --config.check --config.file=/etc/blackbox/blackbox.yml` |
| Show the routing tree | `docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 config routes show` |
| Which receiver gets an alert? | `docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 config routes test severity=critical host=x alertname=Test` |
| Active alerts (add `--silenced` or `--inhibited` to see muted ones) | `docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 alert query` |
| Active silences | `docker compose exec alertmanager amtool --alertmanager.url=http://localhost:9093 silence query` |
| Validate `compose.yaml` | `docker compose config --quiet && echo OK` |

Quick health check in Prometheus (`http://<noc-core-ip>:9090`):

```promql
up == 0               # scrape failures: monitoring itself is broken
probe_success == 0    # services that are down right now
```

## How to apply a change

Each file is read at a different moment, so each change needs a different action. Using the wrong one is the most common reason a change "does nothing".

| What you changed | What to run | Why |
|---|---|---|
| `compose.yaml`: image tags, ports, `command:` flags (for example retention or `--web.external-url`), volumes, new services | `docker compose up -d` | Flags and mounts are fixed when a container is **created**. `up -d` recreates only the services whose definition changed. `restart` reuses the old container with the old flags. |
| `prometheus/prometheus.yml` | `docker compose restart prometheus` | Mounted file, read at startup. |
| `prometheus/rules/*.yml` | `docker compose restart prometheus` | Rule files are read at startup too. |
| `prometheus/targets/*.yml` | **nothing** | file_sd picks up changes by itself within a minute. |
| `blackbox/blackbox.yml` | `docker compose restart blackbox` | Mounted file, read at startup. |
| `alertmanager/alertmanager.yml` or the SMTP secret file | `docker compose restart alertmanager` | Mounted file, read at startup. Silences and the notification log survive (they are in the `alertmanager_data` volume). |
| Grafana data sources or dashboards | nothing (done in the UI) | Stored in the `grafana_data` volume. |

Always validate **before** restarting (see the table above). A service with a broken config doesn't start, and while Prometheus or Alertmanager is down, no alerts go out.

Alternative without a restart: Prometheus and Alertmanager reload their config on `SIGHUP`. If the new config is invalid, they log an error and keep running with the old one:

```bash
docker compose kill -s SIGHUP prometheus
docker compose kill -s SIGHUP alertmanager
```

Single-file mount caveat: `blackbox.yml` is mounted as a **single file**. Some editors save by writing a new file and renaming it, and the running container then keeps seeing the old version. If a Blackbox change doesn't show after a restart, recreate the container: `docker compose up -d --force-recreate blackbox`. Prometheus and Alertmanager mount whole folders and are not affected.

## Troubleshooting

### Problems seen in this project

| Symptom | Cause | Fix |
|---|---|---|
| "View in Alertmanager" in emails or links in the Alertmanager UI point to a container ID or don't open | `--web.external-url` is missing on Alertmanager, or it was added but applied with `restart` (which keeps the old flags). | Set `--web.external-url=http://<noc-core-ip>:9093` in `compose.yaml` and run `docker compose up -d`. |
| The **Source** link on an alert in Alertmanager points to a container ID | That link comes from **Prometheus**, which has no `--web.external-url` in `compose-template.yaml`. | Add `- --web.external-url=http://<noc-core-ip>:9090` to the Prometheus `command:` in your `compose.yaml` and run `docker compose up -d`. Not part of the template yet. |
| `up` is 1 but the service is clearly down | Expected. For blackbox targets, `up` only means Prometheus could scrape the Blackbox Exporter. | Look at `probe_success` (0 = down). See [up vs probe_success](adding-targets.md#up-vs-probe_success). |
| No resolved email after a silence expires | Expected. The alert resolved while it was silenced, so Alertmanager has nothing to report when the silence ends. | Nothing to fix. Check the Prometheus *Alerts* page or `probe_success` to confirm the state. |
| Memory from node_exporter on noc-core shows the Proxmox host's memory, not the LXC limit | **Known limitation.** An LXC shares the Proxmox kernel. node_exporter runs in a Docker container inside the LXC and reads `/proc/meminfo` there, which shows kernel-wide values rather than the LXC's memory limit. | Use disk metrics (they are correct) and treat memory as indicative only. Per-LXC CPU/memory quotas need the Proxmox API exporter (**planned**). |
| A config change has no effect | The wrong apply action was used. | See [How to apply a change](#how-to-apply-a-change). |

### Other checks

- **No emails at all:** `docker compose logs alertmanager | grep -i -E "notify|smtp|error"`. The usual causes are an authentication failure (wrong or revoked app password) and a wrong `smtp_smarthost`. Send a test alert as in [setup.md](setup.md#9-test-the-email-path).
- **Alert stays Pending:** the condition has not been true for the whole `for:` period yet. Rules are evaluated every minute, so add up to 1 minute.
- **Alert fires in Prometheus but no email:** check whether it is silenced or inhibited on the Alertmanager *Alerts* page, and which route it takes with `amtool config routes test <labels>`.
- **New target doesn't appear:** YAML error in the target file. Prometheus logs it and keeps the last good version: `docker compose logs prometheus --since 10m | grep -i file`.

## Security notes

- **Secrets are not committed.** `compose.yaml`, `alertmanager/alertmanager.yml` (SMTP password) and everything else in `alertmanager/` except `template.yml` are in `.gitignore`. Real target files (`prometheus/targets/*.yml` except `template.yml`) are ignored too, because they reveal internal addresses. Run `git status` before every commit and check that none of these are listed.
- **Use an app password**, never your main email password, and prefer `smtp_auth_password_file` ([how-to](how-to-guides.md#move-the-smtp-password-into-a-secret-file)). Revoke the app password if it ever leaks, for example in a screenshot or a commit.
- **No authentication** on Prometheus (9090) or Alertmanager (9093). Anyone who can reach them can read all metrics and create or delete silences. Keep these ports on the LAN or behind a firewall or VPN, never on the internet.
- **Grafana:** change the default `admin` password at first login (Grafana forces this).
- **Exporters are internal.** Blackbox (9115) and node_exporter on noc-core (9100) have no published ports, so only Prometheus can reach them. On other hosts, restrict node_exporter's port 9100 to noc-core ([how-to](how-to-guides.md#add-node_exporter-for-another-host)). Metrics endpoints expose system details and are not meant for public exposure.
- **Least privilege:** all config mounts are read-only (`:ro`), and node_exporter only gets read-only access to the host filesystem.
