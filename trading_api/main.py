"""FastAPI application for TradingAgents job submission and tracking."""

import os
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, status, Query
from fastapi.responses import JSONResponse
from redis import Redis

from trading_api.models import (
    JobRequest,
    JobResponse,
    JobStatusResponse,
    JobResultResponse,
    JobStatus,
    ErrorType,
)
from trading_api.job_store import get_job_store
from trading_api.exceptions import JobNotFoundError, APIException
from trading_api.celery_app import celery_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown.

    Startup: Initialize job store and resources
    Shutdown: Cleanup resources
    """
    print("FastAPI application starting up...")
    # Initialize job store
    get_job_store()
    print("Job store initialized")

    yield

    print("FastAPI application shutting down...")


app = FastAPI(
    title="TradingAgents API",
    description="REST API for remote TradingAgents job submission and tracking",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(JobNotFoundError)
async def job_not_found_handler(request, exc: JobNotFoundError):
    """Handle JobNotFoundError exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "job_id": exc.job_id},
    )


@app.exception_handler(APIException)
async def api_exception_handler(request, exc: APIException):
    """Handle generic API exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message},
    )


@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "name": "TradingAgents API",
        "version": "0.1.0",
        "status": "operational",
        "endpoints": {
            "health": "GET /health",
            "celery_inspect": "GET /celery",
            "submit_job": "POST /jobs",
            "list_jobs": "GET /jobs?error_type={optional}",
            "check_orphaned": "GET /jobs/orphaned",
            "cleanup_jobs": "POST /jobs/cleanup",
            "get_status": "GET /jobs/{job_id}",
            "get_result": "GET /jobs/{job_id}/result",
        },
    }


@app.get("/health")
async def health_check():
    """Health check with dependency validation."""
    health_status = {
        "status": "healthy",
        "components": {}
    }

    # Check Redis
    try:
        redis_client = Redis.from_url(
            os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
            socket_connect_timeout=2
        )
        redis_client.ping()
        health_status["components"]["redis"] = "up"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["components"]["redis"] = f"down: {str(e)}"

    # Check Celery workers
    try:
        inspect = celery_app.control.inspect(timeout=2)
        active_workers = inspect.ping()
        if active_workers:
            health_status["components"]["celery_workers"] = f"{len(active_workers)} active"
        else:
            health_status["status"] = "degraded"
            health_status["components"]["celery_workers"] = "no workers"
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["celery_workers"] = f"unknown: {str(e)}"

    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(health_status, status_code=status_code)


@app.get("/celery")
async def celery_inspect():
    """Inspect Celery queue and worker state.

    Returns detailed information about:
    - Active tasks (currently executing on workers)
    - Reserved tasks (claimed by workers, waiting to execute)
    - Scheduled tasks (in queue, not yet claimed)
    - Registered tasks (available task types)
    - Worker statistics and status

    Useful for debugging job execution and monitoring queue depth.
    """
    try:
        inspect = celery_app.control.inspect(timeout=2)

        # Get various queue states
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        scheduled = inspect.scheduled() or {}
        registered = inspect.registered() or {}
        stats = inspect.stats() or {}

        # Count total tasks across all workers
        total_active = sum(len(tasks) for tasks in active.values())
        total_reserved = sum(len(tasks) for tasks in reserved.values())
        total_scheduled = sum(len(tasks) for tasks in scheduled.values())

        return {
            "status": "ok",
            "workers": list(stats.keys()),
            "worker_count": len(stats),
            "summary": {
                "active_tasks": total_active,
                "reserved_tasks": total_reserved,
                "scheduled_tasks": total_scheduled,
                "total_pending": total_active + total_reserved + total_scheduled
            },
            "details": {
                "active": active,
                "reserved": reserved,
                "scheduled": scheduled,
                "registered_tasks": registered,
                "worker_stats": stats
            }
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "error": str(e),
                "message": "Failed to inspect Celery. Workers may be down or unreachable."
            }
        )


@app.get("/jobs/orphaned")
async def check_orphaned_jobs():
    """Check for orphaned jobs (PRIMARY detection method).

    Cross-references Redis job store with Celery's active tasks.
    Jobs marked as 'running' in Redis but not in Celery are orphaned
    (worker crashed, killed, or lost connection).

    This is much faster and more accurate than heartbeat-based detection.

    Returns:
        List of orphaned jobs
    """
    store = get_job_store()

    # Get active job IDs from Celery
    try:
        inspect = celery_app.control.inspect(timeout=2)
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        scheduled = inspect.scheduled() or {}

        # Extract job_ids from Celery tasks
        celery_job_ids = set()

        for tasks in active.values():
            for task in tasks:
                # Task args contain: [job_id, ticker, date, config]
                if task.get("args") and len(task["args"]) > 0:
                    celery_job_ids.add(task["args"][0])

        for tasks in reserved.values():
            for task in tasks:
                if task.get("args") and len(task["args"]) > 0:
                    celery_job_ids.add(task["args"][0])

        for tasks in scheduled.values():
            for task in tasks:
                if task.get("args") and len(task["args"]) > 0:
                    celery_job_ids.add(task["args"][0])

        orphaned_jobs = store.find_orphaned_jobs(celery_job_ids)

        return {
            "orphaned_count": len(orphaned_jobs),
            "celery_active_count": len(celery_job_ids),
            "orphaned_jobs": orphaned_jobs
        }

    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "error": str(e),
                "message": "Failed to inspect Celery. Using fallback heartbeat detection.",
                "orphaned_jobs": []
            }
        )


@app.post("/jobs/cleanup")
async def cleanup_jobs(method: str = "smart"):
    """Clean up ghost jobs (orphaned or stale).

    Two cleanup methods:
    - 'smart' (default): Cross-reference with Celery - immediate detection, no waiting
    - 'heartbeat': Use heartbeat timestamps - fallback when Celery unavailable

    Args:
        method: 'smart' or 'heartbeat' (default: smart)

    Returns:
        Number of jobs cleaned up
    """
    store = get_job_store()

    if method == "smart":
        # PRIMARY METHOD: Cross-reference with Celery
        try:
            inspect = celery_app.control.inspect(timeout=2)
            active = inspect.active() or {}
            reserved = inspect.reserved() or {}
            scheduled = inspect.scheduled() or {}

            # Extract job_ids from Celery
            celery_job_ids = set()
            for tasks in list(active.values()) + list(reserved.values()) + list(scheduled.values()):
                for task in tasks:
                    if task.get("args") and len(task["args"]) > 0:
                        celery_job_ids.add(task["args"][0])

            cleaned = store.cleanup_orphaned_jobs(celery_job_ids)

            return {
                "method": "smart",
                "cleaned": cleaned,
                "celery_active_count": len(celery_job_ids),
                "message": f"Marked {cleaned} orphaned job(s) as failed (not in Celery)"
            }

        except Exception as e:
            return JSONResponse(
                status_code=503,
                content={
                    "method": "smart",
                    "error": str(e),
                    "message": "Celery unavailable. Use method=heartbeat or try again later."
                }
            )

    elif method == "heartbeat":
        # FALLBACK METHOD: Use heartbeat timestamps
        cleaned = store.cleanup_stale_jobs(stale_threshold_seconds=1800)
        return {
            "method": "heartbeat",
            "cleaned": cleaned,
            "threshold_seconds": 1800,
            "message": f"Marked {cleaned} stale job(s) as failed (heartbeat timeout)"
        }

    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid method. Use 'smart' or 'heartbeat'"
        )


@app.post(
    "/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a new trading analysis job",
    description="Create a new job for analyzing a stock ticker on a specific date. Returns 202 Accepted with job ID.",
)
async def create_job(request: JobRequest) -> JobResponse:
    """Submit a new trading analysis job.

    Args:
        request: Job request containing ticker, date, and optional config

    Returns:
        JobResponse with job_id and status

    Example:
        POST /jobs
        {
            "ticker": "NVDA",
            "date": "2026-02-12",
            "config": {"max_debate_rounds": 1}
        }

        Response (202 Accepted):
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "pending",
            "created_at": "2026-02-12T10:30:00Z",
            "ticker": "NVDA",
            "date": "2026-02-12"
        }
    """
    store = get_job_store()

    # Pydantic already validated config schema
    # Convert to dict for storage
    config_dict = request.config.model_dump() if request.config else None

    # Create job in store
    job_id = store.create_job(
        ticker=request.ticker,
        date=request.date,
        config=config_dict,
    )

    # Get job data for response
    job = store.get_job(job_id)

    # Dispatch Celery task for background execution
    from trading_api.tasks import analyze_stock
    task = analyze_stock.delay(job_id, request.ticker, request.date, config_dict)

    print(f"Job {job_id} dispatched to Celery task {task.id}")

    return JobResponse(
        job_id=job["job_id"],
        status=job["status"],
        created_at=job["created_at"],
        ticker=job["ticker"],
        date=job["date"],
    )


@app.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status",
    description="Poll the status of a submitted job. Returns current status and timestamps.",
)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Get job status by ID.

    Args:
        job_id: Job identifier (UUID)

    Returns:
        JobStatusResponse with status and timestamps

    Raises:
        HTTPException: 404 if job not found

    Example:
        GET /jobs/550e8400-e29b-41d4-a716-446655440000

        Response:
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "running",
            "created_at": "2026-02-12T10:30:00Z",
            "started_at": "2026-02-12T10:30:05Z",
            "completed_at": null,
            "ticker": "NVDA",
            "date": "2026-02-12",
            "error": null
        }
    """
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
        run_time=job.get("run_time"),
    )


@app.get(
    "/jobs/{job_id}/result",
    response_model=JobResultResponse,
    summary="Get job result",
    description="Retrieve the full analysis result for a completed job. Returns 400 if job not completed.",
)
async def get_job_result(job_id: str) -> JobResultResponse:
    """Get job result by ID.

    Args:
        job_id: Job identifier (UUID)

    Returns:
        JobResultResponse with decision, state, and reports

    Raises:
        HTTPException: 404 if job not found, 400 if job not completed

    Example:
        GET /jobs/550e8400-e29b-41d4-a716-446655440000/result

        Response:
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "ticker": "NVDA",
            "date": "2026-02-12",
            "decision": "BUY",
            "final_state": {...},
            "reports": {
                "market": "...",
                "news": "...",
                "sentiment": "...",
                "fundamentals": "..."
            }
        }
    """
    store = get_job_store()

    # Check if job exists
    job = store.get_job(job_id)

    # Check if job is completed
    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed (current status: {job['status']})",
        )

    # Get result
    try:
        result = store.get_job_result(job_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    return JobResultResponse(
        job_id=job["job_id"],
        ticker=job["ticker"],
        date=job["date"],
        decision=result["decision"],
        final_state=result["final_state"],
        reports=result["reports"],
    )


@app.get(
    "/jobs",
    response_model=List[JobStatusResponse],
    summary="List all jobs",
    description="Retrieve all jobs sorted by status (running → pending → failed → completed). Optionally filter by error type. Returns job metadata without full results.",
)
async def list_jobs(
    error_type: Optional[ErrorType] = Query(
        None,
        description="Filter jobs by error type (timeout, llm_error, data_error, worker_lost, invalid_config, unknown)"
    )
) -> List[JobStatusResponse]:
    """List all jobs, sorted by status.

    Args:
        error_type: Optional filter to only return jobs with this specific error type

    Returns:
        List of JobStatusResponse objects sorted by status priority

    Example:
        GET /jobs
        GET /jobs?error_type=timeout
        GET /jobs?error_type=llm_error

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

    # Get jobs from store with optional filter
    jobs = store.list_jobs(error_type=error_type)

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
            run_time=job.get("run_time"),
        )
        for job in jobs
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
