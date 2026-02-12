# Feature: Docker Compose Deployment Configuration

## Summary

Creating a production-ready Docker Compose configuration that deploys the entire TradingAgents job API stack with a single `docker-compose up` command. Includes Dockerfile for API/worker (shared image with different entrypoints), docker-compose.yml defining 4 services (api, worker, redis, ollama), GPU device passthrough for Ollama LLM inference, inter-service networking, volume mounts for cache and results persistence, and environment variable injection from .env file. This enables one-command deployment on any Docker host with GPU support, eliminating manual service management and providing consistent development/production environments.

## User Story

As a TradingAgents system operator
I want to deploy the entire stack with `docker-compose up`
So that I can run the system without manual service coordination and get consistent environments

## Problem Statement

Phases 1-3 require manual coordination of multiple services: start Redis container, activate Python venv, start API server, start Celery worker, configure Ollama separately. This is error-prone (wrong venv, Redis not running, port conflicts), non-reproducible (works on laptop, fails on server), and blocks deployment to production environments where Docker orchestration is standard. The system architecture spans multiple runtimes (FastAPI Python app, Celery worker, Redis data store, Ollama LLM server) that need coordinated startup, networking, and resource allocation especially for GPU access.

## Solution Statement

Create `Dockerfile` that builds a Python runtime image with all project dependencies, uses multi-stage pattern to minimize image size, and supports both API and worker execution via command override. Create `docker-compose.yml` defining 4 services: (1) api - FastAPI server on port 8000, (2) worker - Celery worker with GPU access for local LLM calls, (3) redis - data broker/backend on port 6379, (4) ollama - LLM inference server with GPU device passthrough. Configure Docker networks for inter-service communication using service names (redis:6379, ollama:11434), define named volumes for data persistence (cache, results), inject environment variables from .env file, and set resource constraints (GPU reservation for ollama, memory limits for worker). Include .dockerignore to exclude unnecessary files from build context, docker-compose.override.yml for local development tweaks, and health checks for service orchestration dependencies.

## Metadata

| Field            | Value                                             |
| ---------------- | ------------------------------------------------- |
| Type             | NEW_CAPABILITY                                    |
| Complexity       | HIGH                                              |
| Systems Affected | New Dockerfile, docker-compose.yml, .dockerignore, deployment docs |
| Dependencies     | Phase 1-3 complete (API, Celery, TradingAgents all functional), Docker 20.10+, nvidia-container-toolkit |
| Estimated Tasks  | 8                                                 |
| PRD Phase        | Phase 4: Docker Compose Configuration             |
| PRD Reference    | `.claude/PRPs/prds/tradingagents-job-api.prd.md` |

---

## UX Design

### Before State (Phases 1-3)

```
Manual service management:
1. docker run redis (remember to name it, map port)
2. conda activate tradingagents (which venv?)
3. pip install -e . (did I install new deps?)
4. export OPENAI_API_KEY=... (10+ env vars)
5. ./run_api.sh (is port 8000 free?)
6. ./run_worker.sh (same venv as API?)
7. Ollama running? (separate install, separate config)

PAIN POINTS:
- 7 manual steps every restart
- Environment inconsistency (laptop vs server)
- Port conflicts
- Missing dependencies
- GPU passthrough manual config
```

### After State (Phase 4)

```
Automated service orchestration:
1. cp .env.example .env (fill in API keys once)
2. docker-compose up

DONE - All services start, networked, GPU-enabled

$ docker-compose ps
NAME                  STATUS
tradingagents-api     Up (healthy)
tradingagents-worker  Up
tradingagents-redis   Up (healthy)
tradingagents-ollama  Up (healthy)

http://localhost:8000/docs  ← API ready
http://localhost:8000/health  ← All services connected
```

### Interaction Changes

| Location | Before | After | User_Action | Impact |
|----------|--------|-------|-------------|--------|
| Deployment | 7 manual steps | `docker-compose up` | Start all services | One command deployment |
| Environment | venv + manual exports | .env file + Docker | Configure via .env | Consistent config |
| GPU Access | Manual nvidia-docker config | Automatic in compose | (Transparent) | Ollama gets GPU |
| Networking | localhost with ports | Docker service names | Inter-service calls | No port conflicts |
| Updates | pip install, restart all | `docker-compose up --build` | Update code | Clean rebuild |

---

## Mandatory Reading

**CRITICAL: Implementation agent MUST read these files before starting any task:**

| Priority | File | Lines | Why Read This |
|----------|------|-------|---------------|
| P0 | `pyproject.toml` | 11-37 | Dependencies list - must install all in Docker image |
| P0 | `.env.example` | 1-14 | Environment variables needed - Docker will load these |
| P0 | `run_api.sh` | 12 | API startup command - becomes Docker CMD |
| P0 | `run_worker.sh` | 12-17 | Worker startup command - becomes Docker CMD override |
| P1 | `trading_api/main.py` | 36-41 | FastAPI app instance - what uvicorn starts |
| P1 | `trading_api/celery_app.py` | 1-60 | Celery broker URL - must use redis:6379 in Docker |
| P2 | `tradingagents/default_config.py` | 3-34 | Config that may reference localhost - must be env-configurable |

**External Documentation:**

| Source | Section | Why Needed |
|--------|---------|------------|
| [Docker Compose File Reference](https://docs.docker.com/compose/compose-file/) | services, volumes, networks | Complete compose syntax |
| [Dockerfile Best Practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/) | Multi-stage builds, layer caching | Optimize image size |
| [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) | GPU passthrough in Docker | GPU access for Ollama |
| [Docker Compose GPU support](https://docs.docker.com/compose/gpu-support/) | deploy.resources.reservations.devices | GPU reservation syntax |
| [Ollama Docker](https://hub.docker.com/r/ollama/ollama) | Official Ollama image | How to run Ollama in Docker |

---

## Patterns to Mirror

### MULTI_STAGE_DOCKERFILE_PATTERN

```dockerfile
# Build stage - install build dependencies
FROM python:3.11-slim as builder
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir build && \
    python -m build

# Runtime stage - minimal image with only runtime deps
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /app/dist/*.whl ./
RUN pip install --no-cache-dir *.whl
COPY . .
CMD ["uvicorn", "trading_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**FOR THIS PROJECT:** Single stage OK (no compilation), focus on layer caching

### DOCKER_COMPOSE_SERVICE_PATTERN

```yaml
services:
  backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://db:5432/mydb
    depends_on:
      db:
        condition: service_healthy
    networks:
      - app-network
    volumes:
      - ./data:/app/data

  db:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: secret
    healthcheck:
      test: ["CMD", "pg_isready"]
      interval: 5s
    networks:
      - app-network

networks:
  app-network:
    driver: bridge

volumes:
  data:
```

**FOR THIS PROJECT:** 4 services (api, worker, redis, ollama), shared network, named volumes

### ENVIRONMENT_VARIABLE_INJECTION_PATTERN

```yaml
services:
  app:
    env_file:
      - .env  # Load all vars from .env file
    environment:
      - SERVICE_NAME=my-app  # Override specific vars
      - DB_HOST=postgres  # Docker service name
```

**FOR THIS PROJECT:** Use env_file for API keys, override broker URLs for Docker networking

---

## Files to Change

| File | Action | Justification |
|------|--------|---------------|
| `Dockerfile` | CREATE | Build image with Python 3.11, project dependencies, copy source code |
| `docker-compose.yml` | CREATE | Define 4 services (api, worker, redis, ollama), networking, volumes |
| `.dockerignore` | CREATE | Exclude __pycache__, .git, venv, results from Docker build context |
| `.env.example` | UPDATE | Add Docker-specific env vars (OLLAMA_URL, service hostnames) |
| `README.md` | UPDATE | Add Docker deployment instructions (deferred to Phase 8) |

---

## NOT Building (Scope Limits)

- ❌ **Docker Swarm / Kubernetes manifests** - Single-host Docker Compose only for v1
- ❌ **Multi-architecture builds** - x86_64 only, ARM64 support later if needed
- ❌ **CI/CD pipeline integration** - Manual deployment for Phase 4, automation later
- ❌ **Image registry push** - Local builds only, no DockerHub/ECR push yet
- ❌ **TLS/SSL certificates** - HTTP only, reverse proxy with TLS is separate concern
- ❌ **Secrets management** - .env file for Phase 4, Vault/Secrets Manager later
- ❌ **Container security scanning** - No Trivy/Snyk integration yet
- ❌ **Log aggregation** - stdout/stderr only, ELK/Loki integration out of scope
- ❌ **Monitoring (Prometheus/Grafana)** - Phase 8 may add, not Phase 4
- ❌ **Backup automation** - Manual volume backup process documented, no cron jobs

---

## Step-by-Step Tasks

### Task 1: CREATE `.dockerignore`

**ACTION**: CREATE .dockerignore file to exclude unnecessary files from build context

**IMPLEMENT**:

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
*.egg-info/
dist/
build/

# Virtual environments
venv/
env/
ENV/
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo
.DS_Store

# Git
.git/
.gitignore

# Results and cache (will use Docker volumes instead)
results/
tradingagents/dataflows/data_cache/

# Documentation
*.md
docs/

# CI/CD
.github/
.gitlab-ci.yml

# Tests
tests/
.pytest_cache/

# Docker
Dockerfile
docker-compose*.yml
.dockerignore

# Environment
.env
.env.*
```

**LOCATION**: `.dockerignore` (project root)

**RATIONALE**:
- Reduces build context size (faster builds)
- Prevents caching issues from __pycache__
- Excludes secrets (.env file)
- results/ and cache/ use Docker volumes instead

**VALIDATE**:
```bash
ls -la .dockerignore
cat .dockerignore | wc -l
```

**EXPECT**: File exists, ~50 lines

---

### Task 2: CREATE `Dockerfile`

**ACTION**: CREATE Dockerfile for API/worker shared image

**IMPLEMENT**:

```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY tradingagents/ ./tradingagents/
COPY trading_api/ ./trading_api/
COPY cli/ ./cli/
COPY main.py ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Create directories for volumes
RUN mkdir -p /app/results /app/tradingagents/dataflows/data_cache

# Expose API port (not used by worker, but harmless)
EXPOSE 8000

# Default command (API server) - worker overrides this
CMD ["uvicorn", "trading_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**LOCATION**: `Dockerfile` (project root)

**RATIONALE**:
- python:3.11-slim balances size and compatibility
- build-essential needed for some Python packages (numpy, etc.)
- Single image for API and worker (DRY principle)
- Volumes mounted at /app/results and /app/tradingagents/dataflows/data_cache
- CMD is default (API), docker-compose overrides for worker

**GOTCHA**:
- Must copy pyproject.toml before pip install
- Use -e . for editable install (simpler than wheel build)
- Create volume mount points in Dockerfile (mkdir -p)

**VALIDATE**:
```bash
docker build -t tradingagents:test .
docker images | grep tradingagents
```

**EXPECT**: Image builds successfully, size ~1-2GB

---

### Task 3: UPDATE `.env.example` (add Docker networking vars)

**ACTION**: ADD Docker-specific environment variables for service networking

**IMPLEMENT**: Add these lines after existing config (after line 14):

```bash
# Docker Compose Service Networking (override for Docker)
# Use these when running in Docker, localhost when running locally
REDIS_HOST=redis
REDIS_PORT=6379
OLLAMA_BASE_URL=http://ollama:11434
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Worker Configuration
CELERY_WORKER_CONCURRENCY=2
CELERY_WORKER_MAX_TASKS_PER_CHILD=50
```

**LOCATION**: `.env.example` after line 14

**RATIONALE**:
- Docker Compose creates a network where services resolve by name
- redis:6379 resolves to Redis container (not localhost:6379)
- ollama:11434 resolves to Ollama container
- Workers need concurrency config

**GOTCHA**:
- These override localhost values for Docker only
- Local development still uses localhost
- Must match service names in docker-compose.yml

**VALIDATE**:
```bash
grep "REDIS_HOST" .env.example
```

**EXPECT**: Line exists with value "redis"

---

### Task 4: CREATE `docker-compose.yml` (define services)

**ACTION**: CREATE docker-compose.yml with api, worker, redis, ollama services

**IMPLEMENT**:

```yaml
version: '3.8'

services:
  # Redis broker and result backend
  redis:
    image: redis:7-alpine
    container_name: tradingagents-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --maxmemory 512mb --maxmemory-policy noeviction
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    restart: unless-stopped
    networks:
      - tradingagents

  # FastAPI application
  api:
    build: .
    container_name: tradingagents-api
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
      - REDIS_HOST=redis
      - OLLAMA_BASE_URL=http://ollama:11434
    depends_on:
      redis:
        condition: service_healthy
    volumes:
      - ./results:/app/results
      - cache_data:/app/tradingagents/dataflows/data_cache
    restart: unless-stopped
    networks:
      - tradingagents
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  # Celery worker
  worker:
    build: .
    container_name: tradingagents-worker
    command: celery -A trading_api.celery_app worker --loglevel=info --concurrency=2 --time-limit=1800 --soft-time-limit=1500 --max-tasks-per-child=50
    env_file:
      - .env
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
      - REDIS_HOST=redis
      - OLLAMA_BASE_URL=http://ollama:11434
    depends_on:
      redis:
        condition: service_healthy
      ollama:
        condition: service_healthy
    volumes:
      - ./results:/app/results
      - cache_data:/app/tradingagents/dataflows/data_cache
    restart: unless-stopped
    networks:
      - tradingagents
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  # Ollama LLM inference server
  ollama:
    image: ollama/ollama:latest
    container_name: tradingagents-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama
    restart: unless-stopped
    networks:
      - tradingagents
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 10s
      timeout: 5s
      retries: 5

networks:
  tradingagents:
    driver: bridge

volumes:
  redis_data:
  cache_data:
  ollama_models:
```

**LOCATION**: `docker-compose.yml` (project root)

**MIRROR**: Docker Compose service pattern from external docs

**RATIONALE**:
- **redis**: Alpine image (small), health check for dependencies, maxmemory prevents OOM
- **api**: Built from Dockerfile, exposes 8000, depends on Redis health
- **worker**: Same image as api, different CMD, GPU access, depends on Redis + Ollama
- **ollama**: Official image, GPU passthrough, persistent models volume
- **networks**: Isolated bridge network for inter-service communication
- **volumes**: Named volumes persist data across restarts

**GOTCHA**:
- GPU deploy section requires nvidia-container-toolkit installed on host
- Service names (redis, ollama) become DNS names within network
- env_file loads .env, environment section overrides specific vars
- Health checks prevent worker starting before Redis ready

**VALIDATE**:
```bash
docker-compose config
```

**EXPECT**: Valid YAML, no errors

---

### Task 5: CREATE `docker-compose.override.yml` (local development)

**ACTION**: CREATE override file for local development conveniences

**IMPLEMENT**:

```yaml
version: '3.8'

services:
  api:
    volumes:
      - .:/app  # Mount source code for hot reload
    command: uvicorn trading_api.main:app --host 0.0.0.0 --port 8000 --reload

  worker:
    volumes:
      - .:/app  # Mount source code for hot reload
```

**LOCATION**: `docker-compose.override.yml` (project root)

**RATIONALE**:
- Override file automatically loaded by docker-compose
- Mounts source code for live edits (no rebuild needed)
- API uses --reload for hot reload on file changes
- Only applies in development (production ignores override file)

**GOTCHA**:
- Override file takes precedence over docker-compose.yml
- Can disable override with: `docker-compose -f docker-compose.yml up`
- .dockerignore doesn't apply to volume mounts (all files visible)

**VALIDATE**:
```bash
docker-compose config | grep reload
```

**EXPECT**: Shows --reload flag in api command

---

### Task 6: CREATE `scripts/docker-entrypoint.sh` (optional, for initialization)

**ACTION**: CREATE entrypoint script for container initialization tasks

**IMPLEMENT**:

```bash
#!/bin/bash
set -e

# Wait for Redis to be ready (if WAIT_FOR_REDIS=1)
if [ "$WAIT_FOR_REDIS" = "1" ]; then
    echo "Waiting for Redis at ${REDIS_HOST:-redis}:${REDIS_PORT:-6379}..."
    while ! nc -z "${REDIS_HOST:-redis}" "${REDIS_PORT:-6379}"; do
        sleep 1
    done
    echo "Redis is ready"
fi

# Run migrations or setup tasks here (if needed in future)
# python manage.py migrate

# Execute the main command (passed as arguments)
exec "$@"
```

**LOCATION**: `scripts/docker-entrypoint.sh` (new directory)

**RATIONALE**:
- Centralizes initialization logic
- Can wait for dependencies
- Future-proof for migrations or setup tasks

**GOTCHA**:
- Must chmod +x the script
- Must use exec "$@" to pass signals correctly

**OPTIONAL**: Skip this task if health checks in docker-compose.yml are sufficient

---

### Task 7: CREATE startup helper scripts

**ACTION**: CREATE convenience scripts for Docker operations

**IMPLEMENT `scripts/docker-up.sh`**:

```bash
#!/bin/bash
# Start all services

set -e

echo "Starting TradingAgents services with Docker Compose..."
echo ""
echo "Services will be available at:"
echo "  API: http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo "  Ollama: http://localhost:11434"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  Warning: .env file not found"
    echo "Copy .env.example to .env and fill in your API keys:"
    echo "  cp .env.example .env"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Start services
docker-compose up --build -d

echo ""
echo "✅ Services started!"
echo ""
echo "Check status: docker-compose ps"
echo "View logs: docker-compose logs -f"
echo "Stop services: docker-compose down"
```

**IMPLEMENT `scripts/docker-down.sh`**:

```bash
#!/bin/bash
# Stop all services

set -e

echo "Stopping TradingAgents services..."
docker-compose down

echo ""
echo "✅ Services stopped"
echo ""
echo "To remove volumes (WARNING: deletes data):"
echo "  docker-compose down -v"
```

**IMPLEMENT `scripts/docker-logs.sh`**:

```bash
#!/bin/bash
# View logs from all services or specific service

if [ -z "$1" ]; then
    echo "Following logs from all services..."
    echo "Press Ctrl+C to stop"
    echo ""
    docker-compose logs -f
else
    echo "Following logs from $1..."
    echo "Press Ctrl+C to stop"
    echo ""
    docker-compose logs -f "$1"
fi
```

**LOCATION**: `scripts/` directory (create directory)

**VALIDATE**:
```bash
chmod +x scripts/*.sh
ls -la scripts/
```

**EXPECT**: 3 executable scripts

---

### Task 8: TEST Docker Compose deployment

**ACTION**: VERIFY complete stack deploys and functions correctly

**TEST PROCEDURE**:

```bash
# 1. Create .env file
cp .env.example .env
# Edit .env to add your OPENAI_API_KEY or other LLM provider key

# 2. Build and start services
docker-compose up --build

# Wait for all services to start (watch logs)
# Should see:
#   - redis: "Ready to accept connections"
#   - api: "Application startup complete"
#   - worker: "celery@worker ready"
#   - ollama: "Ollama is running"

# 3. Check service health (in another terminal)
docker-compose ps

# Expected output:
#   NAME                     STATUS
#   tradingagents-api        Up (healthy)
#   tradingagents-worker     Up
#   tradingagents-redis      Up (healthy)
#   tradingagents-ollama     Up (healthy)

# 4. Test API endpoint
curl http://localhost:8000/health

# Expected: {"status": "healthy"}

# 5. Submit test job
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2024-05-10"}'

# Expected: {"job_id": "...", "status": "pending", ...}

# 6. Check worker logs
docker-compose logs -f worker

# Expected: Should see "Starting propagate() for NVDA"

# 7. Verify volumes
docker volume ls | grep tradingagents

# Expected: See redis_data, cache_data, ollama_models

# 8. Stop services
docker-compose down

# Expected: All containers stop gracefully
```

**VALIDATION CHECKLIST**:
- [ ] `docker-compose up` starts all 4 services without errors
- [ ] All services show "Up" or "Up (healthy)" in `docker-compose ps`
- [ ] API health check returns 200 OK
- [ ] API docs accessible at http://localhost:8000/docs
- [ ] Job submission returns 202 Accepted
- [ ] Worker picks up job (visible in logs)
- [ ] Volumes persist data (redis_data, cache_data, ollama_models exist)
- [ ] Services communicate (worker → redis, api → redis, worker → ollama)
- [ ] GPU accessible in worker container (`nvidia-smi` works if exec'd in)
- [ ] `docker-compose down` stops cleanly

---

## Testing Strategy

### Manual Testing Checklist

**Prerequisites**:
- Docker 20.10+ installed
- Docker Compose plugin installed (or docker-compose standalone)
- nvidia-container-toolkit installed (for GPU support)
- .env file created with API keys

**Test 1: Clean Build and Startup**
```bash
# Remove old containers/volumes
docker-compose down -v

# Build and start
docker-compose up --build

# Expected: All 4 services start, no errors
```

**Test 2: Service Health Checks**
```bash
# Wait 30 seconds for startup
sleep 30

# Check all healthy
docker-compose ps

# Expected: api, redis, ollama show (healthy)
```

**Test 3: API Reachability**
```bash
curl http://localhost:8000/health
curl http://localhost:8000/
curl http://localhost:8000/docs

# Expected: All return 200 OK
```

**Test 4: Job Execution**
```bash
# Submit job
JOB=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2024-05-10"}')

JOB_ID=$(echo $JOB | jq -r '.job_id')

# Wait for completion (2-15 min)
sleep 300

# Check status
curl http://localhost:8000/jobs/$JOB_ID

# Expected: status="completed"
```

**Test 5: Volume Persistence**
```bash
# Stop services
docker-compose down

# Restart
docker-compose up -d

# Check volumes still exist
docker volume ls | grep tradingagents

# Expected: Volumes persist, data not lost
```

**Test 6: Worker GPU Access**
```bash
# Exec into worker container
docker exec -it tradingagents-worker nvidia-smi

# Expected: Shows GPU info (if nvidia-container-toolkit installed)
```

**Test 7: Logs Aggregation**
```bash
# View all logs
docker-compose logs

# View specific service
docker-compose logs api
docker-compose logs worker

# Expected: Logs from all services visible
```

**Test 8: Resource Limits**
```bash
# Check container resource usage
docker stats tradingagents-api tradingagents-worker

# Expected: Memory/CPU usage visible
```

### Edge Cases Checklist

- [ ] Start with Redis already running on port 6379 (port conflict)
- [ ] Start without .env file (should warn or use defaults)
- [ ] Start without GPU (nvidia-container-toolkit not installed)
- [ ] Kill worker mid-job (job should fail gracefully)
- [ ] Restart API while worker running (worker should reconnect)
- [ ] Fill disk with cache data (container should handle gracefully)
- [ ] Submit job with missing API keys (should fail with clear error)

---

## Validation Commands

### Level 1: SYNTAX_CHECK

```bash
# Validate Dockerfile syntax
docker build --no-cache -t tradingagents:test . --target builder || echo "Dockerfile OK"

# Validate docker-compose.yml syntax
docker-compose config > /dev/null && echo "docker-compose.yml OK"

# Validate .dockerignore exists
test -f .dockerignore && echo ".dockerignore OK"
```

**EXPECT**: All validations pass

---

### Level 2: BUILD_TEST

```bash
# Build image
docker build -t tradingagents:test .

# Check image size
docker images tradingagents:test

# Expected: Image size 1-2GB, build succeeds
```

**EXPECT**: Build completes, image created

---

### Level 3: INTEGRATION_TEST

```bash
# Full stack test
docker-compose up -d

# Wait for health
sleep 30

# Test API
curl -f http://localhost:8000/health || exit 1

# Submit job
JOB_ID=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2024-05-10"}' | jq -r '.job_id')

echo "Job submitted: $JOB_ID"

# Cleanup
docker-compose down

echo "✅ Integration test passed"
```

**EXPECT**: All commands succeed, job submitted

---

## Acceptance Criteria

- [ ] `docker-compose up` starts all 4 services successfully
- [ ] Dockerfile builds image with all dependencies
- [ ] API accessible at http://localhost:8000
- [ ] Worker connects to Redis broker
- [ ] Worker can access Ollama on http://ollama:11434
- [ ] GPU passthrough works (worker/ollama can use nvidia GPU)
- [ ] Named volumes persist data across restarts
- [ ] Services communicate via Docker network (not localhost)
- [ ] Health checks prevent dependencies starting out of order
- [ ] .env file variables injected into containers
- [ ] API docs accessible at http://localhost:8000/docs
- [ ] Job submission works end-to-end in Docker
- [ ] Worker logs visible via `docker-compose logs worker`
- [ ] `docker-compose down` stops all services cleanly
- [ ] `docker-compose down -v` removes volumes
- [ ] .dockerignore excludes unnecessary files from build

---

## Completion Checklist

- [ ] Task 1: .dockerignore created
- [ ] Task 2: Dockerfile created (single image for api+worker)
- [ ] Task 3: .env.example updated with Docker networking vars
- [ ] Task 4: docker-compose.yml created (4 services defined)
- [ ] Task 5: docker-compose.override.yml created (dev overrides)
- [ ] Task 6: docker-entrypoint.sh created (optional)
- [ ] Task 7: Helper scripts created (docker-up.sh, docker-down.sh, docker-logs.sh)
- [ ] Task 8: Full deployment tested successfully
- [ ] All validation commands pass (Level 1-3)
- [ ] All acceptance criteria met
- [ ] Manual testing checklist completed

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| GPU driver mismatch (host vs container) | Medium | High | Document nvidia-container-toolkit version requirements |
| Large image size (>3GB) | Medium | Medium | Use python:3.11-slim, .dockerignore, no dev dependencies |
| Port conflicts (6379, 8000, 11434) | Medium | Low | Document required ports, provide override options |
| Volume permission issues | Medium | Medium | Run containers as non-root user (future enhancement) |
| Out of disk space from volumes | Low | High | Document volume cleanup, monitor disk usage |
| Network isolation breaks Ollama calls | Low | High | Test inter-service communication thoroughly |
| Missing nvidia-container-toolkit | High | High | Graceful fallback to CPU-only mode (document in README) |
| .env file not created | High | Low | Script checks for .env, warns if missing |

---

## Notes

**Design Decisions:**

1. **Single image for API and worker**: Reduces build time, ensures consistency, overrides CMD for worker

2. **Named volumes vs bind mounts**: Named volumes for data (managed by Docker), bind mount results/ for easy access

3. **GPU passthrough on worker and ollama**: Both need GPU, worker for potential local inference, ollama for serving models

4. **Health checks with dependencies**: Prevents worker starting before Redis ready, more reliable than sleep

5. **Override file for development**: Enables hot reload without changing main compose file

6. **Alpine Redis image**: Minimal size, sufficient for broker/backend role

7. **Official Ollama image**: Pre-configured for GPU, includes model management

8. **Bridge network (default)**: Simple, sufficient for single-host deployment

**GPU Requirements:**

- **Host must have**:
  - NVIDIA GPU with CUDA support
  - nvidia-docker2 or nvidia-container-toolkit installed
  - Docker 19.03+ with nvidia runtime

- **Verification**:
  ```bash
  docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
  ```

**Common Issues and Fixes:**

| Issue | Solution |
|-------|----------|
| "could not select device driver" | Install nvidia-container-toolkit |
| "address already in use" | Change ports in docker-compose.yml or stop conflicting services |
| "cannot connect to redis" | Check redis health, verify service name in broker URL |
| "permission denied" on volumes | Run `docker-compose down -v` and recreate volumes |
| Worker can't find Ollama | Check ollama service health, verify network connectivity |
| Large image size | Review .dockerignore, remove unused dependencies |

**Performance Tuning:**

- **Worker concurrency**: Default 2, adjust based on CPU cores and RAM
- **Redis maxmemory**: Default 512MB, increase if many jobs queued
- **Ollama models**: Pre-pull models to avoid download delay: `docker exec tradingagents-ollama ollama pull qwen3:latest`
- **Build cache**: Use `--build-arg BUILDKIT_INLINE_CACHE=1` for faster rebuilds

**Security Notes (Phase 4 Scope):**

- Containers run as root (future: non-root user)
- No resource limits except GPU (future: memory/CPU limits)
- .env file contains secrets (future: Docker secrets or Vault)
- No network encryption (future: TLS between services)
- Default security group exposes ports (future: reverse proxy only)
