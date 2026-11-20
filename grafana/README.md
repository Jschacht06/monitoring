# Grafana dashboards

**Final — 20 November 2026.** Host Systems and Disk Health and Proxmox VM and LXC Monitoring are the two accepted dashboards. The operator confirmed that they work as expected; the [acceptance record](docs/validation-and-acceptance.md) includes the live Proxmox screenshot results.

The current scope is physical-host monitoring plus automatic VM/LXC monitoring. Individual Blackbox service monitoring and manually configured group budgets are no longer required for these two dashboards.

| Dashboard | Contents |
|---|---|
| [Host Systems and Disk Health](host-systems-and-disk-health.json) | All 124 Node Exporter Full panels plus SMART disk health: physical-host CPU, memory, filesystems, disks, hardware, processes and networking. |
| [Proxmox VM and LXC Monitoring](proxmox-resources-and-group-budgets.json) | 13 panels: API scrape health; discovered/running/stopped/unknown/template counters; one guest inventory; a summary by Proxmox node; guest CPU, memory, LXC filesystem, network and virtual-disk activity. |

The Proxmox file retains its historical filename; replacement is controlled by the dashboard UID, not the filename. Its displayed title is now **Proxmox VM and LXC Monitoring**. The previous combined budget dashboard is preserved in [old templates/proxmox-resources-and-group-budgets_rev1.json](old%20templates/proxmox-resources-and-group-budgets_rev1.json). The original project templates are also preserved unchanged in that folder.

## Import or replace a dashboard

1. Export the existing dashboard as a backup before replacement.
2. In Grafana, open **Dashboards → New → Import** and upload the complete JSON file.
3. To replace the existing Proxmox dashboard, copy its UID from the `/d/<uid>/...` part of its URL into the import form's UID field. Confirm replacement. The file has `uid: null`, so leaving the form with a new UID creates a separate dashboard instead.
4. For Proxmox, map **Prometheus** to your existing data source. For Host Systems, select the data source using its **Datasource** dropdown after import, then choose Job, Nodename and Instance.
5. Save with the time range ending at **now**. The shared **Monitoring dashboards** dropdown finds both dashboards by their `noc-monitoring` tag and keeps the time range.

Importing JSON does not change exporters, targets, alerts or Prometheus rules. The Proxmox template uses the existing `pve_*` metrics and `up`; it needs no Blackbox probes, `noc_*` recording rules, guest-to-group mapping or approved budgets.

## Proxmox filters and inventory

- **API instance** selects the existing `job="pve"` target. All panels use that same source.
- **Proxmox node** and **Guest type** filter every guest counter, inventory, summary and trend. Scrape health remains the health of the selected API instance.
- Node assignment comes from `pve_guest_info`'s **node** label. A scrape-level `host="Smith"` label shared by guests on several nodes is not used as their location.
- One inventory table lists each discovered guest's node, ID, name, VM/LXC type, template flag, state, CPU capacity/usage, memory capacity/usage, root disk capacity and available LXC filesystem usage. Templates and stopped guests remain visible; template counts are part of the discovered total, not additional guests.
- The per-node summary shows guest counts and guest capacities on each node. These are not the physical node's usage, physical capacity or an approved group budget. If one guest lacks a capacity metric, that node's corresponding capacity total is N/A rather than an understated partial total.
- Running/stopped states require a fresh successful scrape and a fresh valid `pve_up` value. Missing, invalid or stale guest state becomes Unknown. An absent inventory is Unknown/No data rather than a healthy zero. Removed or inaccessible guests eventually disappear from discovered inventory; API visibility still determines coverage.
- Resource usage and activity are shown for running guests with fresh source metrics. Missing or not-applicable values display N/A, and trend gaps remain gaps. Capacities can still be shown for stopped guests when the API supplies them.
- LXC root-filesystem usage is shown where available. VM filesystem usage is not inferred from zero-valued Proxmox disk metrics. Root disk capacity is the API-reported root image size, not an accounting of every attached disk, snapshot or backup.

The hidden constant `pve_freshness_s=90` assumes the existing 30-second scrapes. Match it to your collection interval if necessary. The guest-state/resource collectors need to be enabled in your existing PVE exporter; see the [existing PVE recipe](../docs/how-to-guides.md#monitor-proxmox-guests-with-pve-exporter). There is no need to deploy the historical resource-only/budget recipe to use this dashboard.

## Avoiding duplicate data

Host Systems owns the physical-host CPU, RAM, filesystem, disk, SMART, hardware and physical-network views. The Proxmox template contains no Node Exporter or SMART panels and excludes `node/...` and `storage/...` resources from its resource queries. Its network/disk activity belongs to guest virtual devices.

Within Proxmox there is one inventory table, one per-node summary and one set of guest resource/activity charts. The former allocation table and manual-budget section have been consolidated into those views. Nothing was copied into the Host Systems template.

## Host dashboard requirements

Node Exporter Full keeps its original Job/Nodename/Instance selection, queries and row groups. Expand the row groups for detailed metrics. Some sections need optional collectors or suitable hardware, for example systemd, pressure, sensors and ECC. See the panel descriptions and [Node Exporter Full source](https://github.com/rfmoz/grafana-dashboards).

**Disk host** filters SMART health independently of Node Exporter's instance selection because the exporters use different ports. SMART collection belongs on the physical host. Known disks remain Unknown for up to 24 hours after their last device/status sample; this is overall SMART status, not self-test history. `disk_freshness_s=180` is the existing default. Node Exporter inside an LXC can expose host-wide values, so choose physical-host exporter targets for physical-host measurements.

## Sources and history

The Proxmox dashboard uses the guest inventory, allocation, CPU/memory, LXC disk and network/disk activity features from the supplied Proxmox via Prometheus revision 5. Physical-node CPU/RAM and storage-pool panels have been removed from this dashboard to keep physical-host monitoring in Host Systems. CPU utilization is already a ratio and is displayed directly; see the exporter's [metric definitions](https://github.com/prometheus-pve/prometheus-pve-exporter/blob/main/README.rst).

[dashboard-sources.json](docs/dashboard-sources.json) records fingerprints of the supplied files and original project templates. Detailed Blackbox/service-catalogue and group-budget guides are retained in [the documentation archive](docs/archive/README.md); they are not prerequisites for the current dashboards.

## Validation and maintenance

Both dashboards are final and accepted. The live Proxmox view showed 114 discovered guests: 73 running, 41 stopped and 0 Unknown, with 8 templates included in that total. Inventory, per-node summaries and resource/activity charts were populated. See the [final acceptance record](docs/validation-and-acceptance.md) for the evidence and local test results.

Run the local checks from the monitoring repository root:

```bash
python -B -m unittest discover -s grafana -p test_dashboards.py
python -B grafana/test_queries.py --docker
```

The current checks cover structural/query separation, archived-template integrity, 320 unique panel expressions and nine guest-monitoring scenarios. Optional comparisons with supplied downloads require those original files. Missing optional hardware collectors do not create a group-budget or Blackbox dependency.

Use [dashboard operations](docs/operations-and-troubleshooting.md) for read-only operator access, saving/exporting accepted changes, restore and troubleshooting. Older service-check and Smith-budget procedures/results are historical and are not remaining work for these final dashboards.
