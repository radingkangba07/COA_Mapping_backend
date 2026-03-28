#!/bin/bash
set -euo pipefail

# =============================================================================
# COA Migration — Stop All Environments
# Usage: ./stop-all.sh              (stop all)
#        ./stop-all.sh testing      (stop one environment)
# =============================================================================

APP_DIR=/opt/coa-migration
ENV=${1:-all}

stop_env() {
    local ENV_NAME=$1
    local PROJECT=$2
    local COMPOSE=$3
    echo "Stopping ${ENV_NAME}..."
    cd ${APP_DIR}/environments/${ENV_NAME}
    docker compose -p ${PROJECT} -f ${COMPOSE} down
}

case ${ENV} in
    testing)
        stop_env "testing" "coa-testing" "docker-compose.testing.yml"
        ;;
    staging)
        stop_env "staging" "coa-staging" "docker-compose.staging.yml"
        ;;
    production)
        stop_env "production" "coa-prod" "docker-compose.prod.yml"
        ;;
    all)
        docker rm -f coa-gateway-nginx 2>/dev/null || true
        stop_env "testing" "coa-testing" "docker-compose.testing.yml"
        stop_env "staging" "coa-staging" "docker-compose.staging.yml"
        stop_env "production" "coa-prod" "docker-compose.prod.yml"
        echo "All environments stopped."
        ;;
    *)
        echo "Usage: ./stop-all.sh [testing|staging|production|all]"
        exit 1
        ;;
esac