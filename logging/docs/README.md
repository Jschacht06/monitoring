# Logging documentation

Central log collection for the noc-core monitoring stack. **Loki** stores the logs, a **Caddy gateway** is the only way in (HTTPS plus one login per tenant), and **Alloy** ships logs from the machines you want to watch. Grafana reads the logs through the same gateway.

Two log sources are set up:

- the Docker container logs of the noc-core stack, and
- the systemd journal of the Proxmox host (only a short allow-list of units).

| Guide | What it covers |
|---|---|
| [architecture.md](architecture.md) | How the pieces fit together, what a tenant is, the labels, where every file lives and why. **Read this first.** |
| [setup.md](setup.md) | Step by step from an empty Proxmox host to working logs, with a check after every step. |
| [configuration-reference.md](configuration-reference.md) | Every setting in `loki.yml`, the Caddyfile, the compose files and the two Alloy configs. |
| [operations-and-troubleshooting.md](operations-and-troubleshooting.md) | Daily commands, adding a tenant or a log source, changing passwords and retention, backup, upgrades, and a table of problems that really happened. |
| [security.md](security.md) | Who can read what, how that is enforced, what is collected, and the known limits. |
