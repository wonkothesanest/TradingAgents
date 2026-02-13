"""Celery tasks for TradingAgents job processing."""

import signal
from typing import Dict, Any, Optional

from celery.exceptions import SoftTimeLimitExceeded
from trading_api.celery_app import celery_app
from trading_api.job_store import get_job_store
from trading_api.models import JobStatus

# TradingAgents imports
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError

# API exceptions
from trading_api.exceptions import TradingAgentsExecutionError


def cleanup_on_signal(signum, frame):
    """Cleanup handler for worker shutdown."""
    print("Received shutdown signal, cleaning up...")
    # Close LLM connections, save progress, etc.


# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, cleanup_on_signal)
signal.signal(signal.SIGINT, cleanup_on_signal)


@celery_app.task(bind=True, name="tradingagents.analyze_stock")
def analyze_stock(
    self,
    job_id: str,
    ticker: str,
    date: str,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Analyze stock and return trading decision.

    Phase 3: Executes actual TradingAgentsGraph.propagate() for real market analysis.

    Args:
        job_id: Job identifier for status tracking
        ticker: Stock ticker symbol (e.g., "NVDA", "AAPL")
        date: Analysis date in YYYY-MM-DD format
        config: Optional configuration overrides

    Returns:
        Result dictionary with decision, final_state, and reports

    Raises:
        Exception: On task execution failure (status updated to FAILED)
    """
    store = get_job_store()

    try:
        # Log retry attempt
        retry_count = self.request.retries
        print(f"Task {self.request.id}: Attempt {retry_count + 1}")

        # Store retry count in job metadata
        store.update_retry_count(job_id, retry_count)

        # Update job status to RUNNING
        store.update_job_status(job_id, JobStatus.RUNNING)
        print(f"Task {self.request.id}: Started analyzing {ticker} for {date}")

        # Phase 3: Execute actual TradingAgents analysis

        # Merge job-specific config with defaults
        merged_config = DEFAULT_CONFIG.copy()
        if config:
            merged_config.update(config)

        print(f"Task {self.request.id}: Initializing TradingAgentsGraph with config: {merged_config.get('llm_provider')}/{merged_config.get('deep_think_llm')}")

        # Instantiate TradingAgentsGraph
        ta = TradingAgentsGraph(debug=False, config=merged_config)

        # Execute propagate - returns (final_state, decision) tuple
        print(f"Task {self.request.id}: Starting propagate() for {ticker} on {date}")
        final_state, decision = ta.propagate(ticker, date)

        print(f"Task {self.request.id}: Analysis complete - Decision: {decision}")

        # Extract individual analyst reports from final_state
        reports = {
            "market": final_state.get("market_report", ""),
            "sentiment": final_state.get("sentiment_report", ""),
            "news": final_state.get("news_report", ""),
            "fundamentals": final_state.get("fundamentals_report", ""),
        }

        # Build result dict
        result = {
            "decision": decision,
            "final_state": final_state,
            "reports": reports,
        }

        # Store result in job store
        store.set_job_result(
            job_id,
            decision=result["decision"],
            final_state=result["final_state"],
            reports=result["reports"]
        )

        # Update status to completed
        store.update_job_status(job_id, JobStatus.COMPLETED)

        print(f"Task {self.request.id}: Completed analysis for {ticker}")

        return result

    except SoftTimeLimitExceeded:
        # Soft timeout (25 minutes) - attempt graceful shutdown
        error_msg = "Analysis exceeded 25-minute soft limit, attempting graceful shutdown"
        print(f"Task {self.request.id}: {error_msg}")
        store.update_job_status(job_id, JobStatus.FAILED, error_msg, error_type="timeout")
        # Re-raise to let hard limit (30 min) terminate if needed
        raise

    except AlphaVantageRateLimitError as exc:
        # Retryable error - don't update to FAILED, let Celery retry
        print(f"Task {self.request.id}: Rate limit hit, will retry")
        raise self.retry(exc=exc, countdown=60)  # Retry after 60 seconds

    except KeyError as exc:
        # Missing required data in response
        error_msg = f"Missing required data: {str(exc)}"
        print(f"Task {self.request.id}: {error_msg}")
        store.update_job_status(job_id, JobStatus.FAILED, error_msg, error_type="data_error")
        raise TradingAgentsExecutionError(ticker, date, error_msg)

    except Exception as exc:
        # Any other error (LLM API, network, graph execution)
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        error_type = "llm_error" if "llm" in error_msg.lower() or "api" in error_msg.lower() else "unknown"
        print(f"Task {self.request.id}: Unexpected error - {error_msg}")
        store.update_job_status(job_id, JobStatus.FAILED, error_msg, error_type=error_type)
        raise TradingAgentsExecutionError(ticker, date, error_msg)
