"""Redis-based job storage for distributed API/worker architecture."""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from redis import Redis
from trading_api.models import JobStatus
from trading_api.exceptions import JobNotFoundError


class JobStore:
    """Redis-based job storage for API and workers.

    Uses Redis to share job state between the API server and Celery workers.
    Each job is stored as a Redis hash with a TTL of 7 days.
    """

    def __init__(self, redis_client: Optional[Redis] = None):
        """Initialize JobStore with Redis client.

        Args:
            redis_client: Optional Redis client. If not provided, creates one from
                         CELERY_BROKER_URL or CELERY_RESULT_BACKEND env vars.
        """
        if redis_client is None:
            redis_url = os.getenv(
                "CELERY_RESULT_BACKEND",
                os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
            )
            self.redis = Redis.from_url(redis_url, decode_responses=True)
        else:
            self.redis = redis_client

        self.job_ttl = 7 * 24 * 60 * 60  # 7 days in seconds

    def _get_job_key(self, job_id: str) -> str:
        """Get Redis key for a job.

        Args:
            job_id: Job identifier

        Returns:
            Redis key string
        """
        return f"tradingagents:job:{job_id}"

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

        job_data = {
            "job_id": job_id,
            "ticker": ticker,
            "date": date,
            "config": json.dumps(config) if config else "",
            "status": JobStatus.PENDING,
            "created_at": now,
            "started_at": "",
            "completed_at": "",
            "error": "",
            "error_type": "",
            "retry_count": "0",
            "result": "",
        }

        print(f"Creating job {job_id} for {ticker} on {date} with config: {config}")
        print(f"Job data to store: {job_data}")
        print(f"ttl: {self.job_ttl} seconds")
        

        # Store in Redis as hash
        key = self._get_job_key(job_id)
        self.redis.hset(key, mapping=job_data)
        self.redis.expire(key, self.job_ttl)

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

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        error: Optional[str] = None,
        error_type: Optional[str] = None
    ) -> None:
        """Update job status.

        Args:
            job_id: Job identifier
            status: New status
            error: Optional error message for FAILED status
            error_type: Optional error category for FAILED status

        Raises:
            JobNotFoundError: If job ID does not exist
        """
        key = self._get_job_key(job_id)

        # Check if job exists
        if not self.redis.exists(key):
            raise JobNotFoundError(job_id)

        # Update status
        self.redis.hset(key, "status", status)

        # Set started_at if transitioning to RUNNING
        if status == JobStatus.RUNNING:
            current_started = self.redis.hget(key, "started_at")
            if not current_started:
                self.redis.hset(key, "started_at", datetime.now(timezone.utc).isoformat())

        # Set completed_at if done
        if status in (JobStatus.COMPLETED, JobStatus.FAILED):
            self.redis.hset(key, "completed_at", datetime.now(timezone.utc).isoformat())

        # Set error fields
        if error:
            self.redis.hset(key, "error", error)
            self.redis.hset(key, "error_type", error_type or "unknown")

    def update_retry_count(
        self,
        job_id: str,
        retry_count: int
    ) -> None:
        """Update job retry count.

        Args:
            job_id: Job identifier
            retry_count: Number of retry attempts

        Raises:
            JobNotFoundError: If job ID does not exist
        """
        key = self._get_job_key(job_id)

        # Check if job exists
        if not self.redis.exists(key):
            raise JobNotFoundError(job_id)

        self.redis.hset(key, "retry_count", str(retry_count))

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
        key = self._get_job_key(job_id)

        # Check if job exists
        if not self.redis.exists(key):
            raise JobNotFoundError(job_id)

        result = {
            "decision": decision,
            "final_state": final_state,
            "reports": reports,
        }

        # Store result as JSON string
        self.redis.hset(key, "result", json.dumps(result, default=str))

    def get_job_result(self, job_id: str) -> Dict[str, Any]:
        """Get job result.

        Args:
            job_id: Job identifier

        Returns:
            Result dictionary with decision, final_state, and reports

        Raises:
            JobNotFoundError: If job ID does not exist
        """
        key = self._get_job_key(job_id)

        # Check if job exists
        if not self.redis.exists(key):
            raise JobNotFoundError(job_id)

        status = self.redis.hget(key, "status")
        if status != JobStatus.COMPLETED:
            raise ValueError(f"Job {job_id} is not completed (status: {status})")

        result_json = self.redis.hget(key, "result")
        if not result_json:
            raise ValueError(f"Job {job_id} has no result data")

        return json.loads(result_json)


# Global job store instance
_job_store: Optional[JobStore] = None


def get_job_store(redis_client: Optional[Redis] = None) -> JobStore:
    """Get the global job store instance.

    Args:
        redis_client: Optional Redis client for testing/custom configuration

    Returns:
        JobStore instance
    """
    global _job_store
    if _job_store is None:
        _job_store = JobStore(redis_client)
    return _job_store
