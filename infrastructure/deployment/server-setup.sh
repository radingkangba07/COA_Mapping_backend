#!/bin/bash
set -euo pipefail

# =============================================================================
# COA Migration — DigitalOcean Server Setup
# Target: Ubuntu 22.04/24.04, 2 vCPU, 8GB RAM, 150GB SSD
# Server: 209.38.122.199
# =============================================================================

echo "=== COA Migration Server Setup ==="

# --- System updates ---
echo "[1/7] Updating system packages..."
apt-get update && apt-get upgrade -y

# --- Install essential tools ---
echo "[2/7] Installing essential tools..."
apt-get install -y \
    curl \
    git \
    ufw \
    htop \
    unzip \
    fail2ban \
    ca-certificates \
    gnupg \
    lsb-release

# --- Install Docker ---
echo "[3/7] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "Docker installed: $(docker --version)"
else
    echo "Docker already installed: $(docker --version)"
fi

# --- Install Docker Compose plugin ---
echo "[4/7] Installing Docker Compose..."
if ! docker compose version &> /dev/null; then
    apt-get install -y docker-compose-plugin
    echo "Docker Compose installed: $(docker compose version)"
else
    echo "Docker Compose already installed: $(docker compose version)"
fi

# --- Configure firewall ---
echo "[5/7] Configuring firewall (UFW)..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS (for future use)
ufw --force enable
echo "Firewall configured. Open ports: 22, 80, 443"

# --- Configure fail2ban ---
echo "[6/7] Configuring fail2ban..."
systemctl enable fail2ban
systemctl start fail2ban

# --- Create application directory structure ---
echo "[7/7] Creating application directories..."
APP_DIR=/opt/coa-migration
mkdir -p ${APP_DIR}
mkdir -p ${APP_DIR}/frontend
mkdir -p ${APP_DIR}/backend
mkdir -p ${APP_DIR}/nginx
mkdir -p ${APP_DIR}/data/postgres
mkdir -p ${APP_DIR}/logs

# --- Clone repositories ---
echo "Cloning repositories..."

if [ ! -d "${APP_DIR}/frontend/.git" ]; then
    git clone https://github.com/bhavna-linkedrp/COA_Mapping_frontend_V0.git ${APP_DIR}/frontend
    cd ${APP_DIR}/frontend && git checkout main
else
    echo "Frontend repo already cloned"
fi

if [ ! -d "${APP_DIR}/backend/.git" ]; then
    git clone https://github.com/bhavna-linkedrp/COA_Mapping_backend_V0.git ${APP_DIR}/backend
    cd ${APP_DIR}/backend && git checkout feat/project-crud-endpoints
else
    echo "Backend repo already cloned"
fi

# --- Copy deployment files ---
echo "Setting up deployment config..."
cp ${APP_DIR}/frontend/deployment/docker-compose.prod.yml ${APP_DIR}/docker-compose.yml
cp ${APP_DIR}/frontend/deployment/nginx/nginx.conf ${APP_DIR}/nginx/nginx.conf
cp ${APP_DIR}/frontend/deployment/.env.production ${APP_DIR}/.env

echo ""
echo "==========================================="
echo "  Server setup complete!"
echo "==========================================="
echo ""
echo "Next steps:"
echo "  1. Edit /opt/coa-migration/.env with secure passwords"
echo "  2. cd /opt/coa-migration"
echo "  3. docker compose up -d --build"
echo "  4. Check status: docker compose ps"
echo "  5. View logs: docker compose logs -f"
echo ""
echo "App will be available at: http://209.38.122.199"
echo "==========================================="