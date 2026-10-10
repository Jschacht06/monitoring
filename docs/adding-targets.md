# Adding targets

A **target** is something the NOC probes from the outside: a URL, a TCP port or a host that answers ping. Probes run through the Blackbox Exporter, so the monitored machine needs no agent and we need no management rights on it.

Targets are **not** listed in `prometheus.yml`. They live in `prometheus/targets/*.yml` and Prometheus reads them through file-based service discovery (`file_sd`). You add a target by editing or creating a file. No restart needed.

## How to organise the files

All files that match `prometheus/targets/*.yml` are loaded. You can use:

- **one file per group** (for example `group-a.yml`, `noc.yml`). This is recommended, because it matches the `group` label and keeps ownership clear.
- **one file per target**, which can be handy in a small homelab.
- one big file with everything.

Start from the template:

```bash
cd /opt/monitoring
cp prometheus/targets/template.yml prometheus/targets/group-a.yml
nano prometheus/targets/group-a.yml
```

Don't add real targets to `template.yml` itself. It is tracked in Git and its blocks are commented out on purpose. All other files in `prometheus/targets/` are ignored by Git, because they contain internal addresses.

## The fields

Each file is a YAML list of **blocks**. One block holds one or more targets that share the same labels:

```yaml
- targets:
    - http://192.168.1.150:8080/health
  labels:
    module: http_2xx
    group: group-a
    service: wiki
    host: 192.168.1.150
```

| Field | Required | What it does | Where it is used |
|---|---|---|---|
| `targets` | yes | What to probe. The format depends on the module: a full URL for `http_2xx`, `host:port` for `tcp_connect`, a bare host or IP for `icmp`. | Becomes the `instance` label (see the relabeling in [configuration-reference.md](configuration-reference.md#job-blackbox)). Shown in alert descriptions ("Probe ... to `<instance>`"). |
| `module` | yes | Which Blackbox module runs the probe. Must exist in `blackbox/blackbox.yml`: `http_2xx`, `tcp_connect` or `icmp`. | Passed to Blackbox as `?module=`. `ServiceSlow` only looks at `module="http_2xx"`. The inhibit rule uses it (`icmp` suppresses `http_2xx`). |
| `group` | yes (convention) | The owning group or team. | Shown in alert descriptions, so the receiver knows whom to contact. Useful for filtering in Grafana and silences. Not used for routing at the moment. |
| `service` | yes (convention) | Human-readable service name, such as `wiki`, `ssh` or `ping`. | Alert summary: "`<service>` on `<host>` is unreachable". |
| `host` | yes (convention) | The machine the service runs on. Use the **same value for every target on the same machine**. | Alertmanager groups emails by `alertname` and `host`. The inhibit rule matches on `host`. The email subject shows it. |
| `instance` | do not set | Set automatically to the target address by relabeling. | Identifies the individual probe in alerts, `up` and `probe_success`. |

Labels are free text. Use lowercase with dashes (for example `group-a`) and stay consistent. A typo in `host` breaks grouping and inhibition without any error.

## Examples

### Web service (`http_2xx`)

Passes when the URL answers with a 2xx status within 5 s. Redirects are followed.

```yaml
- targets:
    - http://192.168.1.150:8080/
  labels:
    module: http_2xx
    group: group-a
    service: wiki
    host: 192.168.1.150
```

Point it at a health endpoint if the service has one (for example `/health` or `/api/health`). That is a better signal than the start page.

### Host with ICMP (`icmp`)

Passes when the host answers ping. The target is a bare IP or hostname, without a scheme or port.

```yaml
- targets:
    - 192.168.1.144
  labels:
    module: icmp
    group: group-a
    service: ping
    host: 192.168.1.144
```

If ping always fails while the host is up, the host or a firewall drops ICMP. **Don't add an ICMP target for that host**: it would fire permanently and, through the inhibit rule, mute that host's HTTP alerts. Use `tcp_connect` instead.

### TCP port (`tcp_connect`)

Passes when a TCP connection to `host:port` can be opened. Use it for services without HTTP, such as SSH, databases or mail.

```yaml
- targets:
    - 192.168.1.144:22
  labels:
    module: tcp_connect
    group: group-a
    service: ssh
    host: 192.168.1.144
```

It only proves the port is open. It does not prove the service behind it works.

### HTTPS service

Use the same `http_2xx` module with an `https://` URL. The HTTP prober checks the TLS certificate by default: an expired certificate, an untrusted one or a hostname mismatch makes the probe fail (`probe_success 0`). The certificate expiry date is exported as `probe_ssl_earliest_cert_expiry`.

```yaml
- targets:
    - https://wiki.example.org/
  labels:
    module: http_2xx
    group: group-a
    service: wiki-https
    host: wiki.example.org
```

To require exactly HTTP 200, or to make sure plain HTTP is never accepted, add a stricter module. See [configuration-reference.md](configuration-reference.md#adding-a-module).

## Combining ICMP and HTTP for one host

Probe the host with ICMP and the service with HTTP, and give both blocks **exactly the same `host` value**:

```yaml
- targets:
    - 192.168.1.150
  labels:
    module: icmp
    group: group-a
    service: ping
    host: 192.168.1.150

- targets:
    - http://192.168.1.150:8080/
  labels:
    module: http_2xx
    group: group-a
    service: wiki
    host: 192.168.1.150
```

Why this matters:

- **Diagnosis**: for a host that normally answers ping, ICMP down and HTTP down means the host or network is gone. ICMP up and HTTP down means the service failed on a running host.
- **Inhibition**: Alertmanager has an inhibit rule. While `ServiceDown` for the `icmp` probe is firing, it suppresses `ServiceDown` for `http_2xx` probes **with an equal `host` label**. You get one email that says "the host is down" instead of one per service. If the `host` values differ (for example `192.168.1.150` and `wiki-server`), the rule does not match and you get both emails.
  **Only combine them for hosts that reliably answer ping.** If ICMP is blocked, the ICMP alert fires permanently and mutes every HTTP outage on that host. Check that `probe_success{module="icmp"}` is `1` before you rely on it.
- **Grouping**: emails are grouped by `alertname` and `host`, so all `ServiceDown` alerts of one host land in the same email.

## After saving

You don't need to restart anything. Prometheus watches the files and also re-reads them every minute (`refresh_interval: 1m`). New targets usually appear within seconds, and at most after a minute. If a file has a YAML error, Prometheus logs the error and keeps using the last version of that file that loaded fine. So a typo does not delete targets, but your change also does not take effect.

### Verify in Status > Targets

Open `http://<noc-core-ip>:9090`, go to *Status → Target health* and expand the `blackbox` job. Your target should be listed with its labels and state **UP**.

Not listed after a minute? Check the logs for a file_sd error:

```bash
docker compose logs prometheus --since 5m | grep -i -E "file|discovery|error"
```

### Verify with `probe_success`

In Prometheus (or Grafana *Explore*), run:

```promql
probe_success{service="wiki"}
```

- `1`: the probe passes. The service is healthy from the NOC's point of view.
- `0`: the probe fails. If it stays `0` for 2 minutes, `ServiceDown` fires.

Useful extra queries:

```promql
probe_duration_seconds{service="wiki"}              # how long the probe took
probe_http_status_code{service="wiki"}              # HTTP status code (http probes only)
(probe_ssl_earliest_cert_expiry - time()) / 86400   # days until the certificate expires (https only)
```

To see why a probe fails, ask Blackbox directly with debug output. Blackbox has no published port, so run it from inside the Prometheus container:

```bash
docker compose exec prometheus wget -qO- \
  'http://blackbox:9115/probe?module=http_2xx&target=http://192.168.1.150:8080/&debug=true'
```

## `up` vs `probe_success`

These two are easy to mix up, and mixing them up hides real outages.

| Metric | What it means for a blackbox target | Example |
|---|---|---|
| `up` | Prometheus could scrape **the Blackbox Exporter** for this target. It says nothing about the service. | `up=1` while the website is down: Blackbox answered "I probed it and it failed". |
| `probe_success` | **The probed service** passed the check. | `probe_success=0`: the website is down, slow beyond the 5 s timeout, or returned a non-2xx status. |

So:

- Alert on `probe_success` for service health. `ServiceDown` does exactly that.
- `up == 0` on the `blackbox` or `node` job means the **monitoring** is broken: the exporter container is down or unreachable. In that case `probe_success` is missing entirely, so `ServiceDown` cannot fire. That is why `MonitoringCheckFailed` watches `up`.
