"""Celery tasks for TradingAgents job processing."""

import time
from typing import Dict, Any, Optional

from trading_api.celery_app import celery_app
from trading_api.job_store import get_job_store
from trading_api.models import JobStatus


@celery_app.task(bind=True, name="tradingagents.analyze_stock")
def analyze_stock(
    self,
    job_id: str,
    ticker: str,
    date: str,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Analyze stock and return trading decision.

    Phase 2: Test stub that simulates work and returns dummy data.
    Phase 3: Will call TradingAgentsGraph.propagate() for real analysis.

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
        # Update job status to RUNNING
        store.update_job_status(job_id, JobStatus.RUNNING)
        print(f"Task {self.request.id}: Started analyzing {ticker} for {date}")

        # Phase 2: Simulate work with sleep (5 seconds)
        # This proves the worker infrastructure works
        time.sleep(5)

        # Phase 2: Return test stub data
        # Phase 3 will replace this with actual TradingAgentsGraph execution:
        # from tradingagents.graph.trading_graph import TradingAgentsGraph
        # from tradingagents.default_config import DEFAULT_CONFIG
        # merged_config = DEFAULT_CONFIG.copy()
        # if config:
        #     merged_config.update(config)
        # ta = TradingAgentsGraph(debug=False, config=merged_config)
        # final_state, decision = ta.propagate(ticker, date)

        # Test stub result
        result = {
            "decision": "HOLD",
            "final_state": {
                "company_of_interest": ticker,
                "trade_date": date,
                "market_report": f"[TEST STUB] Market analysis for {ticker}",
                "sentiment_report": f"[TEST STUB] Sentiment analysis for {ticker}",
                "news_report": f"[TEST STUB] News analysis for {ticker}",
                "fundamentals_report": f"[TEST STUB] Fundamentals analysis for {ticker}",
                "final_trade_decision": "HOLD - Phase 2 test stub (no real analysis yet)",
            },
            "reports": {
                "market": f"[TEST STUB] Market analysis for {ticker}",
                "sentiment": f"[TEST STUB] Sentiment analysis for {ticker}",
                "news": f"[TEST STUB] News analysis for {ticker}",
                "fundamentals": f"[TEST STUB] Fundamentals analysis for {ticker}",
            }
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

    except Exception as exc:
        # Update status to failed with error message
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        store.update_job_status(job_id, JobStatus.FAILED, error_msg)
        print(f"Task {self.request.id}: Failed for {ticker} - {error_msg}")
        # Re-raise so Celery marks task as failed
        raise
