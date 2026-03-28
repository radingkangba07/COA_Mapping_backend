#!/bin/bash
set -euo pipefail

# =============================================================================
# COA Migration — Add HTTPS via Let's Encrypt
# Run this AFTER you've pointed a domain to 209.38.122.199
# Usage: ./add-https-later.sh yourdomain.com
# =============================================================================

DOMAIN=${1:?"Usage: ./add-https-later.sh yourdomain.com"}
APP_DIR=/opt/coa-migration

echo "=== Adding HTTPS for ${DOMAIN} ==="

# Install certbot
echo "[1/4] Installing Certbot..."
apt-get update
apt-get install -y certbot python3-certbot-nginx

# Stop nginx container (certbot needs port 80)
echo "[2/4] Stopping nginx container temporarily..."
cd ${APP_DIR}
docker compose stop nginx

# Get certificate
echo "[3/4] Obtaining Let's Encrypt certificate..."
certbot certonly --standalone -d ${DOMAIN} --non-interactive --agree-tos --email admin@${DOMAIN}

# Generate new nginx config with SSL
echo "[4/4] Updating nginx config for HTTPS..."
cat > ${APP_DIR}/nginx/nginx.conf << NGINXEOF
upstream frontend {
    server frontend:80;
}

upstream api {
    server api-service:8001;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name ${DOMAIN};
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;

    # SSL settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    client_max_body_size 50M;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript;
    gzip_min_length 256;

    location /api/ {
        proxy_pass http://api;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_connect_timeout 60s;
    }

    location / {
        proxy_pass http://frontend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINXEOF

# Update docker-compose to mount SSL certs
# Add volume mount to nginx service
cd ${APP_DIR}
if ! grep -q "letsencrypt" docker-compose.yml; then
    sed -i '/nginx.conf:\/etc\/nginx\/conf.d\/default.conf:ro/a\      - /etc/letsencrypt:/etc/letsencrypt:ro' docker-compose.yml
    sed -i 's/- "80:80"/- "80:80"\n      - "443:443"/' docker-compose.yml
fi

# Update CORS_ORIGINS in .env
sed -i "s|CORS_ORIGINS=.*|CORS_ORIGINS=https://${DOMAIN}|" ${APP_DIR}/.env

# Restart everything
docker compose up -d

# Set up auto-renewal cron
echo "0 0 1 * * certbot renew --quiet && cd ${APP_DIR} && docker compose restart nginx" | crontab -

echo ""
echo "==========================================="
echo "  HTTPS enabled for ${DOMAIN}"
echo "==========================================="
echo "  - HTTP automatically redirects to HTTPS"
echo "  - Certificate auto-renews monthly"
echo "  - App: https://${DOMAIN}"
echo "==========================================="