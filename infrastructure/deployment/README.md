# COA Migration — Deployment Guide

Production deployment for the COA Migration System on DigitalOcean.

**Server:** 209.38.122.199 (2 vCPU, 8GB RAM, 150GB SSD)

## Architecture

```
┌──────────────────────────────────────────────────┐
│  DigitalOcean Droplet (209.38.122.199)           │
│                                                   │
│  ┌─────────┐                                     │
│  │  Nginx   │ :80 (→ :443 when HTTPS added)      │
│  │  Reverse │                                     │
│  │  Proxy   │                                     │
│  └────┬─────┘                                     │
│       │                                           │
│  ┌────┴──────────────────────┐                   │
│  │            │              │                    │
│  ▼            ▼              │                    │
│  Frontend    API Service     │                    │
│  (Expo Web)  (FastAPI)       │                    │
│  :80         :8001           │                    │
│              │               │                    │
│         ┌────┴────┐         │                    │
│         ▼         ▼         │                    │
│      PostgreSQL  RabbitMQ   │                    │
│      :5432       :5672      │                    │
└──────────────────────────────────────────────────┘
```

## File Structure

```
deployment/
├── server-setup.sh          # One-time server bootstrap
├── deploy.sh                # Pull & rebuild (frontend|backend|all)
├── docker-compose.prod.yml  # Production Docker Compose
├── .env.production          # Environment variable template
├── add-https-later.sh       # Add SSL when you have a domain
├── nginx/
│   └── nginx.conf           # Reverse proxy configuration
└── ci-cd/
    ├── frontend-deploy.yml  # GitHub Action — auto-deploy frontend
    └── backend-deploy.yml   # GitHub Action — auto-deploy backend
```

---

## Step 1: SSH Into the Server

```bash
ssh root@209.38.122.199
```

## Step 2: Run the Setup Script

Option A — clone and run:

```bash
git clone https://github.com/bhavna-linkedrp/COA_Mapping_frontend_V0.git /tmp/coa-setup
bash /tmp/coa-setup/deployment/server-setup.sh
```

Option B — download and run directly:

```bash
curl -fsSL https://raw.githubusercontent.com/bhavna-linkedrp/COA_Mapping_frontend_V0/main/deployment/server-setup.sh | bash
```

This installs Docker, Docker Compose, configures the firewall (ports 22, 80, 443), clones both repos, and creates the directory structure at `/opt/coa-migration`.

## Step 3: Set Secure Passwords

```bash
nano /opt/coa-migration/.env
```

Change **all** `CHANGE_ME_*` values to strong passwords. The password in `DATABASE_URL` **must match** `POSTGRES_PASSWORD`, and the password in `RABBITMQ_URL` **must match** `RABBITMQ_DEFAULT_PASS`.

Example:

```env
POSTGRES_PASSWORD=my_secure_pg_pass_2024
DATABASE_URL=postgresql+asyncpg://coa_user:my_secure_pg_pass_2024@postgres:5432/coa_db

RABBITMQ_DEFAULT_PASS=my_secure_rabbit_pass
RABBITMQ_URL=amqp://coa_rabbit:my_secure_rabbit_pass@rabbitmq:5672/

SECRET_KEY=some-long-random-string-here
```

## Step 4: Start Everything

```bash
cd /opt/coa-migration
docker compose up -d --build
```

First build takes a few minutes (downloading images, installing npm/pip dependencies).

## Step 5: Verify

```bash
# Check all containers are running
docker compose ps

# Watch logs for errors
docker compose logs -f

# Test the frontend
curl http://209.38.122.199

# Test the API
curl http://209.38.122.199/api/v1/health
```

The app is now live at **http://209.38.122.199**.

---

## Deployed Branches

| Service  | Repository                  | Branch                       |
|----------|-----------------------------|------------------------------|
| Frontend | `COA_Mapping_frontend_V0`   | `main`                       |
| Backend  | `COA_Mapping_backend_V0`    | `feat/project-crud-endpoints`|

---

## Manual Deployment

SSH into the server and run:

```bash
cd /opt/coa-migration

# Deploy everything
./deploy.sh all

# Deploy only frontend
./deploy.sh frontend

# Deploy only backend
./deploy.sh backend
```

---

## CI/CD — Auto-Deploy on Push

### 1. Create a Deploy SSH Key on the Server

```bash
ssh root@209.38.122.199
ssh-keygen -t ed25519 -f ~/.ssh/deploy_key -N ""
cat ~/.ssh/deploy_key.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/deploy_key   # copy this private key
```

### 2. Add GitHub Secrets to Both Repos

Go to each repo's **Settings > Secrets and variables > Actions** and add:

| Secret             | Value                                |
|--------------------|--------------------------------------|
| `SSH_USER`         | `root`                               |
| `SSH_PRIVATE_KEY`  | Contents of `~/.ssh/deploy_key`      |

### 3. Copy the Workflow Files

**Frontend repo** (`COA_Mapping_frontend_V0`):

```bash
cp deployment/ci-cd/frontend-deploy.yml .github/workflows/deploy-frontend.yml
```

**Backend repo** (`COA_Mapping_backend_V0`):

```bash
cp deployment/ci-cd/backend-deploy.yml .github/workflows/deploy-backend.yml
```

Commit and push both workflow files.

### How It Works

- Push to `main` in the frontend repo → auto-deploys the frontend
- Push to `feat/project-crud-endpoints` in the backend repo → auto-deploys the backend

---

## Adding HTTPS Later

Once you have a domain name pointed at `209.38.122.199`:

```bash
ssh root@209.38.122.199
bash /opt/coa-migration/frontend/deployment/add-https-later.sh yourdomain.com
```

This will:
- Install Certbot and obtain a Let's Encrypt SSL certificate
- Update Nginx to redirect HTTP → HTTPS
- Configure a monthly auto-renewal cron job

---

## Useful Commands

```bash
cd /opt/coa-migration

# View running containers
docker compose ps

# View logs (all services)
docker compose logs -f

# View logs for a specific service
docker compose logs -f api-service
docker compose logs -f frontend
docker compose logs -f postgres

# Restart a single service
docker compose restart api-service

# Rebuild and restart a single service
docker compose up -d --build api-service

# Stop everything
docker compose down

# Stop and remove all data (destructive!)
docker compose down -v

# Check disk usage
docker system df

# Clean up unused images
docker image prune -f
```