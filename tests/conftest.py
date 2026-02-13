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
