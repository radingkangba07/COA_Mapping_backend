#!/bin/bash
set -euo pipefail

# =============================================================================
# COA Migration — Deployment Script
# Run on the server to pull latest code and rebuild
# Usage: ./deploy.sh [frontend|backend|all]
# =============================================================================

APP_DIR=/opt/coa-migration
COMPONENT=${1:-all}

cd ${APP_DIR}

echo "=== COA Migration Deploy — $(date) ==="

deploy_frontend() {
    echo "[Frontend] Pulling latest from main..."
    cd ${APP_DIR}/frontend
    git fetch origin
    git reset --hard origin/main
    cd ${APP_DIR}

    echo "[Frontend] Rebuilding container..."
    docker compose build --no-cache frontend
    docker compose up -d frontend
    echo "[Frontend] Deployed successfully."
}

deploy_backend() {
    echo "[Backend] Pulling latest from feat/project-crud-endpoints..."
    cd ${APP_DIR}/backend
    git fetch origin
    git reset --hard origin/feat/project-crud-endpoints
    cd ${APP_DIR}

    echo "[Backend] Rebuilding container..."
    docker compose build --no-cache api-service
    docker compose up -d api-service
    echo "[Backend] Deployed successfully."
}

case ${COMPONENT} in
    frontend)
        deploy_frontend
        ;;
    backend)
        deploy_backend
        ;;
    all)
        deploy_frontend
        deploy_backend
        # Restart nginx to pick up any changes
        docker compose restart nginx
        ;;
    *)
        echo "Usage: ./deploy.sh [frontend|backend|all]"
        exit 1
        ;;
esac

# Show status
echo ""
echo "=== Container Status ==="
docker compose ps
echo ""
echo "=== Recent Logs ==="
docker compose logs --tail=20