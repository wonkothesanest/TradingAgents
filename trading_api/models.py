"""Pydantic models for API request/response validation."""

from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from typing_extensions import Literal


class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ErrorType(str, Enum):
    """Job failure error categories."""
    TIMEOUT = "timeout"
    LLM_ERROR = "llm_error"
    DATA_ERROR = "data_error"
    WORKER_LOST = "worker_lost"
    WORKER_SHUTDOWN = "worker_shutdown"
    INVALID_CONFIG = "invalid_config"
    UNKNOWN = "unknown"


class JobConfigSchema(BaseModel):
    """Validated configuration options for job customization."""

    # LLM Configuration
    llm_provider: Optional[Literal["openai", "anthropic", "google", "xai", "ollama", "openrouter"]] = None
    deep_think_llm: Optional[str] = Field(None, max_length=100)
    quick_think_llm: Optional[str] = Field(None, max_length=100)
    backend_url: Optional[str] = Field(None, pattern=r'^https?://.+')

    # Analysis Configuration
    max_debate_rounds: Optional[int] = Field(None, ge=1, le=5)
    max_risk_discuss_rounds: Optional[int] = Field(None, ge=1, le=3)
    selected_analysts: Optional[List[Literal["market", "social", "news", "fundamentals"]]] = None

    # Data Vendor Configuration
    data_vendors: Optional[Dict[str, str]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "llm_provider": "openai",
                "deep_think_llm": "gpt-4",
                "max_debate_rounds": 2,
                "selected_analysts": ["market", "news"]
            }
        }


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
    config: Optional[JobConfigSchema] = Field(
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
    error_type: Optional[ErrorType] = Field(None, description="Error category if job failed")
    retry_count: Optional[int] = Field(None, description="Number of retry attempts")
    run_time: Optional[str] = Field(None, description="Job run time in H:MM:SS format (null if not started)")

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
                "error": None,
                "error_type": None,
                "retry_count": 0
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
