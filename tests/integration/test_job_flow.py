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

@pytest.mark.integration
@pytest.mark.usefixtures("docker_compose_up")
def test_list_jobs_empty(api_base_url):
    """Test: List jobs on empty database returns empty list."""
    resp = requests.get(f"{api_base_url}/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    # Note: May have existing jobs from other tests, so just validate structure
    assert isinstance(jobs, list)
    for job in jobs:
        assert "job_id" in job
        assert "status" in job
        assert "ticker" in job
        assert "date" in job
        assert "created_at" in job

@pytest.mark.integration
@pytest.mark.usefixtures("docker_compose_up")
def test_list_jobs_with_multiple(api_base_url, submit_job):
    """Test: List jobs returns multiple jobs sorted by status."""
    # Submit multiple jobs
    job_id_1 = submit_job("NVDA", "2024-05-10")
    job_id_2 = submit_job("AAPL", "2024-05-10")
    job_id_3 = submit_job("TSLA", "2024-05-10")

    # List all jobs
    resp = requests.get(f"{api_base_url}/jobs")
    assert resp.status_code == 200
    jobs = resp.json()

    # Should contain at least our 3 jobs
    assert isinstance(jobs, list)
    assert len(jobs) >= 3

    # Find our jobs in the list
    our_job_ids = {job_id_1, job_id_2, job_id_3}
    found_jobs = [job for job in jobs if job["job_id"] in our_job_ids]
    assert len(found_jobs) == 3

    # Validate structure of each job
    for job in found_jobs:
        assert job["status"] in ["pending", "running", "completed", "failed"]
        assert job["ticker"] in ["NVDA", "AAPL", "TSLA"]
        assert job["date"] == "2024-05-10"
        assert "created_at" in job
        assert "job_id" in job

@pytest.mark.integration
@pytest.mark.usefixtures("docker_compose_up")
def test_list_jobs_status_sorting(api_base_url, submit_job):
    """Test: List jobs are sorted by status priority."""
    # Submit jobs
    submit_job("TEST1", "2024-05-10")
    submit_job("TEST2", "2024-05-10")

    # List jobs
    resp = requests.get(f"{api_base_url}/jobs")
    assert resp.status_code == 200
    jobs = resp.json()

    # Verify jobs are sorted by status
    # Status priority: running (0), pending (1), failed (2), completed (3)
    status_order = {"running": 0, "pending": 1, "failed": 2, "completed": 3}

    for i in range(len(jobs) - 1):
        current_priority = status_order[jobs[i]["status"]]
        next_priority = status_order[jobs[i + 1]["status"]]
        # Current job should have <= priority (running comes before pending, etc.)
        assert current_priority <= next_priority, \
            f"Jobs not sorted correctly: {jobs[i]['status']} before {jobs[i + 1]['status']}"
