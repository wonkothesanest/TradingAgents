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
