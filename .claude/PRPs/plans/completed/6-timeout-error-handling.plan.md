# Feature: Timeout and Error Handling

## Summary

Implementing comprehensive timeout and error handling for robust job execution. Phase 3 catches exceptions but lacks timeout enforcement, retry logic, and structured error reporting. Phase 6 adds soft/hard timeout warnings (25min/30min), automatic retry for transient failures (rate limits, network errors), structured error messages with categorization (timeout, llm_error, data_error, unknown), health check endpoint for monitoring, and proper cleanup on timeout/failure.

## User Story

As a TradingAgents system operator
I want jobs to timeout after 30 minutes with clear error messages
So that stuck jobs don't consume resources indefinitely and I can debug failures quickly

## Metadata

| Field            | Value                                             |
|------------------|---------------------------------------------------|
| Type             | ENHANCEMENT                                       |
| Complexity       | MEDIUM                                            |
| Systems Affected | trading_api/tasks.py, models.py, main.py          |
| Dependencies     | Phase 3 complete (TradingAgentsGraph integrated)  |
| Estimated Tasks  | 6                                                 |
| PRD Phase        | Phase 6: Timeout & Error Handling                 |

## Files to Change

| File | Action | Justification |
|------|--------|---------------|
| `trading_api/tasks.py` | UPDATE | Add SoftTimeLimitExceeded handling, retry logic |
| `trading_api/models.py` | UPDATE | Add error_type enum to JobStatusResponse |
| `trading_api/main.py` | UPDATE | Enhance /health endpoint with dependency checks |
| `trading_api/celery_app.py` | UPDATE | Add retry configuration for specific exceptions |

## Tasks

### Task 1: ADD soft timeout warning handling

Update `trading_api/tasks.py`:

```python
from celery.exceptions import SoftTimeLimitExceeded

@celery_app.task(bind=True, name="tradingagents.analyze_stock")
def analyze_stock(self, job_id: str, ticker: str, date: str, config: Optional[Dict] = None):
    store = get_job_store()
    
    try:
        store.update_job_status(job_id, JobStatus.RUNNING)
        
        # ... TradingAgentsGraph execution ...
        
    except SoftTimeLimitExceeded:
        # Soft timeout (25 minutes) - attempt graceful shutdown
        error_msg = "Analysis exceeded 25-minute soft limit, attempting graceful shutdown"
        print(f"Task {self.request.id}: {error_msg}")
        store.update_job_status(job_id, JobStatus.FAILED, error_msg)
        # Re-raise to let hard limit (30 min) terminate if needed
        raise
        
    except AlphaVantageRateLimitError as exc:
        # Retryable error - don't update to FAILED, let Celery retry
        print(f"Task {self.request.id}: Rate limit hit, will retry")
        raise self.retry(exc=exc, countdown=60)  # Retry after 60 seconds
        
    # ... other exception handlers ...
```

### Task 2: ADD retry configuration

Update `trading_api/celery_app.py`:

```python
celery_app.conf.update(
    # ... existing config ...
    
    # Retry configuration
    task_autoretry_for=(
        AlphaVantageRateLimitError,
        # Add other retryable errors
    ),
    task_retry_backoff=True,  # Exponential backoff: 60s, 120s, 240s...
    task_retry_backoff_max=600,  # Max 10 minutes between retries
    task_retry_jitter=True,  # Add randomness to prevent thundering herd
    task_max_retries=3,  # Stop after 3 attempts
)
```

### Task 3: ADD error categorization

Update `trading_api/models.py`:

```python
class ErrorType(str, Enum):
    """Job failure error categories."""
    TIMEOUT = "timeout"
    LLM_ERROR = "llm_error"
    DATA_ERROR = "data_error"
    INVALID_CONFIG = "invalid_config"
    UNKNOWN = "unknown"

class JobStatusResponse(BaseModel):
    # ... existing fields ...
    error: Optional[str] = None
    error_type: Optional[ErrorType] = None  # NEW
    retry_count: Optional[int] = Field(None, description="Number of retry attempts")
```

Update `trading_api/job_store.py`:

```python
def update_job_status(
    self,
    job_id: str,
    status: JobStatus,
    error: Optional[str] = None,
    error_type: Optional[str] = None,  # NEW
):
    # ... existing code ...
    if error:
        self._jobs[job_id]["error"] = error
        self._jobs[job_id]["error_type"] = error_type or "unknown"
```

### Task 4: ENHANCE /health endpoint

Update `trading_api/main.py`:

```python
from redis import Redis
from trading_api.celery_app import celery_app

@app.get("/health")
async def health_check():
    """Health check with dependency validation."""
    health_status = {
        "status": "healthy",
        "components": {}
    }
    
    # Check Redis
    try:
        redis_client = Redis.from_url(
            os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
            socket_connect_timeout=2
        )
        redis_client.ping()
        health_status["components"]["redis"] = "up"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["components"]["redis"] = f"down: {str(e)}"
    
    # Check Celery workers
    try:
        inspect = celery_app.control.inspect(timeout=2)
        active_workers = inspect.ping()
        if active_workers:
            health_status["components"]["celery_workers"] = f"{len(active_workers)} active"
        else:
            health_status["status"] = "degraded"
            health_status["components"]["celery_workers"] = "no workers"
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["celery_workers"] = f"unknown: {str(e)}"
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(health_status, status_code=status_code)
```

### Task 5: ADD task metadata tracking

Update task to track retries:

```python
@celery_app.task(bind=True, ...)
def analyze_stock(self, job_id: str, ...):
    # Log retry attempt
    retry_count = self.request.retries
    print(f"Task {self.request.id}: Attempt {retry_count + 1}")
    
    # Store retry count in job metadata
    store = get_job_store()
    store.update_job_metadata(job_id, {"retry_count": retry_count})
    
    # ... rest of task ...
```

### Task 6: ADD graceful shutdown handling

Update task to cleanup on interrupt:

```python
import signal

def cleanup_on_signal(signum, frame):
    """Cleanup handler for worker shutdown."""
    print("Received shutdown signal, cleaning up...")
    # Close LLM connections, save progress, etc.

signal.signal(signal.SIGTERM, cleanup_on_signal)
signal.signal(signal.SIGINT, cleanup_on_signal)
```

## Testing

**Test 1: Soft timeout (simulate 25+ min job)**
```python
# In tasks.py, temporarily add before propagate():
time.sleep(1600)  # 26 minutes

# Submit job, verify it fails with timeout error
```

**Test 2: Rate limit retry**
```bash
# Submit 10 jobs rapidly to hit Alpha Vantage rate limit
# Verify some jobs retry automatically after 60s
```

**Test 3: Health endpoint**
```bash
# With all services running
curl http://localhost:8000/health
# Expected: 200 OK, all components "up"

# Stop Redis
docker stop tradingagents-redis

curl http://localhost:8000/health
# Expected: 503 Service Unavailable, redis "down"
```

**Test 4: Error categorization**
```bash
# Submit job with invalid ticker
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "INVALID", "date": "2024-05-10"}'

# Check status
curl http://localhost:8000/jobs/{job_id}
# Expected: error_type = "data_error"
```

## Acceptance Criteria

- [ ] Jobs timeout after 30 minutes (hard limit)
- [ ] Soft timeout (25 min) triggers graceful shutdown attempt
- [ ] Rate limit errors retry automatically (max 3 times)
- [ ] Retry uses exponential backoff with jitter
- [ ] Error messages categorized by type (timeout, llm_error, data_error, etc.)
- [ ] Health endpoint checks Redis and worker availability
- [ ] Health endpoint returns 503 when dependencies down
- [ ] Job status includes retry_count
- [ ] Worker logs show retry attempts
- [ ] SoftTimeLimitExceeded caught and logged

## Risks

| Risk | Mitigation |
|------|------------|
| Retry storm during outage | Exponential backoff + jitter + max 3 retries |
| Soft timeout doesn't clean up | Hard timeout (30 min) forcefully terminates |
| Health check slows API | Use timeouts (2s max) on dependency checks |
| Error messages leak sensitive data | Sanitize error messages before storing |

