# Smith resource metrics and approved budgets

This guide supplies the data for [the health and usage dashboards](health-and-usage-dashboards.md#7-prepare-smith-resource-metrics). It adds a Proxmox API exporter to noc-core, without installing software on Smith, and records which guests belong to each group and what budget was approved.

**Status: proposed, not tested on this deployment.** The repo currently has Blackbox and Node Exporter monitoring, with optional physical-host hardware exporters. Its Compose and Prometheus templates do not enable a Proxmox API exporter. Complete the checks below on a home/test setup, then repeat them within the approved school scope. The supplied rules template is outside Prometheus's loaded rule directory and has no effect until you create and validate a local copy.

All commands below run as root **inside noc-core**, from `/opt/monitoring`. Proxmox account, permission, certificate and shared-firewall changes belong to the platform administrator. The NOC assignment and [Smith rules in the course repo](https://github.com/JollyJones101/network-experience-2627/blob/main/docs/04-smith-proxmox.md) require approved host/agent access and do not grant cluster administration rights.

Placeholders used in this guide:

| Placeholder | Meaning |
|---|---|
| `<smith-api-host>` | Approved API DNS name, with no `https://`, path or port; TLS certificate must match it |
| `<smith-node-name>` | Exact, case-sensitive `node` value returned by the API, which can differ from the display name Smith |
| `<approved-image-digest>` | SHA-256 digest of the reviewed PVE exporter image |
| `<monitoring-user>@pve` | Dedicated read-only account provided by the administrator |
| `<token-name>` / `<token-secret>` | API token ID component and secret, stored outside Git |
| `<group-name>` | Existing catalogue group label, e.g. `noc` or `group-a` |
| `<type>/<vmid>` | Exact guest ID, e.g. `lxc/101` or `qemu/102` |
| `<same-host-label-as-probes>` | Existing stable `host` value for that guest |

---

## 1. Agree the scope and budget source

Before enabling the collector, record the following with the platform administrator and owning groups:

| Required input | Why it matters |
|---|---|
| Authorized guest/pool list and whether host/storage totals may be read | A working token can still expose only part of the intended inventory |
| Read-only API token, expiry and rotation owner | Metrics need audit access, not VM lifecycle/configuration rights |
| API connectivity from noc-core to TCP 8006 | The exporter calls Proxmox; Grafana does not |
| Trusted server certificate or approved CA bundle | Keep TLS certificate verification enabled |
| Exact node name and guest IDs | Scope/matching is case-sensitive and uses `id`, not an IP address |
| Guest → group → catalogue host mapping | Services cannot identify a VMID automatically |
| Approved vCPU, RAM and disk budget per group | Guest sizes do not reveal the group's approved maximum |
| Disk policy: all provisioned volumes, snapshots, backups, shared volumes | A root-disk size is not a complete group storage budget |

Use the approved [resourcebudget document from the course repo](https://github.com/JollyJones101/network-experience-2627/blob/main/docs/templates/resourcebudget-template.md) as the reference. Confirm units: **GiB = bytes / 1073741824**, **GB = bytes / 1000000000**. The templates use byte metrics displayed as IEC units. For a budget agreed in GiB, multiply by 1073741824 before writing the rule value.

For this first dashboard, disk allocation is a reviewed sum of provisioned guest disks. Document which extra disks are included. Physical Ceph/ZFS usage, snapshot growth, replication and backup consumption need an additional approved source if the budget charges those quantities. Do not present the first disk bar as full physical storage accounting.

Include stopped guests in allocation totals unless the budget owner explicitly uses a different policy. Decide how VM templates are charged too: the supplied live scope excludes `template="1"`; include them separately in reviewed disk inventory if the disk policy charges their volumes, and describe that choice.

**Check:** there is a dated scope/budget decision and a complete guest list. If credentials or access are pending, the service-health dashboard can still proceed; leave Smith live usage pending instead of inferring it from noc-core's Node Exporter.

---

## 2. Have the administrator provide a scoped API token

Ask for a dedicated monitoring account and a token with **Privilege Separation** enabled. The administrator grants the necessary read-only/audit rights to **both the account and token** on the approved guest/pool paths and any required node/API paths. The effective token rights cannot exceed the account's rights. Use the administrator's least-privilege role/scoping decision, with `PVEAuditor` as the read-only reference; see [Proxmox's own user-management source](https://github.com/proxmox/pve-docs/blob/master/pveum.adoc).

The exporter upstream describes a broad read-only setup at `/`. That is not an instruction to grant global access on the school cluster. Start with the administrator-approved scope and the resource-only collector below. If an endpoint denies access or filters guests, have the administrator inspect the precise endpoint/ACL requirement. Do not resolve a 403 by using a root token, disabling privilege separation or increasing permissions yourself.

Keep the token secret in the agreed secret store. The exporter uses the separate `user`, `token_name` and `token_value` fields; it does not require a student/admin password. The full token identity for permissions is `<monitoring-user>@pve!<token-name>`, but the YAML's `token_name` field is only `<token-name>`.

**Check:** the administrator confirms the read-only scope and permitted API endpoint(s), token expiry and certificate trust. Do not put the token in a screenshot, dashboard JSON or a command-line argument.

---

## 3. Prepare local files and a reviewed exporter image

Take the configuration backup from [step 2 of the dashboard guide](health-and-usage-dashboards.md#2-preserve-the-catalogue-and-current-configuration). Then:

```bash
cd /opt/monitoring
mkdir -p pve-exporter
chmod 700 pve-exporter
nano pve-exporter/pve.yml
```

Put the following in the file and replace the credential placeholders locally:

```yaml
default:
  user: '<monitoring-user>@pve'
  token_name: '<token-name>'
  token_value: '<token-secret>'
  verify_ssl: true
```

`pve-exporter/` and `prometheus/rules/smith-resources.yml` are ignored by this repo. If you apply these instructions on an older checkout, add those two paths to its `.gitignore` first. An ignore rule does not remove a file already tracked by Git; check before entering credentials.

The upstream image runs as a non-root user (currently UID/GID 101). Check the chosen release's actual identity in step 4. For that image, allow only its group to read the credential file:

```bash
chown root:101 pve-exporter/pve.yml
chmod 640 pve-exporter/pve.yml
```

The root-owned directory remains mode 700 on noc-core. If the chosen image uses a different identity, adjust the file group to its documented GID; do not make the credential file world-readable.

For a private CA, obtain the approved PEM CA bundle from the administrator and save it as `pve-exporter/pve-ca.pem`. It must contain certificates, not a private key. Make it readable by the exporter:

```bash
chmod 644 pve-exporter/pve-ca.pem
```

If the API already uses a certificate trusted by the image, omit the CA mount/environment setting in step 4. Otherwise `REQUESTS_CA_BUNDLE` points the API client's HTTPS requests at the approved bundle. Use the API DNS name matching the certificate, not an IP unless the certificate includes that IP. Keep `verify_ssl: true`.

Choose a reviewed release from the [PVE exporter project](https://github.com/prometheus-pve/prometheus-pve-exporter). Before using the snippet below, obtain its image digest:

```bash
docker pull prompve/prometheus-pve-exporter:<reviewed-release-tag>
docker image inspect prompve/prometheus-pve-exporter:<reviewed-release-tag> \
  --format '{{index .RepoDigests 0}}'
```

Copy the digest's hexadecimal portion after `sha256:` into `<approved-image-digest>`. Record the release/digest with the test results; avoid a floating `latest` tag for the installed service.

**Check:** the credential file and any CA bundle exist outside Git tracking. The image reference is recorded. Do not commit the local configuration backup or private files.

---

## 4. Add the exporter to the existing Compose file

Edit the existing `compose.yaml`. Add this entry under **its existing `services:` mapping**, at the same indentation as `grafana:`. Keep all existing services, volumes, targets and flags.

```yaml
  pve-exporter:
    image: prompve/prometheus-pve-exporter@sha256:<approved-image-digest>
    restart: unless-stopped
    init: true
    command:
      - --config.file=/etc/prometheus/pve.yml
      - --collector.resources
      - --no-collector.status
      - --no-collector.version
      - --no-collector.node
      - --no-collector.cluster
      - --no-collector.backup-info
      - --no-collector.qdevice
      - --no-collector.config
      - --no-collector.replication
      - --no-collector.subscription
    volumes:
      - ./pve-exporter/pve.yml:/etc/prometheus/pve.yml:ro
      - ./pve-exporter/pve-ca.pem:/etc/prometheus/pve-ca.pem:ro
    environment:
      REQUESTS_CA_BUNDLE: /etc/prometheus/pve-ca.pem
```

For public/system-trusted TLS, omit only the CA volume line and the `environment:` block. The exporter has **no published host port**; Prometheus reaches `pve-exporter:9221` on the existing Compose network. It connects to the Proxmox API at TCP 8006. It needs no Docker socket, privileged mode or Smith host mount.

The flags select resource collection and disable unrelated status/config/backup collectors. Check them against the pinned image's `--help` before starting it; the current upstream [CLI source](https://github.com/prometheus-pve/prometheus-pve-exporter/blob/main/src/pve_exporter/cli.py) defines these switches. Resource-only collection avoids the extra node and cluster-status requests used by other collectors; the administrator must still confirm resource endpoint access.

```bash
docker compose config --quiet
docker compose run --rm --no-deps --entrypoint id pve-exporter
docker compose run --rm --no-deps pve-exporter --help
```

Only continue if validation succeeds, the mounted credential file is readable to that identity, and the flags exist. Start the new service:

```bash
docker compose up -d pve-exporter
docker compose ps pve-exporter
docker compose logs --tail=50 pve-exporter
```

**Check:** the service stays Up, port 9221 is internal, and no config/permission/unknown-flag errors appear. API authentication is exercised by the first `/pve` scrape in step 5, not merely by starting the container.

---

## 5. Add one Prometheus API scrape

Append this job to the existing `scrape_configs:` list in `prometheus/prometheus.yml`. Replace the placeholders and keep the existing jobs, including Node Exporter's LXC filtering:

```yaml
  - job_name: pve
    scrape_interval: 30s
    scrape_timeout: 25s
    metrics_path: /pve
    params:
      module: [default]
      cluster: ['1']
      node: ['0']
    static_configs:
      - targets: ['<smith-api-host>']
        labels:
          group: noc
          service: pve-exporter
          host: noc-core
          owner: '<owner>'
          contact: '<contact-person> (<contact-address>)'
          dependencies: 'external:smith-api'
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: pve-exporter:9221
```

This makes Prometheus call `/pve?target=<smith-api-host>&module=default&cluster=1&node=0`. The target is the **API host**, and `pve-exporter:9221` is the exporter address. Cluster resource collection is requested once; node-specific collectors are skipped. The later recording rules select Smith from returned guest metadata.

Add **one** target for this cluster's resource collection. Scraping each cluster node with `cluster=1` duplicates guest data and breaks joins/sums. A separate home environment uses its own source/configuration. Multiple clusters would need an explicit cluster identity in every inventory key and join; that extension is outside this single-school-cluster recipe.

The static `group: noc` identifies the **monitoring scrape** in the catalogue. It does not assign every guest to the NOC group. Step 7 replaces that label on normalized guest metrics using a reviewed guest-to-group mapping.

Validate, then reload without enabling the HTTP lifecycle endpoint:

```bash
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose kill -s SIGHUP prometheus
docker compose logs --since 2m prometheus
```

Run SIGHUP only after validation succeeds. In *Status → Target health*, the `pve` job should show the API host as instance and `/pve` as the scrape path.

**Check:** `up{job="pve"}` becomes `1` after one or two scrapes. If it stays 0, read the target's last error and exporter logs. A 401 suggests credentials/expiry; 403 suggests scope/rights; TLS errors suggest trust/hostname mismatch; timeouts suggest connectivity or an API collection taking more than 25 seconds. Fix the cause before treating any dashboard data as complete.

---

## 6. Verify guest metrics and authorized coverage

Run these separately in Explore, with the working Prometheus source:

```promql
pve_guest_info{job="pve"}
```

```promql
pve_cpu_usage_limit{job="pve",id=~"qemu/.+|lxc/.+"}
```

```promql
pve_cpu_usage_ratio{job="pve",id=~"qemu/.+|lxc/.+"}
```

```promql
pve_memory_size_bytes{job="pve",id=~"qemu/.+|lxc/.+"}
```

```promql
pve_memory_usage_bytes{job="pve",id=~"qemu/.+|lxc/.+"}
```

These names and `id` labels come from the exporter [resource collector](https://github.com/prometheus-pve/prometheus-pve-exporter/blob/main/src/pve_exporter/collector/cluster.py). Match the chosen release's actual output before creating rules. The API metrics are gauges; do not apply `rate()` to CPU or memory gauges. CPU usage ratio multiplied by the reported CPU count gives an approximate number of busy core equivalents; throttling and guest accounting still need like-for-like comparison with Proxmox.

Find Smith's exact `node` value in `pve_guest_info`. Compare its visible non-template guest IDs with the approved list, including stopped guests. A successful scrape does not guarantee every intended guest was visible to its token. Ask the administrator to reconcile missing IDs; do not remove them from the inventory just to make a dashboard counter green.

Check uniqueness:

```promql
count by(id) (pve_guest_info{job="pve"}) > 1
```

This should return no rows. One guest must have one current identity series. Resource-only collection does not emit `pve_up` because its status collector is disabled; this dashboard uses Blackbox for service health and Prometheus `up` for collector health.

**Check:** every intended guest's allocated CPU and RAM agree with its current Proxmox configuration. Current usage agrees with Proxmox at comparable times. Account for refresh timing, memory accounting and ballooning; do not claim byte-for-byte agreement with guest `free` output. If stopped guests lack usage metrics, retain the missing-data indicator and document that API behavior.

---

## 7. Create the guest mapping, approved budgets and recording rules

Copy the supplied template **once**, then edit your local copy:

```bash
cp grafana/docs/smith-resource-rules-template.yml prometheus/rules/smith-resources.yml
nano prometheus/rules/smith-resources.yml
```

If that local file already exists, edit it directly. The template is not a valid live rules file until you replace all placeholders. Its location in `grafana/docs/` keeps it outside the current `/etc/prometheus/rules/*.yml` glob.

Complete the sections in this order:

1. Replace the review date and budget-owner comment with the approved decision reference.
2. Repeat the three `noc_group_*_budget_*` records for **each** approved group. Give each a positive numeric `vector(...)` value and the same `group` label as its service catalogue.
3. Repeat the `noc_guest_info` / `noc_guest_disk_allocated_bytes` pair for **every** in-scope live guest, including stopped ones. Each ID belongs to exactly one group. Match `host` to its existing probes and guest exporter.
4. Calculate each disk record from all provisioned volumes charged to that guest. Record the source and review date in the comment. Shared volumes must have an agreed attribution and must not be counted twice.
5. Replace `<smith-node-name>` in the two shared scope expressions with the exact API label from step 6. Keep the shared normalized/group rule section **once**, after all inventory/budget records.

For example, **only on a disposable home test**, a group with an approved 8-vCPU, 16-GiB RAM, 100-GiB disk budget would use `vector(8)`, `vector(17179869184)` and `vector(107374182400)`. A test guest with 30 GiB total provisioned disks would use `vector(32212254720)` for its disk record. These numbers are examples, not Smith allocations or a recommended school budget.

The mapping is deliberately separate from the service labels: the exporter identifies guests as `qemu/<vmid>` or `lxc/<vmid>`, while the catalogue identifies services by group/service/host. The supplied rules join these using `id`, add group/host metadata and keep the API's node/name labels. They do not assume a probe IP is a VMID or that a guest name reliably encodes ownership.

The rules evaluate once per minute. They suppress live scope when `up{job="pve"}` is not 1, and suppress a group's total when an inventoried guest lacks that metric. Reviewed disk allocations and approved budgets remain constant inventory references. The unmapped list exposes visible Smith guests without an inventory mapping; a dashboard filter is not an access-control boundary for the underlying Prometheus data.

If templates are charged as a separate disk-only allocation, add their reviewed disk records with the right group, but do not add them to `noc_guest_info` while the live scope excludes them. Explain this policy in the inventory comments. Include every live guest in both records.

Check for leftover placeholders, then validate:

```bash
grep -n '<[^>]*>' prometheus/rules/smith-resources.yml
docker compose exec prometheus promtool check rules /etc/prometheus/rules/smith-resources.yml
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
```

`grep` should print nothing, and both validations must succeed. Then reload:

```bash
docker compose kill -s SIGHUP prometheus
docker compose logs --since 2m prometheus
```

**Check:** after one or two rule evaluations, `noc_guest_info`, `noc_guest_scope` and the four `noc_guest_cpu_*` / `noc_guest_memory_*` metrics appear. In Prometheus *Status → Rules*, the `noc-smith-resources` group has no evaluation errors. Recording rules do not backfill: their trends start after this reload. See [Prometheus recording rules](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/) and [vector matching](https://prometheus.io/docs/prometheus/latest/querying/operators/#vector-matching).

---

## 8. Check the mapping and budgets before drawing charts

Run these current queries. The first two should have **no rows**:

```promql
count by(id) (noc_guest_info) > 1
```

```promql
noc_guest_info unless on(id) noc_guest_scope
```

The third lists visible Smith guests missing from your mapping:

```promql
noc_smith_unmapped_guest_info
```

If the token can see only agreed NOC guests, this should be empty after mapping them all. If broader read access was explicitly approved, list the other returned Smith guests and explain whether they should be mapped or remain outside the dashboard scope. A nonzero unmapped counter means the view is scoped/partial; do not claim coverage of every Smith group.

Check that every inventoried group has all three budgets:

```promql
count by(group) (noc_guest_info) unless on(group) noc_group_cpu_budget_cores
```

```promql
count by(group) (noc_guest_info) unless on(group) noc_group_memory_budget_bytes
```

```promql
count by(group) (noc_guest_info) unless on(group) noc_group_disk_budget_bytes
```

All three should be empty, and each budget must be positive with one series per group. Also verify that each guest has its disk record:

```promql
noc_guest_info unless on(id) noc_guest_disk_allocated_bytes
```

Compare the actual group totals:

```promql
noc_group_cpu_allocated_cores
```

```promql
noc_group_memory_allocated_bytes / 1073741824
```

```promql
noc_group_disk_allocated_bytes / 1073741824
```

They should equal, respectively, configured vCPU, configured RAM in GiB and reviewed disk allocation in GiB for the same guest list. If an allocation metric is missing for a stopped guest, a live total may intentionally be absent; investigate/document that rather than excluding the guest or substituting zero.

**Check:** every approved in-scope guest is mapped once, all budgets have evidence, and totals reconcile. Keep the inventory updated when guests are created, moved, resized or removed. Otherwise a technically successful API scrape can still yield an incorrect budget view.

---

## 9. Include the new scrape in monitoring-health alerts

In the existing `MonitoringCheckFailed` rule in `prometheus/rules/alerts.yml`, extend the job regex to include `pve`:

```yaml
        expr: up{job=~"node|blackbox|smartctl|pve"} == 0
```

Keep its current severity, 2-minute hold and annotations. Then validate and reload:

```bash
docker compose exec prometheus promtool check rules /etc/prometheus/rules/alerts.yml
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose kill -s SIGHUP prometheus
```

Only reload after both validations pass. The new scrape's catalogue labels supply group, host and owner context. This catches failed API/exporter scrapes; it does not detect a token that silently sees too few guests. Inventory comparison and the dashboard's missing/unmapped panels cover that limitation.

**Check:** the existing rule is still listed without errors. On a home/test installation, stop/start only `pve-exporter` and confirm the alert reaches Pending/Firing/Resolved as appropriate. Do not interrupt the school collector just to demonstrate this recipe.

---

## 10. Build the resource dashboard and maintain the source

Return to [step 8 of health-and-usage-dashboards.md](health-and-usage-dashboards.md#8-import-and-verify-the-smith-dashboard) to import the template and compare its panels. Keep the current service catalogue: the API exporter now appears as one additional scrape service, and its catalogue metadata must be complete too.

| Later change | Action |
|---|---|
| New guest / changed group or host label | Update the local inventory and disk records; validate and reload |
| Guest resized | CPU/RAM allocation updates from API; re-review provisioned disk inventory and approved budget policy |
| Approved budget changed | Update only the affected budget records, cite approval, validate and reload |
| Guest moved away from Smith | Review scope and recorded allocation; a previously inventoried but out-of-scope guest becomes missing until reconciled |
| Token rotated | Update the private file, preserve its permissions, recreate exporter and verify `up` plus guest coverage |
| CA/server certificate changed | Verify hostname/trust, update CA bundle if required, recreate exporter and repeat TLS/coverage checks |
| Disk inventory review | Compare every charged volume with the approved source; record date/owner, not just the resulting total |
| Exporter upgrade | Test the pinned image/flags/metric names first; record new digest; validate and recreate |

For a credential/CA file change, recreate to account for single-file bind mounts:

```bash
docker compose up -d --force-recreate pve-exporter
docker compose logs --tail=50 pve-exporter
```

For rollback, remove only the newly added `pve` job and added exporter service from local configuration, restore the old alert expression, and move the local `smith-resources.yml` **outside** `prometheus/rules/`. Validate and reload Prometheus before stopping the exporter. Restore from the saved configuration only where needed, preserving later teammate changes. Do not copy the unfilled rules template into the loaded folder or remove persistent volumes.

Keep secrets in the agreed secret store and private recovery process. Store sanitized dashboard exports and budget decisions as project evidence. Finish the acceptance checks in the dashboard guide before changing the repo's deployment status from proposed to working.
