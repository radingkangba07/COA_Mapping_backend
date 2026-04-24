# Observability — production

Two viable paths. Pick one based on ops budget.

## Option A — Self-hosted Loki + Grafana

Run the same stack we use in dev, with three production hardening changes.

1. **Back Loki with S3 (DigitalOcean Spaces)** instead of a local filesystem volume. In `deploy/loki/loki-config.yaml`:

   ```yaml
   common:
     storage:
       s3:
         s3: https://coa-logs.nyc3.digitaloceanspaces.com
         access_key_id: ${S3_ACCESS_KEY}
         secret_access_key: ${S3_SECRET_KEY}
         s3forcepathstyle: true
         insecure: false

   schema_config:
     configs:
       - from: 2024-01-01
         store: boltdb-shipper
         object_store: s3
         schema: v12
         index:
           prefix: index_
           period: 24h
   ```

   Local filesystem volumes on Loki are fine for dev but lose history on container recycle.

2. **Run the API in a container** and swap Promtail's file-tail scrape for Docker service discovery so we pick up container stdout directly — no log-file mount:

   ```yaml
   scrape_configs:
     - job_name: coa-api-docker
       docker_sd_configs:
         - host: unix:///var/run/docker.sock
           refresh_interval: 5s
           filters:
             - name: label
               values: ["com.coa.service=coa-api"]
       relabel_configs:
         - source_labels: [__meta_docker_container_label_com_coa_service]
           target_label: service
         - source_labels: [__meta_docker_container_label_com_coa_env]
           target_label: env
       pipeline_stages:
         - json:
             expressions:
               level: level
               event: event
               status: status
               method: method
         - template:
             source: status_class
             template: '{{ if .status }}{{ printf "%dxx" (div (int .status) 100) }}{{ end }}'
         - labels:
             level:
             method:
             status_class:
             event:
   ```

   Add `com.coa.service=coa-api` and `com.coa.env=prod` labels on the API container.

3. **Lock down Grafana:**
   - Rotate `GRAFANA_USER` / `GRAFANA_PASSWORD` off the defaults.
   - Put Grafana behind a reverse proxy with TLS (nginx / Caddy).
   - Configure an external notifier (Slack / PagerDuty / email) for the alert rules in `deploy/grafana/provisioning/alerting/`.

**Costs:** ~$5–10/mo on a small DO droplet + a few cents of S3 per GB ingested. Good fit when we want to own retention and query policy.

## Option B — Grafana Cloud (free tier)

Zero-infra option. Keep only Promtail on our host, ship logs to Grafana Cloud.

1. Sign up at https://grafana.com — free tier gives 50 GB/month Loki ingestion with 14-day retention.

2. In Grafana Cloud, generate an API key with `MetricsPublisher` scope.

3. Replace Promtail's `clients` block:

   ```yaml
   clients:
     - url: https://<user-id>:<api-key>@logs-prod-<region>.grafana.net/loki/api/v1/push
   ```

4. Drop the `loki` and `grafana` services from production compose — keep only Promtail locally.

5. Dashboards + alerts live in Grafana Cloud; re-import `deploy/grafana/dashboards/coa-http.json` via the Cloud UI.

**Costs:** $0 under 50 GB/month. Most apps easily fit — `http_request` events are ~300 bytes each, so 50 GB ≈ 170M requests/month.

## Which to pick

| Criterion | Self-hosted | Grafana Cloud |
|-----------|-------------|---------------|
| Upfront work | More (S3 setup, proxy, TLS) | Minimal — paste a URL |
| Retention control | Full — tune `limits_config.retention_period` | 14 days on free tier |
| Data residency | Your infra | Grafana Labs (US/EU regions available) |
| Cost at low volume (<10 GB/mo) | ~$5/mo droplet | $0 |
| Cost at high volume (>100 GB/mo) | Cheaper | Paid plan kicks in |

Default recommendation: **start on Grafana Cloud free tier**, migrate to self-hosted only when we outgrow 50 GB/month or need custom retention.

## Secrets handling

Never check the following into the repo:

- `S3_ACCESS_KEY` / `S3_SECRET_KEY` for Loki S3 storage
- Grafana Cloud API keys
- `GRAFANA_ADMIN_PASSWORD` overrides

Inject them via your deployment secret manager (DO App Platform env vars, GitHub Actions secrets, etc).

## Label cardinality reminder

Even in production, do **not** promote `user_id`, `path`, or raw `status` to Loki labels. They remain JSON fields in the log body, queried via `| json | <field> = "..."`. Promoting a high-cardinality label creates one Loki stream per unique value and will crater ingester performance. The current `deploy/promtail/promtail-config.yaml` is safe — don't loosen it without measuring.
