# Public status page

The public page shows only an approved display name and **Up** or **Down** for each listed service. It uses the existing Blackbox results in Prometheus. It is separate from Grafana: the internal dashboards retain their detailed labels and Unknown state.

**Implementation status — 20 October 2026:** source and container template are implemented. Six functional/privacy tests and six Prometheus query cases passed; the Compose merge and container build also passed. Live installation and the healthy baseline on the homelab monitoring VM are operator-confirmed with a screenshot showing Jellyfin, Scrutiny and Uptime Kuma as three separate Up rows. Controlled live failures, disclosure inspection and approved public HTTPS access still need acceptance evidence.

## Data boundary and status meaning

The browser receives a rendered page at /, a stylesheet at /style.css and optionally JSON at /api/status. The JSON contains only a services array of name/status pairs. There are no source queries, links to dashboards, hostnames, IPs, target URLs, groups, probe modules, owners, contacts, dependencies, error details, metrics, history or internal configuration in these responses. Public names are written explicitly in the private mapping; review them for sensitive wording too. HTML escapes names.

The collector makes one fixed server-side [Prometheus instant query](https://prometheus.io/docs/prometheus/latest/querying/api/#instant-queries) every 30 seconds. It requires probe_success=1 and up=1, with both underlying samples less than 90 seconds old using [timestamp](https://prometheus.io/docs/prometheus/latest/querying/functions/#timestamp). Source labels remain in server memory. Visitor input cannot change the source, selector or query. HTTP requests read the cached sanitized result, so visits do not generate more Prometheus queries.

Every configured check must match one successful fresh series. A failed check, missing target, changed identity, failed scrape, stale sample, invalid module, unavailable source or invalid source response means Down. A service with multiple checks is Up only when **all** checks pass. A newly started collector shows Down until its first successful poll. If polling stops, the cached result expires after 45 seconds. A source error replaces the previous result with Down on the next poll.

**Down means availability cannot currently be confirmed.** The required two-state public view combines destination failures and monitoring uncertainty. Internal Grafana still distinguishes Down and Unknown. Alertmanager silences do not change this page; a silenced outage remains Down. Slow but successful checks remain Up. Updates include the scrape interval plus up to 30 seconds of polling and up to 30 seconds until browser refresh. Source sample freshness and local cache expiry are separate limits, not an instantaneous failure detector.

The container pins `python:3.14.8-slim-trixie` (Python patch release and Debian variant). The tag is not an immutable digest; review future patch/security updates explicitly and rebuild/retest. See the [official Python image tags](https://hub.docker.com/_/python).

The runtime uses Python's standard library, with no external web assets, analytics or browser scripts. It runs without root, with a read-only container filesystem and configuration mount. Its Docker build context excludes the private mapping and tests. Requests and source exceptions are not logged with private content. The small HTTP server is an origin behind a managed reverse proxy; that proxy handles public TLS, connection/rate limits and request size limits.

## 1. Preserve the running setup

Run these steps **on the monitoring VM**, where the existing stack is in /opt/monitoring. Transfer the new tracked files there through your usual Git/file-copy workflow first. No Prometheus job, Blackbox module or Grafana dashboard changes are required.

Back up your current Compose configuration and any existing status configuration before editing. For example:

~~~bash
cd /opt/monitoring
cp -a compose.yaml "compose.yaml.bak.$(date +%Y%m%d-%H%M%S)"
~~~

The status-page service is included in the [main Compose template](../compose-template.yaml). A new installation copies that template to compose.yaml as described in [setup](setup.md#3-create-composeyaml). For an existing installation, copy only the status-page service block into the services section of your private compose.yaml; preserve its other service settings.

## Migrate an existing companion-file installation

The repository now defines status-page in compose-template.yaml together with the rest of the stack. If your running VM was installed using the older companion file, update the private VM copy before using the single-file commands in this guide:

1. Back up compose.yaml and status-page/services.json.
2. Copy the complete status-page service block from the main template under the existing services section of your live compose.yaml. If it is already present, update that block rather than adding a duplicate.
3. Preserve the working port binding from your old companion: keep your actual LAN IP for direct LAN access, or loopback for a local proxy/tunnel. Preserve any custom network and private source settings too. The repository default is loopback, so copying it over a working LAN binding would change reachability.
4. Keep the existing services.json; do not replace it with placeholder configuration.
5. Validate and recreate only status-page:

~~~bash
cd /opt/monitoring
docker compose config --quiet
docker compose run --rm --no-deps --entrypoint python status-page -B -c 'from server import load_services; load_services("/config/services.json"); print("Status mapping valid")'
~~~

Continue only when both checks succeed:

~~~bash
docker compose up -d --no-deps --force-recreate status-page
docker compose ps status-page
~~~

Use ordinary docker compose commands after this migration. The old compose-status-template.yaml file is no longer required on the VM; retire it from local scripts as well. Keep the same project directory/name so Compose updates the existing status service. The other services need no restart for this migration.

## 2. Choose the public services and exact private checks

For first installation:

~~~bash
cd /opt/monitoring
cp -n status-page/config-template.json status-page/services.json
nano status-page/services.json
~~~

The copy command above is for first installation: cp -n preserves an existing services.json. Updating config-template.json or printing a generated replacement does not update the live services.json. Save the desired JSON in /opt/monitoring/status-page/services.json before recreating the container. In nano use Ctrl+O, Enter, then Ctrl+X.

The private services.json file is ignored by Git. Its permissions must allow UID 65534 in the container to read it; keep it in the protected monitoring directory. The file holds internal identities, so retain it in your private configuration backup rather than in a public repository.

Each object in the top-level services array creates one public row. The template below shows three independent rows; give each its own name and checks array. Multiple checks inside one service object describe one combined row that is Up only when every required check passes. For each service, choose a neutral public name such as Community website. Copy the **exact current** service, host, module and instance values from your internal Grafana current-check table or Prometheus. The instance is the full probe destination, including scheme, port and path when present. These selectors are private and never sent to the browser. Labels are case-sensitive: a public name such as Jellyfin can use an exact private service label such as jellyfin, but do not assume the real label from the display name. Replace every angle-bracket placeholder before starting.

~~~json
{
  "services": [
    {
      "name": "Community website",
      "checks": [
        {
          "service": "<website-service-label>",
          "host": "<website-host-label>",
          "module": "http_2xx",
          "instance": "http://<website-address>:<port>/<path>"
        }
      ]
    },
    {
      "name": "Media library",
      "checks": [
        {
          "service": "<media-service-label>",
          "host": "<media-host-label>",
          "module": "http_2xx",
          "instance": "http://<media-address>:<port>/<path>"
        }
      ]
    },
    {
      "name": "Service monitor",
      "checks": [
        {
          "service": "<monitor-service-label>",
          "host": "<monitor-host-label>",
          "module": "http_2xx",
          "instance": "http://<monitor-address>:<port>/<path>"
        }
      ]
    }
  ]
}
~~~

Add group to a check when group is needed to distinguish otherwise identical checks. It must match the real group label exactly; omit it for targets without that label. Do not use wildcards or regular expressions. Add more objects to services for additional public rows, or checks for additional required probes for the same row. Names must be unique; at least one service and one check per service are required. Newly discovered internal targets are never automatically published. Invalid configuration stops startup with a generic message.

## 3. Validate and start only the status component

~~~bash
cd /opt/monitoring
docker compose config --quiet
docker compose build status-page
docker compose run --rm --no-deps --entrypoint python status-page -B -c 'from server import load_services; load_services("/config/services.json"); print("Status mapping valid")'
~~~

Continue only when both validations and the build succeed. A missing services.json file fails the bind mount instead of creating a directory in its place.

~~~bash
docker compose up -d --no-deps status-page
docker compose ps status-page
curl -fsS http://127.0.0.1:8080/api/status
~~~

Wait one polling interval. Expect only the public names and Up/Down. Down for a known healthy service usually means a selector differs from its real target labels, its scrape has failed, or the source is unreachable. Inspect the existing internal dashboards rather than exposing diagnostic endpoints.

The status service joins the existing Compose network and uses http://prometheus:9090 internally. If the live stack has custom networks, attach status-page to the same network as Prometheus. When source authentication is introduced later, adapt the private collector connection for that approved mechanism before claiming it still works; the initial implementation does not provide authentication credentials.

## 4. Preview and inspect the public surface

From another computer, forward the loopback origin through your normal SSH account:

~~~bash
ssh -L 8080:127.0.0.1:8080 <ssh-user>@<monitoring-vm>
~~~

Keep the tunnel open and browse http://127.0.0.1:8080. If local port 8080 is occupied, use -L 18080:127.0.0.1:8080 and browse port 18080. This preview does not publish a new network port on the VM.

Check the visible page, View Source and browser Network responses. Confirm each row contains just its approved name and Up/Down. Check /api/status directly. It must have no contact information, host labels, addresses or source configuration. No Prometheus or Grafana requests should appear in the browser. These routes must return only a generic failure:

~~~bash
curl -i http://127.0.0.1:8080/config/services.json
curl -i 'http://127.0.0.1:8080/api/v1/query?query=up'
curl -i http://127.0.0.1:8080/metrics
~~~

## Live baseline and configuration repair — 20 October 2026

The operator confirmed the page works and supplied a screenshot showing Jellyfin, Scrutiny and Uptime Kuma in three separate rows, all Up. The visible list contains only their public names and statuses. A prior private terminal check confirmed that the collector could query Prometheus and found six fresh successful checks. Screenshot and detailed evidence are retained outside the monitoring repository.

Initial Down results came with no exact matching targets: the configured service and host values were absent from Prometheus. Keeping all checks inside one service object also produced only one public row. Copying placeholder configuration later caused startup validation failures and a restart loop. The working repair generated exact private check identities from Prometheus, selected each intended destination/module uniquely, saved three separate public service objects with a backup, and recreated only status-page. Public names were retained independently of private labels. A generator that prints JSON alone does not save the configuration.

This verifies the healthy live baseline and configuration repair. The screenshot does not establish controlled outage/recovery, automatic refresh timing, inspection of API/page-source responses or approved public HTTPS access.

## 5. Complete live acceptance

Use a temporary lab check or a service you are authorized to interrupt. Add that exact check to the private mapping and recreate only status-page after mapping edits. Keep evidence outside the public repository if it includes private labels.

| Test | Required public result | Internal comparison |
|---|---|---|
| Healthy configured destination | Up | Fresh probe_success=1 and up=1 |
| Controlled destination outage | Down | probe_success=0 |
| Destination recovery | Up | Fresh successful probe restored |
| Invalid module on a temporary check | Down | up=0; Grafana can show Unknown |
| Removed temporary target / wrong exact identity | Row remains, Down | Expected check no longer present |
| Source unavailable | All approved rows become Down | No private error text reaches page/API |
| Source recovery | Healthy rows return Up | Collector resumes successful queries |
| One required check fails in a multi-check row | That service becomes Down | Other required checks may stay healthy |
| Unlisted internal service is added | No new public row | Allowlist unchanged |
| Public page/API/source inspection | Only approved names and Up/Down | No raw labels, config, metrics or query proxy |

To test source unavailability without stopping shared Prometheus, temporarily set status-page's PROMETHEUS_URL in compose.yaml to http://127.0.0.1:1, recreate **only status-page**, and verify Down. Then restore http://prometheus:9090 and recreate it again. Existing Grafana and alerts continue using their own source connection. For stale source data, stop only a temporary lab scrape and verify the page no longer stays Up after the sample and snapshot limits; record the actual timing.

For each live test retain date, tester, expected/actual result and a screenshot or sanitized response. Record public-route inspection from outside the management network once the approved route exists. The healthy-baseline row is verified as recorded above; the remaining live tests are pending until their evidence is collected.

### Controlled stop/start rehearsal

Use a disposable HTTP destination so the failed probe is real and shared services remain available. The operator must select the Docker network shared by Blackbox and the temporary destination. Run on the monitoring VM from the stack directory; keep target/mapping backups outside the discovery folder and public repository.

1. Set the actual shared network name and start the temporary destination:

~~~bash
LAB_NETWORK='<shared-compose-network>'
docker run -d --name status-acceptance --network "$LAB_NETWORK" --workdir /tmp python:3.14.8-slim-trixie python -m http.server 8000
~~~

2. Add a new temporary target file such as `prometheus/targets/status-acceptance.yml`, preserving existing files:

~~~yaml
- targets: ['http://status-acceptance:8000/']
  labels:
    module: http_2xx
    service: status-acceptance
    host: status-acceptance
    owner: lab-operator
    contact: lab-operator
    dependencies: external:docker
~~~

3. Add a separate service object to the private mapping’s existing services array, validate the mapping as in step 3 and recreate only status-page:

~~~json
{
  "name": "Temporary lab check",
  "checks": [{
    "service": "status-acceptance",
    "host": "status-acceptance",
    "module": "http_2xx",
    "instance": "http://status-acceptance:8000/"
  }]
}
~~~

4. Wait for file discovery, a fresh probe and a collector poll. Confirm the temporary row is Up in both the page and /api/status. In the private Prometheus view, inspect probe_success and up with job="blackbox", service="status-acceptance". Record timestamps and baseline evidence.
5. Run `docker stop status-acceptance`. Confirm probe_success becomes 0 while up remains 1, then the page and API show Down. Leave the browser open to check its automatic refresh. Allow up to one scrape interval plus 30 seconds for polling and 30 seconds for browser refresh (about 90 seconds with 30-second scrapes); record actual delay and investigate if it exceeds this.
6. Run `docker start status-acceptance`. Confirm fresh probe_success=1 and up=1, then page/API return to Up. Record actual recovery delay. Inspect page source, API, stylesheet and error responses for private labels as in step 4.
7. Restore the previous private mapping, validate and recreate only status-page. Remove only the temporary target file, then run `docker rm -f status-acceptance`. Verify the original public rows still match their internal checks and the temporary row is gone.

This is a prepared operator procedure, not completed live evidence. Record date/tester, Up → Down → Up timestamps, internal comparison and sanitized screenshots/responses. The external HTTPS route still needs the separate publication checks below.

## 6. Publish through the approved route

The template binds only 127.0.0.1:8080. Have the person responsible for DNS, TLS and the reverse proxy route the approved public hostname to this origin. A proxy on the same VM can use that loopback address. A proxy on another host/container cannot use its own loopback address to reach this service: use an approved private network/bind and firewall rule or a shared container network, with the change recorded. Do not simply open the origin to every network.

Route only the sanitized status component. Do not forward /api paths to Prometheus or Grafana, and do not enable anonymous access on the existing Grafana organization. Disable proxy/CDN caching for this origin and preserve Cache-Control: no-store so Up is not served from an old cache. Recheck the external hostname for unintended upstream routes and internal details in proxy-generated error pages. Keep management ports protected by the separately agreed access controls; this component does not fix their current authentication boundary.

The school's [network/publication procedure](https://github.com/JollyJones101/network-experience-2627/blob/main/docs/03-netwerk-en-firewall.md) requires an approved path. Implementation and local preview do not establish that approval or public reachability.

## If the page still shows the old name or Down

First compare row names before investigating probe status. A file with three service objects should produce three public rows even when every check is Down. If the browser still shows only Community website, the running process or browser is using the old configuration or a different instance.

On the monitoring VM, verify what was actually saved:

~~~bash
cd /opt/monitoring
grep '"name"' status-page/services.json
~~~

Expect one name line per intended public row. Then compare the container's mounted file with the process currently serving the page:

~~~bash
docker compose exec -T status-page python -B - <<'PY'
import json, os
from urllib.request import urlopen
from server import load_services, read_healthy, public_services

filename = os.environ.get("STATUS_CONFIG", "/config/services.json")
services = load_services(filename)
print("Mounted configuration:", filename)
print("Names in mounted file:", [s["name"] for s in services])
with urlopen("http://127.0.0.1:8080/api/status", timeout=5) as response:
    served = json.load(response)["services"]
print("Names served by running process:", [s["name"] for s in served])
healthy = read_healthy(os.environ["PROMETHEUS_URL"])
print("Fresh successful checks:", len(healthy))
print("Current results using mounted file:", public_services(services, healthy))
PY
~~~

- Host file still has the old name: replace the contents of services.json and save it; printing JSON in a terminal does not write that file.
- Host file has three names, but the mounted file has the old name: verify the bind source and recreate only status-page. A replaced file can leave an existing single-file bind mount attached to the old file.
- Mounted file has three names, but the running process serves the old name: recreate status-page; configuration is loaded once at process startup.
- Both container lists have three names, but the browser shows the old row: verify the browser's VM address/port, reload it, and check any proxy/CDN cache or route to another instance.
- Correct names appear but a service remains Down: compare its exact service, host, module and instance labels, including case. A successful source connection alone does not prove those selectors match a fresh successful check.

To inspect which host file Docker actually mounted:

~~~bash
docker inspect "$(docker compose ps -q status-page)" --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
~~~

After saving the correct file, recreate only the status component using the update command below. Wait one poll and compare /api/status again. This terminal diagnostic is private; the public HTTP interface continues exposing only names and Up/Down.

## Change the public service list

Edit the private live mapping, /opt/monitoring/status-page/services.json, on the monitoring VM. The repository's config-template.json is an example for first installation; changing it does not change an existing live list.

1. Back up the working mapping:

~~~bash
cd /opt/monitoring
cp -a status-page/services.json "status-page/services.json.bak.$(date +%Y%m%d-%H%M%S)"
~~~

2. For an added or moved service, look up the actual target labels. This private terminal command works even when the main status container is restarting because it does not load services.json. It prints only the identity fields needed for the mapping, not owners or contacts:

~~~bash
docker compose run --rm --no-deps -T --entrypoint python status-page -B - <<'PY'
import json, os
from urllib.parse import urlencode
from urllib.request import urlopen

base = os.environ["PROMETHEUS_URL"].rstrip("/")
url = base + "/api/v1/query?" + urlencode({"query": 'up{job="blackbox"}'})
with urlopen(url, timeout=5) as response:
    payload = json.load(response)
if payload.get("status") != "success":
    raise SystemExit("Prometheus query failed")
for target in payload["data"]["result"]:
    labels = target["metric"]
    fields = ("service", "host", "module", "instance", "group")
    print(json.dumps({key: labels[key] for key in fields if key in labels}, indent=2))
PY
~~~

These objects are check identities, not a complete services.json. Identify the intended destination/module and copy its exact fields into the corresponding checks entry. This command only prints information; it does not save or replace your mapping.

3. Edit and save the live file:

~~~bash
nano status-page/services.json
~~~

- Rename a displayed row by changing its name only. Private labels stay unchanged.
- Add a row by duplicating one complete object in the top-level services array, choosing a unique public name and replacing its check with the exact target identity from step 2. Separate adjacent service objects with a comma; do not leave a trailing comma.
- Remove a row by deleting its complete service object and fixing the surrounding commas. This removes it only from the public page, not from Prometheus.
- Reorder rows by moving the complete service objects within the services array.
- Add checks inside one service object's checks array only when they are all required for that same public row to be Up. Use separate service objects for independently displayed applications.

The three-service template in section 2 shows the complete structure. Keep private service and host labels case-sensitive; do not turn them into display names. Save in nano with Ctrl+O, Enter, then Ctrl+X.

4. Validate the saved mapping before applying it. A fresh one-off container reads the current host file rather than an old process's in-memory configuration:

~~~bash
docker compose run --rm --no-deps --entrypoint python status-page -B -c 'from server import load_services; services = load_services("/config/services.json"); print("Valid mapping:", [s["name"] for s in services])'
~~~

Continue only after Valid mapping lists the intended public names. A JSONDecodeError means JSON punctuation/syntax needs correcting. Replace check placeholders with exact target labels means a required identity field is missing, unsupported, empty or still contains a placeholder. Schema validation does not prove those exact labels exist in Prometheus; compare them with step 2.

5. Apply only the status component:

~~~bash
docker compose up -d --no-deps --force-recreate status-page
docker compose ps status-page
~~~

Wait about 30 seconds, refresh the browser, and verify the intended rows and their statuses. Adding an unmonitored application requires a real Prometheus probe first; a public-page mapping does not create a probe.

## Recover from an invalid mapping and restart loop

The observed startup message was Invalid status configuration; check the private services file. The validator then reported Replace check placeholders with exact target labels. This was fixed by replacing placeholder/case-mismatched check identities with actual Prometheus labels, saving three separate service entries and recreating status-page. Rebuilding the same image alone does not fix invalid JSON.

When this happens, use the one-off target lookup and validation commands above: exec into the main container may fail while it is restarting. Correct the private file or restore your last working services.json.bak file, validate it, then recreate only status-page. The public page becomes available again once the container starts successfully. The live configuration never belongs in the repository template.

## Updates, rollback and backup

After changing the mapping:

~~~bash
cd /opt/monitoring
docker compose up -d --no-deps --force-recreate status-page
~~~

Recreation ensures a replaced bind-mounted configuration is reread. After source/style changes, build first and then recreate. Check the page and API again. Keep the private mapping, the customized compose.yaml, and the reverse-proxy/DNS/TLS procedure in the protected backup. Source, styles and templates are versioned; there is no status-history database to restore. Verify a restore using the same mapping on an isolated origin and repeat the privacy check.

To roll back the component without affecting the monitoring stack:

~~~bash
cd /opt/monitoring
docker compose stop status-page
~~~

Disable the public proxy route if one was created. Do not use compose down for a component rollback, since that would stop the shared stack.

## Local verification

Run from the repository root with Python 3.14:

~~~bash
python -B -m unittest discover -s status-page -p 'test_*.py' -v
~~~

The tests use an isolated fake Prometheus HTTP endpoint and real local public HTTP requests. They verify allowlisting, multi-check status, startup, source failure/recovery, cache expiry, invalid mapping, HTML escaping, exact routes and absence of private labels in page/API/errors/headers. They verify that the fixed query includes sample-freshness filters; six query cases are also checked by the real Prometheus promtool against the repository version (healthy, failed destination, failed scrape, stale probe, stale scrape and missing probe). The container build and merged Compose configuration were validated locally. The live healthy baseline is confirmed; live failure/recovery, disclosure inspection and the external publication route still require the deployment checks above.

Run the Prometheus expression tests with the same image version as the stack:

~~~bash
docker run --rm --network none -v "$PWD/status-page:/tests:ro" --entrypoint /bin/promtool prom/prometheus:v3.13.3 test rules /tests/query-tests.yml
~~~
