# COA Migration — Multi-Environment Deployment Guide

Three isolated environments (testing, staging, production) on a single DigitalOcean droplet.

**Server:** 209.38.122.199 (2 vCPU, 8GB RAM, 150GB SSD)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  DigitalOcean Droplet — 209.38.122.199                      │
│                                                              │
│  ┌──────────────────────────────────────────────┐           │
│  │  Gateway Nginx (:80)                          │           │
│  │                                                │           │
│  │  /          → Production                       │           │
│  │  /staging/  → Staging                          │           │
│  │  /test/     → Testing                          │           │
│  └──────┬──────────────┬──────────────┬──────────┘           │
│         │              │              │                       │
│  ┌──────▼──────┐ ┌─────▼──────┐ ┌────▼───────┐             │
│  │ PRODUCTION  │ │  STAGING   │ │  TESTING   │             │
│  │             │ │            │ │            │             │
│  │ Frontend    │ │ Frontend   │ │ Frontend   │             │
│  │ API         │ │ API        │ │ API        │             │
│  │ PostgreSQL  │ │ PostgreSQL │ │ PostgreSQL │             │
│  │ RabbitMQ    │ │ RabbitMQ   │ │ RabbitMQ   │             │
│  │             │ │            │ │            │             │
│  │ Network:    │ │ Network:   │ │ Network:   │             │
│  │ coa-prod    │ │ coa-staging│ │ coa-testing│             │
│  └─────────────┘ └────────────┘ └────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

## Environment Details

| Environment | URL | Frontend Branch | Backend Branch |
|---|---|---|---|
| **Production** | http://209.38.122.199/ | `main` | `feat/project-crud-endpoints` |
| **Staging** | http://209.38.122.199/staging/ | `staging` | `staging` |
| **Testing** | http://209.38.122.199/test/ | `develop` | `develop` |

Each environment has its own:
- Docker Compose project (isolated containers)
- Docker network (no cross-talk)
- PostgreSQL database (separate volumes)
- RabbitMQ instance (separate volumes)
- Environment variables (.env file)

## File Structure

```
deployment/
├── server-setup.sh              # One-time multi-env bootstrap
├── deploy.sh                    # Deploy per environment
├── start-all.sh                 # Start all environments + gateway
├── stop-all.sh                  # Stop all or one environment
├── docker-compose.prod.yml      # Production compose
├── docker-compose.staging.yml   # Staging compose
├── docker-compose.testing.yml   # Testing compose
├── .env.production              # Production env template
├── .env.staging                 # Staging env template
├── .env.testing                 # Testing env template
├── add-https-later.sh           # Add SSL when domain available
├── nginx/
│   └── nginx.conf               # Gateway routing all 3 environments
├── ci-cd/
│   ├── frontend-deploy.yml      # GitHub Action — branch → environment
│   └── backend-deploy.yml       # GitHub Action — branch → environment
└── README.md
```

## Server Directory Structure (after setup)

```
/opt/coa-migration/
├── nginx/nginx.conf                  # Gateway config
├── deploy.sh                         # Deployment script
├── start-all.sh
├── stop-all.sh
└── environments/
    ├── testing/
    │   ├── frontend/                 # develop branch
    │   ├── backend/                  # develop branch
    │   ├── docker-compose.testing.yml
    │   └── .env.testing
    ├── staging/
    │   ├── frontend/                 # staging branch
    │   ├── backend/                  # staging branch
    │   ├── docker-compose.staging.yml
    │   └── .env.staging
    └── production/
        ├── frontend/                 # main branch
        ├── backend/                  # feat/project-crud-endpoints
        ├── docker-compose.prod.yml
        └── .env.production
```

---

## Initial Setup

### 1. SSH into the server

```bash
ssh deploy@209.38.122.199
```

### 2. Run the setup script

```bash
# Clone the backend repo to get the deployment files
git clone https://<user>:<pat>@github.com/bhavna-linkedrp/COA_Mapping_backend_V0.git /tmp/coa-setup
cd /tmp/coa-setup && git checkout feat/project-crud-endpoints

# Run setup (pass GitHub credentials for cloning private repos)
sudo bash infrastructure/deployment/server-setup.sh <github-username> <github-pat>
```

This clones all repos for all environments and generates secure passwords.

### 3. Start all environments

```bash
cd /opt/coa-migration
sudo bash start-all.sh
```

### 4. Verify

```bash
# Check containers
docker ps --format "table {{.Names}}\t{{.Status}}" | grep coa

# Test each environment
curl http://209.38.122.199/              # Production frontend
curl http://209.38.122.199/api/v1/erp-systems  # Production API
curl http://209.38.122.199/staging/      # Staging frontend
curl http://209.38.122.199/test/         # Testing frontend
```

---

## Deploying Updates

### Manual deploy

```bash
ssh deploy@209.38.122.199
cd /opt/coa-migration

# Deploy one environment
./deploy.sh production all          # rebuild both frontend + backend
./deploy.sh staging frontend        # rebuild only staging frontend
./deploy.sh testing backend         # rebuild only testing backend
```

### CI/CD auto-deploy

Push to the right branch and it deploys automatically:

| Push to branch | Deploys to |
|---|---|
| `main` (frontend) | Production |
| `feat/project-crud-endpoints` (backend) | Production |
| `staging` (either repo) | Staging |
| `develop` (either repo) | Testing |

**Setup required** — add these secrets to both GitHub repos (Settings > Secrets > Actions):

| Secret | Value |
|---|---|
| `SSH_USER` | `deploy` |
| `SSH_PRIVATE_KEY` | Server deploy key (see below) |

Generate the deploy key on the server:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/deploy_key -N ""
cat ~/.ssh/deploy_key.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/deploy_key   # copy this to GitHub secrets
```

Copy the workflow files to each repo:
```
ci-cd/frontend-deploy.yml → COA_Mapping_frontend_V0/.github/workflows/deploy-frontend.yml
ci-cd/backend-deploy.yml  → COA_Mapping_backend_V0/.github/workflows/deploy-backend.yml
```

---

## Managing Environments

```bash
cd /opt/coa-migration

# Start all
./start-all.sh

# Stop all
./stop-all.sh

# Stop one environment
./stop-all.sh testing

# View all containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep coa

# View logs for an environment
cd environments/production
docker compose -p coa-prod -f docker-compose.prod.yml logs -f

# View logs for a specific service
docker compose -p coa-prod -f docker-compose.prod.yml logs -f api-service

# Restart one service
docker compose -p coa-staging -f docker-compose.staging.yml restart api-service
```

---

## Adding HTTPS Later

Once you have a domain pointed at 209.38.122.199:

```bash
sudo bash /opt/coa-migration/environments/production/backend/infrastructure/deployment/add-https-later.sh yourdomain.com
```

---

## Resource Usage (estimated)

With 8GB RAM on the server:

| Component | Per Environment | x3 Environments | Total |
|---|---|---|---|
| Frontend (nginx) | ~30MB | ~90MB | |
| API (FastAPI) | ~150MB | ~450MB | |
| PostgreSQL | ~100MB | ~300MB | |
| RabbitMQ | ~150MB | ~450MB | |
| **Subtotal** | ~430MB | | **~1.3GB** |
| Gateway Nginx | | | ~30MB |
| OS + Docker | | | ~1GB |
| **Total** | | | **~2.3GB** |

Leaves ~5.7GB free for application data and build caches.

---

## Useful Commands

```bash
cd /opt/coa-migration

# View all COA containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep coa

# Check disk usage
docker system df

# Clean up unused images
docker image prune -f

# View gateway nginx logs
docker logs coa-gateway-nginx -f

# Rebuild everything from scratch
./stop-all.sh
docker system prune -af --volumes   # WARNING: deletes all data
./start-all.sh
```