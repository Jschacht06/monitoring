# Operations and troubleshooting

Day-to-day commands, how to change things, backup, and a table of problems that really happened during the build. For the first installation, see [setup.md](setup.md).

Placeholders: `<logging-host-ip>` is the logging LXC's address. The commands assume the repo is in `/opt/monitoring` and the gateway's root certificate is saved as `/root/logging-root.crt` on the logging LXC.

## Daily commands

### Logging LXC (`cd /opt/monitoring/logging`)

```bash
docker compose ps                                   # loki and caddy should be Up
docker compose logs --tail 50 loki
docker compose logs --tail 50 caddy
docker compose restart caddy                        # after editing the Caddyfile
docker compose restart loki                         # after editing loki.yml
curl -s -o /dev/null -w '%{http_code}\n' --cacert /root/logging-root.crt https://<logging-host-ip>/ready    # 200
docker system df -v                                 # size of the loki_data volume
df -h /                                             # free disk space of the LXC
```

Always run `docker compose` commands from `/opt/monitoring/logging`, next to `compose.yaml`.

### noc-core (`cd /opt/monitoring`)

```bash
docker compose ps alloy
docker compose logs alloy --tail 30
docker compose logs alloy --since 10m | grep "level=error"      # no output = no errors
```

### Proxmox host

```bash
systemctl status alloy
journalctl -u alloy -n 30 --no-pager
```

### Quick health check of the whole chain

On noc-core (reads through the gateway as `noc`):

```bash
cd /opt/monitoring
curl -s --cacert alloy/logging-root.crt -u "noc:$(cat alloy/secrets/logging-password)" -G https://<logging-host-ip>/loki/api/v1/query_range --data-urlencode 'query={service="prometheus"}' --data-urlencode 'limit=1' | head -c 300
```

You should see a log line from the last minutes. For the `infra` side, use the login `infra` and `{service="ssh"}` or `{service="pveproxy"}`.

## Add a tenant

A tenant is one more login in the Caddyfile. Loki does not change.

1. Pick a short lowercase name. It becomes both the username and the tenant.
2. Make a password and a hash, exactly as in [setup.md step 3](setup.md#3-create-the-two-passwords-and-put-the-hashes-in-the-caddyfile). Store the password in the password manager.
3. Add a line to the `basic_auth` block of `logging/caddy/Caddyfile`:
   ```
   <name> <hash>
   ```
4. Restart the gateway: `docker compose restart caddy`. (A restart is the safe choice. Editors sometimes replace the file, and a single-file mount can keep serving the old one.)
5. Test the new login with the tests from [setup.md step 5](setup.md#5-prove-the-gateway-and-the-tenant-isolation): 200 with the right password, 401 with a wrong one, and the other tenants cannot see its lines.
6. For a source that should use the new tenant, copy an Alloy config and change `username` in `basic_auth`. The tracked configs use `noc` and `infra`.

## Change a password

1. Make a new password, store it in the password manager.
2. Make a new hash and replace that user's hash in `logging/caddy/Caddyfile`. Check it is 60 characters long.
3. `docker compose restart caddy`.
4. On the source, write the new password to the secret file with `printf` (no newline), as in [setup.md step 7.3](setup.md#73-password-file) or [8.3](setup.md#83-password-file). Then restart Alloy: `docker compose restart alloy` on noc-core, `systemctl restart alloy` on the Proxmox host.
5. Update the password in the Grafana data source, if one exists.
6. Check: the old password now gives 401, the new one 200.

## Add a log source (a new machine)

1. Decide which tenant it belongs to, or [add a tenant](#add-a-tenant).
2. Install Alloy: as a container (copy the `alloy` service) or as a package (as in [setup.md step 8](setup.md#8-alloy-on-the-proxmox-host-systemd-journal)). Use the same version everywhere.
3. Take the Alloy config that fits (`noc-core.alloy` for Docker logs, `proxmox-host.alloy` for a journal) and put it in the repo's `alloy/` folder if it is generic. Keep addresses, machine names and owner names **out** of it: use `LOGGING_URL`, `LOG_HOST`, `LOG_OWNER`.
4. Save the root certificate and the password file on the new machine, and set the three environment values.
5. Check with `label/service/values` and `label/host/values` as in [setup.md step 7.7](setup.md#77-prove-it). Check the new `host` value appears.
6. Update [security.md](security.md): what the new source collects and who can read it.

## Add a unit to the journal allow-list

Only `ssh`, `pveproxy` and `pvedaemon` are sent from the Proxmox host. To add another unit:

1. In `alloy/proxmox-host.alloy`, add the unit name (without `.service`) to the regex in the `loki.process "allowlist"` selector:
   ```
   selector = "{service!~\"ssh|pveproxy|pvedaemon|<unit>\"}"
   ```
2. Copy the file to `/etc/alloy/config.alloy` on the Proxmox host and run `systemctl restart alloy`.
3. Check with `label/service/values` as `infra`.

Think first about what the unit logs. More units means more personal data (see [security.md](security.md#what-is-collected)).

## Change the retention period

Retention is set in `logging/loki/loki.yml`:

```yaml
limits_config:
  retention_period: 168h
```

It applies to all tenants. After editing, run `docker compose restart loki`.

**How deletion works.** The compactor runs every 10 minutes, marks data older than `retention_period` and deletes it after a further 2 hours. So expect roughly `retention_period` + 2 hours (+ up to 10 minutes) before old data is really gone.

**Choosing a value.** The disk limits how much history fits. Measure the growth of `loki_data` (`docker system df -v`) over a few days and choose `retention_period` so that daily volume × days stays well under the disk size. 7 days (`168h`) is a placeholder until the real period is agreed.

### Proving that deletion works

> The procedure below follows Loki's documentation and has **not** been run yet.
>
> **Warning:** with a short test period, Loki deletes **all** logs older than that period in **every** tenant, not only the test line. Do this when you accept losing the existing history.

1. Set `retention_period: 1h`, then `docker compose restart loki`.
2. Push a marked line as `noc` (variables `H`, `C`, `NOCPW` as in [setup.md step 5](setup.md#5-prove-the-gateway-and-the-tenant-isolation)):
   ```bash
   $C -o /dev/null -w "%{http_code}\n" -u noc:$NOCPW -H 'Content-Type: application/json' -X POST https://$H/loki/api/v1/push \
     -d '{"streams":[{"stream":{"service":"retention-test","host":"logging"},"values":[["'$(date +%s%N)'","this line must disappear"]]}]}'   # 204
   ```
3. Read it back (it should be there):
   ```bash
   $C -u noc:$NOCPW -G https://$H/loki/api/v1/query_range --data-urlencode 'query={service="retention-test"}'
   ```
4. Wait about 3 hours (1 h retention + 2 h delete delay + compaction interval). Note the time of the push and the time of the check as evidence.
5. Query again with an explicit start before the push (the default window is short):
   ```bash
   $C -u noc:$NOCPW -G https://$H/loki/api/v1/query_range --data-urlencode 'query={service="retention-test"}' \
     --data-urlencode "start=$(date -d '6 hours ago' +%s)" --data-urlencode "end=$(date +%s)"
   ```
   The result must be empty.
6. Put the real `retention_period` back and run `docker compose restart loki`.

## Backup and restore

A backup must contain everything that cannot be rebuilt from Git. **Restore has not been tested yet.**

| What | Where | Why it matters |
|---|---|---|
| Plain passwords | Password manager | They are not stored anywhere else. |
| `logging/caddy/Caddyfile` | Logging LXC | Hashes and the tenant list. |
| `logging/compose.yaml` | Logging LXC | The address setting. |
| Docker volume `caddy_data` | Logging LXC | The gateway's CA **and private key**. If it is lost, every source needs the new root certificate. **Most important.** |
| Docker volume `loki_data` | Logging LXC | The stored logs. Optional; large. Copy it with Loki stopped, or use a container snapshot. |
| `compose.yaml`, `alloy/secrets/`, `alloy/logging-root.crt` | noc-core | The source side of noc-core. |
| `/etc/alloy/` and `/etc/default/alloy` | Proxmox host | The source side of the Proxmox host. |
| Grafana data volume | noc-core | The Grafana data sources, once they exist. |

The simplest approach is a Proxmox backup of the whole logging LXC, because the Docker volumes live inside the container's disk.

To copy only the gateway's CA volume (names start with the folder name, here `logging_`):

```bash
docker run --rm -v logging_caddy_data:/data -v /root/backup:/backup alpine tar czf /backup/caddy_data.tgz -C /data .
```

To restore on a new logging LXC: do [setup.md](setup.md) steps 1–2, put back `Caddyfile` and `compose.yaml`, restore the volume **before** the first `docker compose up`, then start. With the CA restored, no source needs a new certificate:

```bash
docker volume create logging_caddy_data
docker run --rm -v logging_caddy_data:/data -v /root/backup:/backup alpine tar xzf /backup/caddy_data.tgz -C /data
```

If the CA could not be restored, copy the new root certificate to every source (setup step 6) and restart all Alloys.

## Upgrade

> Not tested yet.

- **Loki or Caddy:** change the image tag in `logging/compose.yaml` (and in the template), then `docker compose pull && docker compose up -d`. Read the Loki release notes first for breaking changes. Check `/ready` afterwards.
- **Alloy container:** change the tag in the `alloy` service on noc-core, then `docker compose pull alloy && docker compose up -d alloy`.
- **Alloy package:** download the new `.deb` and run `apt install ./<file>.deb`. Check `journalctl -u alloy -n 30`.

Keep Loki, Caddy and Alloy tags pinned to exact versions. Update the version table in [configuration-reference.md](configuration-reference.md#versions-and-ports).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Caddy shows `Restarting (1)` | The Caddyfile is invalid. Typical: a **second global block** (`server block without any key is global configuration, and if used, it must be first`). | `docker compose logs caddy`. Keep exactly one global block at the top. |
| Every request fails with curl error 35 (`tlsv1 alert internal error`) | `default_sni` is missing from the global block. | Add `default_sni {$LOGGING_HOST}` (setup step 2.2) and `docker compose restart caddy`. |
| curl error 60 (certificate problem) | No root certificate given, or the wrong one. | Add `--cacert /root/logging-root.crt`. Check the fingerprint. |
| curl error 77 | The path given to `--cacert` does not exist. | Fix the path. |
| All status codes are `000` | Nothing answers: Caddy is down, wrong address, or the shell variable `H` is empty. | `docker compose ps`, check `echo $H`. |
| `bash: -u: command not found` or empty `$C` | The shell variable only exists in the terminal where it was set. | Set `H`, `CA`, `C` and the passwords again in the current terminal. |
| `/ready` returns 503 | Loki is still starting (about 20 seconds). | Wait and retry. If it stays: `docker compose logs loki`. |
| 401 with a password that should be right | Wrong password, or a damaged hash (`caddy validate` does not catch this; a real hash is 60 characters), or on a source a **trailing newline** in the password file. | Check the hash length (setup step 3). Rewrite the password file with `printf '%s'` and check `wc -c`. |
| Alloy log: `status=400 ... timestamp too old` right after the first start | Alloy sends each container's whole log history; Loki refuses lines older than 7 days. | Expected, once. Entries inside the 7-day window are accepted. No action. |
| Alloy log: `x509: certificate signed by unknown authority` | The `logging-root.crt` file is missing, empty or from an old CA. | Copy it again from the logging LXC and compare the fingerprints. |
| Alloy container does not start, or the secret/certificate is a folder | `alloy/logging-root.crt` or `alloy/secrets` did not exist when the container was created. | Remove the folder, create the file, `docker compose up -d alloy`. |
| Logs show `host="unknown"` or `owner="unknown"` | `LOG_HOST` or `LOG_OWNER` is not set for that Alloy. | Set it (compose `environment:` or `/etc/default/alloy`) and restart Alloy. |
| `infra` returns no services | No allow-listed activity in the last 12 hours, or the `alloy` user lacks the journal groups, or the service did not restart with the new config. | Log in to Proxmox or SSH once; run `id alloy` (must include `adm` and `systemd-journal`); `journalctl -u alloy -n 30`. |
| apt prints `Download is performed unsandboxed as root ... _apt` when installing the `.deb` | `_apt` cannot read files in `/root`. | Only a notice. Keep the file in `/tmp` to avoid it. |
| A grep for `401` in the Alloy log matches a timestamp | The digits `401` appear inside timestamps. | Grep for `status=401` instead. |
| Every client suddenly reports certificate errors | The `caddy_data` volume was deleted or recreated, so the gateway has a new CA. | Copy the new root certificate to every source and restart the Alloys. Restore from backup if you have the old volume. |
| The first `/ready` right after a Caddy restart returned 503 once | Not explained; it happened seconds after Caddy came up and did not repeat. | If a health check flaps later, read the Loki log at that time. An alert with `for: 2m` absorbs short blips. |
