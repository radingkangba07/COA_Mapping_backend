#!/bin/bash
set -euo pipefail

# =============================================================================
# COA Migration — Multi-Environment Server Setup
# Sets up testing, staging, and production on a single server
# Server: 209.38.122.199 (2 vCPU, 8GB RAM, 150GB SSD)
# =============================================================================

APP_DIR=/opt/coa-migration
GITHUB_USER=${1:?"Usage: ./server-setup.sh <github-username> <github-pat>"}
GITHUB_PAT=${2:?"Usage: ./server-setup.sh <github-username> <github-pat>"}

echo "=== COA Migration Multi-Environment Setup ==="

# --- Directory structure ---
echo "[1/4] Creating directory structure..."
mkdir -p ${APP_DIR}/environments/{testing,staging,production}
mkdir -p ${APP_DIR}/nginx
mkdir -p ${APP_DIR}/logs

# --- Clone repos for each environment ---
echo "[2/4] Cloning repositories for each environment..."

clone_env() {
    local ENV_NAME=$1
    local FE_BRANCH=$2
    local BE_BRANCH=$3
    local ENV_DIR=${APP_DIR}/environments/${ENV_NAME}

    echo "  [${ENV_NAME}] Cloning frontend (${FE_BRANCH})..."
    if [ ! -d "${ENV_DIR}/frontend/.git" ]; then
        git clone https://${GITHUB_USER}:${GITHUB_PAT}@github.com/bhavna-linkedrp/COA_Mapping_frontend_V0.git ${ENV_DIR}/frontend
    else
        echo "  [${ENV_NAME}] Frontend already cloned, pulling..."
        cd ${ENV_DIR}/frontend && git fetch origin
    fi
    cd ${ENV_DIR}/frontend && git checkout ${FE_BRANCH} 2>/dev/null || git checkout -b ${FE_BRANCH} origin/${FE_BRANCH}
    git reset --hard origin/${FE_BRANCH}

    echo "  [${ENV_NAME}] Cloning backend (${BE_BRANCH})..."
    if [ ! -d "${ENV_DIR}/backend/.git" ]; then
        git clone https://${GITHUB_USER}:${GITHUB_PAT}@github.com/bhavna-linkedrp/COA_Mapping_backend_V0.git ${ENV_DIR}/backend
    else
        echo "  [${ENV_NAME}] Backend already cloned, pulling..."
        cd ${ENV_DIR}/backend && git fetch origin
    fi
    cd ${ENV_DIR}/backend && git checkout ${BE_BRANCH} 2>/dev/null || git checkout -b ${BE_BRANCH} origin/${BE_BRANCH}
    git reset --hard origin/${BE_BRANCH}
}

clone_env "testing"    "develop"  "develop"
clone_env "staging"    "staging"  "staging"
clone_env "production" "main"     "feat/project-crud-endpoints"

# --- Copy deployment files ---
echo "[3/4] Copying deployment files..."

# Source deployment files from the production backend clone
DEPLOY_SRC=${APP_DIR}/environments/production/backend/infrastructure/deployment

for ENV_NAME in testing staging production; do
    ENV_DIR=${APP_DIR}/environments/${ENV_NAME}
    cp ${DEPLOY_SRC}/docker-compose.${ENV_NAME//production/prod}.yml ${ENV_DIR}/docker-compose.${ENV_NAME//production/prod}.yml
    cp ${DEPLOY_SRC}/.env.${ENV_NAME} ${ENV_DIR}/.env.${ENV_NAME}
done

# Copy shared files
cp ${DEPLOY_SRC}/deploy.sh ${APP_DIR}/deploy.sh
chmod +x ${APP_DIR}/deploy.sh
cp ${DEPLOY_SRC}/nginx/nginx.conf ${APP_DIR}/nginx/nginx.conf

# --- Generate secure passwords ---
echo "[4/4] Generating secure passwords..."

generate_env() {
    local ENV_NAME=$1
    local ENV_FILE=${APP_DIR}/environments/${ENV_NAME}/.env.${ENV_NAME}
    local PG_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
    local RMQ_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
    local SECRET=$(openssl rand -base64 48 | tr -dc 'a-zA-Z0-9' | head -c 48)

    sed -i "s/CHANGE_ME_.*_PG_PASSWORD/${PG_PASS}/g" ${ENV_FILE}
    sed -i "s/CHANGE_ME_.*_RMQ_PASSWORD/${RMQ_PASS}/g" ${ENV_FILE}
    sed -i "s/CHANGE_ME_.*_SECRET_KEY/${SECRET}/g" ${ENV_FILE}

    echo "  [${ENV_NAME}] Passwords generated"
}

generate_env "testing"
generate_env "staging"
generate_env "production"

echo ""
echo "==========================================="
echo "  Multi-environment setup complete!"
echo "==========================================="
echo ""
echo "Directory structure:"
echo "  /opt/coa-migration/"
echo "  ├── nginx/nginx.conf          (gateway)"
echo "  ├── deploy.sh                 (deploy script)"
echo "  ├── environments/"
echo "  │   ├── testing/              (develop branches)"
echo "  │   ├── staging/              (staging branches)"
echo "  │   └── production/           (main + feat branch)"
echo ""
echo "Next steps:"
echo "  1. Start all environments:  cd ${APP_DIR} && ./start-all.sh"
echo "  2. Or start one at a time:"
echo "     cd ${APP_DIR}/environments/production"
echo "     docker compose -p coa-prod -f docker-compose.prod.yml up -d --build"
echo ""
echo "URLs:"
echo "  Production:  http://209.38.122.199/"
echo "  Staging:     http://209.38.122.199/staging/"
echo "  Testing:     http://209.38.122.199/test/"
echo "==========================================="