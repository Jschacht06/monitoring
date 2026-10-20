# Service catalogue dashboard

This guide continues from [step 7 of service-catalogue.md](service-catalogue.md#7-create-or-reuse-the-catalogue-dashboard). Complete the target labels and Prometheus data source first. Grafana is available at `http://<noc-core-ip>:3000`, and the source uses `http://prometheus:9090`.

**Scope and compatibility:** this is a manually imported **Classic** Grafana dashboard JSON definition with `schemaVersion: 39`. That number describes the dashboard schema, not the required Grafana product version. Grafana can migrate older dashboard definitions; confirm the import and all panels in the recipient's installed version before accepting the setup. Menu wording can vary. The catalogue queries were reviewed against official documentation on 14 October 2026; the live import, actual stack configuration and installed versions still require the checks below. See [Grafana's dashboard models](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/view-dashboard-json-model/) and [dashboard migration implementation](https://github.com/grafana/grafana/blob/main/public/app/features/dashboard/state/DashboardMigrator.ts).

The **Every monitored service** table is a current scrape inventory. It does not discover applications automatically or enumerate the VM/LXC guests contained in a Proxmox exporter's response. The three identity labels must be complete and metadata must agree before one table row corresponds to one service instance. The metadata counter checks absent/empty labels; it cannot verify contact accuracy, placeholders or services that were never configured.

If you do not have a catalogue dashboard yet, first create its definition using [dashboard-template.json](../dashboard-template.json). The template already contains all four panels below, including the fully formatted probe status table. Column ordering, headings, status mappings and colours are included; importing does not require recreating them in the editor. Copy it, replace the title, description and environment-tag placeholders, then import the finished file into Grafana. **Import creates the dashboard in Grafana.**

| Position | Panel | Visualisation | Why it is there |
|---|---|---|---|
| Top | Current service probe status | Table | Current destination probes with Up/Down/Unknown text and green/red/grey status cells. |
| Second | Every monitored service | Table | Current scrape inventory grouped by all six catalogue labels. |
| Third | Services with incomplete catalogue metadata | Stat | Counts affected identity-label tuples. Green at 0, red above 0; missing identity labels can merge unrelated services. |
| Bottom | Services missing catalogue metadata | Table | Lists the affected service instances and how many of their checks need metadata. |

---

## 1. Choose how to create the dashboard

| Starting point | Steps to follow |
|---|---|
| No catalogue dashboard yet; use the supplied template | Copy the template in step 2, edit it in step 3, then import it in step 6. This is the recommended route. |
| No catalogue dashboard yet; build it through Grafana's editor | Create the panels in step 4. Export it in step 5 if you want to import it on another LXC. |
| A catalogue dashboard already exists on this Grafana instance | Open it and compare it with the panel list above, then continue with the checks in step 7. |
| A catalogue dashboard exists on another Grafana instance | Export it in step 5, then import that file on the destination instance in step 6. |

**Check:** you have chosen a route. A dashboard built and saved through Grafana's editor is already available on that instance; importing is needed when you start from a JSON file or transfer it elsewhere.

---

## 2. Create your dashboard file from the template

The JSON file only needs to be on your local computer, where you open Grafana in a browser. **It does not need to be copied to or stored on the LXC.** You upload it through Grafana's web interface; Grafana stores the imported dashboard in its database. The supplied stack persists that database in its `grafana_data` volume; confirm the actual storage configuration before relying on it.

1. On your computer, open the supplied [dashboard-template.json](../dashboard-template.json) from the package's `grafana` folder (or the matching file in your local clone).
2. Save a copy named `service-catalogue-dashboard.json` on your computer. Use a different filename if you already have a working copy you want to keep.
3. Open that copy in a text editor.

Why a separate file: the supplied template remains a starting point, while your local copy holds the dashboard you want to upload. The same local file can be imported into your home or school Grafana instance.

**Check:** `service-catalogue-dashboard.json` contains the complete dashboard definition and is saved on your computer. Continue with step 3 before uploading it.

---

## 3. Edit the dashboard file

Replace the `<your ... here>` placeholders in your working copy before importing it. The panel queries and data-source mapping are already configured. The excerpts below show the existing code in [dashboard-template.json](../dashboard-template.json) and explain the required text changes and optional presentation changes.

### Dashboard name and description

Find these fields at the top level of the file, before the `panels` array:

```json
"title": "<your dashboard title here>",
"description": "<your description here>",
```

The `title` is the dashboard name shown in Grafana. Replace `<your dashboard title here>` with a name such as `School service catalogue` or `Home test service catalogue`. Use distinct names when keeping several copies on one instance.

The `description` explains what the dashboard covers. Replace `<your description here>` with your own description, for example `Catalogue of monitored services on the school network`. Keep the surrounding double quotes.

### Dashboard tags

```json
"tags": [
  "<your environment tag here>",
  "service-catalogue"
],
```

Tags help you find the dashboard in Grafana. Replace `<your environment tag here>` with a tag such as `school` or `home-test`, or remove that entry if you do not want an environment tag. Keep `service-catalogue` to make catalogue dashboards easy to find. These are dashboard tags; the service information still comes from Prometheus target labels.

### Refresh interval

```json
"refresh": "30s",
```

This makes Grafana refresh the dashboard every 30 seconds. The supplied stack describes a 30-second scrape interval; confirm the active interval and keep `30s` or choose another refresh such as `1m`. Dashboard refresh does not change metric collection.

### Panel names

Inside the `panels` array, each panel has its own `title` field. Find these four entries:

```json
"title": "Current service probe status",
```

```json
"title": "Every monitored service",
```

```json
"title": "Services with incomplete catalogue metadata",
```

```json
"title": "Services missing catalogue metadata",
```

These names appear above the panels. Keep them or change the text to your preferred names. Renaming a panel changes its heading; its query and results remain the same.

### Catalogue column names

In the **Every monitored service** panel, find `renameByName` under `transformations → options`:

```json
"renameByName": {
  "group": "Group",
  "service": "Service",
  "host": "Host",
  "owner": "Owner",
  "contact": "Contact person",
  "dependencies": "Dependencies",
  "Value": "Checks"
}
```

The keys on the left identify the fields returned by the query. Keep those keys and change only the text on the right if you want different column headings. For example, change `"contact": "Contact person"` to `"contact": "Contact"`. Keep a name such as **Checks** for `Value`, because it counts current scrape-target series, including failing scrapes.

### Query settings

Each panel stores its query in an `expr` field inside its `targets` array. The catalogue panel contains:

```json
"expr": "count by (group, service, host, owner, contact, dependencies) (up)",
"format": "table",
"instant": true,
"range": false,
```

Keep this query and these settings for the standard catalogue. They group checks with matching metadata and return one current table result instead of a row for every scrape time. Step 4 explains all four panel queries and their settings if you want to customise the panels.

### Probe freshness

The template contains one hidden Constant variable named `probe_freshness_s`, initially `90`. It controls the maximum accepted age of scrape/probe results in the status table; it does not change the collection interval. Keep 90 for the supplied 30-second scrape interval, or match the tolerance chosen for your health dashboard. Leave the status panel query, transformations and colour mappings in place when importing.

### Dashboard identity and data source

At the top level of the template, keep:

```json
"id": null,
"uid": null,
```

These let Grafana assign a new dashboard identity during import. Keep them as `null` when creating a new dashboard. Step 7 explains how to use an existing dashboard's UID when updating it. The numbered `id` fields inside the `panels` array identify the panels and should keep their existing values.

In the `__inputs` array, keep this name:

```json
"name": "DS_PROMETHEUS",
```

In each panel and query, keep the matching data-source reference:

```json
"datasource": {
  "type": "prometheus",
  "uid": "${DS_PROMETHEUS}"
},
```

These are import placeholders. They let Grafana ask which existing Prometheus source to use. Keep the placeholder strings; select the source whose URL is `http://prometheus:9090` in the import form.

Service addresses, owners, contacts and dependencies belong in the Prometheus configuration described in [service-catalogue.md](service-catalogue.md#2-add-the-first-targets-and-their-catalogue-labels). Grafana reads them from the metrics. Adding a monitored service does not require editing the dashboard file.

**Check:** search your working file for `<your` and confirm no personalisation placeholders remain. Save the complete file with valid JSON syntax: double quotes around text, commas between entries, and no comments. The excerpts above are parts of that file, so keep the surrounding structure. Keep the time range ending at `now`. For the template route, continue directly to **step 6**.

---

## 4. Create the dashboard manually in Grafana (alternative)

Use this step if you want to build the dashboard through the editor instead of copying the template. The [Grafana dashboard creation guide](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/create-dashboard/) documents the creation controls.

1. Open Grafana and go to *Dashboards → New → New dashboard*.
2. Click **Add visualization** and choose the existing Prometheus data source.
3. Create the first panel using the settings below. Use the query editor's **Code** mode for the PromQL query.
4. Apply the panel or return to the dashboard. Use *Add → Visualization* to create each remaining panel.

### Current service probe status

The template already includes this table. The steps below are only a reference for someone deliberately building the dashboard manually.

Create one hidden **Constant** dashboard variable named `probe_freshness_s`, with value `90` for the supplied 30-second scrape interval. Match the tolerance used by the health dashboard. In Grafana's newer editor, use **Edit → Add new element → Variable**; choose Constant and hide the variable control.

Create a panel with **Add new element → Panel → Configure visualization**, choose the existing Prometheus data source in the query editor, and choose the Table visualization. Use this expression:

```promql
(
  probe_success{job="blackbox"}
  and on(job,instance,module,group,service,host,owner,contact,dependencies) (up{job="blackbox"} == 1)
  and on(job,instance,module,group,service,host,owner,contact,dependencies) (time() - timestamp(up{job="blackbox"}) < $probe_freshness_s)
  and on(job,instance,module,group,service,host,owner,contact,dependencies)
  (time() - timestamp(probe_success{job="blackbox"}) < $probe_freshness_s)
)
or on(job,instance,module,group,service,host,owner,contact,dependencies)
(-1 + 0 * up{job="blackbox"})
```

| Setting | Value |
|---|---|
| Title | Current service probe status |
| Query | Instant; Format Table |
| Transformation | Organize fields by name; hide Time, job and __name__ if present |
| Column order | group, service, host, module, instance, owner, contact, dependencies, Value |
| Display names | Group, Service, Host, Check, Target, Owner, Contact, Dependencies, Status |
| Override | Fields with name: Status |
| Value mappings on Status | 1 → Up/green; 0 → Down/red; -1 → Unknown/grey; null → Unknown/grey |
| Status cell type | Colored background; colour only the status cell |
| No value on Status | Unknown |

All these properties are already stored in the imported template, including the value mappings and override. A successful scrape and fresh destination result are needed for Up/Down. The fallback displays Unknown when the current scrape is failing or results are missing/old. An empty status table is expected when no Blackbox probes exist; it does not prove healthy service coverage. The separate inventory includes scrape-only jobs as well.

### Every monitored service

```promql
count by (group, service, host, owner, contact, dependencies) (up)
```

| Setting | Value |
|---|---|
| Panel title | Every monitored service |
| Visualisation | Table |
| Query format | Table |
| Query type | Instant |
| Transformation | Organize fields by name |
| Fields | Hide Time; order group, service, host, owner, contact, dependencies, Value |
| Display names | Group, Service, Host, Owner, Contact person, Dependencies, Checks |

The query groups checks by all six catalogue labels. **Checks** counts current `up` series, including a scrape whose `up` value is 0. All checks for the same service must have complete, matching catalogue metadata to produce one service row. Newly discovered targets need a first scrape; removed targets disappear after discovery/staleness processing. See [Prometheus scrape-target series](https://prometheus.io/docs/concepts/jobs_instances/).

### Services with incomplete catalogue metadata

```promql
count(
  count by (group, service, host) (
    up{group=""} or up{service=""} or up{host=""}
    or up{owner=""} or up{contact=""} or up{dependencies=""}
  )
)
or (0 * count(up))
```

| Setting | Value |
|---|---|
| Panel title | Services with incomplete catalogue metadata |
| Visualisation | Stat |
| Query format | Time series |
| Query type | Instant |
| Calculation | Last (not null) |
| Decimals | 0 |
| Graph mode | None |
| Colour mode | Background |
| Thresholds | Absolute; base green, 1 red |

The inner query groups incomplete checks by `(group, service, host)`; the outer `count` counts those label tuples. Two incomplete checks with the same identity contribute **1**, even if several labels are missing. When identity labels are absent, unrelated checks can merge into one partial/blank tuple, so this can undercount real affected services. Correct missing identity labels before interpreting it as a service count.

The fallback supplies 0 when current targets exist and all required labels are present. An empty inventory produces no data rather than a successful zero. Placeholder text, whitespace-only labels and incorrect contact details still need manual review. See [Prometheus aggregation and set operators](https://prometheus.io/docs/prometheus/latest/querying/operators/#aggregation-operators) and [empty-label matching](https://prometheus.io/docs/prometheus/latest/querying/basics/#instant-vector-selectors).

### Services missing catalogue metadata

```promql
count by (group, service, host) (
  up{group=""} or up{service=""} or up{host=""}
  or up{owner=""} or up{contact=""} or up{dependencies=""}
)
```

| Setting | Value |
|---|---|
| Panel title | Services missing catalogue metadata |
| Visualisation | Table |
| Query format | Table |
| Query type | Instant |
| Transformation | Organize fields by name |
| Fields | Hide Time; order group, service, host, Value |
| Display names | Group, Service, Host, Checks missing metadata |

This table uses the same missing-label filter and grouping as the counter. It has one row per affected identity-label tuple; **Checks missing metadata** counts its incomplete checks, including scrapes with `up=0`. A check missing several labels is included once by the set union. Once identity labels are complete, each tuple represents one service instance.

When the inventory table has data and the counter is **0**, this bottom table should be empty or show **No data**. If the identity labels themselves are missing, the row can contain blank fields; inspect the missing-label selector in Explore to see the individual `job` and `instance` values and complete those labels.

Use [Instant and Table query options](https://grafana.com/docs/grafana/latest/datasources/prometheus/query-editor/) and [Organize fields by name](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/query-transform-data/transform-data/#organize-fields-by-name) to configure the tables. If the numeric field has a different name in your Grafana version, rename that field to **Checks** or **Checks missing metadata** as appropriate.

Arrange the panels at full width: **Current service probe status** at the top, **Every monitored service** next, the **Services with incomplete catalogue metadata** Stat underneath, and **Services missing catalogue metadata** at the bottom. Set refresh to **30s** and a time range ending at **now**. Save the dashboard as **Service catalogue** in the project folder.

**Check:** all four panels appear on the saved dashboard. On this instance, continue to step 7. To transfer it to another LXC, continue to step 5.

---

## 5. Export a dashboard you already created

Use this step for a manually created dashboard or an existing catalogue you want to reuse.

1. Open the saved dashboard.
2. Open the toolbar's *Export → Export as code* option. Some Grafana versions show **Export as JSON** in the share/export menu.
3. Expand **Advanced options** if needed, choose the **Classic** dashboard model for this workflow, and enable **Share dashboard with another instance** (also called **Export for sharing externally** in some versions). Classic exports are JSON; use the Classic definition for this import procedure.
4. Download the file as `service-catalogue-dashboard.json`.

Why the sharing option: it removes instance-specific details so the destination import can use its own data source. See [Grafana's dashboard export instructions](https://grafana.com/docs/grafana/latest/visualizations/dashboards/share-dashboards-panels/#export-a-dashboard-as-code).

**Check:** you have a complete JSON file on your computer. An exported dashboard can contain an existing UID; check the destination for that UID before importing, and choose a new UID/name in the import form when creating a separate copy. Continue to step 6 on the destination Grafana.

---

## 6. Import the prepared dashboard file

Use the file you copied and edited in steps 2–3, or the export from step 5. Importing it creates the dashboard on the selected Grafana instance, as described in [Grafana's import guide](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/import-dashboards/).

1. Open `http://<noc-core-ip>:3000` and sign in.
2. Go to *Dashboards → New → Import dashboard*.
3. Click **Upload dashboard JSON file** and select `service-catalogue-dashboard.json` from your computer.
4. Confirm the dashboard name and choose the project folder. For a new dashboard, choose an unused name/UID; only confirm replacement if you intend to update the existing dashboard.
5. At the **Prometheus** selection, choose the existing source whose URL is `http://prometheus:9090`.
6. Click **Import**.

The upload picker reads the file from your local computer. You do not need to place it in `/opt/monitoring` on either LXC. You can also copy the complete JSON from your local editor, paste it into Grafana's import JSON field and click **Load**, then complete the name, folder and data-source selections above.

Why `DS_PROMETHEUS`: it is an import placeholder, not a Docker hostname or a required source name. Grafana replaces it with the source you select.

**Check:** Grafana opens the newly imported dashboard with the probe status table at the top, the inventory next, the counter underneath and the missing-metadata table at the bottom. An empty bottom table is expected when the counter is 0 and the catalogue has data. If the catalogue or counter reports no data, or any panel has a query error, verify `up` in Explore using the selected source.

---

## 7. Verify and maintain the dashboard

Keep the time range ending at **now**, check the panel results and save any changes you make in Grafana.

| Check | Expected result |
|---|---|
| Current probe status | One row per visible Blackbox probe; Up/green, Down/red, Unknown/grey; scrape-only entries are not destination probes |
| Inventory table | After identity/metadata checks pass, one row per service instance with readable owner/contact/dependency fields |
| Metadata Stat | Number of affected identity-label tuples; 0 when every current check has all required labels |
| Bottom missing-metadata table | One row per affected identity-label tuple; empty when the counter is 0 and the inventory table has data |
| Counter/list agreement | The number of bottom-table rows matches the counter |
| Column names | Status in the probe table; Checks in the inventory table; Checks missing metadata in the bottom table |

Continue with [step 8 of service-catalogue.md](service-catalogue.md#8-check-what-the-catalogue-query-means), then complete its coverage and persistence checks.

| Later change | How to apply it |
|---|---|
| Add targets or change catalogue metadata | Update the Prometheus target labels as documented in the main guide; the dashboard reads the new values. |
| Edit panels in Grafana | Save the dashboard, then export a fresh JSON copy if you want to reuse those changes. |
| Edit the working JSON file | Import it again using the existing dashboard's UID to update it, or choose a new name/UID for a separate copy. |

If your working file still has `uid: null`, Grafana creates a new UID during import. To update the dashboard you previously imported, copy its UID from the `/d/<uid>/...` part of its URL into the import form's UID field and confirm replacement.

To apply this updated layout to an existing dashboard, make a fresh local copy of `dashboard-template.json`, replace its personalisation placeholders, then import it using the existing dashboard's UID as described above.

Why saving/exporting matters: this workflow imports JSON manually. Saving in Grafana does not update your JSON file, and changing a JSON file does not automatically update Grafana.

**Check:** keep your working JSON or latest export on your computer with the project evidence. Upload that local file through the school Grafana web interface when repeating the import, selecting the school's Prometheus source.

Next step: [health-and-usage-dashboards.md](health-and-usage-dashboards.md) adds service health, Smith resource-budget comparisons and trends while keeping this catalogue as the ownership list.

## 8. Verify the operator account

The operator uses both dashboards to inspect services without changing shared dashboards, data sources or users. Configure this in the running Grafana; dashboard JSON does not create users or provision their permissions. The steps below assume the stack's local Grafana login.

### Create or select a Viewer

1. Keep your existing administrator session open.
2. Go to **Administration → Users and access → Users**.
3. Reuse the intended operator account, or click **New user** to create a separate account, for example login noc-operator and display name NOC Operator. Fill the email field with an address you control if required, and set a separate password. Save the password privately.
4. Click **Create user**, then open the user's details. Direct creation sets the password locally; it does not send an invitation email.
5. Under **Organizations**, confirm the account belongs to the organization containing both dashboards and its role is **Viewer**. Change the role if needed.
6. Under **Permissions**, confirm **Grafana Admin** / server administrator is **No**. This flag is separate from the organization role. Keep your own administrator account unchanged.

If only an invitation action is available, confirm you are using the server administrator account; the invitation workflow is a separate option. See [Grafana user management](https://grafana.com/docs/grafana/latest/administration/user-management/server-user-management/).

### Check dashboard and folder permissions

1. As administrator, open **Service list**, enter its dashboard settings and select **Permissions**. In the current dashboard editor, settings may be the cog in the right sidebar after clicking Edit.
2. Confirm the operator has **View** through its Viewer role or an existing explicit grant. Do not add another grant if it already has access.
3. Look for **Edit** or **Admin** grants that apply directly to this user or through one of its teams. Remove an unnecessary direct grant or change the intended operator grant to View.
4. If a grant is inherited, open the containing folder from **Dashboards**, select its **Permissions** tab and inspect it there. Resolve inherited access at the folder or relevant team membership; a lower dashboard grant cannot cancel a higher grant.
5. Repeat for **Service health**. Preserve the administrators' and intended editors' access.

Grafana applies the highest applicable permission. See [dashboard and folder permissions](https://grafana.com/docs/grafana/latest/administration/user-management/manage-dashboard-permissions/).

### Sign in separately and check normal use

1. Open an Incognito/InPrivate browser window so the administrator's login cookie is not reused.
2. Open the same Grafana address and sign in as the operator. Check the profile identifies the operator.
3. Open **Service list** and confirm the current status, inventory and metadata panels load with data.
4. Open **Service health**. Select one Group and one Service, confirm the panels follow the selection, then restore All.
5. Change the time range to Last 15 minutes, then Last 6 hours, and use Refresh. These viewing actions must work without granting edit access.
6. Open any intended dashboard-navigation links and confirm they reach the expected view. Empty long-term history on a new installation is separate from a permission failure.

### Check that shared settings cannot be changed

1. On both dashboards, confirm the operator cannot save shared panel, query, layout or permission changes. Normally dashboard-edit controls are unavailable. Panel inspection or read-only views alone do not establish edit permission.
2. In the administrator window, copy the URLs of the Users page and the existing Prometheus data-source settings page. Open those same URLs in the operator window.
3. Confirm user administration and data-source editing are denied or unavailable. If a read-only page is visible, visibility alone is not permission to change it. Do not alter a working data source or account to test this.
4. If the operator has actual edit/save rights, review its organization role, server-admin flag, team grants and inherited folder permissions, then sign in again and repeat the check.

Dashboard export may remain available to a Viewer. It downloads a copy of the definition and does not permit saving changes to the running dashboard. Export availability alone is not a failed read-only check; see [dashboard export](https://grafana.com/docs/grafana/latest/visualizations/dashboards/share-dashboards-panels/#export-a-dashboard-as-code).

A Viewer can query data sources. Hiding Explore or a dashboard does not by itself restrict which metrics the account can query. The checks here verify read-only operation, not isolation of different groups' metrics. See [Grafana roles and permissions](https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/).

### Record the separate network boundary

From the network where the operator will work, check whether directly published Prometheus, Alertmanager and Proxmox interfaces are reachable, using their existing addresses and without reusing administrator credentials. Grafana login roles do not protect these separate services.

Record whether each interface is blocked, requires separate authentication or is openly accessible. A Proxmox login page does not grant VM-management rights; an unauthenticated management interface requires separate access controls. Access from a homelab administrator LAN does not establish the school's operator-network boundary. Coordinate restrictions with the stack/network owner, and record school verification as pending until performed there.

### Evidence and completion

Keep a screenshot of the operator's Viewer role/server-admin flag, both working dashboards in its separate session, and denied/unavailable administrative actions. Exclude passwords. Record test date, account, organization, network used and any pending external-interface checks. Do not mark access verified until the live checks are complete.

Users, roles and permissions are deployment configuration and are not restored by importing dashboard JSON.

## 9. Verify dashboard restore on a separate Grafana

This procedure tests dashboard JSON export/import with a fresh Grafana database, using the existing Prometheus for metrics. It does not test restoration of Prometheus, rules, notification configuration, user accounts or the full Grafana database. A full monitoring-stack restore remains a separate project check.

### Export the finished dashboards

As administrator on the working Grafana, save any pending dashboard edits. Record each dashboard's name, URL and UID (the value after /d/ in the URL).

For each of **Service list** and **Service health**:

1. Open **Export → Export as code**, then **Advanced options**.
2. Choose **Classic** for this workflow.
3. With **Share dashboard with another instance** off, download a local restore copy preserving the original instance references and UID.
4. Turn that switch on and download a second, portable copy for mapping to a destination data source. This prepares a file; it does not publish the dashboard.
5. Keep the four files privately on your computer, for example service-list-original.json, service-health-original.json, service-list-portable.json and service-health-portable.json. Keep the original URLs/UIDs with them.

See [Grafana dashboard export](https://grafana.com/docs/grafana/latest/visualizations/dashboards/share-dashboards-panels/#export-a-dashboard-as-code).

### Start the temporary Grafana

On the monitoring machine, create a separate folder; keep its Compose file separate from the running monitoring stack:

~~~bash
mkdir -p /opt/grafana-restore-test
nano /opt/grafana-restore-test/compose.yaml
~~~

Use the same Grafana image version as the running installation. The homelab configuration supplied for this test used grafana/grafana:13.2.2:

~~~yaml
services:
  grafana:
    image: grafana/grafana:13.2.2
    ports:
      - "3001:3000"
    volumes:
      - grafana_restore_data:/var/lib/grafana

volumes:
  grafana_restore_data:
~~~

The explicit project name gives this test its own container, network and data volume. Do not mount the existing Grafana volume. Validate and then start only this Compose project:

~~~bash
docker compose -p grafana-restore-test -f /opt/grafana-restore-test/compose.yaml config --quiet
docker compose -p grafana-restore-test -f /opt/grafana-restore-test/compose.yaml up -d
docker compose -p grafana-restore-test -f /opt/grafana-restore-test/compose.yaml ps
~~~

Run up only if validation succeeds. Open http://<monitoring-host-ip>:3001. On first use, sign in with admin/admin and choose a new password. Confirm this is the empty test Grafana, not the working installation on port 3000. See [Grafana Docker storage](https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/) and [first sign-in](https://grafana.com/docs/grafana/latest/setup-grafana/sign-in-to-grafana/).

### Connect the existing metrics source

1. On port 3001, open **Connections → Data sources → Add new data source → Prometheus**.
2. Name it Prometheus restore test.
3. Set **Prometheus server URL** to http://<monitoring-host-ip>:9090. This separate project does not resolve the other project's prometheus Docker service name.
4. Use the authentication settings required by the live source; do not add credentials if none are configured. Click **Save & test** and require success before continuing.

This procedure reads the existing metrics; it does not start a second collector or Alertmanager. Historical data comes from the connected Prometheus, not from the exported JSON.

### Import and verify both dashboards

1. In the test Grafana, open **Dashboards → New → Import dashboard**.
2. Upload service-list-portable.json from your computer.
3. Keep its normal title. On this fresh instance the original UID can be used; compare with the recorded UID and set it in the import form if needed. If a dashboard already has that UID in the test instance, use an unused UID/name rather than replacing something unintentionally.
4. Select **Prometheus restore test** when prompted and click **Import**.
5. Repeat with service-health-portable.json.
6. Confirm both dashboard URLs start with the test host and port 3001.

If the expected data-source mapping prompt is absent and panels reference a missing source, return to the working dashboard and repeat the portable export with the sharing switch enabled. See [Grafana dashboard import](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/import-dashboards/).

Compare the original and restored dashboards at the same filters/time range:

| View | Expected result |
|---|---|
| Service list | Current probe rows/status, inventory, owner/contact/dependency fields and metadata count agree |
| Health summary | Visible, failed and Unknown counts agree |
| Health table/history | Current status and historical outages agree |
| Latency/availability/coverage | Values and units agree; no missing-source/query errors |
| Certificate table | Expected HTTPS entries appear; HTTP-only probes have no certificate metrics |
| Filters | Group and Service selection update the intended panels |
| Dashboard links, if configured | Navigate to the intended restored dashboard on port 3001 |

Matching UIDs preserve relative dashboard links. Absolute links containing port 3000 can still lead back to the original Grafana; adapt deployment-specific links only in the test copy where needed and record the change. Do not add homelab addresses to reusable templates.

### Verify persistence and a live update

Restart only the test Grafana:

~~~bash
docker compose -p grafana-restore-test -f /opt/grafana-restore-test/compose.yaml restart grafana
~~~

Reopen port 3001 and confirm both dashboards and the source remain configured with working panels. This checks persistence of the test instance; it does not restore the original Grafana database.

For a live-state check, repeat a brief outage/recovery of the disposable Crafty service while watching the restored dashboard. Confirm Down/red, the failure counter increase, then Up/green and retained history after recovery. Existing alerting can still send notifications because both Grafanas read the same monitored service. Record this as a dashboard restore test, not a second notification-system test.

### Recorded homelab restore result — 16 October 2026

The operator reported completing this procedure in approximately 10 minutes. Both restored dashboards behaved the same as the originals, and the operator confirmed the procedure worked as expected. No screenshots were taken. Record this as an operator-confirmed dashboard restore, not as screenshot-verified evidence or a measured recovery guarantee. The [test report](service-health-tests.md#dashboard-backup-and-restore) records the scope and limitations.

The separate Grafana used the existing Prometheus, so visible history came from that source. No Prometheus database, rules or real target catalogue was restored by the JSON import. The reusable repository templates were checked locally; a fresh import of those placeholder templates is distinct from restoring the operator's exported live dashboards.

### Retain evidence and stop the test

Keep the export files, original/restored URLs, source mapping, comparison result, restart result, outage/recovery result and test duration. Attach screenshots or logs when collected; if none were collected, identify the written record as operator-confirmed rather than inventing evidence. Record backup owner, location, retention, agreed RPO/RTO and any measured data loss separately; the homelab operator reported equivalent restored dashboards, with no dashboard differences observed. Record any unchecked panels or deployment-specific link changes. User roles and permissions need separate configuration on a destination Grafana; dashboard JSON does not recreate noc-operator.

Stop only the test project when finished:

~~~bash
docker compose -p grafana-restore-test -f /opt/grafana-restore-test/compose.yaml down
~~~

This keeps its named volume for later inspection. The original monitoring project remains separate. Mark dashboard restore passed only after the imports and live verification succeed; a full stack/database restore remains outside this procedure.
