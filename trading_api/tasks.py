"""Celery tasks for TradingAgents job processing."""

import json
import os
import signal
from pathlib import Path
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


def _safe_update_status(store, job_id: str, status: JobStatus, error: Optional[str] = None, error_type: Optional[str] = None, max_retries: int = 3):
    """Safely update job status with retries.

    Ensures status updates succeed even if Redis is temporarily unavailable.
    """
    for attempt in range(max_retries):
        try:
            store.update_job_status(job_id, status, error, error_type)
            return True
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"CRITICAL: Failed to update status for {job_id} after {max_retries} attempts: {e}")
                return False
            print(f"Warning: Status update failed (attempt {attempt + 1}/{max_retries}): {e}")
            import time
            time.sleep(1)  # Wait 1 second before retry
    return False


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

    # Track if we successfully marked as running
    status_marked_running = False

    try:
        # Log retry attempt
        retry_count = self.request.retries
        print(f"Task {self.request.id}: Attempt {retry_count + 1}")

        # Store retry count in job metadata
        try:
            store.update_retry_count(job_id, retry_count)
        except Exception as e:
            print(f"Warning: Failed to update retry count: {e}")

        # Update job status to RUNNING (with retries)
        status_marked_running = _safe_update_status(store, job_id, JobStatus.RUNNING)
        if not status_marked_running:
            # If we can't mark as running, abort early
            raise Exception("Failed to update job status to RUNNING - Redis may be down")

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

        # Write results to filesystem
        results_base = Path(os.getenv("RESULTS_DIR", "/data/results"))
        ticker_dir = results_base / ticker / date.replace("-", "")
        ticker_dir.mkdir(parents=True, exist_ok=True)

        # Write full state dict
        state_file = ticker_dir / "state.json"
        with open(state_file, "w") as f:
            json.dump(final_state, f, indent=2, default=str)

        # Write decision
        decision_file = ticker_dir / "decision.txt"
        with open(decision_file, "w") as f:
            f.write(decision)

        # Extract individual analyst reports from final_state
        reports = {
            "market": final_state.get("market_report", ""),
            "sentiment": final_state.get("sentiment_report", ""),
            "news": final_state.get("news_report", ""),
            "fundamentals": final_state.get("fundamentals_report", ""),
        }

        # Write individual reports
        for report_name, content in reports.items():
            report_file = ticker_dir / f"{report_name}_report.txt"
            with open(report_file, "w") as f:
                f.write(content)

        print(f"Task {self.request.id}: Results written to {ticker_dir}")

        # Convert final_state to JSON-serializable format
        # Use json.loads(json.dumps()) with default=str to handle non-serializable objects
        serializable_state = json.loads(
            json.dumps(final_state, default=str)
        )

        # Build result dict with serializable data only
        result = {
            "decision": decision,
            "final_state": serializable_state,
            "reports": reports,
        }

        # Store result in job store (with error handling)
        try:
            store.set_job_result(
                job_id,
                decision=result["decision"],
                final_state=result["final_state"],
                reports=result["reports"]
            )
        except Exception as e:
            print(f"Warning: Failed to store result in Redis: {e}")
            # Continue anyway - result is on filesystem

        # Update status to completed (WITH RETRIES - CRITICAL!)
        if not _safe_update_status(store, job_id, JobStatus.COMPLETED):
            print(f"CRITICAL: Task completed but failed to update Redis status for {job_id}")
            # Task still succeeds - smart cleanup will catch this

        print(f"Task {self.request.id}: Completed analysis for {ticker}")

        return result

    except SoftTimeLimitExceeded:
        # Soft timeout (25 minutes) - attempt graceful shutdown
        error_msg = "Analysis exceeded 25-minute soft limit, attempting graceful shutdown"
        print(f"Task {self.request.id}: {error_msg}")
        _safe_update_status(store, job_id, JobStatus.FAILED, error_msg, error_type="timeout")
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
        _safe_update_status(store, job_id, JobStatus.FAILED, error_msg, error_type="data_error")
        raise TradingAgentsExecutionError(ticker, date, error_msg)

    except (SystemExit, KeyboardInterrupt):
        # Worker shutdown - mark as failed
        error_msg = "Worker shutdown during execution"
        print(f"Task {self.request.id}: {error_msg}")
        _safe_update_status(store, job_id, JobStatus.FAILED, error_msg, error_type="worker_shutdown")
        raise

    except Exception as exc:
        # Any other error (LLM API, network, graph execution)
        try:
            error_msg = f"{type(exc).__name__}: {str(exc)}"
        except:
            error_msg = f"{type(exc).__name__}: <error converting to string>"

        error_type = "llm_error" if "llm" in error_msg.lower() or "api" in error_msg.lower() else "unknown"
        print(f"Task {self.request.id}: Unexpected error - {error_msg}")
        _safe_update_status(store, job_id, JobStatus.FAILED, error_msg, error_type=error_type)
        raise TradingAgentsExecutionError(ticker, date, error_msg)

    finally:
        # FINAL SAFETY NET: If we marked as running but never updated status, mark as failed
        # This catches: hard timeouts (SIGKILL), worker crashes, Redis failures during update
        if status_marked_running:
            try:
                # Check current status
                current_job = store.get_job(job_id)
                if current_job["status"] == JobStatus.RUNNING:
                    # Still marked as running - something went wrong
                    print(f"SAFETY NET: Job {job_id} still running in finally block - marking as failed")
                    _safe_update_status(
                        store,
                        job_id,
                        JobStatus.FAILED,
                        "Task ended abnormally (caught in finally block)",
                        error_type="abnormal_exit"
                    )
            except Exception as e:
                print(f"SAFETY NET: Failed to check/update status in finally block: {e}")
                # Can't do anything more - smart cleanup will catch it
