"""FastAPI application for TradingAgents job submission and tracking."""

from contextlib import asynccontextmanager
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from trading_api.models import (
    JobRequest,
    JobResponse,
    JobStatusResponse,
    JobResultResponse,
    JobStatus,
)
from trading_api.job_store import get_job_store
from trading_api.exceptions import JobNotFoundError, APIException


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
            "submit_job": "POST /jobs",
            "get_status": "GET /jobs/{job_id}",
            "get_result": "GET /jobs/{job_id}/result",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
