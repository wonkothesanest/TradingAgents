# Feature: FastAPI Core REST API for Job Submission and Status Tracking

## Summary

Building a FastAPI HTTP REST API skeleton that accepts trading analysis job submissions and provides status tracking endpoints. This phase creates the foundation for async job execution without the actual Celery queue integration - using an in-memory job store for MVP validation. Establishes HTTP 202 Accepted pattern, Pydantic request/response models, and proper REST endpoint structure.

## User Story

As a N8N workflow automation developer
I want to submit TradingAgents analysis jobs via HTTP POST and poll their status
So that I can integrate multi-ticker market analysis into automated pipelines

## Problem Statement

TradingAgents currently only supports local CLI/Python script invocation. There is no HTTP interface to remotely trigger analysis jobs or track their execution status. This blocks automated N8N workflow integration for multi-ticker analysis pipelines.

## Solution Statement

Create a FastAPI application with three REST endpoints (POST /jobs, GET /jobs/{job_id}, GET /jobs/{job_id}/result) that accept job submissions, return 202 Accepted responses with job IDs, and allow status polling. Use in-memory dictionary for job storage as MVP before Celery integration. Follow existing TradingAgents patterns for config management, error handling, and type definitions.

## Metadata

| Field            | Value                                             |
| ---------------- | ------------------------------------------------- |
| Type             | NEW_CAPABILITY                                    |
| Complexity       | MEDIUM                                            |
| Systems Affected | New trading_api/ directory, config system         |
| Dependencies     | FastAPI 0.115+, Pydantic 2.0+, Uvicorn 0.30+      |
| Estimated Tasks  | 8                                                 |
| PRD Phase        | Phase 1: API Core Setup                           |
| PRD Reference    | .claude/PRPs/prds/tradingagents-job-api.prd.md   |

---

## UX Design

### Before State

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                              BEFORE STATE                                      ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║   ┌─────────────┐         ┌─────────────┐         ┌─────────────┐            ║
║   │   N8N       │ ──────► │   Local     │ ──────► │   Manual    │            ║
║   │  Workflow   │         │   Machine   │         │   Execution │            ║
║   └─────────────┘         └─────────────┘         └─────────────┘            ║
║                                                                               ║
║   USER_FLOW:                                                                   ║
║   1. N8N workflow identifies candidate stocks (NVDA, AAPL, MH)                ║
║   2. ❌ NO HTTP INTERFACE - workflow blocked                                  ║
║   3. Manual intervention required: SSH to machine, run CLI                    ║
║   4. Wait 5-15 minutes for completion (blocking terminal session)             ║
║   5. Copy/paste results back to workflow manually                             ║
║                                                                               ║
║   PAIN_POINT:                                                                  ║
║   - No remote triggering capability                                           ║
║   - Cannot automate multi-ticker analysis                                     ║
║   - Manual result retrieval                                                   ║
║   - No status tracking for long-running jobs                                  ║
║                                                                               ║
║   DATA_FLOW: N/A (no remote interface exists)                                 ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════════╗
║                               AFTER STATE (Phase 1)                            ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║   ┌─────────────┐         ┌─────────────┐         ┌─────────────┐            ║
║   │   N8N       │  POST   │   FastAPI   │  Store  │  In-Memory  │            ║
║   │  Workflow   │ ──────► │   Server    │ ──────► │  Job Dict   │            ║
║   └─────────────┘         └─────────────┘         └─────────────┘            ║
║         │                         │                                           ║
║         │ GET (poll)              │ Lookup                                    ║
║         └─────────────────────────┘                                           ║
║                                                                               ║
║   USER_FLOW:                                                                   ║
║   1. N8N → POST /jobs {"ticker": "NVDA", "date": "2026-02-12"}                ║
║   2. API → 202 Accepted {"job_id": "uuid", "status": "accepted"}              ║
║   3. N8N polls → GET /jobs/{job_id} → {"status": "pending"}                   ║
║   4. (Job executes in background - simulated in Phase 1)                      ║
║   5. N8N polls → GET /jobs/{job_id} → {"status": "completed"}                 ║
║   6. N8N → GET /jobs/{job_id}/result → {full report}                          ║
║   7. N8N continues pipeline with analysis results                             ║
║                                                                               ║
║   VALUE_ADD:                                                                   ║
║   - HTTP interface enables remote job submission                              ║
║   - Job ID tracking for status polling                                        ║
║   - Proper REST semantics (202 Accepted for async operations)                 ║
║   - Foundation for Celery integration in Phase 2                              ║
║                                                                               ║
║   DATA_FLOW:                                                                   ║
║   Request → Pydantic validation → UUID generation → Job store →               ║
║   HTTP 202 response → Status polling → Result retrieval                       ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

### Interaction Changes

| Location        | Before          | After                        | User_Action         | Impact                        |
| --------------- | --------------- | ---------------------------- | ------------------- | ----------------------------- |
| N8N HTTP Node   | N/A (no API)    | POST /jobs endpoint          | Submit job payload  | Gets job_id, 202 response     |
| N8N HTTP Node   | N/A             | GET /jobs/{job_id}           | Poll status         | Tracks completion             |
| N8N HTTP Node   | N/A             | GET /jobs/{job_id}/result    | Retrieve report     | Gets full analysis data       |
| Local testing   | CLI only        | curl/Postman/httpie          | Test API endpoints  | Can validate API without N8N  |

---

## Mandatory Reading

**CRITICAL: Implementation agent MUST read these files before starting any task:**

| Priority | File | Lines | Why Read This |
|----------|------|-------|---------------|
| P0 | `tradingagents/graph/trading_graph.py` | 46-131, 186-219 | TradingAgentsGraph constructor signature and propagate() usage - MUST understand contract |
| P0 | `tradingagents/default_config.py` | 3-34 | DEFAULT_CONFIG structure - config keys that can be overridden per request |
| P0 | `main.py` | 10-27 | Pattern for instantiating TradingAgentsGraph and calling propagate() - MIRROR this |
| P1 | `cli/models.py` | 1-11 | Pydantic model pattern for enums - use this style for API models |
| P1 | `tradingagents/agents/utils/agent_states.py` | 50-76 | AgentState structure - what propagate() returns in final_state |
| P1 | `tradingagents/dataflows/config.py` | 15-27 | Global config management pattern - understand set_config/get_config |
| P2 | `cli/main.py` | 899-1168 | How CLI currently executes jobs - understand flow but DON'T mirror (it's sync) |
| P2 | `tradingagents/dataflows/alpha_vantage_common.py` | 38-40 | Custom exception pattern - follow this for API errors |

**External Documentation:**

| Source | Section | Why Needed |
|--------|---------|------------|
| [FastAPI Basics](https://fastapi.tiangolo.com/tutorial/first-steps/) | Getting Started | How to create FastAPI app and define routes |
| [Pydantic Models](https://fastapi.tiangolo.com/tutorial/body-fields/) | Request/Response Validation | How to define request/response schemas |
| [HTTP 202 Pattern](https://restfulapi.net/http-status-202-accepted/) | Async Operations | Proper REST semantics for long-running jobs |
| [FastAPI Lifespan](https://fastapi.tiangolo.com/advanced/events/) | Startup/Shutdown Events | How to initialize resources at API startup |
| [Python UUID](https://docs.python.org/3/library/uuid.html) | uuid.uuid4() | How to generate secure job IDs |

---

## Patterns to Mirror

### NAMING_CONVENTION (Function Names)

```python
# SOURCE: tradingagents/graph/trading_graph.py:46-66
# COPY THIS PATTERN: snake_case for functions, descriptive parameter names

def __init__(
    self,
    selected_analysts=["market", "social", "news", "fundamentals"],
    debug=False,
    config: Dict[str, Any] = None,
    callbacks: Optional[List] = None,
):
    """Initialize the trading agents graph and components."""
    self.debug = debug
    self.config = config or DEFAULT_CONFIG
```

**FOR API:** Use snake_case for function names, route handlers follow FastAPI convention

### ERROR_HANDLING (Custom Exceptions)

```python
# SOURCE: tradingagents/dataflows/alpha_vantage_common.py:38-40
# COPY THIS PATTERN: Custom exception classes with descriptive names

class AlphaVantageRateLimitError(Exception):
    """Exception raised when Alpha Vantage API rate limit is exceeded."""
    pass
```

**FOR API:** Create similar exceptions for API-specific errors:
- `JobNotFoundError` - when job_id doesn't exist
- `InvalidJobRequestError` - when request validation fails

### PYDANTIC_MODEL_PATTERN (Enums and Models)

```python
# SOURCE: cli/models.py:5-11
# COPY THIS PATTERN: String enums with explicit values

from enum import Enum
from pydantic import BaseModel

class AnalystType(str, Enum):
    MARKET = "market"
    SOCIAL = "social"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"
```

**FOR API:** Define JobStatus enum and request/response models similarly

### CONFIG_USAGE_PATTERN (Configuration Handling)

```python
# SOURCE: main.py:10-24
# COPY THIS PATTERN: Copy DEFAULT_CONFIG, override specific keys

from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5-mini"
config["quick_think_llm"] = "gpt-5-mini"
config["max_debate_rounds"] = 1
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",
    "news_data": "yfinance",
}
```

**FOR API:** Accept optional config in request, merge with DEFAULT_CONFIG

### PROPAGATE_INVOCATION_PATTERN (How to Call TradingAgentsGraph)

```python
# SOURCE: main.py:24-27
# COPY THIS PATTERN: Instantiate graph, call propagate(), handle return tuple

ta = TradingAgentsGraph(debug=True, config=config)
final_state, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

**FOR API:** In Phase 1, simulate this in job store. In Phase 2, move to Celery task.

### TYPE_HINTS_PATTERN (Type Annotations)

```python
# SOURCE: tradingagents/graph/trading_graph.py:50, 186
# COPY THIS PATTERN: Use Dict, Optional, List from typing

from typing import Dict, Any, Optional, List

def __init__(
    self,
    config: Dict[str, Any] = None,
    callbacks: Optional[List] = None,
):
    pass

def propagate(self, company_name: str, trade_date: str):
    """Run the trading agents graph for a company on a specific date."""
    pass
```

**FOR API:** Use comprehensive type hints in all function signatures

---

## Files to Change

| File | Action | Justification |
|------|--------|---------------|
| `trading_api/__init__.py` | CREATE | Package marker for new API module |
| `trading_api/main.py` | CREATE | FastAPI app definition and route handlers |
| `trading_api/models.py` | CREATE | Pydantic request/response models |
| `trading_api/exceptions.py` | CREATE | Custom exception classes for API errors |
| `trading_api/job_store.py` | CREATE | In-memory job storage (dict-based) for Phase 1 MVP |
| `pyproject.toml` | UPDATE | Add FastAPI, Uvicorn, and Pydantic to dependencies |
| `.env.example` | UPDATE | Add API_HOST and API_PORT config examples |
| `README.md` | UPDATE | Document new API endpoints and usage (deferred to Phase 8) |

---

## NOT Building (Scope Limits)

Explicit exclusions to prevent scope creep:

- ❌ **Celery job queue integration** - Phase 2 dependency, not Phase 1. Use in-memory dict for now.
- ❌ **Actual TradingAgents execution** - Phase 3 dependency. Simulate job completion in Phase 1.
- ❌ **Redis or database persistence** - Phase 2 infrastructure. In-memory storage sufficient for Phase 1 validation.
- ❌ **Docker containerization** - Phase 4 dependency. Run directly with `uvicorn` for now.
- ❌ **Authentication/authorization** - Out of scope for entire project (PRD: network-level security).
- ❌ **Webhook callbacks** - Out of scope for v1 (PRD: polling-only for MVP).
- ❌ **Job cancellation/deletion** - Stretch goal (PRD: Could priority), not required for Phase 1.
- ❌ **Job listing (GET /jobs)** - Stretch goal, not required for Phase 1 MVP.
- ❌ **Configuration validation** - Phase 5 dependency. Accept any config dict in Phase 1.
- ❌ **Timeout handling** - Phase 6 dependency. No timeout logic in Phase 1.
- ❌ **Comprehensive error handling** - Phase 6 dependency. Basic errors only in Phase 1.
- ❌ **Production-ready logging** - Phase 8 dependency. Use print() or basic logging for now.

---

## Step-by-Step Tasks

Execute in order. Each task is atomic and independently verifiable.

### Task 1: UPDATE `pyproject.toml` (add dependencies)

**ACTION**: ADD FastAPI, Uvicorn, and Pydantic dependencies to project

**IMPLEMENT**:
```toml
dependencies = [
    # ... existing dependencies ...
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.0.0",
]
```

**LOCATION**: `pyproject.toml` after existing dependencies (around line 34)

**RATIONALE**: FastAPI requires these three packages for full functionality. Uvicorn[standard] includes performance optimizations (uvloop, httptools).

**GOTCHA**: Pydantic 2.0 has breaking changes from 1.x. Ensure examples use v2 syntax.

**VALIDATE**:
```bash
pip install -e .
python -c "import fastapi, uvicorn, pydantic; print('Dependencies installed successfully')"
```

**EXPECT**: Exit 0, success message printed

---

### Task 2: CREATE `trading_api/__init__.py`

**ACTION**: CREATE package marker file

**IMPLEMENT**:
```python
"""
TradingAgents REST API

Provides HTTP endpoints for remote job submission and status tracking.
"""

__version__ = "0.1.0"
```

**LOCATION**: `trading_api/__init__.py` (new file)

**VALIDATE**:
```bash
python -c "import trading_api; print(trading_api.__version__)"
```

**EXPECT**: "0.1.0" printed

---

### Task 3: CREATE `trading_api/exceptions.py`

**ACTION**: CREATE custom exception classes for API errors

**IMPLEMENT**:
```python
"""Custom exceptions for the TradingAgents API."""


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


class InvalidJobRequestError(APIException):
    """Exception raised when job request validation fails."""

    def __init__(self, message: str):
        super().__init__(
            message=f"Invalid job request: {message}",
            status_code=422
        )
```

**MIRROR**: `tradingagents/dataflows/alpha_vantage_common.py:38-40` - custom exception pattern

**LOCATION**: `trading_api/exceptions.py` (new file)

**VALIDATE**:
```bash
python -c "from trading_api.exceptions import JobNotFoundError; e = JobNotFoundError('test-id'); print(f'{e.message}, {e.status_code}')"
```

**EXPECT**: "Job not found: test-id, 404" printed

---

### Task 4: CREATE `trading_api/models.py`

**ACTION**: CREATE Pydantic request/response models

**IMPLEMENT**:
```python
"""Pydantic models for API request/response validation."""

from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobRequest(BaseModel):
    """Request model for creating a new job."""

    ticker: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Stock ticker symbol (e.g., 'NVDA', 'AAPL')"
    )
    date: str = Field(
        ...,
        pattern=r'^\d{4}-\d{2}-\d{2}$',
        description="Analysis date in YYYY-MM-DD format"
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional configuration overrides for this job"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "NVDA",
                "date": "2026-02-12",
                "config": {
                    "max_debate_rounds": 1,
                    "llm_provider": "openai"
                }
            }
        }


class JobResponse(BaseModel):
    """Response model for job creation."""

    job_id: str = Field(..., description="Unique job identifier (UUID)")
    status: JobStatus = Field(..., description="Current job status")
    created_at: str = Field(..., description="Job creation timestamp (ISO 8601)")
    ticker: str = Field(..., description="Stock ticker for this job")
    date: str = Field(..., description="Analysis date for this job")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "pending",
                "created_at": "2026-02-12T10:30:00Z",
                "ticker": "NVDA",
                "date": "2026-02-12"
            }
        }


class JobStatusResponse(BaseModel):
    """Response model for job status queries."""

    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Current job status")
    created_at: str = Field(..., description="Job creation timestamp")
    started_at: Optional[str] = Field(None, description="Job start timestamp")
    completed_at: Optional[str] = Field(None, description="Job completion timestamp")
    ticker: str = Field(..., description="Stock ticker")
    date: str = Field(..., description="Analysis date")
    error: Optional[str] = Field(None, description="Error message if job failed")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "running",
                "created_at": "2026-02-12T10:30:00Z",
                "started_at": "2026-02-12T10:30:05Z",
                "completed_at": None,
                "ticker": "NVDA",
                "date": "2026-02-12",
                "error": None
            }
        }


class JobResultResponse(BaseModel):
    """Response model for job results."""

    job_id: str = Field(..., description="Unique job identifier")
    ticker: str = Field(..., description="Stock ticker")
    date: str = Field(..., description="Analysis date")
    decision: str = Field(..., description="Final trading decision (BUY/SELL/HOLD)")
    final_state: Dict[str, Any] = Field(..., description="Complete state dict from TradingAgentsGraph")
    reports: Dict[str, str] = Field(
        ...,
        description="Individual analyst reports (market, sentiment, news, fundamentals)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "ticker": "NVDA",
                "date": "2026-02-12",
                "decision": "BUY",
                "final_state": {},
                "reports": {
                    "market": "Market analysis report...",
                    "news": "News analysis report...",
                    "sentiment": "Sentiment analysis report...",
                    "fundamentals": "Fundamentals report..."
                }
            }
        }
```

**MIRROR**: `cli/models.py:5-11` - Enum pattern with explicit string values

**LOCATION**: `trading_api/models.py` (new file)

**RATIONALE**: Pydantic provides automatic validation, JSON serialization, and OpenAPI schema generation

**GOTCHA**: Use `json_schema_extra` (Pydantic v2) instead of `schema_extra` (v1)

**VALIDATE**:
```bash
python -c "from trading_api.models import JobRequest; req = JobRequest(ticker='NVDA', date='2026-02-12'); print(req.model_dump_json())"
```

**EXPECT**: JSON output with ticker and date fields

---

### Task 5: CREATE `trading_api/job_store.py`

**ACTION**: CREATE in-memory job storage using dictionary

**IMPLEMENT**:
```python
"""In-memory job storage for Phase 1 MVP."""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from trading_api.models import JobStatus
from trading_api.exceptions import JobNotFoundError


class JobStore:
    """In-memory job storage using a dictionary.

    This is a temporary implementation for Phase 1. Will be replaced
    with Redis/Celery result backend in Phase 2.
    """

    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def create_job(
        self,
        ticker: str,
        date: str,
        config: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a new job and return its ID.

        Args:
            ticker: Stock ticker symbol
            date: Analysis date
            config: Optional configuration overrides

        Returns:
            Job ID (UUID string)
        """
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        self._jobs[job_id] = {
            "job_id": job_id,
            "ticker": ticker,
            "date": date,
            "config": config,
            "status": JobStatus.PENDING,
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "result": None,
        }

        return job_id

    def get_job(self, job_id: str) -> Dict[str, Any]:
        """Get job by ID.

        Args:
            job_id: Job identifier

        Returns:
            Job data dictionary

        Raises:
            JobNotFoundError: If job ID does not exist
        """
        if job_id not in self._jobs:
            raise JobNotFoundError(job_id)
        return self._jobs[job_id].copy()

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        error: Optional[str] = None
    ) -> None:
        """Update job status.

        Args:
            job_id: Job identifier
            status: New status
            error: Optional error message for FAILED status

        Raises:
            JobNotFoundError: If job ID does not exist
        """
        if job_id not in self._jobs:
            raise JobNotFoundError(job_id)

        self._jobs[job_id]["status"] = status

        if status == JobStatus.RUNNING and self._jobs[job_id]["started_at"] is None:
            self._jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()

        if status in (JobStatus.COMPLETED, JobStatus.FAILED):
            self._jobs[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

        if error:
            self._jobs[job_id]["error"] = error

    def set_job_result(
        self,
        job_id: str,
        decision: str,
        final_state: Dict[str, Any],
        reports: Dict[str, str]
    ) -> None:
        """Store job result.

        Args:
            job_id: Job identifier
            decision: Trading decision (BUY/SELL/HOLD)
            final_state: Complete state dict from TradingAgentsGraph
            reports: Individual analyst reports

        Raises:
            JobNotFoundError: If job ID does not exist
        """
        if job_id not in self._jobs:
            raise JobNotFoundError(job_id)

        self._jobs[job_id]["result"] = {
            "decision": decision,
            "final_state": final_state,
            "reports": reports,
        }

    def get_job_result(self, job_id: str) -> Dict[str, Any]:
        """Get job result.

        Args:
            job_id: Job identifier

        Returns:
            Result dictionary with decision, final_state, and reports

        Raises:
            JobNotFoundError: If job ID does not exist
        """
        job = self.get_job(job_id)

        if job["status"] != JobStatus.COMPLETED:
            raise ValueError(f"Job {job_id} is not completed (status: {job['status']})")

        if job["result"] is None:
            raise ValueError(f"Job {job_id} has no result data")

        return job["result"]


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

**MIRROR**: `tradingagents/dataflows/config.py:15-27` - global singleton pattern

**LOCATION**: `trading_api/job_store.py` (new file)

**RATIONALE**: Simple in-memory storage for Phase 1 validation. Will be replaced by Redis in Phase 2.

**GOTCHA**: Jobs are lost on restart (not persistent). This is acceptable for Phase 1 MVP.

**VALIDATE**:
```bash
python -c "
from trading_api.job_store import get_job_store
store = get_job_store()
job_id = store.create_job('NVDA', '2026-02-12')
print(f'Created job: {job_id}')
job = store.get_job(job_id)
print(f'Retrieved job: {job[\"ticker\"]} on {job[\"date\"]}')
"
```

**EXPECT**: Job created and retrieved successfully with matching ticker/date

---

### Task 6: CREATE `trading_api/main.py`

**ACTION**: CREATE FastAPI application with three endpoints

**IMPLEMENT**:
```python
"""FastAPI application for TradingAgents job submission and tracking."""

from contextlib import asynccontextmanager
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from trading_api.models import (
    JobRequest,
    JobResponse,
    JobStatusResponse,
    JobResultResponse,
    JobStatus,
)
from trading_api.job_store import get_job_store
from trading_api.exceptions import JobNotFoundError, APIException


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
    description="REST API for remote TradingAgents job submission and tracking",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(JobNotFoundError)
async def job_not_found_handler(request, exc: JobNotFoundError):
    """Handle JobNotFoundError exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "job_id": exc.job_id},
    )


@app.exception_handler(APIException)
async def api_exception_handler(request, exc: APIException):
    """Handle generic API exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message},
    )


@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "name": "TradingAgents API",
        "version": "0.1.0",
        "status": "operational",
        "endpoints": {
            "submit_job": "POST /jobs",
            "get_status": "GET /jobs/{job_id}",
            "get_result": "GET /jobs/{job_id}/result",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post(
    "/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a new trading analysis job",
    description="Create a new job for analyzing a stock ticker on a specific date. Returns 202 Accepted with job ID.",
)
async def create_job(request: JobRequest) -> JobResponse:
    """Submit a new trading analysis job.

    Args:
        request: Job request containing ticker, date, and optional config

    Returns:
        JobResponse with job_id and status

    Example:
        POST /jobs
        {
            "ticker": "NVDA",
            "date": "2026-02-12",
            "config": {"max_debate_rounds": 1}
        }

        Response (202 Accepted):
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "pending",
            "created_at": "2026-02-12T10:30:00Z",
            "ticker": "NVDA",
            "date": "2026-02-12"
        }
    """
    store = get_job_store()

    # Create job in store
    job_id = store.create_job(
        ticker=request.ticker,
        date=request.date,
        config=request.config,
    )

    # Get job data for response
    job = store.get_job(job_id)

    # TODO Phase 2: Trigger Celery task here
    # task = analyze_stock.delay(job_id, request.ticker, request.date, request.config)

    # TODO Phase 1: Simulate job execution for testing
    # In a real implementation, this would be handled by Celery worker
    # For now, jobs remain in PENDING state until manually updated

    return JobResponse(
        job_id=job["job_id"],
        status=job["status"],
        created_at=job["created_at"],
        ticker=job["ticker"],
        date=job["date"],
    )


@app.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status",
    description="Poll the status of a submitted job. Returns current status and timestamps.",
)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Get job status by ID.

    Args:
        job_id: Job identifier (UUID)

    Returns:
        JobStatusResponse with status and timestamps

    Raises:
        HTTPException: 404 if job not found

    Example:
        GET /jobs/550e8400-e29b-41d4-a716-446655440000

        Response:
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "running",
            "created_at": "2026-02-12T10:30:00Z",
            "started_at": "2026-02-12T10:30:05Z",
            "completed_at": null,
            "ticker": "NVDA",
            "date": "2026-02-12",
            "error": null
        }
    """
    store = get_job_store()

    # Will raise JobNotFoundError if job doesn't exist
    # Exception handler converts to 404 response
    job = store.get_job(job_id)

    return JobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        created_at=job["created_at"],
        started_at=job["started_at"],
        completed_at=job["completed_at"],
        ticker=job["ticker"],
        date=job["date"],
        error=job["error"],
    )


@app.get(
    "/jobs/{job_id}/result",
    response_model=JobResultResponse,
    summary="Get job result",
    description="Retrieve the full analysis result for a completed job. Returns 400 if job not completed.",
)
async def get_job_result(job_id: str) -> JobResultResponse:
    """Get job result by ID.

    Args:
        job_id: Job identifier (UUID)

    Returns:
        JobResultResponse with decision, state, and reports

    Raises:
        HTTPException: 404 if job not found, 400 if job not completed

    Example:
        GET /jobs/550e8400-e29b-41d4-a716-446655440000/result

        Response:
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "ticker": "NVDA",
            "date": "2026-02-12",
            "decision": "BUY",
            "final_state": {...},
            "reports": {
                "market": "...",
                "news": "...",
                "sentiment": "...",
                "fundamentals": "..."
            }
        }
    """
    store = get_job_store()

    # Check if job exists
    job = store.get_job(job_id)

    # Check if job is completed
    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed (current status: {job['status']})",
        )

    # Get result
    try:
        result = store.get_job_result(job_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    return JobResultResponse(
        job_id=job["job_id"],
        ticker=job["ticker"],
        date=job["date"],
        decision=result["decision"],
        final_state=result["final_state"],
        reports=result["reports"],
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**MIRROR**:
- `cli/main.py:35-39` - Typer app structure (adapted to FastAPI)
- `tradingagents/dataflows/alpha_vantage_common.py:38-40` - exception handling

**LOCATION**: `trading_api/main.py` (new file)

**RATIONALE**: FastAPI provides automatic OpenAPI docs, request validation, and async support

**GOTCHA**: Use `@asynccontextmanager` for lifespan (replaces old `@app.on_event` decorators)

**VALIDATE**:
```bash
# Start server in background
python -m trading_api.main &
SERVER_PID=$!
sleep 2

# Test endpoints
curl http://localhost:8000/health
curl http://localhost:8000/

# Stop server
kill $SERVER_PID
```

**EXPECT**: Health check returns `{"status": "healthy"}`, root returns API info

---

### Task 7: UPDATE `.env.example`

**ACTION**: ADD API configuration examples

**IMPLEMENT**: Add these lines to `.env.example`:
```bash
# API Server Configuration
API_HOST=0.0.0.0
API_PORT=8000
```

**LOCATION**: `.env.example` (append to end of file)

**VALIDATE**:
```bash
grep "API_HOST" .env.example
```

**EXPECT**: Line exists in file

---

### Task 8: CREATE API startup script

**ACTION**: CREATE convenience script for running the API server

**IMPLEMENT**: Create `run_api.sh`:
```bash
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

**LOCATION**: `run_api.sh` (project root)

**VALIDATE**:
```bash
chmod +x run_api.sh
head -n 5 run_api.sh
```

**EXPECT**: Script is executable, contains uvicorn command

---

## Testing Strategy

### Unit Tests to Write

| Test File | Test Cases | Validates |
|-----------|------------|-----------|
| `tests/trading_api/test_models.py` | Valid/invalid JobRequest, enum values | Pydantic model validation |
| `tests/trading_api/test_job_store.py` | Create/get/update jobs, error cases | Job storage operations |
| `tests/trading_api/test_exceptions.py` | Exception properties, status codes | Custom exception behavior |
| `tests/trading_api/test_api.py` | POST /jobs, GET /jobs/{id}, GET /jobs/{id}/result | API endpoint behavior |

### Manual Testing Checklist

**Prerequisites**: API server running (`./run_api.sh` or `uvicorn trading_api.main:app`)

**Test 1: Submit Job**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2026-02-12"}'
```
**Expected**: 202 Accepted, returns job_id and status="pending"

**Test 2: Get Job Status**
```bash
# Replace {job_id} with actual ID from Test 1
curl http://localhost:8000/jobs/{job_id}
```
**Expected**: 200 OK, returns job status with timestamps

**Test 3: Get Result (Should Fail)**
```bash
curl http://localhost:8000/jobs/{job_id}/result
```
**Expected**: 400 Bad Request (job not completed)

**Test 4: Invalid Job ID**
```bash
curl http://localhost:8000/jobs/invalid-uuid
```
**Expected**: 404 Not Found with error message

**Test 5: Invalid Request**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "invalid-date"}'
```
**Expected**: 422 Unprocessable Entity with validation error

**Test 6: OpenAPI Docs**
```bash
curl http://localhost:8000/docs
```
**Expected**: HTML page with Swagger UI

### Edge Cases Checklist

- [ ] Job ID does not exist (404 error)
- [ ] Invalid date format (422 validation error)
- [ ] Empty ticker string (422 validation error)
- [ ] Ticker too long (>10 chars) (422 validation error)
- [ ] Get result for pending job (400 error)
- [ ] Get result for failed job (400 error)
- [ ] Optional config parameter omitted (should work)
- [ ] Optional config parameter is null (should work)
- [ ] Optional config parameter is empty dict (should work)

---

## Validation Commands

### Level 1: STATIC_ANALYSIS

```bash
# Type checking (if mypy installed)
mypy trading_api/ --ignore-missing-imports

# Linting (if ruff installed)
ruff check trading_api/

# Or basic Python syntax check
python -m py_compile trading_api/*.py
```

**EXPECT**: Exit 0, no errors or warnings

---

### Level 2: UNIT_TESTS

```bash
# If pytest is set up (Phase 8)
pytest tests/trading_api/ -v

# Or basic import test
python -c "
from trading_api.main import app
from trading_api.models import JobRequest, JobStatus
from trading_api.job_store import get_job_store
print('All imports successful')
"
```

**EXPECT**: All tests pass or imports succeed

---

### Level 3: INTEGRATION_TEST

```bash
# Start server
uvicorn trading_api.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
sleep 3

# Test job submission
JOB_RESPONSE=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2026-02-12"}')

echo "Job response: $JOB_RESPONSE"

# Extract job_id (requires jq)
if command -v jq &> /dev/null; then
  JOB_ID=$(echo $JOB_RESPONSE | jq -r '.job_id')
  echo "Job ID: $JOB_ID"

  # Test status endpoint
  curl -s http://localhost:8000/jobs/$JOB_ID | jq
fi

# Cleanup
kill $SERVER_PID
```

**EXPECT**: Job submitted successfully, status retrieved

---

### Level 4: OPENAPI_VALIDATION

```bash
# Verify OpenAPI schema is accessible
curl -s http://localhost:8000/openapi.json | python -m json.tool > /dev/null
echo "OpenAPI schema valid: $?"
```

**EXPECT**: Exit 0 (valid JSON)

---

## Acceptance Criteria

- [ ] FastAPI application starts successfully with `uvicorn`
- [ ] POST /jobs endpoint accepts valid requests and returns 202 with job_id
- [ ] POST /jobs validates request body and returns 422 for invalid data
- [ ] GET /jobs/{job_id} returns job status for valid job_id
- [ ] GET /jobs/{job_id} returns 404 for non-existent job_id
- [ ] GET /jobs/{job_id}/result returns 400 when job not completed
- [ ] OpenAPI documentation accessible at /docs and /redoc
- [ ] Job IDs are valid UUIDs
- [ ] JobStatus enum has all required states (pending, running, completed, failed)
- [ ] In-memory job store persists data for server lifetime
- [ ] Optional config parameter works (can be None or Dict)
- [ ] Created timestamps are ISO 8601 formatted strings
- [ ] All Pydantic models have example schemas in OpenAPI docs

---

## Completion Checklist

- [ ] Task 1: pyproject.toml updated with FastAPI, Uvicorn, Pydantic
- [ ] Task 2: trading_api/__init__.py created with version
- [ ] Task 3: trading_api/exceptions.py created with custom exceptions
- [ ] Task 4: trading_api/models.py created with Pydantic models
- [ ] Task 5: trading_api/job_store.py created with in-memory storage
- [ ] Task 6: trading_api/main.py created with FastAPI app and 3 endpoints
- [ ] Task 7: .env.example updated with API config
- [ ] Task 8: run_api.sh script created
- [ ] All validation commands pass (Level 1-4)
- [ ] All acceptance criteria met
- [ ] Manual testing checklist completed
- [ ] OpenAPI docs accessible and correct

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| FastAPI async/sync confusion | Medium | Low | Use `async def` for route handlers but call sync code (OK for Phase 1) |
| Pydantic v1/v2 incompatibility | Low | Medium | Explicitly use Pydantic 2.0+ syntax (json_schema_extra, model_dump) |
| Job store memory leak | Medium | Medium | Document that Phase 1 is MVP only, no production use |
| UUID collision (extremely rare) | Very Low | High | Use uuid.uuid4() which has negligible collision probability |
| Port 8000 already in use | Medium | Low | Document how to change port via --port flag or env var |
| Missing dependencies in venv | Medium | Low | Clear installation instructions, use `pip install -e .` |
| JSON serialization of complex types | Low | Medium | Phase 1 stores simple types only, complex serialization in Phase 3 |

---

## Notes

**Design Decisions:**

1. **In-memory storage**: Acceptable for Phase 1 MVP validation. Jobs lost on restart is expected. Redis integration comes in Phase 2.

2. **No actual execution**: Phase 1 focuses on API structure. Jobs remain in PENDING state unless manually updated. TradingAgents integration comes in Phase 3.

3. **Synchronous route handlers**: Using `async def` for FastAPI best practices, but not calling any async operations yet. This simplifies Phase 1 while keeping door open for async in Phase 2+.

4. **UUID v4 for job IDs**: Random, secure, unpredictable. Prevents enumeration attacks. Standard for REST APIs.

5. **HTTP 202 Accepted pattern**: Proper REST semantics for long-running operations. Client polls for completion rather than blocking.

6. **Pydantic v2**: Using latest Pydantic for best FastAPI integration. Note syntax differences from v1 (json_schema_extra, model_dump vs dict).

7. **Global job store singleton**: Mirrors existing config.py pattern. Simple for Phase 1, will be replaced by Redis in Phase 2.

8. **No authentication**: Per PRD requirements, security handled at network level (Docker networking, reverse proxy). Out of scope for entire project.

**Future Considerations (Later Phases):**

- **Phase 2**: Replace job_store.py with Celery + Redis
- **Phase 3**: Add actual TradingAgentsGraph execution in Celery tasks
- **Phase 4**: Dockerize with docker-compose.yml
- **Phase 5**: Add per-job config validation and merging
- **Phase 6**: Add timeout handling and comprehensive error handling
- **Phase 7**: Add volume management for results persistence
- **Phase 8**: Add comprehensive tests and documentation

**Integration Notes:**

- TradingAgentsGraph expects `ticker` (str) and `date` (str) - API models match this exactly
- Config dict from API can be passed directly to TradingAgentsGraph constructor in Phase 3
- Final state structure from AgentState matches what we expect in JobResultResponse
- No changes needed to core TradingAgents code for Phase 1

**OpenAPI Documentation:**

FastAPI auto-generates OpenAPI schema at `/openapi.json`, Swagger UI at `/docs`, and ReDoc at `/redoc`. No additional configuration needed. This makes API consumption easy for N8N workflows.
