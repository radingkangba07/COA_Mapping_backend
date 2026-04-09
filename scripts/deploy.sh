#!/bin/bash
set -euo pipefail

# =============================================================================
# COA Migration — Multi-Environment Deployment Script
#
# Usage: ./deploy.sh <environment> [frontend|backend|all]
#
# Examples:
#   ./deploy.sh testing backend
#   ./deploy.sh staging all
#   ./deploy.sh production frontend
#
# Layout assumed on the host:
#   /opt/coa-migration/
#   ├── deploy.sh                                  ← this file
#   └── environments/
#       └── <env>/
#           ├── docker-compose.<env>.yml           ← maintained on the host
#           ├── .env.<env>                         ← maintained on the host
#           ├── backend/                           ← git checkout of api repo
#           └── frontend/                          ← git checkout of frontend repo
#
# The compose and env files live in the environment directory and are NOT
# synced from the backend repo. The api refactor moved away from carrying
# infra files in-tree; if you need to change compose/env, edit the file in
# /opt/coa-migration/environments/<env>/ directly.
# =============================================================================

APP_DIR=/opt/coa-migration
ENV=${1:?"Usage: ./deploy.sh <testing|staging|production> [frontend|backend|all]"}
COMPONENT=${2:-all}

case ${ENV} in
    testing)
        FE_BRANCH="develop"
        BE_BRANCH="develop"
        COMPOSE_FILE="docker-compose.testing.yml"
        PROJECT_NAME="coa-testing"
        ;;
    staging)
        FE_BRANCH="staging"
        BE_BRANCH="staging"
        COMPOSE_FILE="docker-compose.staging.yml"
        PROJECT_NAME="coa-staging"
        ;;
    production)
        FE_BRANCH="main"
        BE_BRANCH="main"
        COMPOSE_FILE="docker-compose.prod.yml"
        PROJECT_NAME="coa-prod"
        ;;
    *)
        echo "Unknown environment: ${ENV}"
        echo "Usage: ./deploy.sh <testing|staging|production> [frontend|backend|all]"
        exit 1
        ;;
esac

ENV_DIR=${APP_DIR}/environments/${ENV}
COMPOSE_PATH=${ENV_DIR}/${COMPOSE_FILE}

if [[ ! -f ${COMPOSE_PATH} ]]; then
    echo "ERROR: compose file not found at ${COMPOSE_PATH}"
    echo "Create/maintain it on the host — it is no longer synced from the repo."
    exit 1
fi

cd ${ENV_DIR}

echo "=== COA Deploy [${ENV}] — $(date -u) ==="
echo "    backend  branch: ${BE_BRANCH}"
echo "    frontend branch: ${FE_BRANCH}"
echo "    compose file:    ${COMPOSE_PATH}"
echo "    project name:    ${PROJECT_NAME}"

dc() {
    docker compose -p ${PROJECT_NAME} -f ${COMPOSE_PATH} "$@"
}

deploy_backend() {
    echo "[${ENV}/Backend] Pulling latest from ${BE_BRANCH}..."
    cd ${ENV_DIR}/backend
    git fetch origin
    git reset --hard origin/${BE_BRANCH}
    cd ${ENV_DIR}

    echo "[${ENV}/Backend] Rebuilding api-service..."
    dc build --no-cache api-service
    dc up -d api-service
    echo "[${ENV}/Backend] Done."
}

deploy_frontend() {
    echo "[${ENV}/Frontend] Pulling latest from ${FE_BRANCH}..."
    cd ${ENV_DIR}/frontend
    git fetch origin
    git reset --hard origin/${FE_BRANCH}
    cd ${ENV_DIR}

    echo "[${ENV}/Frontend] Rebuilding frontend..."
    dc build --no-cache frontend
    dc up -d frontend
    echo "[${ENV}/Frontend] Done."
}

case ${COMPONENT} in
    backend)  deploy_backend ;;
    frontend) deploy_frontend ;;
    all)      deploy_backend; deploy_frontend ;;
    *)
        echo "Unknown component: ${COMPONENT} (expected frontend|backend|all)"
        exit 1
        ;;
esac

echo "=== COA Deploy [${ENV}] complete ==="
dc ps
