# Grafana dashboard operations

This guide covers the two final dashboards: **Host Systems and Disk Health** and **Proxmox VM and LXC Monitoring**. Use the [dashboard guide](../README.md) for import, filters and metric interpretation, and the [acceptance record](validation-and-acceptance.md) for the confirmed results.

## Daily use

1. Open the intended dashboard and select the correct Prometheus source or API instance.
2. Keep the time range ending at **now**. Refresh when checking current state.
3. On Host Systems, select Job, Nodename and Instance for the physical host. Use Disk host independently for SMART health.
4. On Proxmox, choose API instance and then Proxmox node/Guest type. Start with All to see the complete discovered inventory for that API source.
5. Use the shared Monitoring dashboards dropdown to switch between the two dashboards at the same time range.

Running and stopped counts add to the discovered guest count when Unknown is zero. Templates are already included in the discovered total. Per-node capacities are sums of guest allocations, not measurements of physical-host usage. Expand row groups and use table scrolling/filtering to inspect all columns and entries.

## Read-only operator access

Use the intended operator account in the Grafana organization containing both dashboards. For read-only use, its organization role should be Viewer, with View access to the relevant folder/dashboards and no server-administrator role. Inspect applicable team and inherited folder grants as well: Grafana uses the highest effective permission. See [Grafana dashboard permissions](https://grafana.com/docs/grafana/latest/administration/user-management/manage-dashboard-permissions/).

In a separate operator session, confirm that both dashboards load, filters/time range/refresh work, and shared dashboard changes cannot be saved. User and data-source administration should remain unavailable to the operator. A read-only panel inspector or export action does not itself grant permission to change the saved dashboard.

Dashboard JSON does not create users or restore permissions. These are separate Grafana settings.

## Save and export accepted changes

Keep the repository templates and the saved live dashboards in sync deliberately: a Grafana save does not edit the repository file, and editing the file does not update Grafana.

For each final dashboard:

1. Save accepted changes in Grafana. Record the dashboard title, folder, URL/UID and Prometheus source.
2. Open the dashboard's Export menu and select Export as code. Under Advanced options, choose the Classic JSON model used by this repository.
3. Download an original-instance restore copy with Share dashboard with another instance off. Keep the UID and source information with that copy.
4. Download a portable copy with that option on for importing into another Grafana instance.
5. Keep the exports in the project's agreed backup location. Review environment-specific references before replacing a reusable repository template with a live export.

For Host Systems, also record the Datasource selection; it uses a dashboard variable rather than the Proxmox import mapping. Grafana's [export procedure](https://grafana.com/docs/grafana/latest/visualizations/dashboards/share-dashboards-panels/#export-a-dashboard-as-code) describes the model and portability options.

## Restore or replace on the current Grafana

Use the saved original-instance export to restore a prior accepted version, or import an updated portable template and select the current source. Enter the existing dashboard UID from its `/d/<uid>/...` URL and confirm replacement. A new UID creates a separate dashboard, even if the filename is the same.

After import, verify the title, source selection, filters, table columns and representative values. For Proxmox, check the overview totals against the inventory and inspect guests on several nodes. For Host Systems, check the selected physical host and the independent SMART selection. Save any intended default selections and export the accepted state again.

See [Grafana import](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/import-dashboards/) for the upload, UID and source-mapping workflow.

## Check restore on a separate Grafana

Use a separate Grafana installation/database matching the deployed version. Add the existing Prometheus source at an address reachable from that installation, then import the two portable exports. Select the destination source during the Proxmox import and using the Host Systems Datasource dropdown.

Compare original and restored dashboards at the same filters and time range:

| Dashboard | Compare |
|---|---|
| Host Systems and Disk Health | Host selection, representative CPU/memory/filesystem/network values, SMART entries and row groups. |
| Proxmox VM and LXC Monitoring | Discovered/running/stopped/unknown/template counts, guest inventory, actual node assignment, per-node capacities and resource/activity charts. |
| Both | Titles/UIDs, saved selections, units, source references and Monitoring dashboards navigation. |

Reopen the test Grafana after a restart to check persistence. Record the exports used, destination, duration and result, then stop the test installation when finished. The older October service-dashboard restore is retained in the [archive](archive/service-health-tests.md#dashboard-backup-and-restore); it is a historical result for different dashboards.

This procedure restores dashboard definitions. Metric history comes from Prometheus; users, permissions, alert rules and a full Grafana/Prometheus database backup are separate from dashboard JSON.

## Troubleshooting

| Symptom | Check |
|---|---|
| Most Proxmox panels have no data | Select the correct API instance and Prometheus source; check `up{job="pve"}` and `pve_guest_info{job="pve"}` in Explore. |
| Scrape health is Up but guest state is Unknown | Check `pve_up` for guest IDs and the exporter's status collector. A successful scrape alone does not supply every guest metric. |
| Node list or guest type has an old/empty selection | Reload the dashboard, then select All for node and type. Variables refresh from the selected source's labels. |
| Guests appear under the wrong physical location | Compare `pve_guest_info`'s `node` label. The shared scrape-level `host` label is not used as guest location. |
| Stopped guest usage is N/A | Expected: usage/activity is displayed for running guests; capacities remain visible where reported. |
| VM filesystem usage is N/A | Expected: the template does not infer VM filesystem use from zero-valued API disk metrics. LXC root-filesystem usage is shown where available. |
| A per-node capacity total is N/A | Inspect that node's guest capacities. One missing/invalid capacity suppresses the corresponding total to avoid showing a partial sum. |
| A guest disappears | Check API visibility, the configured target, filters and the current Proxmox inventory. The dashboard discovers visible guests; it is not a manually maintained expected inventory. |
| Host Systems panels are empty | Select the intended source/job/nodename/instance. Some panels require optional Node Exporter collectors or appropriate hardware. |
| SMART is Unknown or empty | Check the independently selected Disk host and smartctl exporter collection on the physical host. Known devices can remain Unknown for 24 hours after their last sample. |
| Values become Unknown despite ordinary collection | Match the freshness constants to actual scrape intervals. Defaults are 90 seconds for PVE and 180 seconds for SMART. |
| An imported change does not appear | Confirm the correct dashboard UID/source, save and reload. Editing local JSON alone does not update the live dashboard. |

Use a shorter time range for detailed incident inspection and the panel's query inspector when checking query results. Keep the two dashboards' responsibilities separate: physical hosts in Host Systems, virtual guests in Proxmox. The archived Blackbox and group-budget procedures are not needed to troubleshoot these final templates.
