# Configuration reference

What every setting in the logging setup does and why it is set that way. Paths are relative to the repository root unless stated otherwise. For the step-by-step build, see [setup.md](setup.md).

## Overview of the files

| File | In Git | Machine | Purpose |
|---|---|---|---|
| [`logging/loki/loki.yml`](../loki/loki.yml) | Yes | Logging LXC | Loki configuration. |
| [`logging/caddy/Caddyfile.template`](../caddy/Caddyfile.template) | Yes | Logging LXC | Template for the gateway configuration. |
| `logging/caddy/Caddyfile` | **No** | Logging LXC | The real gateway configuration with the password hashes. |
| [`logging/compose-template.yaml`](../compose-template.yaml) | Yes | Logging LXC | Template for the logging stack (Loki + Caddy). |
| `logging/compose.yaml` | **No** | Logging LXC | The real compose file; holds the logging server's address. |
| [`alloy/noc-core.alloy`](../../alloy/noc-core.alloy) | Yes | noc-core | Alloy config for the Docker logs. |
| [`alloy/proxmox-host.alloy`](../../alloy/proxmox-host.alloy) | Yes | Proxmox host | Alloy config for the systemd journal. |
| [`compose-template.yaml`](../../compose-template.yaml) (root) | Yes | noc-core | Template for the whole noc-core stack, including the `alloy` service. |
| `compose.yaml` (root) | **No** | noc-core | The real compose file; holds `LOGGING_URL`, `LOG_HOST`, `LOG_OWNER`. |

## logging/loki/loki.yml

Loki runs as one process ("monolithic") with all data on its own disk.

| Setting | Value | What it does and why |
|---|---|---|
| `auth_enabled` | `true` | Turns on multi-tenancy. Every request must carry the header `X-Scope-OrgID` (the tenant). Without it Loki answers 401 "no org id". The gateway sets this header, so clients never choose their tenant. |
| `server.http_listen_port` | `3100` | Loki's HTTP API. Not published outside the Docker network. |
| `server.grpc_listen_port` | `9096` | Internal gRPC port. Not published. |
| `server.log_level` | `info` | Loki's own log verbosity. |
| `common.instance_addr` | `127.0.0.1` | Single instance, so it advertises itself on localhost. |
| `common.path_prefix` | `/loki` | Base folder for all data. In the container this is the `loki_data` volume. |
| `common.storage.filesystem.chunks_directory` | `/loki/chunks` | Where the log content is stored. |
| `common.storage.filesystem.rules_directory` | `/loki/rules` | Folder for alerting rules (not used yet). |
| `common.replication_factor` | `1` | One copy. There is only one instance. |
| `common.ring.kvstore.store` | `inmemory` | The ring (instance bookkeeping) stays in memory because there is only one instance. |
| `schema_config` | tsdb, `v13`, from `2024-04-01`, index period `24h` | The storage format. `tsdb` with schema `v13` is the current recommended format. To change the schema later, **add** a new entry with a later `from` date; never edit the old one. |
| `limits_config.retention_period` | `168h` | **How long logs are kept**: 7 days, for all tenants. This is a placeholder until the real period is agreed. |
| `compactor.working_directory` | `/loki/retention` | Scratch folder of the compactor. |
| `compactor.compaction_interval` | `10m` | How often the compactor runs. |
| `compactor.retention_enabled` | `true` | Without this, nothing is ever deleted. |
| `compactor.retention_delete_delay` | `2h` | Safety delay between marking data for deletion and deleting it. |
| `compactor.delete_request_store` | `filesystem` | Required when retention is on. |
| `analytics.reporting_enabled` | `false` | No usage statistics are sent to Grafana Labs. |

Not in the file, but good to know: by default Loki **rejects log lines older than 7 days** when they arrive (`reject_old_samples`). That is why Alloy's first start prints a burst of "timestamp too old" errors. It is independent of the retention period.

Because of the compactor delay, deleted data does not disappear the moment it expires. Expect roughly `retention_period` + 2 hours (+ up to 10 minutes) before it is really gone.

## logging/caddy/Caddyfile

The gateway. The template is [`Caddyfile.template`](../caddy/Caddyfile.template); the only differences in the real file are the two password hashes. The tenant list is the `basic_auth` block.

### Global options (one block, at the top)

| Setting | What it does |
|---|---|
| `auto_https disable_redirects` | The address is internal, so Caddy must not try to get public certificates or open a port-80 redirect. |
| `skip_install_trust` | Do not try to install Caddy's root certificate into the container's trust store. |
| `default_sni {$LOGGING_HOST}` | The certificate to use when the client sends no server name. **Required.** Clients that connect to an IP send no server name, and behind Docker's port mapping Caddy sees the container address instead of the LAN address. Without it every connection fails with curl error 35. |

Only **one** global options block is allowed, and it must be first. A second block makes Caddy exit and the container restart in a loop.

### The site

| Directive | What it does |
|---|---|
| `https://{$LOGGING_HOST}` | The site address. `LOGGING_HOST` is an environment variable from `compose.yaml`: the logging LXC's address. The certificate is issued for exactly this value. |
| `tls internal` | Use Caddy's own local certificate authority. |
| `@delete path /loki/api/v1/delete*` + `handle @delete { respond "forbidden" 403 }` | Blocks Loki's delete API for everyone, **before** any login check. Placed first so a valid login cannot reach it. |
| `handle /ready { reverse_proxy loki:3100 }` | `/ready` is open: it only answers "ready" and lets a monitor check Loki without a password. |
| `handle /loki/api/v1/*` | The only path that carries data (push and query). |
| `basic_auth { noc <hash> infra <hash> }` | One login per tenant. **The username is the tenant name.** A password is stored as a bcrypt hash. |
| `reverse_proxy loki:3100 { header_up X-Scope-OrgID {http.auth.user.id} }` | Forwards to Loki and sets the tenant header to the username of the login. This **overwrites** any header the client sent. |
| `handle { respond "not found" 404 }` | Everything else (`/config`, `/metrics`, ...) returns 404. |

To add a tenant, add one line to `basic_auth` (see [operations-and-troubleshooting.md](operations-and-troubleshooting.md#add-a-tenant)).

`caddy validate` checks the syntax but does **not** notice a malformed password hash. A real bcrypt hash is exactly 60 characters.

## logging/compose-template.yaml

| Service | Setting | What it does |
|---|---|---|
| `loki` | `image: grafana/loki:3.7.8` | Pinned version. |
| | `command: -config.file=/etc/loki/loki.yml` | Use the mounted config. |
| | `./loki/loki.yml:/etc/loki/loki.yml:ro` | The config, read-only. The path is relative to the compose file's folder. |
| | `loki_data:/loki` | Named volume with all log data. |
| | no `ports:` | Loki is reachable only from the Docker network, i.e. only via Caddy. |
| `caddy` | `image: caddy:2.11.7` | Pinned version. |
| | `ports: "443:443"` | The only published port of the logging LXC. |
| | `LOGGING_HOST: <logging-host-ip>` | Becomes `{$LOGGING_HOST}` in the Caddyfile. Replace the placeholder in the real `compose.yaml`. |
| | `./caddy/Caddyfile:/etc/caddy/Caddyfile:ro` | The real Caddyfile. It must exist before `docker compose up`. |
| | `caddy_data:/data` | Keeps Caddy's local CA, so the root certificate stays the same across restarts and upgrades. |
| | `caddy_config:/config` | Caddy's autosaved configuration. |
| | `depends_on: loki` | Start order. |

Docker prefixes volume names with the project name, which is the folder name, for example `logging_loki_data` and `logging_caddy_data`.

## The `alloy` service in the root compose-template.yaml (noc-core)

| Setting | What it does |
|---|---|
| `image: grafana/alloy:v1.20.1` | Pinned version. The image runs as root, which is needed to read the Docker socket and the password file. |
| `LOGGING_URL` | The push URL: `https://<logging-host-ip>/loki/api/v1/push`. |
| `LOG_HOST` | Value of the `host` label. |
| `LOG_OWNER` | Value of the `owner` label. |
| `./alloy/noc-core.alloy:/etc/alloy/config.alloy:ro` | The config. The image runs `alloy run /etc/alloy/config.alloy` by default. |
| `./alloy/secrets:/etc/alloy/secrets:ro` | The folder with the password file. |
| `./alloy/logging-root.crt:/etc/alloy/logging-root.crt:ro` | The gateway's root certificate. |
| `/var/run/docker.sock:/var/run/docker.sock:ro` | Lets Alloy discover containers and read their logs. Read-only, but effectively root access to the host, see [security.md](security.md). |
| `alloy_data:/var/lib/alloy/data` | Remembers how far each log has been read, so a restart does not send everything again. |

Alloy's own web interface listens only on `127.0.0.1:12345` inside the container and is not published.

## alloy/noc-core.alloy

| Component | What it does |
|---|---|
| `local.file "logging_password"` | Reads `/etc/alloy/secrets/logging-password`. `is_secret = true` keeps the value out of Alloy's web interface and logs. |
| `discovery.docker "containers"` | Finds the containers on the host through the Docker socket. |
| `discovery.relabel "containers"` | Builds the labels. `service` is the container name; if the container has a compose service name, that name replaces it. `host` comes from `LOG_HOST` and `owner` from `LOG_OWNER`; a missing variable gives `unknown`. |
| `loki.source.docker "containers"` | Reads the logs of the discovered containers and applies the relabel rules. |
| `loki.write "logging"` | Sends to `LOGGING_URL` with basic authentication (user `noc`, password from the file). `ca_file` points at the gateway's root certificate. |

## alloy/proxmox-host.alloy

| Component | What it does |
|---|---|
| `local.file "logging_password"` | Reads `/etc/alloy/secrets/logging-password`. |
| `loki.relabel "journal"` | `service` = the systemd unit name without `.service`; `level` = the journal priority (`err`, `warning`, `info`, ...). |
| `loki.source.journal "host"` | Reads the journal. `max_age = "12h"` limits how far back it reads on the first start. Adds the labels `host` (`LOG_HOST`) and `owner` (`LOG_OWNER`). |
| `loki.process "allowlist"` | `stage.match` with `selector = {service!~"ssh|pveproxy|pvedaemon"}` and `action = "drop"`: **only these three units are sent**. Entries from any other unit, and entries without a unit, are dropped on the Proxmox host. |
| `loki.write "logging"` | Same as above, with user `infra`. |

Why a drop rule: the journal source's `matches` option combines conditions with AND and cannot express "this unit OR that unit". To ship another unit, add it to the regex (see [operations-and-troubleshooting.md](operations-and-troubleshooting.md#add-a-unit-to-the-journal-allow-list)).

The Alloy user must be in the groups `adm` and `systemd-journal`. The Debian package adds it to both.

## Environment variables for Alloy

| Variable | Used by | Meaning | Where it is set |
|---|---|---|---|
| `LOGGING_URL` | both configs | Push URL of the gateway | noc-core: `environment:` of the `alloy` service in `compose.yaml`. Proxmox host: `/etc/default/alloy`. |
| `LOG_HOST` | both configs | Value of the `host` label | same places |
| `LOG_OWNER` | both configs | Value of the `owner` label | same places |

`LOG_HOST` and `LOG_OWNER` should use the same spelling as the `host` and `owner` labels of your Prometheus targets.

## Secrets and generated files

| File or volume | Contains | Permissions / protection | If it is lost |
|---|---|---|---|
| Password manager entries | The plain passwords of `noc` and `infra` | — | Make new passwords, hashes and secret files (see [operations-and-troubleshooting.md](operations-and-troubleshooting.md#change-a-password)). |
| `logging/caddy/Caddyfile` | bcrypt hashes | git-ignored | Recreate from the template with new hashes. |
| `logging/compose.yaml` | The logging server's address | git-ignored | Recreate from the template. |
| Volume `caddy_data` | Gateway CA certificate and **private key** | Docker volume; treat as a secret | Caddy makes a new CA; **every client needs the new root certificate**. |
| Volume `loki_data` | All stored logs | Docker volume | Log history is gone. |
| `alloy/secrets/logging-password` (noc-core) | Password of `noc` | folder 700, file 600, git-ignored | Recreate with `printf`. |
| `alloy/logging-root.crt` (noc-core) | Root certificate (public) | git-ignored | Copy again from the logging LXC. |
| `/etc/alloy/secrets/logging-password` (Proxmox host) | Password of `infra` | `root:alloy`, folder 750, file 640 | Recreate with `printf`. |
| `/etc/alloy/logging-root.crt` (Proxmox host) | Root certificate (public) | — | Copy again. |
| `/etc/default/alloy` (Proxmox host) | `LOGGING_URL`, `LOG_HOST`, `LOG_OWNER` | — | Add the three lines again. |
| Volume `alloy_data` (noc-core) | Read positions | Docker volume | Alloy re-sends the history (one burst of "timestamp too old" errors). |

## Versions and ports

| Component | Version | Pinned in |
|---|---|---|
| Loki | 3.7.8 | `logging/compose-template.yaml` |
| Caddy | 2.11.7 | `logging/compose-template.yaml` |
| Alloy (container) | 1.20.1 | `compose-template.yaml` |
| Alloy (package) | 1.20.1-1 | the `.deb` you install on the Proxmox host |

| Port | Where | Reachable from |
|---|---|---|
| 443 | Logging LXC, Caddy | The LAN (published) |
| 3100, 9096 | Logging LXC, Loki | Only the Docker network of the logging stack |
| 12345 | Alloy web interface | Only inside the Alloy container / on the Proxmox host's localhost |
