# Smith resource metrics and approved budgets

This guide supplies the data for [the health and usage dashboards](health-and-usage-dashboards.md#7-prepare-smith-resource-metrics). It reads the Proxmox API from noc-core, without installing software on Smith, and records which guests belong to each group and what budget was approved.

**Status: the resource dashboard extension is proposed and has not been verified on the deployment.** The supplied [monitoring setup](../../docs/setup.md) and [PVE how-to](../../docs/how-to-guides.md#monitor-proxmox-guests-with-pve-exporter) describe an existing `pve-exporter` service, image `3.10.1`, private configuration `pve/pve.yml`, an optional `pve` job and guest-status alerts. These supporting guides were supplied as context; their deployment claims are not evidence that a particular recipient has those services running. Inspect local configuration first. Reuse a working exporter/job/secret and preserve collectors used by existing alerts. Steps 3–5 include a fallback for a deployment without PVE monitoring. Complete the resource checks on a home/test setup, then repeat within the approved school scope.

This guide assumes Linux with Docker Engine and the Compose v2 plugin, a working Prometheus/Grafana stack at `/opt/monitoring`, and one Proxmox cluster. Confirm that Compose mounts `./prometheus` at `/etc/prometheus` and Prometheus has `rule_files: ['/etc/prometheus/rules/*.yml']`. The rules template in `grafana/docs/` has no effect until its filled local copy is loaded. A successful syntax check cannot confirm API permissions, actual guest coverage or Grafana rendering.

All commands below run as root **inside noc-core**, from `/opt/monitoring`. Proxmox account, permission, certificate and shared-firewall changes belong to the platform administrator. Obtain the current permitted scope from the NOC assignment/platform owner. The [course Smith-policy link](https://github.com/JollyJones101/network-experience-2627/blob/main/docs/04-smith-proxmox.md) could not be retrieved during this review; confirm the owner-provided policy rather than relying on that link as authorization.

Placeholders used in this guide:

| Placeholder | Meaning |
|---|---|
| `<smith-api-host>` | Approved API DNS name, with no `https://`, path or port; TLS certificate must match it |
| `<smith-node-name>` | Exact, case-sensitive `node` value returned by the API, which can differ from the display name Smith |
| `<approved-image-digest>` | SHA-256 digest of the reviewed PVE exporter image |
| `<monitoring-user>@pve` | Dedicated read-only account provided by the administrator |
| `<token-name>` / `<token-secret>` | API token ID component and secret, stored outside Git |
| `<group-name>` | Reviewed budget group, e.g. `noc` or `group-a`; independent of service-target labels |
| `<type>/<vmid>` | Exact guest ID, e.g. `lxc/101` or `qemu/102` |
| `<same-host-label-as-probes>` | Existing stable `host` value for that guest |
| `<owner>` / `<contact-person>` / `<contact-address>` | Responsible owner and agreed contact details for the collector |
| `<reviewed-release-tag>` | Approved exporter release tag; the supplied context uses `3.10.1` |

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

Use a dated, approved budget decision supplied by the budget owner as the reference. The [course resource-budget template link](https://github.com/JollyJones101/network-experience-2627/blob/main/docs/templates/resourcebudget-template.md) could not be retrieved during this review; a template is not an approved budget. Confirm units: **GiB = bytes / 1073741824**, **GB = bytes / 1000000000**. The dashboard uses byte metrics displayed as IEC units. For a budget agreed in GiB, multiply by 1073741824 before writing the rule value.

For this first dashboard, disk allocation is a reviewed sum of provisioned guest disks. Document which extra disks are included. Physical Ceph/ZFS usage, snapshot growth, replication and backup consumption need an additional approved source if the budget charges those quantities. Do not present the first disk bar as full physical storage accounting.

Include stopped guests in allocation totals unless the budget owner explicitly uses a different policy. The live rules exclude `template="1"`. Include charged template disks separately in reviewed disk inventory. If the budget also charges template CPU/RAM, this live recipe is incomplete: add a reviewed allocation source before reporting budget compliance.

The CPU bar uses the API's `maxcpu`, exported as `pve_cpu_usage_limit`; this is available guest CPU capacity, not a reservation or CPU quota. In Proxmox's [LXC implementation](https://github.com/proxmox/pve-container/blob/master/src/PVE/LXC.pm), it can come from `cores`, then `cpulimit`, then host CPU count. Confirm that this matches the approved vCPU accounting policy, especially for an unlimited container. If it does not, use a reviewed allocation inventory instead of claiming the API bar proves compliance.

**Handover inputs still needed:** provide the approved API endpoint/node and certificate trust, a scoped read-only token through the agreed secret store (including expiry/rotation owner), the complete authorized guest list (`qemu/<vmid>` or `lxc/<vmid>`, stable host and budget group, including stopped guests), and dated CPU/RAM/disk budgets with units and disk-charging policy. These are deployment inputs; template values must not be treated as approved allocations.

**Check:** there is a dated scope/budget decision and a complete guest list. If credentials or access are pending, the service-health dashboard can still proceed; leave Smith live usage pending instead of inferring it from noc-core's Node Exporter.

---

## 2. Have the administrator provide a scoped API token

Ask for a dedicated monitoring account and a token with **Privilege Separation** enabled. The administrator grants the necessary read-only/audit rights to **both the account and token** on the approved guest/pool paths and any required node/API paths. The effective token rights cannot exceed the account's rights. Use the administrator's least-privilege role/scoping decision, with `PVEAuditor` as the read-only reference; see [Proxmox's own user-management source](https://github.com/proxmox/pve-docs/blob/master/pveum.adoc).

The exporter upstream describes a broad read-only setup at `/`. Use the administrator-approved scope. The [Proxmox resource endpoint implementation](https://github.com/proxmox/pve-manager/blob/master/PVE/API2/Cluster.pm) filters guest visibility by `VM.Audit`; HTTP success does not prove complete guest permissions. Other enabled collectors can require additional endpoints. Have the administrator inspect denied or filtered requests; do not increase permissions yourself. For an existing token, agree any account/token change with its owner before affecting a working collector.

Keep the token secret in the agreed secret store. The exporter uses the separate `user`, `token_name` and `token_value` fields; it does not require a student/admin password. The full token identity for permissions is `<monitoring-user>@pve!<token-name>`, but the YAML's `token_name` field is only `<token-name>`.

**Check:** the administrator confirms the read-only scope and permitted API endpoint(s), token expiry and certificate trust. Do not put the token in a screenshot, dashboard JSON or a command-line argument.

---

## 3. Prepare local files and a reviewed exporter image

Take the configuration backup from [step 2 of the dashboard guide](health-and-usage-dashboards.md#2-preserve-the-catalogue-and-current-configuration). Inspect the existing service, its private file path and loaded `pve` job. If they work, reuse them and verify TLS, file permissions, image identity and resource output below; do not create another secret file or replace its token unnecessarily. The following commands use the supplied stack's `pve/pve.yml` path; substitute the actual mounted path if it differs.

For a new credential file only:

```bash
cd /opt/monitoring
mkdir -p pve
chmod 700 pve
(umask 077; nano pve/pve.yml)
```

Put the following in the file and replace the credential placeholders locally:

```yaml
default:
  user: '<monitoring-user>@pve'
  token_name: '<token-name>'
  token_value: '<token-secret>'
  verify_ssl: true
```

Before entering credentials, confirm both `pve/pve.yml` and `prometheus/rules/smith-resources.yml` are ignored and untracked. If necessary, add those exact local paths to `.gitignore`. An ignore rule does not untrack a file already committed. These commands print paths, not secret contents:

```bash
git check-ignore pve/pve.yml prometheus/rules/smith-resources.yml
git ls-files -- pve/pve.yml prometheus/rules/smith-resources.yml
```

The first should print both paths; the second should print nothing. If a credential file is already tracked, stop and arrange removal/rotation with its owner.

The [exporter 3.10.1 Dockerfile](https://github.com/prometheus-pve/prometheus-pve-exporter/blob/v3.10.1/Dockerfile) uses UID/GID 101. Check the chosen image's actual identity in step 4. For that image, allow only its group to read the credential file:

```bash
chown root:101 pve/pve.yml
chmod 640 pve/pve.yml
```

The root-owned directory can remain mode 700 with the **single-file** bind mount shown below: the container reads the mounted file, not that host directory. A whole-directory mount needs traversal permission too. Check the chosen image's GID and test readability in the container; rootless Docker/user namespace mappings may need a different host ownership. Keep the file restricted to the intended reader. See [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/).

For a private CA, obtain the approved PEM CA bundle from the administrator and save it as `pve/pve-ca.pem`. It must contain certificates, not a private key. Make it readable by the exporter:

```bash
chmod 644 pve/pve-ca.pem
```

If the API already uses a certificate trusted by the image, omit the CA mount/environment setting in step 4. Otherwise [Requests' `REQUESTS_CA_BUNDLE`](https://requests.readthedocs.io/en/latest/user/advanced/#ssl-cert-verification) supplies the approved trust bundle to the exporter's HTTPS client. It replaces the default bundle for these requests. Use the DNS name matching the certificate, not an IP unless the certificate includes that IP. Keep `verify_ssl: true`, including when reusing an existing file that used a TLS bypass for a home test.

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

If `pve-exporter` exists, reuse its existing image, mount, network and collector flags. Verify `--collector.resources` is enabled (it is enabled by default in [exporter 3.10.1](https://github.com/prometheus-pve/prometheus-pve-exporter/blob/v3.10.1/src/pve_exporter/cli.py)). Retain status/node collectors and `node` scrape parameters needed by existing alerts. In particular, disabling `--collector.status` removes `pve_up` and can silently disable the documented guest-status alerts.

**Only when no exporter service exists:** add this resource-only entry under the existing `services:` mapping, at the same indentation as `grafana:`. It is a narrower option for an installation that does not already depend on guest-status metrics. Keep all existing services and volumes.

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
      - type: bind
        source: ./pve/pve.yml
        target: /etc/prometheus/pve.yml
        read_only: true
        bind:
          create_host_path: false
      - type: bind
        source: ./pve/pve-ca.pem
        target: /etc/prometheus/pve-ca.pem
        read_only: true
        bind:
          create_host_path: false
    environment:
      REQUESTS_CA_BUNDLE: /etc/prometheus/pve-ca.pem
```

For system-trusted TLS, omit the complete CA bind-mount entry and `environment:` block. Long bind syntax prevents a missing credential/CA file from becoming a directory. This new service has no published host port; Prometheus reaches `pve-exporter:9221` if both services share the [Compose network](https://docs.docker.com/compose/how-tos/networking/). If the existing stack uses explicit networks, attach this service to the same network as Prometheus. A pre-existing loopback-only test port need not be changed. The exporter connects to TCP 8006; it needs no Docker socket, privileged mode or Smith host mount.

The flags select resource collection and disable unrelated status/config/backup collectors. Check them against the pinned image's `--help` before starting it; the current upstream [CLI source](https://github.com/prometheus-pve/prometheus-pve-exporter/blob/main/src/pve_exporter/cli.py) defines these switches. Resource-only collection avoids the extra node and cluster-status requests used by other collectors; the administrator must still confirm resource endpoint access.

```bash
docker compose config --quiet
docker compose run --rm --no-deps --entrypoint id pve-exporter
docker compose run --rm --no-deps --entrypoint sh pve-exporter -c 'test -r /etc/prometheus/pve.yml'
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

If a `pve` job already exists, update that single job's missing metadata and verify its target; do not append a second one. Preserve `node: ['1']` where current collectors/alerts require it. For a new resource-only service, append this job to the existing `scrape_configs:` list. Replace placeholders and keep all other jobs, including Node Exporter's LXC filtering:

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

The resource-only example calls `/pve?target=<smith-api-host>&module=default&cluster=1&node=0`. The target is the API host; `pve-exporter:9221` is the exporter address. The later rules select Smith from guest metadata. An existing integration can keep `node=1` and its additional approved collectors. Complete metadata should describe the API/collector endpoint: preserve the existing `host` used by its host alerts, and use that same value in its catalogue entry. The example's `host: noc-core` describes an exporter running there; it is not a guest identity.

Add **one** target for this cluster's resource collection. Scraping each cluster node with `cluster=1` duplicates guest data and breaks joins/sums. A separate home environment uses its own source/configuration. Multiple clusters would need an explicit cluster identity in every inventory key and join; that extension is outside this single-school-cluster recipe.

The scrape uses the five catalogue labels: `service`, `host`, `owner`, `contact` and `dependencies`. Budget `group` labels are added separately to normalized guest metrics by the reviewed guest-to-group mapping in step 7. A service target does not need a `group` label.

Validate, then reload without enabling the HTTP lifecycle endpoint:

```bash
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose kill -s SIGHUP prometheus
docker compose logs --since 2m prometheus
```

Run SIGHUP only after validation succeeds. In *Status → Target health*, the `pve` job should show the API host as instance and `/pve` as the scrape path.

**Check:** `up{job="pve"}` becomes `1` after one or two scrapes. If it stays 0, read the target's last error and exporter logs. Proxmox API 401 suggests credentials/expiry; API 403 suggests scope/rights. The exporter can wrap API exceptions in HTTP 500, so the detailed cause may appear only in its logs. TLS errors suggest trust/hostname mismatch; timeouts suggest connectivity or collection exceeding the 25-second scrape timeout. Fix the cause before accepting complete data.

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

This should return no rows. One guest must have one current identity series. The resource-only fallback does not emit `pve_up`; a reused status-enabled integration should retain it for its existing alerts. The resource dashboard uses `up` for collector health, independently of the guest's running/stopped state.

**Check:** every intended guest's API capacity reconciles with the approved CPU/RAM accounting policy and Proxmox. Proxmox's [resource statistics](https://github.com/proxmox/pve-manager/blob/master/PVE/API2Tools.pm) are supplied from its status/RRD data; a fresh scrape does not prove its underlying host statistics are fresh. Compare usage at similar times and confirm node health. Account for memory accounting/ballooning; do not expect equality with guest `free`. If a stopped guest lacks metrics or reports zero capacity, retain the missing-data indicator and document that behavior.

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
2. Repeat the three `noc_group_*_budget_*` records for **each** approved group. Give each a positive numeric `vector(...)` value and the same reviewed `group` value as its guest inventory.
3. Repeat the `noc_guest_info` / `noc_guest_disk_allocated_bytes` pair for **every** in-scope live guest, including stopped ones. Each ID belongs to exactly one group. Match `host` to its existing probes and guest exporter.
4. Calculate each disk record from all provisioned volumes charged to that guest. Record the source and review date in the comment. Shared volumes must have an agreed attribution and must not be counted twice.
5. Replace `<smith-node-name>` in the two shared scope expressions with the exact API label from step 6. Keep the shared normalized/group rule section **once**, after all inventory/budget records.

For example, **only on a disposable home test**, a group with an approved 8-vCPU, 16-GiB RAM, 100-GiB disk budget would use `vector(8)`, `vector(17179869184)` and `vector(107374182400)`. A test guest with 30 GiB total provisioned disks would use `vector(32212254720)` for its disk record. These numbers are examples, not Smith allocations or a recommended school budget.

The mapping is deliberately separate from the service labels: the exporter identifies guests as `qemu/<vmid>` or `lxc/<vmid>`, while the catalogue identifies services by service/host. The supplied rules join these using `id`, add group/host metadata and keep the API's node/name labels. They do not assume a probe IP is a VMID or that a guest name reliably encodes ownership.

The rules evaluate once per minute. `noc_pve_source_ready` exists only when exactly one `pve` target is up and its latest `up` sample is less than 90 seconds old. Duplicate API IDs or inventory mappings are filtered before arithmetic joins, and source joins include `job`, `instance` and `id`. CPU/RAM capacity must be positive; usage can be zero. A group's live total disappears when any inventoried guest lacks that metric. Reviewed disk allocations/budgets remain inventory references during API outages. With the 30-second scrape, detection also waits for the next one-minute rule evaluation. If the scrape interval changes, review the 90-second limit in both rules and dashboard health query.

Recording-rule failures can leave old output readable until Prometheus staleness/lookback expires, so inspect *Status → Rules* for errors and check `prometheus_rule_group_last_evaluation_timestamp_seconds`, `prometheus_rule_evaluation_failures_total` and `prometheus_rule_group_iterations_missed_total` on a working Prometheus self-scrape. A dashboard filter is not access control for underlying Prometheus data.

If templates are charged as a separate disk-only allocation, add their reviewed disk records with the right group, but do not add them to `noc_guest_info` while the live scope excludes them. Explain this policy in the inventory comments. Include every live guest in both records.

The rule file contains inventory/budget references, never a token. Ensure it is readable by the Prometheus container user and its parent directories are traversable; `promtool` below runs as that same container user. A normal non-secret rules file can use mode 644. If inventory metadata requires restricted readership, use the correct Prometheus group with mode 640 instead. The credential creation used a subshell, so its private umask does not leak into this copy step.

Check for leftover placeholders, then validate:

```bash
grep -n '<[^>]*>' prometheus/rules/smith-resources.yml
chmod 644 prometheus/rules/smith-resources.yml
docker compose exec prometheus promtool check rules /etc/prometheus/rules/smith-resources.yml
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
```

`grep` should print nothing, and both validations must succeed. Then [reload configuration and rules by SIGHUP](https://prometheus.io/docs/prometheus/latest/management_api/#reload):

```bash
docker compose kill -s SIGHUP prometheus
docker compose logs --since 2m prometheus
```

**Check:** after one or two rule evaluations, `noc_guest_info`, `noc_guest_scope` and the four `noc_guest_cpu_*` / `noc_guest_memory_*` metrics appear. In Prometheus *Status → Rules*, the `noc-smith-resources` group has no evaluation errors. Recording rules do not backfill: their trends start after this reload. See [Prometheus recording rules](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/) and [vector matching](https://prometheus.io/docs/prometheus/latest/querying/operators/#vector-matching).

---

## 8. Check the mapping and budgets before drawing charts

First confirm `noc_pve_source_ready` returns one value of `1`. Then run these current queries. The first two should have **no rows**:

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

All three should be empty. Each budget must be positive with one series per group. Also run these checks for **each** budget metric; replace the metric name for memory/disk:

```promql
count by(group) (noc_group_cpu_budget_cores) != 1
```

```promql
noc_group_cpu_budget_cores <= 0
```

Verify unique disk ownership and that each guest has its disk record:

```promql
count by(id) (noc_guest_disk_allocated_bytes) > 1
```

```promql
noc_guest_info unless on(id,group,host) noc_guest_disk_allocated_bytes
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

They should equal API-reported CPU capacity, API-reported RAM capacity in GiB and reviewed disk allocation in GiB for the same scope. Confirm that the first two match the approved accounting policy before using them as budget allocation. If a metric is missing for a stopped guest, a live total can intentionally be absent; investigate rather than excluding the guest or substituting zero. The dashboard includes missing-metric and unmapped-guest tables, missing/invalid-budget and duplicate-ID counters. A missing group bar is incomplete data, never implicit zero. Grafana can display an entirely empty query result as **No data** rather than the field's **Unknown** null-value label; treat either as unknown and investigate. The 80%/95% colors are display choices and do not create alerts or represent approved policy unless the budget owner adopts them.

**Check:** every approved in-scope guest is mapped once, all budgets have evidence, and totals reconcile. Keep the inventory updated when guests are created, moved, resized or removed. Otherwise a technically successful API scrape can still yield an incorrect budget view.

---

## 9. Include the new scrape in monitoring-health alerts

Inspect the existing `MonitoringCheckFailed` rule in `prometheus/rules/alerts.yml`. The supplied context already includes `pve`; leave it unchanged if present. Otherwise extend its existing job regex without removing other jobs:

```yaml
        expr: up{job=~"node|blackbox|smartctl|pve"} == 0
```

Keep its current severity, hold time and annotations (the supplied context uses 2 minutes). Validate and reload only if you changed the rule:

```bash
docker compose exec prometheus promtool check rules /etc/prometheus/rules/alerts.yml
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose kill -s SIGHUP prometheus
```

Only reload after both validations pass. The new scrape's catalogue labels supply service, host and owner context. This catches failed API/exporter scrapes; it does not detect a token that silently sees too few guests. Inventory comparison and the dashboard's missing/unmapped panels cover that limitation.

**Check:** the existing rule is still listed without errors. On a home/test installation, stop/start only `pve-exporter` and confirm the alert reaches Pending/Firing/Resolved as appropriate. Do not interrupt the school collector just to demonstrate this recipe.

---

## 10. Build the resource dashboard and maintain the source

Return to [step 8 of health-and-usage-dashboards.md](health-and-usage-dashboards.md#8-import-and-verify-the-smith-dashboard) to import the template and compare its panels. Keep the current service catalogue and ensure the single reused/new PVE scrape has complete metadata and one catalogue entry. Reusing an exporter does not add a second service.

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

For rollback, move the local `smith-resources.yml` outside `prometheus/rules/`, restore only the changes made by this resource extension, validate and reload Prometheus. Keep a pre-existing PVE service/job/token and its alerts. If you created a new exporter/job solely for this extension, remove those additions and restore the prior alert expression before stopping that exporter. Preserve later teammate changes and persistent volumes; never load the unfilled template.

Keep secrets in the agreed secret store and private recovery process. Store sanitized dashboard exports and budget decisions as project evidence. Finish the acceptance checks in the dashboard guide before changing the repo's deployment status from proposed to working.
