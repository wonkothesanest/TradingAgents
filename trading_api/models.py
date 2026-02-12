"""Pydantic models for API request/response validation."""

from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobRequest(BaseModel):
    """Request model for creating a new job."""

    ticker: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Stock ticker symbol (e.g., 'NVDA', 'AAPL')"
    )
    date: str = Field(
        ...,
        pattern=r'^\d{4}-\d{2}-\d{2}$',
        description="Analysis date in YYYY-MM-DD format"
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional configuration overrides for this job"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "NVDA",
                "date": "2026-02-12",
                "config": {
                    "max_debate_rounds": 1,
                    "llm_provider": "openai"
                }
            }
        }


class JobResponse(BaseModel):
    """Response model for job creation."""

    job_id: str = Field(..., description="Unique job identifier (UUID)")
    status: JobStatus = Field(..., description="Current job status")
    created_at: str = Field(..., description="Job creation timestamp (ISO 8601)")
    ticker: str = Field(..., description="Stock ticker for this job")
    date: str = Field(..., description="Analysis date for this job")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "pending",
                "created_at": "2026-02-12T10:30:00Z",
                "ticker": "NVDA",
                "date": "2026-02-12"
            }
        }


class JobStatusResponse(BaseModel):
    """Response model for job status queries."""

    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Current job status")
    created_at: str = Field(..., description="Job creation timestamp")
    started_at: Optional[str] = Field(None, description="Job start timestamp")
    completed_at: Optional[str] = Field(None, description="Job completion timestamp")
    ticker: str = Field(..., description="Stock ticker")
    date: str = Field(..., description="Analysis date")
    error: Optional[str] = Field(None, description="Error message if job failed")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "running",
                "created_at": "2026-02-12T10:30:00Z",
                "started_at": "2026-02-12T10:30:05Z",
                "completed_at": None,
                "ticker": "NVDA",
                "date": "2026-02-12",
                "error": None
            }
        }


class JobResultResponse(BaseModel):
    """Response model for job results."""

    job_id: str = Field(..., description="Unique job identifier")
    ticker: str = Field(..., description="Stock ticker")
    date: str = Field(..., description="Analysis date")
    decision: str = Field(..., description="Final trading decision (BUY/SELL/HOLD)")
    final_state: Dict[str, Any] = Field(..., description="Complete state dict from TradingAgentsGraph")
    reports: Dict[str, str] = Field(
        ...,
        description="Individual analyst reports (market, sentiment, news, fundamentals)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "ticker": "NVDA",
                "date": "2026-02-12",
                "decision": "BUY",
                "final_state": {},
                "reports": {
                    "market": "Market analysis report...",
                    "news": "News analysis report...",
                    "sentiment": "Sentiment analysis report...",
                    "fundamentals": "Fundamentals report..."
                }
            }
        }
