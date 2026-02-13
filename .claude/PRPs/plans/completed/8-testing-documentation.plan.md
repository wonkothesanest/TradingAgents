# Feature: Testing & Documentation

## Summary

Implementing comprehensive integration, load, and timeout tests to validate the complete TradingAgents Job API system. Creating deployment documentation, troubleshooting guide, and leveraging FastAPI's auto-generated OpenAPI docs. Success validated by 3-stock concurrent analysis completing within 11 minutes per ticker.

## User Story

As a N8N workflow developer
I want comprehensive tests and clear documentation
So that I can confidently deploy the system and debug issues when they arise

## Metadata

| Field            | Value                                             |
|------------------|---------------------------------------------------|
| Type             | ENHANCEMENT                                       |
| Complexity       | MEDIUM                                            |
| Systems Affected | tests/, README.md, docs/                          |
| Dependencies     | Phases 1-7 complete (full system operational)     |
| Estimated Tasks  | 8                                                 |
| PRD Phase        | Phase 8: Testing & Documentation                  |

## Files to Change

| File | Action | Justification |
|------|--------|---------------|
| `tests/integration/test_job_flow.py` | CREATE | End-to-end job submission → polling → result retrieval |
| `tests/integration/test_load.py` | CREATE | Concurrent job handling and queue behavior |
| `tests/integration/test_timeout.py` | CREATE | Timeout enforcement at 30 minutes |
| `tests/conftest.py` | CREATE | Shared pytest fixtures (Docker setup, cleanup) |
| `README.md` | UPDATE | Add deployment, usage, troubleshooting sections |
| `docs/DEPLOYMENT.md` | CREATE | Detailed deployment guide |
| `docs/TROUBLESHOOTING.md` | CREATE | Common issues and solutions |
| `pyproject.toml` | UPDATE | Add pytest and test dependencies |

## Tasks

### Task 1: CREATE tests/conftest.py with shared fixtures

```python
"""Pytest configuration and shared fixtures."""
import pytest
import docker
import time
import requests
from typing import Generator

@pytest.fixture(scope="session")
def docker_client():
    """Docker client for managing containers."""
    return docker.from_env()

@pytest.fixture(scope="session")
def api_base_url():
    """Base URL for API during tests."""
    return "http://localhost:8000"

@pytest.fixture(scope="session")
def docker_compose_up(docker_client):
    """Start docker-compose stack before tests."""
    import subprocess
    
    # Start services
    subprocess.run(["docker-compose", "up", "-d"], check=True)
    
    # Wait for API to be ready
    api_url = "http://localhost:8000/health"
    for _ in range(30):
        try:
            resp = requests.get(api_url, timeout=2)
            if resp.status_code == 200:
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    else:
        raise RuntimeError("API failed to start within 30 seconds")
    
    yield
    
    # Cleanup after all tests
    subprocess.run(["docker-compose", "down"], check=True)

@pytest.fixture
def submit_job(api_base_url):
    """Helper to submit a job and return job_id."""
    def _submit(ticker: str, date: str, config: dict = None):
        payload = {"ticker": ticker, "date": date}
        if config:
            payload["config"] = config
        
        resp = requests.post(f"{api_base_url}/jobs", json=payload)
        resp.raise_for_status()
        return resp.json()["job_id"]
    
    return _submit

@pytest.fixture
def wait_for_job(api_base_url):
    """Helper to poll until job completes or fails."""
    def _wait(job_id: str, timeout: int = 660) -> dict:
        start = time.time()
        while time.time() - start < timeout:
            resp = requests.get(f"{api_base_url}/jobs/{job_id}")
            resp.raise_for_status()
            job = resp.json()
            
            if job["status"] in ["completed", "failed"]:
                return job
            
            time.sleep(5)
        
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")
    
    return _wait
```

**VALIDATE**: `python -c "import tests.conftest; print('OK')"`

### Task 2: CREATE tests/integration/test_job_flow.py

```python
"""Integration test for complete job flow."""
import pytest
import requests

@pytest.mark.integration
@pytest.mark.usefixtures("docker_compose_up")
def test_submit_poll_retrieve_flow(api_base_url, submit_job, wait_for_job):
    """Test: Submit job → Poll status → Retrieve result."""
    
    # Submit job
    job_id = submit_job("NVDA", "2024-05-10")
    assert job_id is not None
    
    # Verify initial status
    resp = requests.get(f"{api_base_url}/jobs/{job_id}")
    assert resp.status_code == 200
    job = resp.json()
    assert job["status"] in ["pending", "running"]
    assert job["ticker"] == "NVDA"
    assert job["date"] == "2024-05-10"
    
    # Wait for completion
    final_job = wait_for_job(job_id, timeout=660)  # 11 minutes
    assert final_job["status"] == "completed"
    assert final_job["completed_at"] is not None
    
    # Retrieve result
    resp = requests.get(f"{api_base_url}/jobs/{job_id}/result")
    assert resp.status_code == 200
    result = resp.json()
    
    # Validate result structure
    assert result["job_id"] == job_id
    assert result["ticker"] == "NVDA"
    assert result["decision"] in ["BUY", "SELL", "HOLD"]
    assert "final_state" in result
    assert "reports" in result
    
    # Validate reports structure
    reports = result["reports"]
    assert "market" in reports
    assert "sentiment" in reports
    assert "news" in reports
    assert "fundamentals" in reports
    assert all(isinstance(v, str) for v in reports.values())

@pytest.mark.integration
@pytest.mark.usefixtures("docker_compose_up")
def test_job_not_found(api_base_url):
    """Test: GET non-existent job returns 404."""
    resp = requests.get(f"{api_base_url}/jobs/nonexistent")
    assert resp.status_code == 404

@pytest.mark.integration
@pytest.mark.usefixtures("docker_compose_up")
def test_result_before_completion(api_base_url, submit_job):
    """Test: GET result for running job returns 400."""
    job_id = submit_job("AAPL", "2024-05-10")
    
    # Immediately try to get result (job still running)
    resp = requests.get(f"{api_base_url}/jobs/{job_id}/result")
    assert resp.status_code == 400
    assert "not completed" in resp.json()["detail"].lower()
```

**VALIDATE**: `pytest tests/integration/test_job_flow.py -v --tb=short`

### Task 3: CREATE tests/integration/test_load.py

```python
"""Load test for concurrent job handling."""
import pytest
import requests
import time
from typing import List

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.usefixtures("docker_compose_up")
def test_concurrent_job_limit(api_base_url, submit_job, wait_for_job):
    """Test: Submit 5 jobs, verify concurrency=2, all complete within expected time."""
    
    tickers = ["NVDA", "AAPL", "TSLA", "MSFT", "GOOGL"]
    date = "2024-05-10"
    
    # Submit all jobs simultaneously
    start_time = time.time()
    job_ids = [submit_job(ticker, date) for ticker in tickers]
    submit_duration = time.time() - start_time
    
    # All submissions should be fast (<5s total)
    assert submit_duration < 5.0, f"Job submission took {submit_duration}s"
    
    # Poll status to verify concurrency behavior
    # With concurrency=2, expect:
    # - 2 jobs running immediately
    # - 3 jobs pending
    time.sleep(2)  # Let workers pick up jobs
    
    running_count = 0
    pending_count = 0
    for job_id in job_ids:
        resp = requests.get(f"{api_base_url}/jobs/{job_id}")
        status = resp.json()["status"]
        if status == "running":
            running_count += 1
        elif status == "pending":
            pending_count += 1
    
    # Verify concurrency limit enforced
    assert running_count <= 2, f"Expected ≤2 running, got {running_count}"
    assert pending_count >= 3, f"Expected ≥3 pending, got {pending_count}"
    
    # Wait for all jobs to complete
    # Expected: ~5min * 3 batches = 15min (with concurrency=2, running 2+2+1)
    # Allow up to 20min for safety
    for job_id in job_ids:
        final_job = wait_for_job(job_id, timeout=1200)
        assert final_job["status"] == "completed"
    
    total_duration = time.time() - start_time
    
    # Verify total time reasonable (5 jobs with concurrency=2)
    # Best case: 3 batches (2+2+1) * 5min = 15min
    # Worst case: ~20min
    assert total_duration < 1200, f"5 jobs took {total_duration/60:.1f}min (expected <20min)"

@pytest.mark.integration
@pytest.mark.usefixtures("docker_compose_up")
def test_three_stock_benchmark(api_base_url, submit_job, wait_for_job):
    """Test: 3 stocks complete within 11 minutes per ticker (PRD success metric)."""
    
    tickers = ["NVDA", "AAPL", "MSFT"]
    date = "2024-05-10"
    
    start_time = time.time()
    job_ids = [submit_job(ticker, date) for ticker in tickers]
    
    # Wait for all jobs
    for job_id in job_ids:
        final_job = wait_for_job(job_id, timeout=660)  # 11min per ticker
        assert final_job["status"] == "completed"
    
    total_duration = time.time() - start_time
    per_ticker_avg = total_duration / len(tickers)
    
    # PRD requirement: ≤11 min per ticker average
    assert per_ticker_avg <= 660, f"Avg {per_ticker_avg/60:.1f}min per ticker (expected ≤11min)"
```

**VALIDATE**: `pytest tests/integration/test_load.py -v -m slow`

### Task 4: CREATE tests/integration/test_timeout.py

```python
"""Timeout enforcement tests."""
import pytest
import requests
import time

@pytest.mark.integration
@pytest.mark.timeout
@pytest.mark.usefixtures("docker_compose_up")
def test_job_timeout_30min(api_base_url, submit_job, wait_for_job):
    """Test: Job exceeding 30 minutes fails with timeout error."""
    
    # This test requires a way to simulate a slow job
    # Option 1: Mock a ticker that causes slow data fetching
    # Option 2: Set a shorter timeout for testing (modify config)
    # Option 3: Skip in CI, run manually with real 30min wait
    
    pytest.skip("Requires 30-minute wait or mock implementation")
    
    # job_id = submit_job("SLOW_TICKER", "2024-05-10")
    # final_job = wait_for_job(job_id, timeout=1900)  # 31min
    # assert final_job["status"] == "failed"
    # assert "timeout" in final_job["error"].lower()

@pytest.mark.integration
@pytest.mark.usefixtures("docker_compose_up")
def test_soft_timeout_warning(api_base_url):
    """Test: Soft timeout at 25 minutes logs warning (manual verification)."""
    
    # This test validates that soft timeout behavior exists
    # Actual validation requires checking worker logs
    pytest.skip("Requires log inspection after 25-minute run")
```

**VALIDATE**: `pytest tests/integration/test_timeout.py -v`

### Task 5: UPDATE pyproject.toml with test dependencies

Add to `[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
test = [
    "pytest>=7.4.0",
    "pytest-timeout>=2.1.0",
    "requests>=2.31.0",
    "docker>=6.1.0",
]
```

**VALIDATE**: `python -c "import toml; toml.load('pyproject.toml')"`

### Task 6: CREATE docs/DEPLOYMENT.md

```markdown
# Deployment Guide

## Prerequisites

- Docker Engine 24.0+ with Docker Compose plugin
- NVIDIA GPU with CUDA support (for Ollama)
- nvidia-container-toolkit installed
- 50GB free disk space (models + cache)
- Ports available: 8000 (API), 6379 (Redis), 11434 (Ollama)

## Quick Start

1. **Clone repository:**
   ```bash
   git clone https://github.com/your-org/TradingAgents.git
   cd TradingAgents
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env and set required API keys
   ```

3. **Start services:**
   ```bash
   docker-compose up -d
   ```

4. **Verify health:**
   ```bash
   curl http://localhost:8000/health
   ```

5. **Submit test job:**
   ```bash
   curl -X POST http://localhost:8000/jobs \
     -H "Content-Type: application/json" \
     -d '{"ticker": "NVDA", "date": "2024-05-10"}'
   ```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_URL` | Yes | redis://redis:6379/0 | Redis connection URL |
| `CELERY_BROKER_URL` | Yes | redis://redis:6379/0 | Celery broker URL |
| `CELERY_RESULT_BACKEND` | Yes | redis://redis:6379/0 | Celery result backend |
| `OLLAMA_BASE_URL` | No | http://ollama:11434 | Ollama service URL |
| `RESULTS_DIR` | No | /data/results | Results storage path |
| `OPENAI_API_KEY` | No* | - | OpenAI API key (* if using openai) |

### Concurrency

Edit `docker-compose.yml` worker service:
```yaml
worker:
  command: celery -A trading_api.celery_app worker --concurrency=2
  #                                                             ↑
  #                                            Adjust based on GPU memory
```

## Production Considerations

1. **Reverse Proxy:** Use nginx/traefik for SSL and rate limiting
2. **Monitoring:** Add Prometheus + Grafana for metrics
3. **Log Aggregation:** Ship logs to ELK or Loki
4. **Backup:** Regularly backup `/data/results` volume
5. **Security:** Run API behind firewall, use API keys

## Scaling

**Vertical (single machine):**
- Increase worker concurrency based on GPU memory
- Add more Redis memory if queues grow large

**Horizontal (multi-machine):**
- Deploy workers on separate GPU machines
- Use shared Redis instance
- Use S3/NFS for shared results storage

## Monitoring

**Container health:**
```bash
docker-compose ps
docker-compose logs -f worker
```

**Queue status:**
```bash
docker exec -it tradingagents-redis-1 redis-cli
> LLEN celery
> KEYS celery*
```

**GPU utilization:**
```bash
nvidia-smi -l 1
```

## Updates

```bash
git pull origin main
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```
```

**VALIDATE**: Markdown renders correctly

### Task 7: CREATE docs/TROUBLESHOOTING.md

```markdown
# Troubleshooting Guide

## Common Issues

### API Returns 503 Service Unavailable

**Cause:** Redis not running or not accessible

**Fix:**
```bash
docker-compose ps redis  # Check status
docker-compose logs redis  # Check logs
docker-compose restart redis
```

### Job Stuck in "pending" Status

**Cause:** Worker not running or crashed

**Fix:**
```bash
docker-compose ps worker  # Check status
docker-compose logs worker  # Check for errors
docker-compose restart worker
```

**Verify queue:**
```bash
docker exec -it tradingagents-redis-1 redis-cli LLEN celery
# Should show pending jobs count
```

### Job Failed: "LLM service unavailable"

**Cause:** Ollama not running or out of memory

**Fix:**
```bash
docker-compose ps ollama
nvidia-smi  # Check GPU memory
docker-compose logs ollama

# Restart Ollama
docker-compose restart ollama
```

### Result Endpoint Returns 404

**Cause:** Results not persisted or volume not mounted

**Fix:**
```bash
# Check volume exists
docker volume ls | grep results

# Inspect volume
docker volume inspect tradingagents_results_data

# Check results directory
docker run --rm -v tradingagents_results_data:/data alpine ls -lah /data/results
```

### Docker Compose Fails to Start

**Cause:** Port conflicts or GPU not available

**Fix:**
```bash
# Check port availability
sudo lsof -i :8000
sudo lsof -i :6379
sudo lsof -i :11434

# Check GPU
nvidia-smi
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

### Job Times Out After 30 Minutes

**Expected behavior** if analysis takes too long.

**Fix (increase timeout):**

Edit `trading_api/celery_app.py`:
```python
celery_app.conf.task_time_limit = 3600  # 60 minutes
celery_app.conf.task_soft_time_limit = 3300  # 55 minutes
```

Rebuild and restart:
```bash
docker-compose down
docker-compose build worker
docker-compose up -d
```

### High Memory Usage

**Cause:** Multiple concurrent jobs with large models

**Fix:**
1. Reduce worker concurrency:
   ```yaml
   worker:
     command: celery ... --concurrency=1
   ```

2. Use smaller model in config:
   ```json
   {
     "llm_provider": "ollama",
     "deep_think_llm": "qwen3:8b"
   }
   ```

## Debugging Tips

### Enable Debug Logging

Edit `docker-compose.yml`:
```yaml
worker:
  environment:
    - LOG_LEVEL=DEBUG
```

### Access Worker Shell

```bash
docker exec -it tradingagents-worker-1 bash
```

### Inspect Celery Tasks

```bash
docker exec -it tradingagents-worker-1 celery -A trading_api.celery_app inspect active
docker exec -it tradingagents-worker-1 celery -A trading_api.celery_app inspect stats
```

### Check API Logs

```bash
docker-compose logs -f api --tail=100
```

## Getting Help

1. Check GitHub issues: https://github.com/your-org/TradingAgents/issues
2. Enable debug logging and capture full error
3. Include docker-compose.yml and .env (redact secrets)
4. Provide `docker-compose logs` output
```

**VALIDATE**: Markdown renders correctly

### Task 8: UPDATE README.md with comprehensive docs

Add/update sections:

```markdown
## TradingAgents Job API

Async job API for TradingAgents multi-agent trading analysis.

### Features

- 🚀 Async job queue with configurable concurrency
- 🐳 Docker Compose deployment with GPU support
- 🤖 Multi-provider LLM support (OpenAI, Anthropic, Ollama, etc.)
- 📊 Full analyst reports with trading decisions
- 💾 Persistent results across container restarts
- 🔍 OpenAPI docs at `/docs`

### Quick Start

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed instructions.

```bash
# Configure
cp .env.example .env

# Start services
docker-compose up -d

# Submit job
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2024-05-10"}'

# Check status
curl http://localhost:8000/jobs/{job_id}

# Get result
curl http://localhost:8000/jobs/{job_id}/result
```

### API Documentation

Interactive docs: http://localhost:8000/docs
OpenAPI spec: http://localhost:8000/openapi.json

### Testing

```bash
# Install test dependencies
pip install -e ".[test]"

# Run integration tests
pytest tests/integration/ -v

# Run load tests
pytest tests/integration/test_load.py -v -m slow

# Run specific test
pytest tests/integration/test_job_flow.py::test_submit_poll_retrieve_flow -v
```

### Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common issues.

### Architecture

```
N8N Workflow
     ↓
FastAPI (Port 8000)
     ↓
Redis Queue
     ↓
Celery Workers (concurrency=2)
     ↓
TradingAgentsGraph
     ↓
Ollama LLM (GPU)
```

### License

MIT
```

**VALIDATE**: Markdown renders correctly

## Testing Strategy

### Unit Tests
- Covered in Phase 1-7 implementation
- Each module has dedicated test file

### Integration Tests

| Test File | Test Cases | Validates |
|-----------|------------|-----------|
| `test_job_flow.py` | Submit → poll → result | End-to-end workflow |
| `test_load.py` | 5 concurrent jobs | Concurrency limits |
| `test_timeout.py` | 30-minute timeout | Timeout enforcement |

### Performance Tests

**3-Stock Benchmark** (PRD success metric):
- Submit 3 jobs (NVDA, AAPL, MSFT)
- Verify all complete within 11 minutes per ticker
- Run: `pytest tests/integration/test_load.py::test_three_stock_benchmark -v`

## Validation Commands

### Level 1: UNIT_TESTS
```bash
pytest tests/ -v --tb=short
```
**EXPECT**: All tests pass

### Level 2: INTEGRATION_TESTS
```bash
docker-compose up -d
pytest tests/integration/ -v -m "not slow"
```
**EXPECT**: All quick integration tests pass

### Level 3: LOAD_TESTS
```bash
pytest tests/integration/test_load.py -v -m slow
```
**EXPECT**: Concurrency verified, 3-stock benchmark <11min/ticker

### Level 4: DOCS_VALIDATION
```bash
# Start services and verify docs accessible
docker-compose up -d
curl -s http://localhost:8000/docs | grep -q "TradingAgents"
curl -s http://localhost:8000/openapi.json | jq '.info.title'
```
**EXPECT**: Docs render correctly

### Level 5: MANUAL_E2E_TEST
```bash
# Follow Quick Start in README
# Verify each step works
```
**EXPECT**: Complete workflow succeeds

## Acceptance Criteria

- [ ] Integration test suite passes (submit → poll → result)
- [ ] Load test verifies concurrency=2 enforcement
- [ ] 3-stock benchmark completes within 11min per ticker
- [ ] Timeout test validates 30-minute cutoff (or documented skip)
- [ ] README includes Quick Start and API docs link
- [ ] DEPLOYMENT.md covers prerequisites, config, scaling
- [ ] TROUBLESHOOTING.md covers common issues
- [ ] FastAPI auto-docs accessible at /docs
- [ ] pyproject.toml includes test dependencies

## Completion Checklist

- [ ] Task 1: conftest.py with fixtures
- [ ] Task 2: test_job_flow.py integration tests
- [ ] Task 3: test_load.py concurrent job tests
- [ ] Task 4: test_timeout.py timeout tests
- [ ] Task 5: pyproject.toml test dependencies
- [ ] Task 6: DEPLOYMENT.md created
- [ ] Task 7: TROUBLESHOOTING.md created
- [ ] Task 8: README.md updated
- [ ] Level 1-5 validation passes
- [ ] All acceptance criteria met

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Load tests too slow for CI | High | Low | Mark with `@pytest.mark.slow`, run separately |
| Timeout test requires 30min | High | Low | Skip in CI, document manual testing |
| Docker-in-Docker issues in CI | Medium | Medium | Use Docker socket mount or separate test environment |
| Flaky network tests | Medium | Medium | Add retries, increase timeouts for CI |

## Notes

- Integration tests require Docker Compose running
- Load tests marked with `@pytest.mark.slow` (separate execution)
- Timeout tests skipped by default (manual verification)
- FastAPI auto-generates OpenAPI docs (no manual work needed)
- Focus on end-to-end validation, not unit test coverage
- PRD success metric: 3 stocks within 11min per ticker
