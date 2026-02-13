"""In-memory job storage for Phase 1 MVP."""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from trading_api.models import JobStatus
from trading_api.exceptions import JobNotFoundError


class JobStore:
    """In-memory job storage using a dictionary.

    This is a temporary implementation for Phase 1. Will be replaced
    with Redis/Celery result backend in Phase 2.
    """

    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}

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

        self._jobs[job_id] = {
            "job_id": job_id,
            "ticker": ticker,
            "date": date,
            "config": config,
            "status": JobStatus.PENDING,
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "error_type": None,
            "retry_count": 0,
            "result": None,
        }

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
        if job_id not in self._jobs:
            raise JobNotFoundError(job_id)
        return self._jobs[job_id].copy()

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
        if job_id not in self._jobs:
            raise JobNotFoundError(job_id)

        self._jobs[job_id]["status"] = status

        if status == JobStatus.RUNNING and self._jobs[job_id]["started_at"] is None:
            self._jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()

        if status in (JobStatus.COMPLETED, JobStatus.FAILED):
            self._jobs[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

        if error:
            self._jobs[job_id]["error"] = error
            self._jobs[job_id]["error_type"] = error_type or "unknown"

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
        if job_id not in self._jobs:
            raise JobNotFoundError(job_id)

        self._jobs[job_id]["retry_count"] = retry_count

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
        if job_id not in self._jobs:
            raise JobNotFoundError(job_id)

        self._jobs[job_id]["result"] = {
            "decision": decision,
            "final_state": final_state,
            "reports": reports,
        }

    def get_job_result(self, job_id: str) -> Dict[str, Any]:
        """Get job result.

        Args:
            job_id: Job identifier

        Returns:
            Result dictionary with decision, final_state, and reports

        Raises:
            JobNotFoundError: If job ID does not exist
        """
        job = self.get_job(job_id)

        if job["status"] != JobStatus.COMPLETED:
            raise ValueError(f"Job {job_id} is not completed (status: {job['status']})")

        if job["result"] is None:
            raise ValueError(f"Job {job_id} has no result data")

        return job["result"]


# Global job store instance
_job_store: Optional[JobStore] = None


def get_job_store() -> JobStore:
    """Get the global job store instance.

    Returns:
        JobStore instance
    """
    global _job_store
    if _job_store is None:
        _job_store = JobStore()
    return _job_store
