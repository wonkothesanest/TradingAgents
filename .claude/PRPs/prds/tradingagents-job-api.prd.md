# TradingAgents Async Job API

## Problem Statement

N8N workflow automation requires remote execution of TradingAgents analysis, but the system currently only supports local CLI/Python invocation. Without an API interface, automated market analysis pipelines cannot trigger multi-ticker analysis on demand or retrieve structured results for downstream decision-making.

## Evidence

- TradingAgents `propagate()` method is blocking, synchronous, single-ticker only (tradingagents/graph/trading_graph.py:186-219)
- No HTTP interface exists for remote job submission
- Current runtime: 2-5 minutes per ticker (estimated from workflow structure)
- User requirement: Analyze 3+ stocks (NVDA, AAPL, MH) within 11 minutes per ticker in automated pipeline
- N8N workflows require HTTP REST endpoints with status polling for long-running tasks

## Proposed Solution

Build a containerized async job API service that wraps TradingAgents with:
- HTTP REST endpoints for job submission and status polling
- Job queue with configurable concurrency (default: 2 concurrent jobs for GPU constraints)
- Docker Compose deployment with Ollama (qwen3:latest) for local LLM inference
- Per-job configuration (model selection, debate rounds, analyst selection)
- Full state + report return in results payload

This keeps the API code architecturally separate from core TradingAgents but within the same repository.

## Key Hypothesis

We believe **an async job API with configurable concurrency** will **enable automated N8N pipeline execution** for **multi-ticker market analysis workflows**. We'll know we're right when **3 stocks can be analyzed in parallel (2 concurrent + 1 queued) and return full reports within 11 minutes per ticker**.

## What We're NOT Building

- ❌ **Web UI for job management** - N8N is the interface, API is headless
- ❌ **Authentication/authorization** - Handled at network level (Docker networking, future reverse proxy)
- ❌ **Webhook callbacks (v1)** - Polling-only for MVP, webhooks are stretch goal
- ❌ **Job history database** - Results saved to disk volume, no separate DB
- ❌ **Streaming/progressive results** - Only final report returned when job completes
- ❌ **Cloud GPU support (v1)** - Local GPU only, cloud deployment is future consideration
- ❌ **Multi-provider LLM support (v1)** - Default qwen3:latest, other providers are stretch goal

## Success Metrics

| Metric | Target | How Measured |
|--------|--------|--------------|
| Job submission latency | <500ms | Time from POST to 202 response |
| Concurrent job capacity | 2+ (configurable) | Number of simultaneous analyses |
| Analysis completion time | ≤11 min per ticker | From job start to completion |
| API uptime | >99% | Docker health checks + manual monitoring |
| Result retrieval success | 100% | Full state dict + reports returned |

## Open Questions

- [x] Job timeout duration - **Resolved: 30 minutes**
- [x] Result retention policy - **Resolved: Store forever, manual cleanup**
- [x] Ollama crash handling - **Deferred: Fail jobs immediately, restart handled by Docker**
- [x] GPU memory management with concurrency - **Deferred: Configurable limit, user responsibility**

---

## Users & Context

**Primary User**
- **Who**: Self (technically proficient developer building N8N automation pipelines)
- **Current behavior**: Running TradingAgents via CLI manually or Python scripts
- **Trigger**: N8N workflow selects stocks for analysis based on upstream filters/signals
- **Success state**: N8N receives full analyst reports + final trading decision for downstream buy/sell logic

**Job to Be Done**
When **my N8N workflow identifies candidate stocks**, I want to **trigger TradingAgents analysis via HTTP API**, so I can **automate market analysis at scale and feed results into trading decisions**.

**Non-Users**
- External clients (private API, Docker network only)
- Real-time traders (11-min latency too high)
- Teams needing collaborative UI (no web interface)

---

## Solution Detail

### Core Capabilities (MoSCoW)

| Priority | Capability | Rationale |
|----------|------------|-----------|
| Must | POST /jobs - Submit analysis job | Core functionality for job creation |
| Must | GET /jobs/{job_id} - Poll status | N8N needs to check completion |
| Must | GET /jobs/{job_id}/result - Retrieve report | Get full state dict + decision |
| Must | Configurable max concurrency | GPU constraint management (default 2) |
| Must | 30-minute job timeout | Prevent zombie jobs |
| Must | qwen3:latest default model | Local GPU inference requirement |
| Must | Docker Compose with Ollama | Simplified deployment |
| Should | Per-job config override | Custom LLM, debate rounds, analysts per request |
| Should | Job failure states with errors | Debugging and error handling |
| Should | Health check endpoint | Container orchestration |
| Could | DELETE /jobs/{job_id} - Cancel job | Nice-to-have for job management |
| Could | GET /jobs - List all jobs | Debugging and monitoring |
| Could | Webhook callback on completion | Alternative to polling (stretch goal) |
| Could | Support all LLM providers | OpenAI, Anthropic, Google (stretch goal) |
| Won't | Authentication/authorization | Network-level security sufficient for v1 |
| Won't | Job history database | Disk storage sufficient, no DB complexity |
| Won't | Streaming results | Final report only for v1 |

### MVP Scope

**Minimum to validate hypothesis:**
1. FastAPI server with 3 endpoints (submit, status, result)
2. Celery + Redis job queue
3. Worker pool (configurable concurrency)
4. Docker Compose: API + Worker + Redis + Ollama
5. qwen3:latest model integration
6. Results persisted to volume
7. 30-minute timeout handling

### User Flow

**Successful Job Flow:**
```
1. N8N → POST /jobs {"ticker": "NVDA", "date": "2026-02-12"}
2. API → 202 Accepted {"job_id": "abc123", "status": "pending"}
3. N8N polls → GET /jobs/abc123 → {"status": "running", "started_at": "..."}
4. (Wait ~5 minutes)
5. N8N polls → GET /jobs/abc123 → {"status": "completed", "completed_at": "..."}
6. N8N → GET /jobs/abc123/result → {
     "job_id": "abc123",
     "ticker": "NVDA",
     "decision": "BUY",
     "final_state": { ... full state dict ... },
     "reports": { "market": "...", "news": "...", ... }
   }
7. N8N continues pipeline with reports
```

**Parallel Job Flow (3 stocks):**
```
1. N8N submits 3 jobs: NVDA (job1), AAPL (job2), MH (job3)
2. job1 + job2 start immediately (concurrency=2)
3. job3 queued (pending)
4. job1 completes after 5min → job3 starts
5. job2 completes after 6min
6. job3 completes after 5min (11min total elapsed)
7. N8N retrieves all 3 results
```

**Error Handling:**
```
Timeout (30min) → {"status": "failed", "error": "Job exceeded 30-minute timeout"}
Ollama crash → {"status": "failed", "error": "LLM service unavailable"}
Invalid ticker → {"status": "failed", "error": "Invalid ticker symbol"}
Config error → {"status": "failed", "error": "Invalid configuration: ..."}
```

---

## Technical Approach

**Feasibility**: HIGH (8.5/10)

**Architecture Notes**
- **No GPU code dependencies**: TradingAgents uses network calls to LLM APIs (Ollama, OpenAI, etc.)
- **Config per request**: Full dict-based override support for model, debate rounds, analysts
- **Stateless design**: Each job is isolated via TradingAgentsGraph instance
- **Two persistent volumes**:
  - `/data/cache` - Market data cache (yfinance CSV files)
  - `/data/results` - Analysis reports and logs

**Key Technical Decisions:**

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| API Framework | FastAPI | Flask, Django | Native async, auto-docs, type hints |
| Job Queue | Celery + Redis | RQ, Temporal | Battle-tested, mature, result backend |
| LLM Default | qwen3:latest (Ollama) | GPT, Claude | Local GPU, no API costs, user requirement |
| Container Runtime | Docker Compose | Kubernetes | Simplicity, local deployment, single-machine |
| Result Storage | Disk volume | PostgreSQL, MongoDB | Matches existing TradingAgents pattern |
| Status Polling | Client-side | Webhooks | Simpler v1, webhooks are stretch goal |
| Concurrency Control | Celery worker pool | FastAPI BackgroundTasks | Proper queue management, configurable |

**Technical Risks**

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Ollama GPU memory exhaustion | Medium | Configurable concurrency limit (default 2) |
| 30-min timeout insufficient | Low | Configurable per deployment, user can increase |
| Docker network DNS issues | Low | Use service names in compose, test networking |
| Celery worker crash | Medium | Docker restart policy, health checks |
| Volume mount permission errors | Medium | Proper UID/GID mapping in Dockerfile |
| Result disk space exhaustion | Medium | Document manual cleanup process, no auto-expiration |

**Code Changes Required:**
1. **New directory**: `trading_api/` for API code (separate from core `tradingagents/`)
2. **Minor fix**: Make Ollama URL configurable via env var (currently hardcoded localhost:11434)
3. **Optional**: Use LangGraph's `ainvoke()` instead of sync `invoke()` for true async

---

## Implementation Phases

<!--
  STATUS: pending | in-progress | complete
  PARALLEL: phases that can run concurrently (e.g., "with 3" or "-")
  DEPENDS: phases that must complete first (e.g., "1, 2" or "-")
  PRP: link to generated plan file once created
-->

| # | Phase | Description | Status | Parallel | Depends | PRP Plan |
|---|-------|-------------|--------|----------|---------|----------|
| 1 | API Core Setup | FastAPI skeleton with 3 endpoints (POST /jobs, GET /jobs/{id}, GET /jobs/{id}/result) | complete | - | - | [api-core-setup.plan.md](../../plans/api-core-setup.plan.md) |
| 2 | Job Queue Infrastructure | Celery + Redis configuration, worker setup | complete | - | 1 | [job-queue-infrastructure.plan.md](../../plans/job-queue-infrastructure.plan.md) |
| 3 | TradingAgents Integration | Worker task that calls TradingAgentsGraph.propagate() | complete | - | 1, 2 | [3-tradingagents-integration.plan.md](../../plans/3-tradingagents-integration.plan.md) |
| 4 | Docker Compose Configuration | API + Worker + Redis + Ollama services with GPU support | complete | - | 1, 2 | [docker-compose-configuration.plan.md](../../plans/docker-compose-configuration.plan.md) |
| 5 | Configuration System | Per-job config override, env var management, Ollama URL fix | complete | with 6 | 3 | [configuration-system.plan.md](../../plans/completed/5-configuration-system.plan.md) |
| 6 | Timeout & Error Handling | 30-min timeout, failure states, health checks | complete | with 5 | 3 | [timeout-error-handling.plan.md](../../plans/timeout-error-handling.plan.md) |
| 7 | Volume & Results Management | Persistent volumes for cache + results, result format API response | complete | - | 4, 6 | [7-volume-results-management.plan.md](../../plans/completed/7-volume-results-management.plan.md) |
| 8 | Testing & Documentation | Integration tests, API docs, deployment guide | complete | - | 7 | [8-testing-documentation.plan.md](../../plans/completed/8-testing-documentation.plan.md) |

### Phase Details

**Phase 1: API Core Setup**
- **Goal**: Working HTTP API with job submission and status checking
- **Scope**:
  - FastAPI app skeleton in `trading_api/main.py`
  - POST /jobs endpoint (accepts ticker, date, optional config)
  - GET /jobs/{job_id} endpoint (returns status object)
  - GET /jobs/{job_id}/result endpoint (returns full state + reports)
  - In-memory job store (dict) for MVP
- **Success signal**: Can submit job and get 202 response with job_id

**Phase 2: Job Queue Infrastructure**
- **Goal**: Celery workers can process jobs from Redis queue
- **Scope**:
  - Celery app configuration in `trading_api/celery_app.py`
  - Redis connection setup
  - Task definition stub (no TradingAgents yet)
  - Worker process configuration
  - Result backend for status tracking
- **Success signal**: Worker picks up test task from queue and updates status

**Phase 3: TradingAgents Integration**
- **Goal**: Worker can execute full TradingAgents analysis
- **Scope**:
  - Celery task wraps `TradingAgentsGraph.propagate()`
  - Pass ticker, date, config from job payload
  - Capture full state dict + decision string
  - Handle exceptions and set failure status
  - Store results in result backend
- **Success signal**: Job completes and returns full state dict

**Phase 4: Docker Compose Configuration**
- **Goal**: Single `docker-compose up` deploys entire system
- **Scope**:
  - Dockerfile for API/worker (same image, different commands)
  - docker-compose.yml with 4 services: api, worker, redis, ollama
  - GPU device reservation for ollama service
  - Network configuration for inter-service communication
  - Volume definitions for cache + results
  - Environment variable injection
- **Success signal**: All services start, API reachable on localhost:8000

**Phase 5: Configuration System**
- **Goal**: Per-job LLM/config customization works
- **Scope**:
  - Accept optional config dict in POST /jobs payload
  - Merge with DEFAULT_CONFIG in worker
  - Make Ollama URL env-configurable (fix hardcoded localhost)
  - Document supported config options
  - Validate config before job submission
- **Success signal**: Job can override model, debate rounds, analysts via API

**Phase 6: Timeout & Error Handling**
- **Goal**: Jobs timeout at 30 minutes, failures are graceful
- **Scope**:
  - Celery task time_limit=1800 (30 minutes)
  - Soft timeout warning at 25 minutes
  - Exception handling for LLM errors, data fetch errors
  - Health check endpoint GET /health
  - Proper error messages in status object
- **Success signal**: Job times out at 30min and returns failed status

**Phase 7: Volume & Results Management**
- **Goal**: Results persist across container restarts
- **Scope**:
  - Named volumes in docker-compose
  - Results written to /data/results/{ticker}/{date}/
  - Cache written to /app/tradingagents/dataflows/data_cache/
  - Format API response with reports nested by section
  - Document manual cleanup process
- **Success signal**: Container restart preserves job results

**Phase 8: Testing & Documentation**
- **Goal**: System is testable and documented
- **Scope**:
  - Integration test: submit job → poll → retrieve result
  - Load test: submit 5 jobs, verify concurrency=2
  - Timeout test: simulate slow job, verify 30min cutoff
  - README with deployment instructions
  - API documentation (FastAPI auto-generates)
  - Troubleshooting guide
- **Success signal**: 3-stock test completes within 11min per ticker

### Parallelism Notes

Phases 5 and 6 can run in parallel as they touch different concerns:
- **Phase 5** (Configuration): Modifies request handling and config merging
- **Phase 6** (Timeout/Errors): Modifies worker task behavior and monitoring

Both depend on Phase 3 (TradingAgents Integration) being complete, but don't block each other.

---

## Decisions Log

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| API in same repo | Yes | Separate microservice repo | Keep related code together, share TradingAgents imports |
| Separate directory | `trading_api/` | `api/`, `server/`, `service/` | Clear namespace, avoid confusion with `cli/` |
| Job store | Redis (Celery result backend) | PostgreSQL, MongoDB | Simple, no extra dependency, matches queue infrastructure |
| Default concurrency | 2 | 1, 4, auto-detect GPU | User stated GPU supports 2 concurrent |
| Model config | Per-job override | API-level default only | Flexibility for testing different models |
| Polling interval | Client-defined | Server-side suggestion | N8N controls polling, not our concern |
| Result format | Full state dict + reports nested | Decision string only | User needs "full report for each to make decisions" |
| Docker networking | Compose internal network | Host network | Better isolation, service discovery via DNS |

---

## Research Summary

**Market Context**
- **N8N long-running job pattern**: HTTP 202 Accepted → poll status endpoint → retrieve result when complete
- **Job queue options**: Celery (mature, feature-rich), RQ (simpler), Temporal (complex but robust)
- **GPU Docker**: NVIDIA CUDA base images with `deploy.resources.reservations.devices` for GPU access
- **Common anti-patterns**: No timeouts, aggressive polling, missing retry logic, synchronous blocking requests

**Technical Context**
- **TradingAgents execution**: Single-ticker per `propagate()` call, 2-5 min runtime, returns (state_dict, decision_string)
- **Configuration system**: Dict-based, fully overridable per request via TradingAgentsGraph constructor
- **Dependencies**: Pure Python (LangChain, LangGraph, pandas, yfinance), no GPU libraries (PyTorch, CUDA)
- **Memory system**: BM25-based offline retrieval, no vector DB needed
- **LLM support**: Multi-provider (OpenAI, Anthropic, Google, xAI, OpenRouter, Ollama), Ollama hardcoded to localhost:11434 (needs fix)
- **State isolation**: Each TradingAgentsGraph instance is independent, no shared state
- **Volumes required**: Two persistent (data cache, results), one ephemeral (project dir)

---

*Generated: 2026-02-12*
*Status: DRAFT - ready for implementation planning*
