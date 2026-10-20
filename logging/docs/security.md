# Security and access control

Who can read the logs, how that is enforced, what is collected, and what is not covered. For how the pieces connect, see [architecture.md](architecture.md).

## Layers of protection

| Layer | What it does | Shown to work |
|---|---|---|
| Network exposure | Only port 443 of the logging LXC is published. Loki's port 3100 exists only inside the Docker network. | Yes: `http://<logging-host-ip>:3100` refuses the connection. |
| HTTPS | The gateway uses its own CA. Without the root certificate a client gets a certificate error. | Yes: curl error 60 without `--cacert`. |
| Login per tenant | The API needs a username and password. No login or a wrong password gives 401. | Yes. |
| Tenant isolation | Caddy turns the username into the tenant and overwrites any `X-Scope-OrgID` header the client sends. | Yes: each tenant sees only its own lines, also with a spoofed header. |
| Reduced API surface | Only `/loki/api/v1/*` is forwarded. The delete API returns 403, `/config` and `/metrics` return 404. `/ready` is open and only answers "ready". | Yes. |
| Secrets handling | Password hashes live in the git-ignored `Caddyfile`; plain passwords only in a password manager and in root-only secret files on the sources. | Partly: file permissions are set as described in [setup.md](setup.md), not audited. |

"Shown to work" refers to real output from the servers, see the status table in [README.md](README.md#status--20-october-2026).

## Passwords and files

| Secret | Where | Protection |
|---|---|---|
| Plain passwords of `noc` and `infra` | Password manager | Never written into Git or chat. |
| bcrypt hashes | `logging/caddy/Caddyfile` | Git-ignored. A hash is not reversible, but it can be attacked offline, so use long random passwords (`openssl rand -base64 24`). |
| Password on noc-core | `alloy/secrets/logging-password` | Git-ignored, directory mode 700, file mode 600. The Alloy container runs as root and can read it. |
| Password on the Proxmox host | `/etc/alloy/secrets/logging-password` | Owner `root`, group `alloy`, mode 640. |
| Gateway CA private key | Docker volume `caddy_data` on the logging LXC | Anyone with access to the Docker host can read it. Back it up like a secret. |
| Root certificate | `logging-root.crt` on every client | Public, no protection needed. Git-ignored on noc-core only to keep the repo free of environment files. |

## What is collected

| Tenant | Content | May contain |
|---|---|---|
| `noc` | stdout/stderr of every container on noc-core: Prometheus, Grafana, Alertmanager, Blackbox, node-exporter, pve-exporter, Alloy | Monitored target URLs, Grafana login events (usernames, source IPs), notification errors (mail server names, recipients). |
| `infra` | Journal entries of the units `ssh`, `pveproxy` and `pvedaemon` | SSH and Proxmox login attempts: usernames and source IP addresses. |

Everything else in the journal is dropped inside Alloy, before it leaves the Proxmox host.

Retention is a single global period for all tenants. The configured value (7 days) is a placeholder until the real period is agreed. Loki also refuses lines that are older than 7 days when they arrive.

A full privacy and retention analysis is **not written yet**.

## Accepted risks and known limits

| Item | Explanation |
|---|---|
| Access is per tenant, not per person | A tenant login is shared by everything that uses it. There is no per-person audit trail. |
| Grafana can query every data source it holds | Grafana's data source permissions (restricting which users may query which data source) are an Enterprise/Cloud feature. In free Grafana the Viewer role can query data sources directly, and Grafana users in the same organisation can therefore read both tenants once both data sources exist. **Open decision:** put the `infra` data source in a separate Grafana organisation with only admins as members, or accept that everyone with a Grafana account can read both tenants. |

Source for the Grafana limit: [Grafana documentation, roles and permissions (v13.2)](https://grafana.com/docs/grafana/v13.2/administration/roles-and-permissions.md).
