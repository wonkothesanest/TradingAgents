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
