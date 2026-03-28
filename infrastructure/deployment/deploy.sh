#!/bin/bash
set -euo pipefail

# =============================================================================
# COA Migration — Multi-Environment Deployment Script
# Usage: ./deploy.sh <environment> [frontend|backend|all]
#
# Examples:
#   ./deploy.sh production all
#   ./deploy.sh staging frontend
#   ./deploy.sh testing backend
# =============================================================================

APP_DIR=/opt/coa-migration
ENV=${1:?"Usage: ./deploy.sh <testing|staging|production> [frontend|backend|all]"}
COMPONENT=${2:-all}

# --- Environment config ---
case ${ENV} in
    testing)
        FE_BRANCH="develop"
        BE_BRANCH="develop"
        COMPOSE_FILE="docker-compose.testing.yml"
        PROJECT_NAME="coa-testing"
        FE_BASE_URL="/test"
        ;;
    staging)
        FE_BRANCH="staging"
        BE_BRANCH="staging"
        COMPOSE_FILE="docker-compose.staging.yml"
        PROJECT_NAME="coa-staging"
        FE_BASE_URL="/staging"
        ;;
    production)
        FE_BRANCH="main"
        BE_BRANCH="feat/project-crud-endpoints"
        COMPOSE_FILE="docker-compose.prod.yml"
        PROJECT_NAME="coa-prod"
        FE_BASE_URL=""
        ;;
    *)
        echo "Unknown environment: ${ENV}"
        echo "Usage: ./deploy.sh <testing|staging|production> [frontend|backend|all]"
        exit 1
        ;;
esac

ENV_DIR=${APP_DIR}/environments/${ENV}
cd ${ENV_DIR}

echo "=== COA Deploy [${ENV}] — $(date) ==="

deploy_frontend() {
    echo "[${ENV}/Frontend] Pulling latest from ${FE_BRANCH}..."
    cd ${ENV_DIR}/frontend
    git fetch origin
    git reset --hard origin/${FE_BRANCH}
    cd ${ENV_DIR}

    echo "[${ENV}/Frontend] Rebuilding (BASE_URL=${FE_BASE_URL})..."
    docker compose -p ${PROJECT_NAME} -f ${COMPOSE_FILE} build --no-cache --build-arg BASE_URL="${FE_BASE_URL}" frontend
    docker compose -p ${PROJECT_NAME} -f ${COMPOSE_FILE} up -d frontend
    echo "[${ENV}/Frontend] Done."
}

deploy_backend() {
    echo "[${ENV}/Backend] Pulling latest from ${BE_BRANCH}..."
    cd ${ENV_DIR}/backend
    git fetch origin
    git reset --hard origin/${BE_BRANCH}
    cd ${ENV_DIR}

    # Sync compose and env files from backend repo
    echo "[${ENV}/Backend] Syncing compose/env files..."
    cp ${ENV_DIR}/backend/infrastructure/deployment/${COMPOSE_FILE} ${ENV_DIR}/${COMPOSE_FILE}
    cp ${ENV_DIR}/backend/infrastructure/deployment/.env.${ENV} ${ENV_DIR}/.env.${ENV}
    cp ${ENV_DIR}/backend/infrastructure/deployment/deploy.sh ${APP_DIR}/deploy.sh

    echo "[${ENV}/Backend] Rebuilding..."
    docker compose -p ${PROJECT_NAME} -f ${COMPOSE_FILE} build --no-cache api-service
    docker compose -p ${PROJECT_NAME} -f ${COMPOSE_FILE} up -d api-service
    echo "[${ENV}/Backend] Done."
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
        ;;
    *)
        echo "Usage: ./deploy.sh <testing|staging|production> [frontend|backend|all]"
        exit 1
        ;;
esac

# Restart gateway nginx
echo "[Gateway] Restarting nginx..."
docker restart coa-gateway-nginx 2>/dev/null || true

echo ""
echo "=== [${ENV}] Container Status ==="
docker compose -p ${PROJECT_NAME} -f ${COMPOSE_FILE} ps