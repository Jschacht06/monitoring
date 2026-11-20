# Grafana dashboards

**Final — 20 November 2026.** Host Systems and Disk Health and Proxmox VM and LXC Monitoring are the two accepted dashboards. The operator confirmed that they work as expected; the live Proxmox screenshot results are recorded below.

A separate [Logs template](logs.json) is available for the working Loki setup. Its JSON and references are checked locally; importing this new template into the live Grafana instance remains to be verified.

The current scope is physical-host monitoring plus automatic VM/LXC monitoring. Individual Blackbox service monitoring and manually configured group budgets are no longer required for these two dashboards.

| Dashboard | Contents |
|---|---|
| [All Nodes Overview](all-nodes-overview.json) | Five panels: one table comparing every configured Node Exporter target, plus CPU, RAM, disk-space and network trend charts. |
| [Host Systems and Disk Health](host-systems-and-disk-health.json) | All 124 Node Exporter Full panels plus SMART disk health: physical-host CPU, memory, filesystems, disks, hardware, processes and networking. |
| [Proxmox VM and LXC Monitoring](proxmox-resources-and-group-budgets.json) | 13 panels: API scrape health; discovered/running/stopped/unknown/template counters; one guest inventory; a summary by Proxmox node; guest CPU, memory, LXC filesystem, network and virtual-disk activity. |
| [Logs](logs.json) | Two panels: log volume by service and recent log messages. Select the Loki source, host and service. |

The Proxmox file retains its historical filename; replacement is controlled by the dashboard UID, not the filename. Its displayed title is now **Proxmox VM and LXC Monitoring**. The previous combined budget dashboard is preserved in [old templates/proxmox-resources-and-group-budgets_rev1.json](old%20templates/proxmox-resources-and-group-budgets_rev1.json). The original project templates are also preserved unchanged in that folder.

## Import or replace a dashboard

1. Export the existing dashboard as a backup before replacement.
2. In Grafana, open **Dashboards → New → Import** and upload the complete JSON file.
3. To replace the existing Proxmox dashboard, copy its UID from the `/d/<uid>/...` part of its URL into the import form's UID field. Confirm replacement. The file has `uid: null`, so leaving the form with a new UID creates a separate dashboard instead.
4. For Proxmox and All Nodes Overview, map **Prometheus** to your existing data source. For Host Systems, select the data source using its **Datasource** dropdown after import, then choose Job, Nodename and Instance. For Logs, select your existing Loki source using its **Loki source** dropdown.
5. Save with the time range ending at **now**. The shared **Monitoring dashboards** dropdown finds the dashboards by their `noc-monitoring` tag and keeps the time range.

Importing JSON does not change exporters, targets, alerts or Prometheus rules. The Proxmox template uses the existing `pve_*` metrics and `up`; it needs no Blackbox probes, `noc_*` recording rules, guest-to-group mapping or approved budgets.

## All Nodes Overview

Import [all-nodes-overview.json](all-nodes-overview.json) as a new dashboard and choose the existing Prometheus source. Leave **Node Exporter job** and **Node** on **All** to compare all configured Linux Node Exporter targets. The new overview supplements the two accepted dashboards; it does not replace or change them. The first live import was confirmed on 20 November 2026. This revision corrects monitoring-container inclusion and the network filter; re-import it using the existing dashboard UID.

The top table shows each node's state, CPU/RAM/disk use, fullest eligible filesystem and receive/transmit throughput. Four charts show those same core measurements over time. It defaults to the last six hours with a 30-second refresh. Use Host Systems and Disk Health for detailed inspection of one host, and Proxmox VM and LXC Monitoring for virtual guests.

- **Discovery:** new Node Exporter targets appear from Prometheus without editing the JSON. The project job `node` is included even before a first successful scrape; other exporter jobs are identified from their Node Exporter metrics or `service="node-exporter"` label. Proxmox API discovery alone does not provide Node Exporter measurements. Node names come from `node_uname_info`, with the target address as a fallback. The monitoring-container source is excluded by `host="noc-core"` or its internal `node-exporter:9100` endpoint; future physical targets are still discovered automatically. This only filters the overview and does not remove the target from Prometheus or change alerts.
- **CPU:** average busy percentage across the node's cores, using the same idle-counter calculation as the detailed host dashboard. **RAM:** used percentage based on MemAvailable/MemTotal.
- **Disk:** the highest used percentage among eligible filesystems, based on available space. Temporary/pseudo filesystems and container runtime mounts are excluded. The table identifies the current fullest mount. Filesystem capacities are not summed, avoiding duplicate bind-mount accounting.
- **Network:** receive/transmit rates in bytes per second, summed over eligible interfaces. Leave **Network interfaces = `.*`** and **Network view = Physical interfaces** for the default overview. This accepts arbitrary physical NIC names rather than requiring an `en`/`eth` prefix, and excludes known loopback, bridge, VLAN, firewall, bond-parent and container-interface names. To use a logical uplink instead, choose **Custom selection** and enter only that uplink (for example `vmbr0` or `bond0`) in Network interfaces. Choose physical members or their logical parent, not both. If the import retains a previous textbox value in the URL, reset Network interfaces to `.*`.
- **Missing data:** failed/stale targets remain in the table as Down/Unknown while they have an `up` series. Unavailable resource values display N/A and charts keep gaps. Incomplete core rates, eligible filesystem values or selected interface rates suppress the corresponding node total rather than showing partial data as a healthy value.

The hidden `sample_freshness_s=90` matches the project's 30-second scrapes. There are no new collectors or recording rules. Node Exporter's [host-metrics guide](https://prometheus.io/docs/guides/node-exporter/) describes the underlying source. Local checks cover all-node/single-node selection, zero usage, missing/stale metrics, extra exporter jobs, unseen failed targets, filesystem selection and interface totals. Live visual acceptance is separate from these query checks.

## Logs

Import [logs.json](logs.json), then choose **Loki infra** for the Proxmox host journal or your existing **noc** Loki source for Docker logs. The selected source's existing credentials determine which tenant is visible; this template creates no data source and contains no credentials. Host and Service dropdowns read the available labels from that source. Leave both on **All** to see its collected logs.

The default view is the last 12 hours, refreshing every 30 seconds. The chart counts entries per query interval by service. The log viewer shows up to 1,000 matching entries, newest first, with timestamps, log levels and expandable details. Narrow the time range or filters when the limit is reached. Empty results can mean no matching activity, a wrong source/filter or a collection problem.

The template follows the existing dashboards' full-width layout, chart palette, legend and shared navigation. It uses Grafana's built-in [logs visualization](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/logs/) and [Loki variables](https://grafana.com/docs/grafana/latest/datasources/loki/template-variables/); no additional plugins or collectors are needed for the logs already flowing to Loki.

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

All Nodes Overview summarizes the existing Node Exporter measurements across nodes; Host Systems provides the detailed view of one host. They reuse the same Prometheus data and do not add another scrape or collector.

Host Systems owns the physical-host CPU, RAM, filesystem, disk, SMART, hardware and physical-network views. The Proxmox template contains no Node Exporter or SMART panels and excludes `node/...` and `storage/...` resources from its resource queries. Its network/disk activity belongs to guest virtual devices.

Within Proxmox there is one inventory table, one per-node summary and one set of guest resource/activity charts. The former allocation table and manual-budget section have been consolidated into those views. Nothing was copied into the Host Systems template.

## Host dashboard requirements

Node Exporter Full keeps its original Job/Nodename/Instance selection, queries and row groups. Expand the row groups for detailed metrics. Some sections need optional collectors or suitable hardware, for example systemd, pressure, sensors and ECC. See the panel descriptions and [Node Exporter Full source](https://github.com/rfmoz/grafana-dashboards).

**Disk host** filters SMART health independently of Node Exporter's instance selection because the exporters use different ports. SMART collection belongs on the physical host. Known disks remain Unknown for up to 24 hours after their last device/status sample; this is overall SMART status, not self-test history. `disk_freshness_s=180` is the existing default. Node Exporter inside an LXC can expose host-wide values, so choose physical-host exporter targets for physical-host measurements.

## Sources and history

The Proxmox dashboard uses the guest inventory, allocation, CPU/memory, LXC disk and network/disk activity features from the supplied Proxmox via Prometheus revision 5. Physical-node CPU/RAM and storage-pool panels have been removed from this dashboard to keep physical-host monitoring in Host Systems. CPU utilization is already a ratio and is displayed directly; see the exporter's [metric definitions](https://github.com/prometheus-pve/prometheus-pve-exporter/blob/main/README.rst).

Detailed Blackbox/service-catalogue and group-budget guides are retained in [the documentation archive](docs/archive/README.md); they are not prerequisites for the current dashboards.

## Validation and maintenance

Both dashboards are final and accepted. The live Proxmox view showed 114 discovered guests: 73 running, 41 stopped and 0 Unknown, with 8 templates included in that total. Inventory, per-node summaries and resource/activity charts were populated. The baseline was confirmed by the operator with live screenshots.

Run the local checks from the monitoring repository root:

```bash
python -B -m unittest discover -s grafana -p test_dashboards.py
python -B grafana/test_queries.py --docker
```

The current checks cover structural/query separation, 331 unique PromQL panel expressions and 24 query scenarios (nine guest-monitoring and fifteen all-node overview scenarios). Original source-fingerprint checks run only when their manifest is present. Optional comparisons with supplied downloads require those original files. Missing optional hardware collectors do not create a group-budget or Blackbox dependency.

Use [dashboard operations](docs/operations-and-troubleshooting.md) for read-only operator access, saving/exporting accepted changes, restore and troubleshooting. Older service-check and Smith-budget procedures/results are historical and are not remaining work for these final dashboards.
