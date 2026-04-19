# Observability — local dev

Loki + Promtail + Grafana run in the same `src/docker-compose.yml` stack as postgres/nats/minio. The API itself continues to run on the host (`uv run uvicorn ...`) — Promtail tails a log file instead of scraping a container.

## Start the stack

```bash
# Bring everything up (postgres, nats, minio, loki, promtail, grafana)
docker compose -f src/docker-compose.yml up -d

# Or just the observability stack
docker compose -f src/docker-compose.yml up -d loki promtail grafana
```

Service URLs:

| Service | URL | Notes |
|---------|-----|-------|
| Grafana | http://localhost:3000 | default login `admin` / `admin`, override via `GRAFANA_USER` / `GRAFANA_PASSWORD` |
| Loki | http://localhost:3100 | raw API — you usually query it through Grafana |
| Promtail | http://localhost:9080 | metrics + `/targets` endpoint for debugging |

## Run the API with JSON log capture

Promtail reads from `./logs/*.log` (mounted into the Promtail container from the repo root). Start the API in production log mode and redirect its output:

```bash
mkdir -p logs
APP_ENV=production uv run uvicorn src.main:app --port 8001 >> logs/app.log 2>&1 &
```

In dev mode (`APP_ENV=development`, the default) the output is pretty-printed and Promtail's JSON pipeline stage will skip those lines — you'll see nothing in Grafana. **Use `APP_ENV=production` when you want to test the log pipeline.**

## Verify it works

1. Hit the API to generate traffic:

   ```bash
   curl -s http://localhost:8001/api/v1/erp-systems
   curl -s http://localhost:8001/does-not-exist      # 404 to exercise 4xx
   ```

2. Open Grafana → **Explore** → pick **Loki** datasource → run:

   ```logql
   {service="coa-api"}
   ```

   You should see JSON events, including the `http_request` audit lines.

3. Open **Dashboards → COA → COA HTTP** — panels populate after ~30 s.

## Label discipline

Only **low-cardinality** fields are promoted to Loki labels:

| Label | Values |
|-------|--------|
| `service` | always `coa-api` |
| `env` | `dev` (local) / `prod` (production deployment) |
| `level` | `info` / `warning` / `error` / `debug` |
| `method` | `GET` / `POST` / `PATCH` / `DELETE` / ... |
| `status_class` | `2xx` / `3xx` / `4xx` / `5xx` |
| `event` | structlog event name (e.g. `http_request`) |

Everything else — `user_id`, `path`, raw `status`, `duration_ms`, `ip`, `user_agent` — stays in the log body. Query it in LogQL with `| json | user_id = "..."`. Promoting high-cardinality values (like `path` with UUIDs) would explode Loki's index.

## Troubleshooting

- **No logs in Grafana:** confirm `logs/app.log` is being written (check `ls -la logs/`), then check Promtail targets at http://localhost:9080/targets.
- **`Client.Timeout exceeded` in Promtail logs:** Loki didn't start in time. Wait for the healthcheck, or `docker compose restart promtail`.
- **Parsing errors (`pipeline stage json ...`):** your API is emitting non-JSON (most likely dev console format). Set `APP_ENV=production`.
- **Grafana `Unauthorized`:** default creds are `admin` / `admin`, override with `GRAFANA_USER` / `GRAFANA_PASSWORD` in your shell env before `docker compose up`.

## Cleanup

```bash
docker compose -f src/docker-compose.yml down
# Drop volumes (loses Loki history and Grafana state)
docker compose -f src/docker-compose.yml down -v
```
