# Feature: GET /jobs Endpoint for Job Listing

## Summary

Add a new GET /jobs endpoint to the TradingAgents API that returns all known job objects from Redis storage, ordered by status (running, pending, failed, completed). This enables users to query and monitor all jobs in the system rather than tracking individual job IDs manually. The implementation follows existing FastAPI/Pydantic patterns, adds a new `list_jobs()` method to JobStore using Redis SCAN for efficient key enumeration, and returns a list of JobStatusResponse objects.

## User Story

As a developer/API consumer
I want to query all jobs via a GET /jobs endpoint with status-based ordering
So that I can monitor job execution status with running jobs prioritized first, without needing to track individual job IDs

## Problem Statement

Currently, the TradingAgents API only supports querying jobs by specific job ID (GET /jobs/{job_id}). Users must track job IDs manually to monitor multiple jobs. There is no way to:
1. Discover all jobs in the system
2. Monitor running jobs across multiple submissions
3. View pending jobs waiting for execution
4. Check failed jobs for debugging
5. Retrieve completed jobs for bulk processing

This requires implementing a list endpoint that enumerates all jobs from Redis and returns them sorted by execution status.

## Solution Statement

Add a GET /jobs endpoint that:
1. Uses Redis SCAN to enumerate all job keys matching `tradingagents:job:*` pattern
2. Fetches job data for each key using HGETALL
3. Sorts jobs by status priority (running → pending → failed → completed) with secondary sort by created_at
4. Returns List[JobStatusResponse] with FastAPI validation
5. Handles edge cases: expired jobs, duplicate keys from SCAN, empty result sets

The implementation adds a `list_jobs()` method to JobStore class, creates a new FastAPI endpoint following existing patterns, and updates the root documentation endpoint to include the new route.

## Metadata

| Field            | Value                                             |
| ---------------- | ------------------------------------------------- |
| Type             | NEW_CAPABILITY                                    |
| Complexity       | LOW                                               |
| Systems Affected | trading_api (main.py, job_store.py, models.py)   |
| Dependencies     | redis>=6.2.0, fastapi>=0.115.0, pydantic>=2.0.0  |
| Estimated Tasks  | 5                                                 |

---

## UX Design

### Before State
```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                              BEFORE STATE                                      ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║   ┌─────────────┐                                                             ║
║   │   Client    │──── POST /jobs {"ticker": "NVDA"} ────────┐                ║
║   │             │                                            │                ║
║   └─────────────┘                                            ▼                ║
║          │                                         ┌──────────────────┐       ║
║          │                                         │  API Response    │       ║
║          │◄──────── 202 ACCEPTED ─────────────────│  job_id: "abc"   │       ║
║          │          {"job_id": "abc"}             └──────────────────┘       ║
║          │                                                                    ║
║          │         (Must manually track job_id "abc")                        ║
║          │                                                                    ║
║          └──── GET /jobs/abc ──────────────┐                                 ║
║                                             ▼                                 ║
║                                    ┌──────────────────┐                       ║
║                                    │  Job Status      │                       ║
║                                    │  status: running │                       ║
║                                    └──────────────────┘                       ║
║                                                                               ║
║   USER_FLOW:                                                                  ║
║   1. Submit job → receive job_id                                              ║
║   2. Manually store job_id                                                    ║
║   3. Poll each job_id individually                                            ║
║   4. No way to discover jobs if ID is lost                                    ║
║                                                                               ║
║   PAIN_POINT:                                                                 ║
║   - Cannot discover all jobs in system                                        ║
║   - Must manually track multiple job IDs                                      ║
║   - No overview of running/pending/failed jobs                                ║
║   - Lost job IDs cannot be recovered                                          ║
║                                                                               ║
║   DATA_FLOW: Client → API (submit job) → Redis (store job) → Client (poll)   ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════════╗
║                               AFTER STATE                                      ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║   ┌─────────────┐                                                             ║
║   │   Client    │──── POST /jobs {"ticker": "NVDA"} ────────┐                ║
║   │             │                                            │                ║
║   └─────────────┘                                            ▼                ║
║          │                                         ┌──────────────────┐       ║
║          │                                         │  API Response    │       ║
║          │◄──────── 202 ACCEPTED ─────────────────│  job_id: "abc"   │       ║
║          │          {"job_id": "abc"}             └──────────────────┘       ║
║          │                                                                    ║
║          │         (Can now list ALL jobs, not just one)                     ║
║          │                                                  NEW CAPABILITY    ║
║          └──── GET /jobs ──────────────┐                         ▲            ║
║                                        │                          │            ║
║                                        ▼                          │            ║
║                              ┌─────────────────┐                  │            ║
║                              │  Jobs List      │──────────────────┘            ║
║                              │  Sorted:        │                               ║
║                              │  - running (2)  │  Priority: running first      ║
║                              │  - pending (3)  │            pending second     ║
║                              │  - failed (1)   │            failed third       ║
║                              │  - completed(5) │            completed last     ║
║                              └─────────────────┘                               ║
║                                                                               ║
║   USER_FLOW:                                                                  ║
║   1. Submit job → receive job_id (same as before)                             ║
║   2. Call GET /jobs to see ALL jobs with status sorting                       ║
║   3. Monitor running jobs at top of list                                      ║
║   4. Discover lost/forgotten job IDs                                          ║
║   5. Poll individual jobs for details as needed                               ║
║                                                                               ║
║   VALUE_ADD:                                                                  ║
║   + Discover all jobs without tracking IDs                                    ║
║   + Monitor system-wide job status at a glance                                ║
║   + Running jobs prioritized for quick visibility                             ║
║   + Recover lost job IDs                                                      ║
║   + Support bulk job management workflows                                     ║
║                                                                               ║
║   DATA_FLOW: Client → API (GET /jobs) → Redis SCAN (enumerate keys) →        ║
║              Redis HGETALL (fetch job data) → Python sort (by status) →       ║
║              FastAPI/Pydantic (validate & serialize) → Client (JSON list)     ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

### Interaction Changes
| Location        | Before                          | After                                      | User_Action         | Impact                              |
| --------------- | ------------------------------- | ------------------------------------------ | ------------------- | ----------------------------------- |
| `/jobs`         | 405 Method Not Allowed          | 200 OK with list of jobs                   | GET /jobs           | Can now list all jobs in system     |
| `/`             | Endpoint list excludes list_all | Endpoint list includes "list_all": GET /jobs | GET /              | API discovery shows new capability  |
| Client workflow | Must track all job IDs manually | Can call GET /jobs to discover all         | Call list endpoint  | No manual ID tracking needed        |
| Monitoring      | Poll each job individually      | Get overview of running/pending jobs       | Single API call     | System-wide status visibility       |

---

## Mandatory Reading

**CRITICAL: Implementation agent MUST read these files before starting any task:**

| Priority | File                        | Lines   | Why Read This                                      |
| -------- | --------------------------- | ------- | -------------------------------------------------- |
| P0       | `trading_api/main.py`       | 181-231 | GET endpoint pattern to MIRROR for /jobs route     |
| P0       | `trading_api/job_store.py`  | 95-128  | JobStore.get_job() pattern for new list_jobs()     |
| P1       | `trading_api/models.py`     | 108-137 | JobStatusResponse model to use in List return type |
| P1       | `trading_api/models.py`     | 10-16   | JobStatus enum for status ordering logic           |
| P2       | `trading_api/exceptions.py` | 4-21    | Exception patterns (may not need custom exception) |
| P2       | `trading_api/main.py`       | 65-77   | Root endpoint to UPDATE with new /jobs route       |

**External Documentation:**
| Source                                                                                        | Section               | Why Needed                                               |
| --------------------------------------------------------------------------------------------- | --------------------- | -------------------------------------------------------- |
| [redis-py SCAN Iterator](https://redis.io/docs/latest/develop/clients/redis-py/scaniter/)    | scan_iter() usage     | Implement Redis key enumeration for job listing          |
| [FastAPI Response Model](https://fastapi.tiangolo.com/tutorial/response-model/)               | List[Model] pattern   | Declare List[JobStatusResponse] return type              |
| [Redis SCAN Command](https://redis.io/docs/latest/commands/scan/)                            | Cursor-based scanning | Understand SCAN cursor behavior and count parameter      |
| [Pydantic v2 Migration](https://docs.pydantic.dev/latest/migration/)                          | Config deprecation    | Optional: understand Config class → model_config pattern |

---

## Patterns to Mirror

**GET ENDPOINT PATTERN:**
```python
# SOURCE: trading_api/main.py:181-231
# COPY THIS PATTERN:
@app.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status",
    description="Poll the status of a submitted job. Returns current status and timestamps.",
)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Get job status by ID."""
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
        error_type=job.get("error_type"),
        retry_count=job.get("retry_count", 0),
    )
```

**JOBSTORE METHOD PATTERN:**
```python
# SOURCE: trading_api/job_store.py:95-128
# COPY THIS PATTERN:
def get_job(self, job_id: str) -> Dict[str, Any]:
    """Get job by ID.

    Args:
        job_id: Job identifier

    Returns:
        Job data dictionary

    Raises:
        JobNotFoundError: If job ID does not exist
    """
    key = self._get_job_key(job_id)
    job_data = self.redis.hgetall(key)

    if not job_data:
        raise JobNotFoundError(job_id)

    # Convert stored strings back to proper types
    result = {
        "job_id": job_data["job_id"],
        "ticker": job_data["ticker"],
        "date": job_data["date"],
        "config": json.loads(job_data["config"]) if job_data.get("config") else None,
        "status": job_data["status"],
        "created_at": job_data["created_at"],
        "started_at": job_data.get("started_at") or None,
        "completed_at": job_data.get("completed_at") or None,
        "error": job_data.get("error") or None,
        "error_type": job_data.get("error_type") or None,
        "retry_count": int(job_data.get("retry_count", 0)),
    }

    return result
```

**REDIS KEY PATTERN:**
```python
# SOURCE: trading_api/job_store.py:38-47
# COPY THIS PATTERN:
def _get_job_key(self, job_id: str) -> str:
    """Get Redis key for a job.

    Args:
        job_id: Job identifier

    Returns:
        Redis key string
    """
    return f"tradingagents:job:{job_id}"
```

**JOBSTATUS ENUM:**
```python
# SOURCE: trading_api/models.py:10-16
# USE THIS FOR STATUS ORDERING:
class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
```

**ROOT ENDPOINT UPDATE PATTERN:**
```python
# SOURCE: trading_api/main.py:65-77
# UPDATE THIS TO INCLUDE NEW ENDPOINT:
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
            # ADD THIS LINE:
            "list_jobs": "GET /jobs",
        },
    }
```

---

## Files to Change

| File                           | Action | Justification                                                  |
| ------------------------------ | ------ | -------------------------------------------------------------- |
| `trading_api/job_store.py`    | UPDATE | Add `list_jobs()` method to enumerate and return all jobs      |
| `trading_api/main.py`          | UPDATE | Add GET /jobs endpoint using new JobStore.list_jobs() method   |
| `trading_api/main.py`          | UPDATE | Update root endpoint (/) to document new list_jobs route       |

---

## NOT Building (Scope Limits)

Explicit exclusions to prevent scope creep:

- **Pagination**: Not implementing limit/offset or cursor-based pagination (can add later if needed for >10k jobs)
- **Filtering by status**: Not adding query parameters like `?status=running` (return all jobs, client can filter)
- **Sorting options**: Only one sort order supported: status priority + created_at (no query params for custom sort)
- **Job aggregation/stats**: Not adding counts like "total_running", "total_pending" (client can count from list)
- **Redis SET index**: Not adding `tradingagents:job:ids` Redis SET for faster enumeration (SCAN is sufficient for now)
- **Response caching**: Not caching the jobs list (real-time data preferred)
- **Batch operations**: Not adding bulk delete, bulk cancel, or other multi-job operations

---

## Step-by-Step Tasks

Execute in order. Each task is atomic and independently verifiable.

### Task 1: UPDATE `trading_api/job_store.py` - Add list_jobs() method

- **ACTION**: ADD new method `list_jobs()` to JobStore class
- **IMPLEMENT**: Use Redis SCAN to enumerate all `tradingagents:job:*` keys, fetch each job with HGETALL, convert to dict, sort by status
- **MIRROR**: `job_store.py:95-128` - follow get_job() pattern for type conversion
- **LOCATION**: After `get_job()` method (around line 129)
- **IMPORTS**: None needed (redis client already available as `self.redis`)
- **LOGIC**:
  1. Use `self.redis.scan_iter(match="tradingagents:job:*", count=1000)` to enumerate keys
  2. For each key, call `self.redis.hgetall(key)` to get job data
  3. Skip if hgetall returns empty dict (job expired between SCAN and HGETALL)
  4. Use deduplication set to handle SCAN returning duplicate keys
  5. Convert each job_data to dict using same pattern as `get_job()` (lines 114-127)
  6. Sort by status priority: {"running": 0, "pending": 1, "failed": 2, "completed": 3}
  7. Secondary sort by created_at timestamp (ascending, oldest first within same status)
  8. Return List[Dict[str, Any]]
- **GOTCHA**: SCAN can return duplicate keys during iteration - use `seen = set()` to track processed keys
- **GOTCHA**: Jobs may expire between SCAN finding key and HGETALL fetching it - check `if not job_data: continue`
- **GOTCHA**: Use COUNT=1000 in scan_iter for better performance (default is too low)
- **VALIDATE**: No automated validation yet - will test via endpoint in Task 2

**Code to add:**
```python
def list_jobs(self) -> List[Dict[str, Any]]:
    """List all jobs, sorted by status.

    Returns jobs ordered by status priority (running → pending → failed → completed),
    with secondary sort by created_at timestamp within each status group.

    Returns:
        List of job data dictionaries

    Note:
        Uses Redis SCAN for non-blocking key enumeration. May take several seconds
        for large job counts (1000+ jobs).
    """
    jobs = []
    seen = set()  # Deduplicate keys (SCAN may return duplicates)

    # Use SCAN iterator with high count for performance
    for key in self.redis.scan_iter(match="tradingagents:job:*", count=1000):
        if key in seen:
            continue
        seen.add(key)

        # Fetch job data
        job_data = self.redis.hgetall(key)

        # Skip if job expired between SCAN and HGETALL
        if not job_data:
            continue

        # Convert to dict using same pattern as get_job()
        job = {
            "job_id": job_data["job_id"],
            "ticker": job_data["ticker"],
            "date": job_data["date"],
            "config": json.loads(job_data["config"]) if job_data.get("config") else None,
            "status": job_data["status"],
            "created_at": job_data["created_at"],
            "started_at": job_data.get("started_at") or None,
            "completed_at": job_data.get("completed_at") or None,
            "error": job_data.get("error") or None,
            "error_type": job_data.get("error_type") or None,
            "retry_count": int(job_data.get("retry_count", 0)),
        }
        jobs.append(job)

    # Sort by status priority, then by created_at
    status_order = {
        JobStatus.RUNNING: 0,
        JobStatus.PENDING: 1,
        JobStatus.FAILED: 2,
        JobStatus.COMPLETED: 3,
    }

    jobs.sort(key=lambda j: (status_order.get(j["status"], 999), j["created_at"]))

    return jobs
```

### Task 2: UPDATE `trading_api/main.py` - Add GET /jobs endpoint

- **ACTION**: ADD new GET /jobs endpoint
- **IMPLEMENT**: Call `store.list_jobs()`, convert to List[JobStatusResponse], return with FastAPI
- **MIRROR**: `main.py:181-231` - follow get_job_status() endpoint pattern
- **LOCATION**: After `get_job_result()` endpoint (after line 298)
- **IMPORTS**: Need to add `List` to imports: `from typing import Dict, Any, List`
- **DECORATOR**: `@app.get("/jobs", response_model=List[JobStatusResponse], summary="...", description="...")`
- **LOGIC**:
  1. Get job store via `store = get_job_store()`
  2. Call `jobs = store.list_jobs()`
  3. Convert each job dict to JobStatusResponse
  4. Return List[JobStatusResponse]
- **GOTCHA**: Must import `List` from typing module (currently only imports `Dict, Any`)
- **GOTCHA**: FastAPI automatically validates and serializes each item in the list
- **VALIDATE**: Manual test via curl or httpie after implementation

**Code to add:**
```python
@app.get(
    "/jobs",
    response_model=List[JobStatusResponse],
    summary="List all jobs",
    description="Retrieve all jobs sorted by status (running → pending → failed → completed). Returns job metadata without full results.",
)
async def list_jobs() -> List[JobStatusResponse]:
    """List all jobs, sorted by status.

    Returns:
        List of JobStatusResponse objects sorted by status priority

    Example:
        GET /jobs

        Response (200 OK):
        [
            {
                "job_id": "abc-123",
                "status": "running",
                "created_at": "2026-02-12T10:30:00Z",
                "started_at": "2026-02-12T10:30:05Z",
                "completed_at": null,
                "ticker": "NVDA",
                "date": "2026-02-12",
                "error": null,
                "error_type": null,
                "retry_count": 0
            },
            {
                "job_id": "def-456",
                "status": "pending",
                ...
            }
        ]
    """
    store = get_job_store()

    # Get all jobs from store
    jobs = store.list_jobs()

    # Convert to response models
    return [
        JobStatusResponse(
            job_id=job["job_id"],
            status=job["status"],
            created_at=job["created_at"],
            started_at=job["started_at"],
            completed_at=job["completed_at"],
            ticker=job["ticker"],
            date=job["date"],
            error=job["error"],
            error_type=job.get("error_type"),
            retry_count=job.get("retry_count", 0),
        )
        for job in jobs
    ]
```

### Task 3: UPDATE `trading_api/main.py` - Add List import

- **ACTION**: UPDATE imports at top of file
- **IMPLEMENT**: Add `List` to typing import line
- **MIRROR**: Existing import pattern on line 3: `from typing import Dict, Any`
- **LOCATION**: Line 3
- **CHANGE**: `from typing import Dict, Any` → `from typing import Dict, Any, List`
- **VALIDATE**: `python -c "from trading_api.main import app; print('Imports OK')"`

### Task 4: UPDATE `trading_api/main.py` - Update root endpoint documentation

- **ACTION**: UPDATE root() endpoint to document new list_jobs route
- **IMPLEMENT**: Add `"list_jobs": "GET /jobs"` to endpoints dict
- **MIRROR**: `main.py:65-77` - follow existing endpoint documentation pattern
- **LOCATION**: Line 72 (inside endpoints dict)
- **ADD LINE**: `"list_jobs": "GET /jobs",` after line 76
- **GOTCHA**: Ensure trailing comma on previous line
- **VALIDATE**: Manual test via `curl http://localhost:8000/` and verify output includes new endpoint

### Task 5: MANUAL TEST - Verify endpoint behavior

- **ACTION**: MANUAL TESTING of new endpoint
- **IMPLEMENT**: Test various scenarios:
  1. Empty database (no jobs) - should return `[]`
  2. Single job - should return 1-item list
  3. Multiple jobs with different statuses - verify sort order
  4. Jobs with same status - verify secondary sort by created_at
- **COMMANDS**:
  ```bash
  # Start API server (if not running)
  python -m trading_api.main

  # Test empty list
  curl http://localhost:8000/jobs
  # Expected: []

  # Submit test jobs
  curl -X POST http://localhost:8000/jobs \
    -H "Content-Type: application/json" \
    -d '{"ticker": "NVDA", "date": "2026-02-12"}'
  # Note the job_id from response

  curl -X POST http://localhost:8000/jobs \
    -H "Content-Type: application/json" \
    -d '{"ticker": "AAPL", "date": "2026-02-12"}'

  # List all jobs
  curl http://localhost:8000/jobs
  # Expected: JSON array with 2 jobs, sorted by status

  # Verify status sorting (running should come first)
  # Wait for one job to start running, then check order
  ```
- **VALIDATE**:
  - Response is valid JSON array
  - Status code is 200 OK
  - Jobs are sorted correctly (running before pending before failed before completed)
  - All required fields present in each job object
  - No duplicate jobs in response

---

## Testing Strategy

### Unit Tests to Write

| Test File                              | Test Cases                                                            | Validates                   |
| -------------------------------------- | --------------------------------------------------------------------- | --------------------------- |
| `tests/test_job_store.py` (if exists) | test_list_jobs_empty, test_list_jobs_sorting, test_list_jobs_deduplication | JobStore.list_jobs() method |
| `tests/test_api.py` (if exists)       | test_list_jobs_endpoint_empty, test_list_jobs_endpoint_multiple       | GET /jobs endpoint          |

**Note**: Existing test files may not exist. If test infrastructure is not set up, skip unit tests and rely on manual testing.

### Edge Cases Checklist

- [ ] Empty database (no jobs) - returns empty list []
- [ ] Single job - returns 1-item list
- [ ] Multiple jobs with same status - secondary sort by created_at works
- [ ] Job expires between SCAN and HGETALL - skipped gracefully (no error)
- [ ] SCAN returns duplicate keys - deduplication handles correctly
- [ ] Large job count (100+ jobs) - performance is acceptable (<5 seconds)
- [ ] All four status types present - sort order is correct
- [ ] Jobs with missing optional fields (error, error_type, retry_count) - handled gracefully

---

## Validation Commands

### Level 1: STATIC_ANALYSIS

```bash
# Type checking (if project has mypy or similar)
python -m mypy trading_api/main.py trading_api/job_store.py
# OR just verify imports work
python -c "from trading_api.main import app; from trading_api.job_store import JobStore; print('OK')"
```

**EXPECT**: No import errors, no type errors

### Level 2: MANUAL_ENDPOINT_TEST

```bash
# Start API server
python -m trading_api.main &
API_PID=$!
sleep 2

# Test empty list
curl -s http://localhost:8000/jobs | jq .

# Submit test jobs
curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "TEST1", "date": "2026-02-12"}' | jq .

curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "TEST2", "date": "2026-02-12"}' | jq .

# List jobs
curl -s http://localhost:8000/jobs | jq .

# Verify root endpoint documents new route
curl -s http://localhost:8000/ | jq .endpoints

# Cleanup
kill $API_PID
```

**EXPECT**: All commands return valid JSON, status 200, jobs sorted correctly

### Level 3: INTEGRATION_TEST (if Docker Compose available)

```bash
# Start full stack (Redis + API + Worker)
docker-compose up -d

# Wait for services
sleep 5

# Test via public API endpoint
curl -s http://localhost:8000/jobs | jq .

# Cleanup
docker-compose down
```

**EXPECT**: Endpoint accessible, returns valid response

### Level 4: LOAD_TEST (optional)

```bash
# Submit 100 jobs
for i in {1..100}; do
  curl -s -X POST http://localhost:8000/jobs \
    -H "Content-Type: application/json" \
    -d "{\"ticker\": \"LOAD$i\", \"date\": \"2026-02-12\"}" > /dev/null &
done
wait

# Measure list response time
time curl -s http://localhost:8000/jobs | jq 'length'
```

**EXPECT**: Response time < 5 seconds for 100 jobs

---

## Acceptance Criteria

- [ ] GET /jobs endpoint returns 200 OK with empty list when no jobs exist
- [ ] GET /jobs endpoint returns list of jobs with all required fields (job_id, status, created_at, ticker, date)
- [ ] Jobs are sorted by status priority: running → pending → failed → completed
- [ ] Within same status, jobs are sorted by created_at (oldest first)
- [ ] No duplicate jobs in response (deduplication works)
- [ ] Expired jobs are skipped gracefully (no errors)
- [ ] Root endpoint (GET /) documents new list_jobs route
- [ ] Response validates against List[JobStatusResponse] schema
- [ ] Large job counts (100+) return in reasonable time (<5 seconds)

---

## Completion Checklist

- [ ] Task 1: JobStore.list_jobs() method added and working
- [ ] Task 2: GET /jobs endpoint added to main.py
- [ ] Task 3: List import added to main.py
- [ ] Task 4: Root endpoint updated with new route documentation
- [ ] Task 5: Manual testing completed successfully
- [ ] Level 1: Import validation passes
- [ ] Level 2: Manual endpoint test passes
- [ ] Level 3: Integration test passes (if applicable)
- [ ] All acceptance criteria met

---

## Risks and Mitigations

| Risk                                       | Likelihood | Impact | Mitigation                                                                                |
| ------------------------------------------ | ---------- | ------ | ----------------------------------------------------------------------------------------- |
| SCAN performance degrades with 10k+ jobs   | MEDIUM     | MEDIUM | Use COUNT=1000 in scan_iter; document expected response time; consider pagination later   |
| Job expires between SCAN and HGETALL       | LOW        | LOW    | Check `if not job_data: continue` to skip expired jobs gracefully                         |
| SCAN returns duplicate keys                | MEDIUM     | LOW    | Use deduplication set to track processed keys                                             |
| Redis connection fails during SCAN         | LOW        | HIGH   | Let exception propagate to FastAPI; existing error handling converts to 500              |
| Client overwhelmed by large response (1MB+)| LOW        | MEDIUM | Document response size; clients can implement their own filtering; add pagination later  |
| Status sort order ambiguous to users       | LOW        | LOW    | Document sort order in API description and docstring                                      |

---

## Notes

**Design Decisions:**
- **No pagination initially**: SCAN is efficient enough for thousands of jobs. Can add limit/offset or cursor-based pagination later if needed.
- **Status sort priority**: Running jobs first because they're most actionable (can monitor progress). Completed jobs last because they're done (least urgent).
- **Secondary sort by created_at**: Within same status group, show oldest jobs first (FIFO processing order).
- **No Redis SET index**: SCAN pattern matching is sufficient. Adding `tradingagents:job:ids` SET would require updating create_job() and add complexity.
- **Deduplication in Python**: SCAN may return duplicates, so we deduplicate in application layer rather than relying on Redis.

**Performance Characteristics:**
- Redis SCAN with COUNT=1000: ~1ms per 1000 keys scanned
- HGETALL per job: ~0.1ms per job
- Python sorting: O(n log n), negligible for <10k jobs
- FastAPI/Pydantic serialization: ~0.01ms per job
- **Expected response time**: ~200ms for 1000 jobs, ~2s for 10k jobs

**Future Enhancements** (not in scope):
- Pagination with `?limit=50&cursor=abc123`
- Status filtering with `?status=running`
- Aggregation with `?include_stats=true` returning `{"jobs": [...], "stats": {"running": 2, ...}}`
- Redis SET index for O(1) job enumeration instead of O(N) SCAN
- Response caching with short TTL (5-10 seconds)

**Alternative Approaches Considered:**
1. **Redis SET index**: `SADD tradingagents:job:ids {job_id}` on creation → `SMEMBERS` for listing
   - **Rejected**: Adds complexity to create_job(), requires migration for existing jobs, SCAN is sufficient
2. **Sorted Set by timestamp**: `ZADD tradingagents:jobs:by_time {timestamp} {job_id}`
   - **Rejected**: Only allows one sort dimension (timestamp), we need status-based sort
3. **Separate sorted sets per status**: `ZADD tradingagents:jobs:running {timestamp} {job_id}`
   - **Rejected**: Requires updating multiple sets on status transitions, complex to maintain consistency
4. **Server-side pagination**: Implement limit/offset in JobStore.list_jobs()
   - **Deferred**: Not needed for initial implementation, can add later if job counts grow large

**Migration Notes:**
- No database migration needed (read-only operation)
- Existing jobs are automatically included (SCAN finds all existing keys)
- No backward compatibility concerns (new endpoint, no breaking changes)
