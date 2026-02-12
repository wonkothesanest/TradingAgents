# Feature: Job Queue Infrastructure with Celery + Redis

## Summary

Implementing Celery 5.x with Redis broker/backend to enable asynchronous background execution of TradingAgents analysis jobs. Phase 1 created the FastAPI REST API with in-memory job tracking, but jobs never execute. Phase 2 adds distributed task queue infrastructure so workers can pick up and process jobs in the background while the API responds immediately with 202 Accepted. Uses Celery for task distribution, retry logic, and worker management, while maintaining the existing job_store interface for status tracking to preserve API contract compatibility.

## User Story

As a TradingAgents API user
I want submitted jobs to be processed asynchronously by workers
So that long-running analysis tasks don't block the API and multiple jobs can run concurrently

## Problem Statement

Phase 1 implemented the HTTP API layer (POST /jobs, GET /jobs/{id}, GET /jobs/{id}/result) with in-memory job storage, but jobs remain in PENDING status indefinitely because there's no background worker infrastructure to execute them. N8N workflows submit jobs and poll for completion, but the API never transitions jobs through RUNNING → COMPLETED states. This blocks the core value proposition: parallel multi-ticker analysis for automated trading pipelines.

## Solution Statement

Add Celery 5.x distributed task queue with Redis as both broker (job queue) and result backend. When FastAPI receives POST /jobs, it dispatches a Celery task with `analyze_stock.delay(job_id, ticker, date, config)`. One or more Celery workers listen on the Redis queue, pick up tasks, update job status to RUNNING, and execute a test stub (Phase 3 will add actual TradingAgentsGraph execution). Workers update job status to COMPLETED or FAILED via the existing job_store methods, maintaining full API compatibility. This infrastructure enables the PRD success metric: 2+ concurrent jobs with configurable worker pools.

## Metadata

| Field            | Value                                             |
| ---------------- | ------------------------------------------------- |
| Type             | NEW_CAPABILITY                                    |
| Complexity       | MEDIUM                                            |
| Systems Affected | trading_api/ (main.py, new celery_app.py, tasks.py), config, dependencies |
| Dependencies     | celery[redis]>=5.4.0, redis>=6.2.0 (already in pyproject.toml) |
| Estimated Tasks  | 7                                                 |
| PRD Phase        | Phase 2: Job Queue Infrastructure                 |
| PRD Reference    | `.claude/PRPs/prds/tradingagents-job-api.prd.md` |

---

## UX Design

### Before State (Phase 1)

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                              BEFORE STATE (Phase 1)                            ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║   ┌─────────────┐         ┌─────────────┐         ┌─────────────┐            ║
║   │   N8N       │  POST   │  FastAPI    │ create  │  In-Memory  │            ║
║   │  Workflow   │ ──────► │    API      │ ──────► │  Job Dict   │            ║
║   └─────────────┘         └─────────────┘         └─────────────┘            ║
║         │                                                 │                   ║
║         │ GET /jobs/{id} (poll every 10s)                │                   ║
║         └─────────────────────────────────────────────────┘                   ║
║                                                                               ║
║   USER_FLOW:                                                                   ║
║   1. N8N → POST /jobs {ticker, date}                                           ║
║   2. API → 202 Accepted {job_id, status: PENDING}                             ║
║   3. N8N polls → GET /jobs/{id} → {status: PENDING}                           ║
║   4. [BLOCKED] Job never executes - stays PENDING forever                     ║
║   5. N8N times out waiting for completion                                     ║
║                                                                               ║
║   PAIN_POINT:                                                                  ║
║   - Jobs created but never executed                                           ║
║   - No background worker infrastructure                                       ║
║   - Polling returns PENDING indefinitely                                      ║
║   - Cannot analyze multiple tickers in parallel                               ║
║                                                                               ║
║   DATA_FLOW:                                                                   ║
║   Request → Validation → UUID generation → In-memory storage → 202 response   ║
║   → [DEAD END - no execution]                                                 ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

### After State (Phase 2)

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                          AFTER STATE (Phase 2 + Celery)                        ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║   ┌─────────────┐         ┌─────────────┐         ┌─────────────┐            ║
║   │   N8N       │  POST   │  FastAPI    │ dispatch│   Celery    │            ║
║   │  Workflow   │ ──────► │    API      │ ──────► │    Broker   │            ║
║   └─────────────┘         └─────────────┘         │   (Redis)   │            ║
║         │                         │                └──────┬──────┘            ║
║         │                         │                       │                   ║
║         │                         │                       ▼                   ║
║         │                         │                ┌─────────────┐            ║
║         │                         │                │   Celery    │            ║
║         │                         │                │   Worker    │            ║
║         │                         │                └──────┬──────┘            ║
║         │                         │                       │                   ║
║         │                         │                       │ executes          ║
║         │                         │                       ▼                   ║
║         │                         │                ┌─────────────┐            ║
║         │                         │                │ Test Stub    │            ║
║         │                         │                │  (Phase 2)   │            ║
║         │                         │                └──────┬──────┘            ║
║         │                         │                       │                   ║
║         │                         │      update status    │                   ║
║         │                         │  ◄────────────────────┘                   ║
║         │                         │                                           ║
║         │ GET /jobs/{id} (poll)   │                                           ║
║         └─────────────────────────┘                                           ║
║                                                                               ║
║   USER_FLOW:                                                                   ║
║   1. N8N → POST /jobs {ticker: "NVDA", date: "2026-02-12"}                    ║
║   2. API → create_job() → task.delay() → 202 Accepted                         ║
║   3. Celery picks up task from Redis queue                                    ║
║   4. Worker → update_status(RUNNING) → execute test stub                      ║
║   5. N8N polls → GET /jobs/{id} → {status: RUNNING, started_at: timestamp}    ║
║   6. Worker completes → update_status(COMPLETED) → set_job_result()           ║
║   7. N8N polls → GET /jobs/{id} → {status: COMPLETED}                         ║
║   8. N8N → GET /jobs/{id}/result → {decision: "HOLD", reports, final_state}   ║
║                                                                               ║
║   VALUE_ADD:                                                                   ║
║   - Jobs execute asynchronously in background                                 ║
║   - Multiple workers can process parallel jobs                                ║
║   - Status automatically updates through lifecycle                            ║
║   - Distributed task queue enables horizontal scaling                         ║
║   - Foundation for actual TradingAgents execution in Phase 3                  ║
║                                                                               ║
║   DATA_FLOW:                                                                   ║
║   Request → API → Celery Broker (Redis) → Worker picks up →                   ║
║   Test stub execution → Status updates → Result storage →                     ║
║   N8N polls and retrieves results                                             ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

### Interaction Changes

| Location                | Before                   | After                                  | User_Action              | Impact                            |
| ----------------------- | ------------------------ | -------------------------------------- | ------------------------ | --------------------------------- |
| POST /jobs endpoint     | Creates job, returns 202 | Creates job, dispatches Celery task    | Submit analysis job      | Job actually executes now         |
| GET /jobs/{id}          | Always returns PENDING   | Returns PENDING→RUNNING→COMPLETED      | Poll job status          | Can track progress through states |
| Worker (new)            | N/A                      | Celery worker processes tasks          | Start worker: celery -A  | Background execution enabled      |
| Redis (infrastructure)  | N/A                      | Stores task queue and results          | (Transparent to user)    | Distributed queue infrastructure  |

---

## Mandatory Reading

**CRITICAL: Implementation agent MUST read these files before starting any task:**

| Priority | File | Lines | Why Read This |
|----------|------|-------|---------------|
| P0 | `trading_api/main.py` | 83-141 | POST /jobs endpoint - exact location to add `task.delay()` call (line 128-130 has TODO comment) |
| P0 | `trading_api/job_store.py` | 10-163 | JobStore class - methods to call from worker: `update_job_status()`, `set_job_result()`, `get_job()` |
| P0 | `trading_api/models.py` | 9-14 | JobStatus enum - must use PENDING, RUNNING, COMPLETED, FAILED exactly as defined |
| P0 | `tradingagents/default_config.py` | 3-34 | DEFAULT_CONFIG pattern - copy this for Celery config with env var overrides |
| P1 | `trading_api/exceptions.py` | 1-32 | Exception patterns - follow this style for Celery-specific errors |
| P1 | `.env.example` | 8-11 | Environment variable pattern - add CELERY_BROKER_URL and CELERY_RESULT_BACKEND here |
| P1 | `main.py` | 1-28 | TradingAgentsGraph usage pattern - will be used in Phase 3, stub for now |
| P2 | `pyproject.toml` | 11-37 | Dependencies list - add celery[redis] here alongside existing redis>=6.2.0 |
| P2 | `run_api.sh` | 1-13 | Startup script pattern - mirror this for run_worker.sh |

**External Documentation:**

| Source | Section | Why Needed |
|--------|---------|------------|
| [Celery Using Redis](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html) | Redis Configuration | Broker URL format, connection options |
| [Celery Configuration](https://docs.celeryq.dev/en/stable/userguide/configuration.html) | task_serializer, result_backend | Essential config settings for security and results |
| [FastAPI + Celery Integration](https://testdriven.io/blog/fastapi-and-celery/) | Lifespan Context, Task Dispatch | How to dispatch tasks from async FastAPI endpoints |
| [Celery Tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html) | @task decorator, bind=True | Task definition best practices |
| [Celery Workers](https://docs.celeryq.dev/en/stable/userguide/workers.html) | Worker startup options | Command-line arguments for celery worker |

---

## Patterns to Mirror

### CONFIG_PATTERN (Environment Variable Defaults)

```python
# SOURCE: tradingagents/default_config.py:3-9
# COPY THIS PATTERN for Celery config:

import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    # ... more config
}
```

**FOR CELERY:** Add to `tradingagents/default_config.py`:

```python
# Celery Configuration
"celery_broker_url": os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
"celery_result_backend": os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
"celery_task_serializer": "json",  # Security: Never use pickle
"celery_result_serializer": "json",
"celery_accept_content": ["json"],
"celery_task_time_limit": 1800,  # 30 minutes (PRD requirement)
"celery_worker_prefetch_multiplier": 1,  # Better priority handling
```

### SINGLETON_PATTERN (Global Celery App Instance)

```python
# SOURCE: trading_api/job_store.py:150-163
# COPY THIS PATTERN for Celery app:

from typing import Optional

# Global job store instance
_job_store: Optional[JobStore] = None

def get_job_store() -> JobStore:
    """Get the global job store instance.

    Returns:
        JobStore instance
    """
    global _job_store
    if _job_store is None:
        _job_store = JobStore()
    return _job_store
```

**FOR CELERY:** Similar pattern in `trading_api/celery_app.py`:

```python
from celery import Celery
from typing import Optional

_celery_app: Optional[Celery] = None

def get_celery_app() -> Celery:
    """Get the global Celery app instance."""
    global _celery_app
    if _celery_app is None:
        _celery_app = create_celery_app()
    return _celery_app
```

### EXCEPTION_PATTERN (Custom Error Classes)

```python
# SOURCE: trading_api/exceptions.py:4-21
# COPY THIS PATTERN for Celery errors:

class APIException(Exception):
    """Base exception for all API errors."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class JobNotFoundError(APIException):
    """Exception raised when a job ID does not exist."""

    def __init__(self, job_id: str):
        super().__init__(
            message=f"Job not found: {job_id}",
            status_code=404
        )
        self.job_id = job_id
```

**FOR CELERY:** Add to `trading_api/exceptions.py`:

```python
class CeleryTaskError(APIException):
    """Exception raised when Celery task execution fails."""

    def __init__(self, task_id: str, error: str):
        super().__init__(
            message=f"Task {task_id} failed: {error}",
            status_code=500
        )
        self.task_id = task_id
```

### LIFESPAN_PATTERN (FastAPI Startup/Shutdown)

```python
# SOURCE: trading_api/main.py:19-41
# COPY THIS PATTERN for Celery connection warmup:

from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown.

    Startup: Initialize job store and resources
    Shutdown: Cleanup resources
    """
    print("FastAPI application starting up...")
    # Initialize job store
    get_job_store()
    print("Job store initialized")

    yield

    print("FastAPI application shutting down...")

app = FastAPI(
    title="TradingAgents API",
    version="0.1.0",
    lifespan=lifespan,
)
```

**FOR CELERY:** Update lifespan to warm up Celery connection:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("FastAPI application starting up...")
    get_job_store()
    print("Job store initialized")

    # Warm up Celery connection
    celery_app = get_celery_app()
    celery_app.connection_or_acquire()
    print("Celery connection established")

    yield

    print("FastAPI application shutting down...")
```

### TASK_DISPATCH_PATTERN (How to Call Celery from FastAPI)

```python
# SOURCE: trading_api/main.py:128-133 (TODO comment)
# IMPLEMENT THIS PATTERN:

# Current code (Phase 1):
# TODO Phase 2: Trigger Celery task here
# task = analyze_stock.delay(job_id, request.ticker, request.date, request.config)

# Phase 2 implementation:
from trading_api.tasks import analyze_stock

@app.post("/jobs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(request: JobRequest) -> JobResponse:
    store = get_job_store()

    job_id = store.create_job(
        ticker=request.ticker,
        date=request.date,
        config=request.config,
    )

    # Dispatch Celery task
    task = analyze_stock.delay(job_id, request.ticker, request.date, request.config)

    job = store.get_job(job_id)

    return JobResponse(
        job_id=job["job_id"],
        status=job["status"],
        created_at=job["created_at"],
        ticker=job["ticker"],
        date=job["date"],
    )
```

### STARTUP_SCRIPT_PATTERN (Bash Convenience Script)

```bash
# SOURCE: run_api.sh:1-13
# COPY THIS PATTERN for worker script:

#!/bin/bash
# Convenience script to run the FastAPI server

set -e

echo "Starting TradingAgents API server..."
echo "API will be available at: http://localhost:8000"
echo "API docs (Swagger UI): http://localhost:8000/docs"
echo "API docs (ReDoc): http://localhost:8000/redoc"
echo ""

uvicorn trading_api.main:app --host 0.0.0.0 --port 8000 --reload
```

**FOR CELERY:** Create `run_worker.sh`:

```bash
#!/bin/bash
# Convenience script to run Celery worker

set -e

echo "Starting TradingAgents Celery worker..."
echo "Worker will consume tasks from: default queue"
echo "Concurrency: 2 workers (configurable with --concurrency)"
echo "Time limit: 1800 seconds (30 minutes)"
echo ""

celery -A trading_api.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --time-limit=1800 \
    --soft-time-limit=1500
```

---

## Files to Change

| File | Action | Justification |
|------|--------|---------------|
| `tradingagents/default_config.py` | UPDATE | Add Celery broker/backend URLs with env var defaults |
| `.env.example` | UPDATE | Add CELERY_BROKER_URL and CELERY_RESULT_BACKEND examples |
| `pyproject.toml` | UPDATE | Add celery[redis]>=5.4.0 to dependencies |
| `trading_api/celery_app.py` | CREATE | Celery app initialization with config from default_config |
| `trading_api/tasks.py` | CREATE | Task definitions (analyze_stock task) |
| `trading_api/main.py` | UPDATE | Add Celery task dispatch in POST /jobs endpoint (line 128-130) |
| `run_worker.sh` | CREATE | Convenience script to start Celery worker |

---

## NOT Building (Scope Limits)

Explicit exclusions to prevent scope creep:

- ❌ **Actual TradingAgentsGraph execution** - Phase 3 dependency. Use test stub that sleeps 5 seconds in Phase 2.
- ❌ **Multiple queue routing** - Phase 2 uses single "default" queue. Advanced routing in Phase 4.
- ❌ **Flower monitoring dashboard** - Nice-to-have, not required for Phase 2 MVP.
- ❌ **Task priority configuration** - Not in PRD requirements for v1.
- ❌ **Result persistence to disk** - Phase 7 dependency (Docker volumes).
- ❌ **Worker autoscaling** - Fixed concurrency (default: 2) for Phase 2. Configurable but not auto.
- ❌ **Advanced retry configuration** - Basic retry only. Comprehensive retry logic in Phase 6.
- ❌ **Task cancellation (DELETE /jobs/{id})** - "Could priority" in PRD, deferred.
- ❌ **Job listing (GET /jobs)** - "Could priority" in PRD, deferred.
- ❌ **Webhook callbacks** - Explicitly out of scope per PRD ("Won't" priority).
- ❌ **Authentication/authorization** - Handled at network level per PRD.

---

## Step-by-Step Tasks

Execute in order. Each task is atomic and independently verifiable.

### Task 1: UPDATE `tradingagents/default_config.py` (add Celery config)

**ACTION**: ADD Celery configuration keys with environment variable overrides

**IMPLEMENT**: Add these keys to the DEFAULT_CONFIG dict after existing config:

```python
# Celery Configuration
"celery_broker_url": os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
"celery_result_backend": os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
"celery_task_serializer": "json",
"celery_result_serializer": "json",
"celery_accept_content": ["json"],
"celery_task_time_limit": 1800,  # 30 minutes hard limit
"celery_task_soft_time_limit": 1500,  # 25 minutes soft limit
"celery_worker_prefetch_multiplier": 1,
"celery_result_expires": 3600,  # 1 hour
```

**LOCATION**: `tradingagents/default_config.py` after line 34 (end of dict)

**MIRROR**: Existing config pattern at lines 3-34

**RATIONALE**:
- Environment variable overrides enable Docker/production config
- JSON serialization prevents pickle security vulnerabilities
- Time limits match PRD 30-minute requirement
- Prefetch=1 improves priority queue handling

**GOTCHA**:
- Use `redis://` not `redis+socket://` for standard connections
- Time limits in seconds, not minutes
- JSON can't serialize datetime objects - use ISO strings

**VALIDATE**:
```bash
python -c "from tradingagents.default_config import DEFAULT_CONFIG; print(DEFAULT_CONFIG['celery_broker_url'])"
```

**EXPECT**: Prints `redis://localhost:6379/0` (default value)

---

### Task 2: UPDATE `.env.example` (add Celery environment vars)

**ACTION**: ADD Celery configuration examples to environment template

**IMPLEMENT**: Add these lines after the API configuration section (after line 11):

```bash
# Celery + Redis Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
REDIS_MAX_CONNECTIONS=20
```

**LOCATION**: `.env.example` after "API Server Configuration" section

**MIRROR**: Existing API_HOST/API_PORT pattern at lines 8-11

**RATIONALE**: Developers copy .env.example to .env and fill in values

**GOTCHA**: These are examples, not secrets - don't add actual passwords

**VALIDATE**:
```bash
grep "CELERY_BROKER_URL" .env.example
```

**EXPECT**: Line exists in file

---

### Task 3: UPDATE `pyproject.toml` (add Celery dependency)

**ACTION**: ADD celery[redis] to project dependencies

**IMPLEMENT**: Add this line to dependencies array after line 36 (after pydantic):

```toml
"celery[redis]>=5.4.0",
```

**LOCATION**: `pyproject.toml` in `dependencies` array (line 37, after pydantic)

**RATIONALE**:
- celery[redis] includes redis client and celery-specific Redis backend
- 5.4.0 is latest stable Celery 5.x
- redis>=6.2.0 already in dependencies (line 26), compatible with Celery 5.x

**GOTCHA**:
- Use `celery[redis]` not just `celery` to include Redis support
- Bracket notation `[redis]` is "extras" syntax for optional dependencies

**VALIDATE**:
```bash
pip install -e .
python -c "import celery; print(celery.__version__)"
```

**EXPECT**: Prints version like `5.4.0` or higher

---

### Task 4: CREATE `trading_api/celery_app.py`

**ACTION**: CREATE Celery application instance with configuration

**IMPLEMENT**:

```python
"""Celery application for TradingAgents background task processing."""

import os
from celery import Celery
from typing import Optional

from tradingagents.default_config import DEFAULT_CONFIG


def create_celery_app() -> Celery:
    """Create and configure Celery application.

    Reads configuration from tradingagents.default_config.DEFAULT_CONFIG,
    which supports environment variable overrides via os.getenv().

    Returns:
        Configured Celery application instance
    """
    celery_app = Celery(
        "tradingagents",
        broker=DEFAULT_CONFIG["celery_broker_url"],
        backend=DEFAULT_CONFIG["celery_result_backend"],
    )

    # Configure Celery from default_config
    celery_app.conf.update(
        task_serializer=DEFAULT_CONFIG["celery_task_serializer"],
        result_serializer=DEFAULT_CONFIG["celery_result_serializer"],
        accept_content=DEFAULT_CONFIG["celery_accept_content"],
        task_time_limit=DEFAULT_CONFIG["celery_task_time_limit"],
        task_soft_time_limit=DEFAULT_CONFIG["celery_task_soft_time_limit"],
        worker_prefetch_multiplier=DEFAULT_CONFIG["celery_worker_prefetch_multiplier"],
        result_expires=DEFAULT_CONFIG["celery_result_expires"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        broker_connection_retry_on_startup=True,
    )

    # Broker transport options for Redis
    celery_app.conf.broker_transport_options = {
        "visibility_timeout": 3600,  # 1 hour
        "socket_keepalive": True,
        "socket_timeout": 10.0,
    }

    return celery_app


# Global Celery app instance (singleton pattern)
_celery_app: Optional[Celery] = None


def get_celery_app() -> Celery:
    """Get the global Celery app instance.

    Returns:
        Celery application instance
    """
    global _celery_app
    if _celery_app is None:
        _celery_app = create_celery_app()
    return _celery_app


# Create app instance for worker discovery
celery_app = get_celery_app()
```

**LOCATION**: `trading_api/celery_app.py` (new file)

**MIRROR**:
- Singleton pattern from `job_store.py:150-163`
- Config loading from `default_config.py:3-34`

**IMPORTS**:
- `from celery import Celery` - Main Celery class
- `from tradingagents.default_config import DEFAULT_CONFIG` - Config source

**GOTCHA**:
- Must create `celery_app` at module level for `celery -A trading_api.celery_app worker` to discover it
- Use `broker_connection_retry_on_startup=True` for Docker where Redis might not be ready immediately

**VALIDATE**:
```bash
python -c "from trading_api.celery_app import celery_app; print(celery_app.conf.broker_url)"
```

**EXPECT**: Prints broker URL like `redis://localhost:6379/0`

---

### Task 5: CREATE `trading_api/tasks.py`

**ACTION**: CREATE Celery task definitions with test stub execution

**IMPLEMENT**:

```python
"""Celery tasks for TradingAgents job processing."""

import time
from typing import Dict, Any, Optional

from trading_api.celery_app import celery_app
from trading_api.job_store import get_job_store
from trading_api.models import JobStatus


@celery_app.task(bind=True, name="tradingagents.analyze_stock")
def analyze_stock(
    self,
    job_id: str,
    ticker: str,
    date: str,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Analyze stock and return trading decision.

    Phase 2: Test stub that simulates work and returns dummy data.
    Phase 3: Will call TradingAgentsGraph.propagate() for real analysis.

    Args:
        job_id: Job identifier for status tracking
        ticker: Stock ticker symbol (e.g., "NVDA", "AAPL")
        date: Analysis date in YYYY-MM-DD format
        config: Optional configuration overrides

    Returns:
        Result dictionary with decision, final_state, and reports

    Raises:
        Exception: On task execution failure (status updated to FAILED)
    """
    store = get_job_store()

    try:
        # Update job status to RUNNING
        store.update_job_status(job_id, JobStatus.RUNNING)
        print(f"Task {self.request.id}: Started analyzing {ticker} for {date}")

        # Phase 2: Simulate work with sleep (5 seconds)
        # This proves the worker infrastructure works
        time.sleep(5)

        # Phase 2: Return test stub data
        # Phase 3 will replace this with actual TradingAgentsGraph execution:
        # from tradingagents.graph.trading_graph import TradingAgentsGraph
        # from tradingagents.default_config import DEFAULT_CONFIG
        # merged_config = DEFAULT_CONFIG.copy()
        # if config:
        #     merged_config.update(config)
        # ta = TradingAgentsGraph(debug=False, config=merged_config)
        # final_state, decision = ta.propagate(ticker, date)

        # Test stub result
        result = {
            "decision": "HOLD",
            "final_state": {
                "company_of_interest": ticker,
                "trade_date": date,
                "market_report": f"[TEST STUB] Market analysis for {ticker}",
                "sentiment_report": f"[TEST STUB] Sentiment analysis for {ticker}",
                "news_report": f"[TEST STUB] News analysis for {ticker}",
                "fundamentals_report": f"[TEST STUB] Fundamentals analysis for {ticker}",
                "final_trade_decision": "HOLD - Phase 2 test stub (no real analysis yet)",
            },
            "reports": {
                "market": f"[TEST STUB] Market analysis for {ticker}",
                "sentiment": f"[TEST STUB] Sentiment analysis for {ticker}",
                "news": f"[TEST STUB] News analysis for {ticker}",
                "fundamentals": f"[TEST STUB] Fundamentals analysis for {ticker}",
            }
        }

        # Store result in job store
        store.set_job_result(
            job_id,
            decision=result["decision"],
            final_state=result["final_state"],
            reports=result["reports"]
        )

        # Update status to completed
        store.update_job_status(job_id, JobStatus.COMPLETED)

        print(f"Task {self.request.id}: Completed analysis for {ticker}")

        return result

    except Exception as exc:
        # Update status to failed with error message
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        store.update_job_status(job_id, JobStatus.FAILED, error_msg)
        print(f"Task {self.request.id}: Failed for {ticker} - {error_msg}")
        # Re-raise so Celery marks task as failed
        raise
```

**LOCATION**: `trading_api/tasks.py` (new file)

**MIRROR**:
- Task decorator pattern from Celery docs
- Error handling from `exceptions.py:4-21`
- JobStore method calls from `job_store.py:70-126`

**IMPORTS**:
- `from trading_api.celery_app import celery_app` - Celery app instance
- `from trading_api.job_store import get_job_store` - Status tracking
- `from trading_api.models import JobStatus` - Status enum values

**RATIONALE**:
- `bind=True` gives access to `self.request.id` for logging
- `name="tradingagents.analyze_stock"` provides explicit task name
- Test stub validates infrastructure without TradingAgentsGraph dependency
- `time.sleep(5)` proves async execution (API returns immediately, worker sleeps)

**GOTCHA**:
- Must call `store.update_job_status()` BEFORE and AFTER execution to track state
- Must re-raise exceptions so Celery knows task failed
- Don't use `async def` - Celery tasks are synchronous functions

**VALIDATE**:
```bash
python -c "from trading_api.tasks import analyze_stock; print(analyze_stock.name)"
```

**EXPECT**: Prints `tradingagents.analyze_stock`

---

### Task 6: UPDATE `trading_api/main.py` (dispatch Celery task)

**ACTION**: ADD Celery task dispatch in POST /jobs endpoint

**IMPLEMENT**: Replace lines 128-133 (the TODO comment block) with:

```python
    # Dispatch Celery task for background execution
    from trading_api.tasks import analyze_stock
    task = analyze_stock.delay(job_id, request.ticker, request.date, request.config)

    print(f"Job {job_id} dispatched to Celery task {task.id}")
```

**LOCATION**: `trading_api/main.py:128-133` (inside `create_job` function)

**OLD CODE**:
```python
    # TODO Phase 2: Trigger Celery task here
    # task = analyze_stock.delay(job_id, request.ticker, request.date, request.config)

    # TODO Phase 1: Simulate job execution for testing
    # In a real implementation, this would be handled by Celery worker
    # For now, jobs remain in PENDING state until manually updated
```

**NEW CODE**:
```python
    # Dispatch Celery task for background execution
    from trading_api.tasks import analyze_stock
    task = analyze_stock.delay(job_id, request.ticker, request.date, request.config)

    print(f"Job {job_id} dispatched to Celery task {task.id}")
```

**MIRROR**: Task dispatch pattern from FastAPI + Celery integration guide

**RATIONALE**:
- `.delay()` is shorthand for `.apply_async()` - non-blocking task dispatch
- Task gets queued in Redis immediately
- API continues and returns 202 without waiting
- Worker picks up task from queue when available

**GOTCHA**:
- Import inside function to avoid circular dependency
- Don't `await` the task - `.delay()` returns AsyncResult immediately
- Task ID from Celery differs from job_id (both are UUIDs but independent)

**VALIDATE**: Run after Task 7 completion (need worker running)

---

### Task 7: CREATE `run_worker.sh`

**ACTION**: CREATE convenience script to start Celery worker

**IMPLEMENT**:

```bash
#!/bin/bash
# Convenience script to run the Celery worker

set -e

echo "Starting TradingAgents Celery worker..."
echo "Worker will consume tasks from Redis: redis://localhost:6379/0"
echo "Concurrency: 2 workers (configurable with --concurrency)"
echo "Time limit: 1800 seconds (30 minutes)"
echo "Soft time limit: 1500 seconds (25 minutes)"
echo ""
echo "Press Ctrl+C to stop the worker"
echo ""

celery -A trading_api.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --time-limit=1800 \
    --soft-time-limit=1500 \
    --max-tasks-per-child=50
```

**LOCATION**: `run_worker.sh` (project root, alongside `run_api.sh`)

**MIRROR**: `run_api.sh:1-13` - script structure and style

**RATIONALE**:
- Concurrency=2 matches PRD requirement (2 concurrent jobs default)
- Time limits match DEFAULT_CONFIG settings
- `--max-tasks-per-child=50` prevents memory leaks
- `-A trading_api.celery_app` tells Celery where to find the app

**GOTCHA**:
- Must make script executable: `chmod +x run_worker.sh`
- Worker must run in same virtualenv as API
- Redis must be running before starting worker

**VALIDATE**:
```bash
chmod +x run_worker.sh
head -n 5 run_worker.sh
```

**EXPECT**: Script is executable, contains celery command

---

## Testing Strategy

### Unit Tests to Write (Phase 8)

| Test File | Test Cases | Validates |
|-----------|------------|-----------|
| `tests/trading_api/test_celery_app.py` | Celery app creation, config loading | Celery initialization |
| `tests/trading_api/test_tasks.py` | Task execution with mocked job_store | Task logic, status updates |
| `tests/trading_api/test_main_celery.py` | POST /jobs dispatches task | API integration |

### Manual Testing Checklist

**Prerequisites**:
- Redis running (`docker run -d -p 6379:6379 redis:7-alpine`)
- API server running (`./run_api.sh`)
- Celery worker running (`./run_worker.sh`)

**Test 1: Submit Job and Verify Dispatch**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2026-02-12"}'
```
**Expected**:
- API returns 202 Accepted with job_id
- Worker logs show: `Task <task_id>: Started analyzing NVDA`

**Test 2: Poll Status During Execution**
```bash
# Replace {job_id} with actual ID from Test 1
curl http://localhost:8000/jobs/{job_id}
```
**Expected**:
- Initially: `{"status": "pending", ...}` (very brief)
- During: `{"status": "running", "started_at": "...", ...}`
- After 5 seconds: `{"status": "completed", "completed_at": "...", ...}`

**Test 3: Retrieve Result**
```bash
curl http://localhost:8000/jobs/{job_id}/result
```
**Expected**:
```json
{
  "job_id": "...",
  "ticker": "NVDA",
  "date": "2026-02-12",
  "decision": "HOLD",
  "final_state": {
    "market_report": "[TEST STUB] Market analysis for NVDA",
    ...
  },
  "reports": {
    "market": "[TEST STUB] Market analysis for NVDA",
    ...
  }
}
```

**Test 4: Multiple Concurrent Jobs**
```bash
# Submit 3 jobs simultaneously
for ticker in NVDA AAPL TSLA; do
  curl -X POST http://localhost:8000/jobs \
    -H "Content-Type: application/json" \
    -d "{\"ticker\": \"$ticker\", \"date\": \"2026-02-12\"}" &
done
wait
```
**Expected**:
- All 3 jobs get job_ids
- Worker logs show 2 tasks running concurrently
- Third task queued, starts after first two complete
- All complete within ~15 seconds (3 jobs × 5 sec each, 2 concurrent)

**Test 5: Worker Restart Preserves Jobs**
```bash
# Submit job
JOB_ID=$(curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "MH", "date": "2026-02-12"}' | jq -r '.job_id')

# Kill worker immediately (Ctrl+C)
# Restart worker (./run_worker.sh)

# Check status
curl http://localhost:8000/jobs/$JOB_ID
```
**Expected**:
- Job status tracked in job_store (in-memory, API-side)
- Task in Redis queue gets picked up by restarted worker
- Job completes normally after worker restart

**Test 6: API Without Worker (Graceful Degradation)**
```bash
# Stop worker (Ctrl+C)
# Submit job
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "TEST", "date": "2026-02-12"}'
```
**Expected**:
- API still returns 202 Accepted
- Job stays in PENDING (no worker to process)
- No API errors (graceful)

**Test 7: Redis Connection Failure**
```bash
# Stop Redis (docker stop <redis-container>)
# Submit job
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "TEST", "date": "2026-02-12"}'
```
**Expected**:
- API may return 500 Internal Server Error or timeout
- Phase 6 will add proper connection error handling

### Edge Cases Checklist

- [ ] Job submitted while worker is busy (queuing works)
- [ ] Worker crashes mid-task (task marked failed)
- [ ] Redis connection lost during task dispatch (task fails to enqueue)
- [ ] Invalid config dict passed to task (task handles gracefully)
- [ ] Job ID not found in job_store (task fails with clear error)
- [ ] Task exceeds 30-minute time limit (Celery terminates, status updated to FAILED)

---

## Validation Commands

### Level 1: STATIC_ANALYSIS

```bash
# Python imports and syntax
python -m py_compile trading_api/celery_app.py
python -m py_compile trading_api/tasks.py

# Check Celery app can be imported
python -c "from trading_api.celery_app import celery_app; print('Celery app OK')"

# Check task is registered
python -c "from trading_api.tasks import analyze_stock; print(f'Task: {analyze_stock.name}')"
```

**EXPECT**: All commands exit 0, no import errors

---

### Level 2: UNIT_TESTS

```bash
# If pytest is set up (Phase 8)
pytest tests/trading_api/test_celery_app.py -v
pytest tests/trading_api/test_tasks.py -v

# Or basic smoke test
python -c "
from trading_api.celery_app import get_celery_app
from trading_api.tasks import analyze_stock
app = get_celery_app()
assert app.conf.broker_url is not None
assert analyze_stock.name == 'tradingagents.analyze_stock'
print('Unit tests passed')
"
```

**EXPECT**: All tests pass or smoke test succeeds

---

### Level 3: INTEGRATION_TEST

```bash
# Start Redis in background (Docker)
docker run -d --name tradingagents-redis -p 6379:6379 redis:7-alpine

# Start API in background
./run_api.sh &
API_PID=$!
sleep 3

# Start worker in background
./run_worker.sh &
WORKER_PID=$!
sleep 3

# Submit test job
JOB_RESPONSE=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "TEST", "date": "2026-02-12"}')

echo "Job response: $JOB_RESPONSE"

# Extract job_id
JOB_ID=$(echo $JOB_RESPONSE | python -c "import sys, json; print(json.load(sys.stdin)['job_id'])")

echo "Job ID: $JOB_ID"

# Wait for task to complete (5 seconds + buffer)
sleep 8

# Check final status
STATUS_RESPONSE=$(curl -s http://localhost:8000/jobs/$JOB_ID)
echo "Status: $STATUS_RESPONSE"

# Verify status is COMPLETED
STATUS=$(echo $STATUS_RESPONSE | python -c "import sys, json; print(json.load(sys.stdin)['status'])")

if [ "$STATUS" = "completed" ]; then
    echo "✅ Integration test PASSED"
else
    echo "❌ Integration test FAILED (status: $STATUS)"
    exit 1
fi

# Cleanup
kill $API_PID $WORKER_PID
docker stop tradingagents-redis
docker rm tradingagents-redis
```

**EXPECT**:
- Job submitted successfully
- Status transitions PENDING → RUNNING → COMPLETED
- Integration test prints "✅ Integration test PASSED"

---

### Level 4: WORKER_VALIDATION

```bash
# Check worker can connect to broker
celery -A trading_api.celery_app inspect ping

# Check registered tasks
celery -A trading_api.celery_app inspect registered

# Check worker stats
celery -A trading_api.celery_app inspect stats
```

**EXPECT**:
- `inspect ping` returns `pong` from worker
- `inspect registered` shows `tradingagents.analyze_stock`
- `inspect stats` shows worker info (concurrency, pool, etc.)

---

## Acceptance Criteria

- [ ] Celery app initializes with config from DEFAULT_CONFIG
- [ ] Worker starts with `./run_worker.sh` and connects to Redis
- [ ] POST /jobs dispatches Celery task with `.delay()`
- [ ] Worker picks up task from Redis queue
- [ ] Task updates job status: PENDING → RUNNING → COMPLETED
- [ ] Task stores result via `job_store.set_job_result()`
- [ ] GET /jobs/{id} returns status=RUNNING while task executes
- [ ] GET /jobs/{id} returns status=COMPLETED after task finishes
- [ ] GET /jobs/{id}/result returns test stub data
- [ ] Multiple jobs can be submitted and queued
- [ ] Worker concurrency default is 2 (configurable)
- [ ] Task time limit is 30 minutes (1800 seconds)
- [ ] Task failure updates status to FAILED with error message
- [ ] Worker logs show task start/completion messages
- [ ] Redis stores task queue and results
- [ ] API returns 202 immediately (doesn't wait for task completion)

---

## Completion Checklist

- [ ] Task 1: default_config.py updated with Celery settings
- [ ] Task 2: .env.example updated with broker/backend URLs
- [ ] Task 3: pyproject.toml updated with celery[redis] dependency
- [ ] Task 4: trading_api/celery_app.py created with app initialization
- [ ] Task 5: trading_api/tasks.py created with analyze_stock task
- [ ] Task 6: trading_api/main.py updated to dispatch task
- [ ] Task 7: run_worker.sh script created
- [ ] All validation commands pass (Level 1-4)
- [ ] All acceptance criteria met
- [ ] Manual testing checklist completed
- [ ] Worker can be started and stopped cleanly
- [ ] Jobs execute in background and complete

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Redis connection failure on startup | Medium | High | Add `broker_connection_retry_on_startup=True` in celery_app.py |
| Worker crash mid-task | Low | Medium | Celery auto-retries failed tasks (default 3 attempts) |
| Task timeout not enforced | Low | High | Explicitly set `task_time_limit` and `task_soft_time_limit` in config |
| Job store out of sync with Celery state | Medium | Medium | Always update job_store status before/after task execution |
| Memory leak in long-running worker | Medium | Low | Use `--max-tasks-per-child=50` to restart workers periodically |
| Redis maxmemory eviction | Low | High | Configure Redis with `maxmemory-policy noeviction` |
| Circular import (main.py ↔ tasks.py) | Medium | Low | Import task inside function (`from trading_api.tasks import ...`) |
| Worker can't find Celery app | Medium | Low | Export `celery_app` at module level in celery_app.py |

---

## Notes

**Design Decisions:**

1. **Test Stub in Phase 2**: Validates infrastructure without TradingAgentsGraph dependency. Phase 3 adds real execution.

2. **JSON Serialization Only**: Security best practice - pickle can execute arbitrary code. JSON is safe and human-readable.

3. **Single Queue for Phase 2**: Simplifies initial implementation. Phase 4 adds multiple queues for priority routing.

4. **Job Store + Celery Result Backend**: Hybrid approach maintains API compatibility while leveraging Celery for distribution.

5. **Concurrency=2 Default**: Matches PRD requirement (2 concurrent jobs for GPU constraints).

6. **30-Minute Time Limit**: Hard requirement from PRD for long-running analysis tasks.

7. **Worker Startup Script**: Mirrors `run_api.sh` pattern for consistent developer experience.

8. **Environment Variable Config**: Enables Docker deployment without code changes (Phase 4).

**Future Considerations (Later Phases):**

- **Phase 3**: Replace test stub with actual `TradingAgentsGraph.propagate()` call
- **Phase 4**: Docker Compose with Redis, API, and worker services
- **Phase 5**: Per-job config merging and validation
- **Phase 6**: Advanced retry logic, timeout handling, comprehensive error handling
- **Phase 7**: Docker volumes for results persistence
- **Phase 8**: Comprehensive tests, Flower monitoring, documentation

**Integration Notes:**

- Celery task signature matches TradingAgentsGraph.propagate() signature for easy Phase 3 integration
- JobStatus enum used by both job_store and tasks.py for consistency
- Worker prints match existing FastAPI log style for unified logging
- Config pattern matches existing default_config.py for maintainability

**Celery 5.x Gotchas (from Research):**

- CLI syntax changed: `celery -A proj worker` (global -A flag before subcommand)
- Default serializer changed from pickle to JSON (good for security)
- `broker_connection_retry_on_startup` prevents startup failures when Redis is slow
- Prefetch multiplier should be 1 for priority queues (we set this in config)
- Visibility timeout must exceed task ETA/countdown (we set 1 hour, sufficient for 30-min tasks)
