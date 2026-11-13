# Proxmox host logs over the API

Alternative to installing Alloy on the Proxmox host in [setup step 8](../docs/setup.md#8-alloy-on-the-proxmox-host-systemd-journal).
Run this standalone Compose project on the **logging LXC**. The existing Alloy
on noc-core continues collecting Docker logs. Do not also collect the same host
journal with the host Alloy service.

Plan: grant API read access, install the collector files on the logging LXC,
provide certificates and credentials, run the read-only check, send one batch,
then start continuous collection and verify the `infra` tenant in Grafana.

## What is collected

The collector requests the structured journal for `ssh`, `pveproxy` and
`pvedaemon` separately using `GET /api2/json/nodes/{node}/journal` with `unit`
and `structured=1`. It polls every 15 seconds. On a fresh state volume, it asks
for the previous 12 hours. Entries retain the API's microsecond timestamp, which
is converted to Loki nanoseconds. Labels are `host`, `owner`, `service`, `level`.

**Compatibility gate:** the installed Proxmox API and mini-journalreader must
support the structured/unit options and the object format used by Proxmox
JournalView (`t`, `msg`, `p`, cursor records with `ty`/`c`). The preflight must
pass before starting collection. A product version alone does not prove the
installed packages expose those features. No unstructured fallback is silently
enabled, and no host update is performed by these instructions.

## 1. Administrator: credentials, permission and network

Use the Proxmox web UI; no package installation on the host is needed.

1. Datacenter > Permissions > Roles: create `NocLogReader` with only `Sys.Syslog`.
2. Create a dedicated service user, for example `noc-logs@pve`.
3. Add a user permission at `/nodes/<node>` for that user, role `NocLogReader`.
4. Create an API token for that user, token ID `journal`, with privilege
   separation enabled. Retain the secret shown once.
5. Add an API-token permission at `/nodes/<node>` for
   `noc-logs@pve!journal`, role `NocLogReader`. User and token both need the role;
   do not disable privilege separation to resolve a 403.
6. Allow logging LXC -> Proxmox API on TCP 8006. The collector publishes no port.
7. Choose the Proxmox TLS verification setting:
   - **CA mode (default):** supply the CA certificate/chain and its independently
     checked SHA-256 fingerprint. For default Proxmox certificates, the issuing
     CA is normally `/etc/pve/pve-root-ca.pem`. Use a URL in the server certificate's SANs.
   - **No Proxmox CA file:** explicitly set `PVE_TLS_VERIFY: "false"` in the local
     Compose environment. This is equivalent to curl --insecure: HTTPS encrypts
     traffic, but the server certificate/identity is not verified. The gateway
     connection retains its own CA verification.

`Sys.Syslog` grants node-wide log read access. The three selected units are a
collection filter, not an ACL limiting the token to those units. This access
must be agreed with the administrator of a shared host. An existing metrics
token with `PVEAuditor` may not have `Sys.Syslog`. An administrator-approved
existing token can be reused once its effective permissions include Sys.Syslog.

## 2. Logging LXC: install the files

Place `collector.py`, `Dockerfile`, `.dockerignore`, and
`compose-template.yaml` together in `/opt/monitoring/logging/proxmox-api`.
These can come from the repository after the change is published, or from the
copy-and-paste installer delivered with this change. **Local changes do not
arrive on another server with `git pull` until they have been pushed.**

Run the following as root on the logging LXC:

```bash
cd /opt/monitoring/logging/proxmox-api
cp -n compose-template.yaml compose.yaml
nano compose.yaml
```

Fill the five environment placeholders. `LOGGING_URL` is the gateway base URL
without `/loki/api/v1/push`. Set host/owner spelling to the Prometheus labels.
Keep `compose.yaml`, certificates and secrets private; they are Git-ignored.

```bash
install -d -o root -g 65534 -m 750 secrets
install -d -m 755 certs

read -rp 'API token ID (user@realm!token): ' TOKEN_ID
read -rsp 'API token secret: ' TOKEN_SECRET; echo
printf 'PVEAPIToken=%s=%s' "$TOKEN_ID" "$TOKEN_SECRET" > secrets/pve-token
unset TOKEN_ID TOKEN_SECRET

read -rsp 'Existing infra password: ' PW; echo
printf '%s' "$PW" > secrets/logging-password
unset PW

chown root:65534 secrets/pve-token secrets/logging-password
chmod 640 secrets/pve-token secrets/logging-password
```

This is the **infra** password already configured in Caddy, not the noc
password and not the Proxmox token secret. Secret files contain no newline.
The container runs as UID/GID 65534 and only reads the mounted secrets.

Install the existing gateway CA:

```bash
install -m 644 /root/logging-root.crt certs/logging-root.crt
```

For verified Proxmox TLS (`PVE_TLS_VERIFY: "true"`, the default), also save the
teacher-supplied Proxmox CA:

```bash
nano certs/proxmox-ca.crt
chmod 644 certs/proxmox-ca.crt
openssl x509 -in certs/proxmox-ca.crt -noout -subject -fingerprint -sha256
```

Paste the complete PEM CA certificate/chain into nano. Compare the fingerprint
with the teacher's value. In CA mode, both certificates and both secret files
must exist as regular files before running Compose.

### Alternative: work without a Proxmox CA file

Set this explicit option under the collector's `environment` in the local
`compose.yaml`:

```yaml
      PVE_TLS_VERIFY: "false"
```

Then `certs/proxmox-ca.crt` is not required and the collector logs that Proxmox
certificate verification is disabled. Traffic still uses HTTPS; server identity
and certificate validity are not checked. This setting affects only Proxmox.
Keep `certs/logging-root.crt` for the Loki gateway. Omitting the setting defaults
to verified Proxmox TLS. Values other than true/false are rejected.

## 3. Check, then send once

```bash
docker compose config -q
docker compose build proxmox-api
docker compose run --rm --no-deps proxmox-api --check
```

Expect `API check OK` for each unit and `infra login and certificate check OK`.
Zero sample entries is valid for an inactive unit. The check neither sends logs
nor changes progress. A 400 may mean unsupported journal options; stop and
inspect the installed API schema instead of starting a loop of failing polls.

Once preflight passes:

```bash
docker compose run --rm --no-deps proxmox-api --once
docker compose up -d proxmox-api
docker compose ps
docker compose logs --tail 30 proxmox-api
```

Expect `poll OK; delivered=N` and eventually a healthy container. `N=0` is
normal when there are no new entries. A file lock rejects a second poller using
the same state volume; `--check` can run while the main poller is active.

## 4. Grafana

Create a separate `Loki infra` source using the same gateway base URL and CA
as `Loki noc`, but username `infra` and the infra password. Keep TLS verification
on. Follow [the project's Grafana access decision](../docs/security.md#accepted-risks-and-known-limits)
before adding school-host logs to a shared organisation.

Select this source in Explore and query:

```logql
{host="<proxmox-host-label>", service=~"ssh|pveproxy|pvedaemon"}
```

Use a 12-hour range initially. Create ordinary permitted Proxmox login activity
if the selected services have not logged recently. The same query in the noc
source should not reveal the infra records.

## Progress, retries and limits

- Persistent volume `proxmox-log-api_collector_state` contains cursors, pending
  batches and last-success time. Back it up privately: pending batches contain
  host log content.
- A pending batch is written and fsynced before delivery. Batches are bounded
  to 100 entries / approximately 256 KiB. Each accepted sub-batch is checkpointed;
  the source cursor advances only after all its batches are accepted with 204.
- Delivery is **at least once**, not exactly once. A crash between acceptance
  and saving progress can replay the last batch. Ordinary restarts resume saved
  positions. Deleting/replacing the state volume replays the initial window.
- Source rotation, removed cursors or downtime exceeding host journal retention
  can cause gaps. This collector does not control host retention. Monitor failed
  polls; unread data is not guaranteed indefinitely.
- Loki rejects entries outside its ingestion age limits. Persistent 400/413
  failures retain pending data for diagnosis; no line is silently truncated or
  discarded. More than 10,000 records or a 16 MiB response stops the poll rather
  than silently skipping a large backlog. A fresh installation can reduce
  `INITIAL_LOOKBACK_SECONDS`; existing saved progress is deliberately retained.
- Changes to source identity, owner/host labels, or gateway require an explicit
  state review; the collector refuses to silently reuse different identities.
- Proxmox verification is on by default and can be explicitly disabled with
  PVE_TLS_VERIFY=false. The Loki gateway always uses CA/name verification. Redirects and environment
  proxies are disabled. Only counts and safe diagnostics are printed, not API
  tokens, passwords, response bodies or raw host log messages.

## Troubleshooting and rollback

| Result | Check |
|---|---|
| API 401 | Full token ID, secret, enabled user/token and expiration |
| API 403 | Sys.Syslog for both user and separated token at the correct node |
| API 400 or legacy text response | Structured/unit feature support in installed packages |
| Connection/TLS failure | Firewall/routing, issuer CA, URL matches certificate SAN |
| Loki 401 | Existing infra password, no newline, Caddy infra hash |
| Loki 400 | Log age/limits; inspect gateway/Loki logs locally |
| PermissionError | secrets directory 750 root:65534; files 640 root:65534; certs readable |
| unhealthy | Last successful complete poll is older than 180 seconds; inspect logs |

Stop only this collector with `docker compose stop proxmox-api` from its own
directory. Do not remove its volume when troubleshooting a restart. To return
to the host-Alloy method, stop this collector first, then follow setup step 8
with the same infra credentials and approved access scope.

## Local verification and sources

Run `python -B -m unittest discover -s logging/proxmox-api -p test_collector.py -v`
from the repository root. Tests exercise parsing, timestamp precision, empty
responses, malformed data, persistent delivery retries, partial batches,
restart recovery, decompression bounds, secret validation and safe errors.
TLS-context tests check that the no-CA setting requires no Proxmox CA file,
leaves Loki verification enabled, and preserves verified Proxmox TLS by default.
Passing synthetic tests is not evidence that the school's API supports the
required options: run the live preflight and Grafana acceptance above.

- [Proxmox node API schema](https://github.com/proxmox/pve-manager/blob/master/PVE/API2/Nodes.pm)
- [Proxmox JournalView structured response parsing](https://github.com/proxmox/proxmox-widget-toolkit/blob/master/src/panel/JournalView.js)
- [Proxmox API token permission model](https://github.com/proxmox/pve-docs/blob/master/pveum.adoc#api-tokens)
- [Proxmox API HTTPS listener](https://github.com/proxmox/pve-docs/blob/master/pveproxy.adoc)
- [Loki push API](https://grafana.com/docs/loki/latest/reference/loki-http-api/)
