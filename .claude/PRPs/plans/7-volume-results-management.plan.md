# Feature: Volume & Results Management

## Summary

Implementing persistent Docker volumes for job results and data cache, filesystem structure for organized result storage, and API response formatting with nested report sections. Results persist across container restarts with documented manual cleanup procedures.

## User Story

As a N8N workflow developer
I want job results and cached data to persist across container restarts
So that I don't lose analysis results or have to re-fetch market data after deployments

## Metadata

| Field            | Value                                             |
|------------------|---------------------------------------------------|
| Type             | ENHANCEMENT                                       |
| Complexity       | LOW                                               |
| Systems Affected | docker-compose.yml, tasks.py, main.py             |
| Dependencies     | Phase 4 complete (Docker Compose configuration)   |
| Estimated Tasks  | 6                                                 |
| PRD Phase        | Phase 7: Volume & Results Management              |

## Files to Change

| File | Action | Justification |
|------|--------|---------------|
| `docker-compose.yml` | UPDATE | Add named volumes for results and cache |
| `trading_api/tasks.py` | UPDATE | Write results to structured filesystem |
| `trading_api/main.py` | UPDATE | Format API response with nested reports |
| `README.md` | UPDATE | Document volume locations and cleanup |
| `.env.example` | UPDATE | Document RESULTS_DIR and CACHE_DIR paths |

## Tasks

### Task 1: ADD named volumes to docker-compose.yml

Update the volumes section:

```yaml
volumes:
  results_data:
    driver: local
  cache_data:
    driver: local

services:
  api:
    volumes:
      - results_data:/data/results
      - cache_data:/app/tradingagents/dataflows/data_cache
  
  worker:
    volumes:
      - results_data:/data/results
      - cache_data:/app/tradingagents/dataflows/data_cache
```

**VALIDATE**: `docker-compose config` - YAML must be valid

### Task 2: UPDATE tasks.py to write structured results

In `trading_api/tasks.py`, after `ta.propagate()`:

```python
import json
from pathlib import Path

# After: final_state, decision = ta.propagate(ticker, date)

# Create results directory structure
results_base = Path(os.getenv("RESULTS_DIR", "/data/results"))
ticker_dir = results_base / ticker / date.replace("-", "")
ticker_dir.mkdir(parents=True, exist_ok=True)

# Write full state dict
state_file = ticker_dir / "state.json"
with open(state_file, "w") as f:
    json.dump(final_state, f, indent=2, default=str)

# Write decision
decision_file = ticker_dir / "decision.txt"
with open(decision_file, "w") as f:
    f.write(decision)

# Write individual reports
reports = {
    "market": final_state.get("market_report", ""),
    "sentiment": final_state.get("sentiment_report", ""),
    "news": final_state.get("news_report", ""),
    "fundamentals": final_state.get("fundamentals_report", "")
}

for report_name, content in reports.items():
    report_file = ticker_dir / f"{report_name}_report.txt"
    with open(report_file, "w") as f:
        f.write(content)

logger.info(f"Results written to {ticker_dir}")
```

**VALIDATE**: `python -m pylint trading_api/tasks.py --disable=all --enable=E`

### Task 3: UPDATE JobResult model with nested reports

In `trading_api/models.py`, update JobResult:

```python
class JobResult(BaseModel):
    job_id: str
    ticker: str
    date: str
    decision: str
    final_state: Dict[str, Any]
    reports: Dict[str, str] = Field(
        ...,
        description="Analyst reports by category"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "abc123",
                "ticker": "NVDA",
                "date": "2026-02-12",
                "decision": "BUY",
                "final_state": {"...": "..."},
                "reports": {
                    "market": "Technical analysis shows...",
                    "sentiment": "Social sentiment is positive...",
                    "news": "Recent news indicates...",
                    "fundamentals": "Company financials show..."
                }
            }
        }
```

**VALIDATE**: `python -c "from trading_api.models import JobResult; print('OK')"`

### Task 4: UPDATE GET /jobs/{job_id}/result endpoint

In `trading_api/main.py`, update result endpoint:

```python
@app.get("/jobs/{job_id}/result", response_model=JobResult)
async def get_job_result(job_id: str) -> JobResult:
    """Retrieve completed job results with full state and reports."""
    store = get_job_store()
    job = store.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed (status: {job.status.value})"
        )
    
    # Parse result from Celery
    result = AsyncResult(job.celery_task_id, app=celery_app)
    if not result.ready():
        raise HTTPException(status_code=400, detail="Result not ready")
    
    final_state, decision = result.get()
    
    # Extract reports from state
    reports = {
        "market": final_state.get("market_report", ""),
        "sentiment": final_state.get("sentiment_report", ""),
        "news": final_state.get("news_report", ""),
        "fundamentals": final_state.get("fundamentals_report", "")
    }
    
    return JobResult(
        job_id=job_id,
        ticker=job.ticker,
        date=job.date,
        decision=decision,
        final_state=final_state,
        reports=reports
    )
```

**VALIDATE**: `python -m pylint trading_api/main.py --disable=all --enable=E`

### Task 5: UPDATE .env.example with volume paths

Add to `.env.example`:

```bash
# Results Storage
RESULTS_DIR=/data/results
CACHE_DIR=/app/tradingagents/dataflows/data_cache

# Volume Management:
# Results are stored in: /data/results/{ticker}/{YYYYMMDD}/
# - state.json - Full analysis state dict
# - decision.txt - Trading decision (BUY/SELL/HOLD)
# - market_report.txt - Market analyst report
# - sentiment_report.txt - Sentiment analyst report
# - news_report.txt - News analyst report
# - fundamentals_report.txt - Fundamentals analyst report
#
# Cleanup: docker volume prune (removes unused volumes)
# Inspect: docker volume inspect tradingagents_results_data
```

**VALIDATE**: File syntax correct

### Task 6: DOCUMENT volume management in README

Add section to `README.md`:

```markdown
## Volume Management

### Storage Locations

**Results** (`/data/results`):
- Structured as: `/data/results/{ticker}/{YYYYMMDD}/`
- Contains: state.json, decision.txt, *_report.txt files
- Persists across container restarts
- Docker volume: `tradingagents_results_data`

**Cache** (`/app/tradingagents/dataflows/data_cache`):
- Market data cache (yfinance CSV files)
- Reduces API calls for repeated analysis
- Docker volume: `tradingagents_cache_data`

### Inspecting Volumes

```bash
# List volumes
docker volume ls | grep tradingagents

# Inspect volume details
docker volume inspect tradingagents_results_data

# Access results from host
docker run --rm -v tradingagents_results_data:/data alpine ls -lah /data/results
```

### Manual Cleanup

**Remove specific job results:**
```bash
docker run --rm -v tradingagents_results_data:/data alpine \
  rm -rf /data/results/NVDA/20260212
```

**Clear all results (WARNING: irreversible):**
```bash
docker-compose down
docker volume rm tradingagents_results_data
docker-compose up -d
```

**Clear cache only:**
```bash
docker-compose down
docker volume rm tradingagents_cache_data
docker-compose up -d
```
```

**VALIDATE**: Markdown renders correctly

## Testing

**Test 1: Volume persistence**
```bash
# Submit job
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2024-05-10"}'
# Get job_id from response

# Wait for completion, then restart containers
docker-compose restart api worker

# Retrieve result (should still work)
curl http://localhost:8000/jobs/{job_id}/result
```
**Expected**: Result retrieved successfully after restart

**Test 2: Filesystem structure**
```bash
# After job completes
docker run --rm -v tradingagents_results_data:/data alpine \
  ls -R /data/results/NVDA/20240510/
```
**Expected**: 
```
state.json
decision.txt
market_report.txt
sentiment_report.txt
news_report.txt
fundamentals_report.txt
```

**Test 3: Nested reports in API response**
```bash
curl http://localhost:8000/jobs/{job_id}/result | jq '.reports'
```
**Expected**: JSON object with keys: market, sentiment, news, fundamentals

## Acceptance Criteria

- [ ] Named volumes defined in docker-compose.yml
- [ ] Results written to `/data/results/{ticker}/{YYYYMMDD}/` structure
- [ ] All 6 files created per job (state, decision, 4 reports)
- [ ] API response includes `reports` object with nested sections
- [ ] Container restart preserves results
- [ ] Volume inspection commands documented
- [ ] Manual cleanup procedures documented
- [ ] Test 1-3 pass

## Validation Commands

### Level 1: STATIC_ANALYSIS
```bash
docker-compose config  # Validate YAML
python -m pylint trading_api/ --disable=all --enable=E  # Check errors only
```
**EXPECT**: Exit 0

### Level 2: VOLUME_VALIDATION
```bash
docker-compose up -d
docker volume ls | grep tradingagents  # Should show 2 volumes
docker volume inspect tradingagents_results_data  # Should show mountpoint
```
**EXPECT**: Volumes exist and mounted

### Level 3: FILESYSTEM_VALIDATION
```bash
# After submitting and completing a test job
docker run --rm -v tradingagents_results_data:/data alpine \
  find /data/results -type f -name "*.json" -o -name "*.txt"
```
**EXPECT**: Files present in correct structure

### Level 4: API_RESPONSE_VALIDATION
```bash
# After job completes
curl -s http://localhost:8000/jobs/{job_id}/result | jq '.reports | keys'
```
**EXPECT**: `["fundamentals", "market", "news", "sentiment"]`

### Level 5: PERSISTENCE_VALIDATION
```bash
# Submit job, wait for completion, restart, retrieve result
docker-compose restart api worker
sleep 5
curl -s http://localhost:8000/jobs/{job_id}/result | jq '.decision'
```
**EXPECT**: Result retrieved successfully

## Completion Checklist

- [ ] Task 1: Named volumes added to docker-compose.yml
- [ ] Task 2: tasks.py writes structured results
- [ ] Task 3: JobResult model includes nested reports
- [ ] Task 4: GET /result endpoint returns nested reports
- [ ] Task 5: .env.example documents volume paths
- [ ] Task 6: README documents volume management
- [ ] Level 1: YAML and Python syntax valid
- [ ] Level 2: Volumes created and mounted
- [ ] Level 3: Filesystem structure correct
- [ ] Level 4: API response format correct
- [ ] Level 5: Persistence verified after restart

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Disk space exhaustion | Medium | High | Document cleanup procedures, no auto-expiration |
| Volume permission errors | Low | Medium | Proper UID/GID in Dockerfile (from Phase 4) |
| Results not persisting | Low | High | Test restart scenario early, verify mount paths |

## Notes

- Results directory uses `YYYYMMDD` format (no hyphens) for easier sorting
- Cache directory matches TradingAgents default location
- No auto-cleanup to preserve historical results - user responsibility
- Volume driver is `local` (sufficient for single-machine deployment)
- Future consideration: S3/cloud storage for multi-machine deployments
