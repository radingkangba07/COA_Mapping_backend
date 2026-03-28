#!/bin/bash
set -euo pipefail

# =============================================================================
# COA Migration — Start All Environments + Gateway Nginx
# =============================================================================

APP_DIR=/opt/coa-migration

echo "=== Starting all environments ==="

# Start each environment as a separate Docker Compose project
echo "[1/4] Starting Testing..."
cd ${APP_DIR}/environments/testing
docker compose -p coa-testing -f docker-compose.testing.yml up -d --build

echo "[2/4] Starting Staging..."
cd ${APP_DIR}/environments/staging
docker compose -p coa-staging -f docker-compose.staging.yml up -d --build

echo "[3/4] Starting Production..."
cd ${APP_DIR}/environments/production
docker compose -p coa-prod -f docker-compose.prod.yml up -d --build

# Start gateway nginx (connects to all environment networks)
echo "[4/4] Starting Gateway Nginx..."
docker rm -f coa-gateway-nginx 2>/dev/null || true

docker run -d \
    --name coa-gateway-nginx \
    --restart always \
    -p 80:80 \
    -v ${APP_DIR}/nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro \
    --network coa-testing_coa-testing \
    nginx:alpine

# Connect gateway to all networks
docker network connect coa-staging_coa-staging coa-gateway-nginx 2>/dev/null || true
docker network connect coa-prod_coa-prod coa-gateway-nginx 2>/dev/null || true

# Reload nginx config
docker exec coa-gateway-nginx nginx -s reload

echo ""
echo "==========================================="
echo "  All environments running!"
echo "==========================================="
echo ""
echo "  Production:  http://209.38.122.199/"
echo "  Staging:     http://209.38.122.199/staging/"
echo "  Testing:     http://209.38.122.199/test/"
echo ""
echo "=== Container Status ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep coa