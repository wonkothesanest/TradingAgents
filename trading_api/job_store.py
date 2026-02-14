"""Redis-based job storage for distributed API/worker architecture."""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from redis import Redis
from trading_api.models import ErrorType, JobStatus
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
            "last_heartbeat": "",
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
            "last_heartbeat": job_data.get("last_heartbeat") or None,
            "error": job_data.get("error") or None,
            "error_type": job_data.get("error_type") or None,
            "retry_count": int(job_data.get("retry_count", 0)),
        }

        return result

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
                "last_heartbeat": job_data.get("last_heartbeat") or None,
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

    def update_heartbeat(self, job_id: str) -> None:
        """Update job heartbeat timestamp.

        Args:
            job_id: Job identifier

        Raises:
            JobNotFoundError: If job ID does not exist
        """
        key = self._get_job_key(job_id)

        if not self.redis.exists(key):
            raise JobNotFoundError(job_id)

        self.redis.hset(key, "last_heartbeat", datetime.now(timezone.utc).isoformat())

    def find_orphaned_jobs(self, celery_active_job_ids: set) -> List[Dict[str, Any]]:
        """Find jobs marked as 'running' but not actually running in Celery.

        This is the PRIMARY detection method - much faster and more accurate than heartbeat.
        Cross-references Redis job store with Celery's active tasks.

        Args:
            celery_active_job_ids: Set of job_ids currently in Celery (active/reserved/scheduled)

        Returns:
            List of orphaned job dictionaries
        """
        orphaned_jobs = []

        for key in self.redis.scan_iter(match="tradingagents:job:*", count=1000):
            job_data = self.redis.hgetall(key)

            if not job_data:
                continue

            status = job_data.get("status")
            if status != JobStatus.RUNNING:
                continue

            job_id = job_data.get("job_id")

            # Job says it's running, but Celery doesn't know about it = GHOST
            if job_id not in celery_active_job_ids:
                job = self._parse_job_data(job_data)
                job["orphaned_reason"] = "Job marked as running but not in Celery queue"
                orphaned_jobs.append(job)

        return orphaned_jobs

    def find_stale_jobs(self, stale_threshold_seconds: int = 1800) -> List[Dict[str, Any]]:
        """Find jobs stuck in 'running' state without recent heartbeat.

        Args:
            stale_threshold_seconds: Jobs running longer than this without heartbeat are stale.
                                    Default: 1800 seconds (30 minutes)

        Returns:
            List of stale job dictionaries
        """
        stale_jobs = []
        now = datetime.now(timezone.utc)

        for key in self.redis.scan_iter(match="tradingagents:job:*", count=1000):
            job_data = self.redis.hgetall(key)

            if not job_data:
                continue

            status = job_data.get("status")
            if status != JobStatus.RUNNING:
                continue

            # Check if job has a heartbeat
            last_heartbeat_str = job_data.get("last_heartbeat")
            if not last_heartbeat_str:
                # No heartbeat ever - check how long it's been running
                started_at_str = job_data.get("started_at")
                if started_at_str:
                    started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                    running_time = (now - started_at).total_seconds()
                    if running_time > stale_threshold_seconds:
                        job = self._parse_job_data(job_data)
                        job["stale_reason"] = f"No heartbeat, running for {running_time:.0f}s"
                        stale_jobs.append(job)
            else:
                # Has heartbeat - check how old it is
                last_heartbeat = datetime.fromisoformat(last_heartbeat_str.replace("Z", "+00:00"))
                heartbeat_age = (now - last_heartbeat).total_seconds()
                if heartbeat_age > stale_threshold_seconds:
                    job = self._parse_job_data(job_data)
                    job["stale_reason"] = f"Heartbeat stale for {heartbeat_age:.0f}s"
                    stale_jobs.append(job)

        return stale_jobs

    def _parse_job_data(self, job_data: Dict[str, str]) -> Dict[str, Any]:
        """Parse job data from Redis hash.

        Helper method to convert Redis string values to proper types.
        """
        return {
            "job_id": job_data["job_id"],
            "ticker": job_data["ticker"],
            "date": job_data["date"],
            "config": json.loads(job_data["config"]) if job_data.get("config") else None,
            "status": job_data["status"],
            "created_at": job_data["created_at"],
            "started_at": job_data.get("started_at") or None,
            "completed_at": job_data.get("completed_at") or None,
            "last_heartbeat": job_data.get("last_heartbeat") or None,
            "error": job_data.get("error") or None,
            "error_type": job_data.get("error_type") or None,
            "retry_count": int(job_data.get("retry_count", 0)),
        }

    def cleanup_orphaned_jobs(self, celery_active_job_ids: set) -> int:
        """Mark orphaned jobs as failed (PRIMARY cleanup method).

        Jobs marked as 'running' in Redis but not in Celery are orphaned
        (worker crashed, was killed, or lost connection). Mark them as failed immediately.

        Args:
            celery_active_job_ids: Set of job_ids currently in Celery

        Returns:
            Number of jobs marked as failed
        """
        orphaned_jobs = self.find_orphaned_jobs(celery_active_job_ids)

        for job in orphaned_jobs:
            self.update_job_status(
                job["job_id"],
                JobStatus.FAILED,
                error=f"Worker lost: {job.get('orphaned_reason', 'Not in Celery queue')}",
                error_type=ErrorType.WORKER_LOST
            )

        return len(orphaned_jobs)

    def cleanup_stale_jobs(self, stale_threshold_seconds: int = 1800) -> int:
        """Mark stale running jobs as failed (BACKUP cleanup method).

        Use this as a fallback when Celery inspection is unavailable.
        Prefer cleanup_orphaned_jobs() which uses Celery as source of truth.

        Args:
            stale_threshold_seconds: Jobs running longer than this without heartbeat are stale.
                                    Default: 1800 seconds (30 minutes)

        Returns:
            Number of jobs marked as failed
        """
        stale_jobs = self.find_stale_jobs(stale_threshold_seconds)

        for job in stale_jobs:
            self.update_job_status(
                job["job_id"],
                JobStatus.FAILED,
                error=f"Job stale: {job.get('stale_reason', 'No heartbeat')}",
                error_type="timeout"
            )

        return len(stale_jobs)

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
