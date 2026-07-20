#!/bin/bash
# =============================================================================
# COA Migration — Demo Environment Host Setup (one-time)
#
# Run this ONCE on the server as the deploy user to bootstrap the demo env.
# Assumes /opt/coa-migration/ already exists (testing/staging are there).
#
# Usage:
#   bash host-setup.sh <github-pat> <nginx-container-name>
#
# Example:
#   bash host-setup.sh ghp_xxxxxxxxxxxx nginx-proxy
# =============================================================================
set -euo pipefail

GITHUB_PAT=${1:?"Usage: $0 <github-pat> <nginx-container-name>"}
NGINX_CONTAINER=${2:?"Usage: $0 <github-pat> <nginx-container-name>"}

DEMO_DIR=/opt/coa-migration/environments/demo
BACKEND_REPO="https://x-access-token:${GITHUB_PAT}@github.com/bhavna-linkedrp/COA_Mapping_backend_V0.git"

echo "=== Demo environment bootstrap ==="

# ── 1. Directory structure ────────────────────────────────────────────────────
echo "[1/6] Creating directory structure..."
mkdir -p "${DEMO_DIR}"

# ── 2. Clone backend repo ─────────────────────────────────────────────────────
echo "[2/6] Cloning backend (deploy-demo branch)..."
if [[ -d "${DEMO_DIR}/backend/.git" ]]; then
    echo "  Backend already cloned — fetching latest..."
    cd "${DEMO_DIR}/backend"
    git remote set-url origin "${BACKEND_REPO}"
    git fetch origin
    git reset --hard origin/deploy-demo
else
    git clone -b deploy-demo "${BACKEND_REPO}" "${DEMO_DIR}/backend"
fi

# ── 3. Copy compose file ──────────────────────────────────────────────────────
echo "[3/6] Copying docker-compose.demo.yml..."
cp "${DEMO_DIR}/backend/deploy/demo/docker-compose.demo.yml" "${DEMO_DIR}/docker-compose.demo.yml"

# ── 4. GitHub PAT for private dependency installs ────────────────────────────
echo "[4/6] Writing .gh_pat..."
echo "${GITHUB_PAT}" > "${DEMO_DIR}/.gh_pat"
chmod 600 "${DEMO_DIR}/.gh_pat"

# ── 5. .env.demo — fill this in before running deploy ────────────────────────
if [[ ! -f "${DEMO_DIR}/.env.demo" ]]; then
    echo "[5/6] Copying .env.demo.example → .env.demo (fill in secrets before deploying)..."
    cp "${DEMO_DIR}/backend/deploy/demo/.env.demo.example" "${DEMO_DIR}/.env.demo"
    echo ""
    echo "  !! ACTION REQUIRED: Edit ${DEMO_DIR}/.env.demo and replace all CHANGE_ME_ values !!"
    echo ""
else
    echo "[5/6] .env.demo already exists — skipping copy."
fi

# ── 6. Connect nginx to the coa-demo Docker network ──────────────────────────
echo "[6/6] Connecting nginx container (${NGINX_CONTAINER}) to coa-demo network..."
# The coa-demo network is created by docker compose on first up.
# Run the initial deploy first, then re-run this step:
#   docker network connect coa-demo ${NGINX_CONTAINER}
# Skipping here — network doesn't exist until first compose up.
echo "  Skipped — run after the first 'docker compose up': docker network connect coa-demo ${NGINX_CONTAINER}"

echo ""
echo "=== Bootstrap complete ==="
echo ""
echo "Next steps:"
echo "  1. Fill in ${DEMO_DIR}/.env.demo (all CHANGE_ME_ values)"
echo "  2. Run the initial deploy:"
echo "       cd ${DEMO_DIR}/backend"
echo "       GITHUB_TOKEN=${GITHUB_PAT} BE_REF=deploy-demo COA_DB_MODELS_BRANCH=develop bash scripts/deploy.sh demo backend"
echo "  3. Connect nginx to the demo network:"
echo "       docker network connect coa-demo ${NGINX_CONTAINER}"
echo "  4. Add the nginx blocks from deploy/demo/nginx-demo.conf into the live nginx.conf"
echo "  5. Reload nginx:"
echo "       docker exec ${NGINX_CONTAINER} nginx -s reload"
echo "  6. Run Alembic migrations:"
echo "       docker exec coa-demo-api-service-1 uv run alembic upgrade head"
