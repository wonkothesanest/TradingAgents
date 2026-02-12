# Feature: TradingAgents Integration with Celery Workers

## Summary

Replacing the Phase 2 test stub with actual TradingAgentsGraph.propagate() execution in Celery worker tasks. Phase 2 proved the infrastructure works (task dispatch, queue, status updates), now Phase 3 adds real trading analysis by instantiating TradingAgentsGraph inside the worker, passing job parameters, capturing the full state dict and decision, and handling exceptions from LLM/data fetch operations. This completes the core job execution pipeline: API receives request → Celery dispatches → Worker executes TradingAgentsGraph → Results stored → N8N retrieves analysis.

## User Story

As a N8N workflow automation developer
I want Celery workers to execute actual TradingAgents analysis
So that I get real trading decisions and analyst reports instead of test stub data

## Problem Statement

Phase 2 implemented the distributed task queue infrastructure with a 5-second sleep test stub that returns dummy data. This validates that tasks dispatch, workers pick them up, and status updates flow correctly. However, the core value proposition - running TradingAgentsGraph analysis on real market data to generate actionable trading decisions - is still missing. N8N workflows can submit jobs and retrieve results, but those results are meaningless "[TEST STUB]" placeholders rather than actual market analysis, sentiment scores, news summaries, and fundamentals data.

## Solution Statement

Replace the `time.sleep(5)` test stub in `trading_api/tasks.py:analyze_stock` with actual TradingAgentsGraph instantiation and propagate() execution. Import TradingAgentsGraph and DEFAULT_CONFIG, merge job-specific config overrides with defaults, create the graph instance, call propagate(ticker, date), capture the returned (final_state, decision) tuple, extract individual analyst reports from final_state keys (market_report, sentiment_report, news_report, fundamentals_report), and store everything via job_store methods. Add comprehensive exception handling for common failure modes: LLM API errors (rate limits, timeouts), data fetch failures (Alpha Vantage, yfinance), and graph execution errors.

## Metadata

| Field            | Value                                             |
| ---------------- | ------------------------------------------------- |
| Type             | ENHANCEMENT                                       |
| Complexity       | MEDIUM                                            |
| Systems Affected | trading_api/tasks.py (replace stub), exception handling |
| Dependencies     | Phase 2 complete (Celery + Redis working), TradingAgentsGraph stable |
| Estimated Tasks  | 4                                                 |
| PRD Phase        | Phase 3: TradingAgents Integration                |
| PRD Reference    | `.claude/PRPs/prds/tradingagents-job-api.prd.md` |

---

## UX Design

### Before State (Phase 2)

```
Worker picks up task → Sleep 5 seconds → Return dummy data
  - decision: "HOLD"
  - reports: "[TEST STUB] Market analysis for {ticker}"
  - final_state: Minimal test dict
```

### After State (Phase 3)

```
Worker picks up task → TradingAgentsGraph.propagate(ticker, date) → Real analysis
  - decision: "BUY" | "SELL" | "HOLD" (from actual LLM reasoning)
  - reports: {
      market: Full technical analysis with MACD, RSI, price trends
      sentiment: Social media sentiment scores and trends
      news: News summaries with impact analysis
      fundamentals: Financial ratios, earnings, balance sheet analysis
    }
  - final_state: Complete AgentState with all analyst outputs, debate history, risk analysis
```

### Interaction Changes

| Location | Before | After | User_Action | Impact |
|----------|--------|-------|-------------|--------|
| Worker task execution | 5-sec sleep, dummy data | TradingAgentsGraph analysis (2-5 min) | (Background) | Real trading insights |
| GET /jobs/{id}/result | Test stub reports | Actual analyst reports | Retrieve result | Actionable trading data |
| Job duration | ~5 seconds | 2-15 minutes (varies by ticker/config) | Poll for completion | Realistic execution time |
| Error scenarios | No errors | LLM rate limits, data fetch failures, timeout | Handle failures | Robust error reporting |

---

## Mandatory Reading

**CRITICAL: Implementation agent MUST read these files before starting any task:**

| Priority | File | Lines | Why Read This |
|----------|------|-------|---------------|
| P0 | `main.py` | 10-28 | How to instantiate TradingAgentsGraph and call propagate() - EXACT pattern to copy |
| P0 | `tradingagents/graph/trading_graph.py` | 46-131, 186-219 | TradingAgentsGraph constructor signature and propagate() return values |
| P0 | `tradingagents/default_config.py` | 3-34 | DEFAULT_CONFIG structure - what config keys exist and their defaults |
| P0 | `tradingagents/agents/utils/agent_states.py` | 50-76 | AgentState structure - what keys exist in final_state returned by propagate() |
| P1 | `trading_api/tasks.py` | 1-110 | Current test stub - exact location to replace with real implementation |
| P1 | `tradingagents/dataflows/alpha_vantage_common.py` | 38-40, 70-78 | AlphaVantageRateLimitError exception - must catch in worker |
| P2 | `cli/main.py` | 899-1168 | How CLI currently executes jobs - understand flow but DON'T mirror (it's sync) |

**External Documentation:**

| Source | Section | Why Needed |
|--------|---------|------------|
| [Celery Error Handling](https://docs.celeryq.dev/en/stable/userguide/tasks.html#retrying) | Retry Logic | How to retry on specific exceptions |
| [Python Exception Handling](https://docs.python.org/3/tutorial/errors.html) | try/except patterns | Catching multiple exception types |

---

## Patterns to Mirror

### TRADINGAGENTS_INVOCATION_PATTERN

```python
# SOURCE: main.py:10-28
# COPY THIS PATTERN in worker task:

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Merge config with defaults
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5-mini"
config["quick_think_llm"] = "gpt-5-mini"
config["max_debate_rounds"] = 1

# Instantiate graph
ta = TradingAgentsGraph(debug=True, config=config)

# Execute propagate - returns tuple
final_state, decision = ta.propagate("NVDA", "2024-05-10")

# Decision is a string: "BUY", "SELL", or "HOLD"
print(decision)
```

**FOR WORKER:** Use debug=False (no trace needed), merge job-specific config with DEFAULT_CONFIG

### STATE_EXTRACTION_PATTERN

```python
# SOURCE: tradingagents/agents/utils/agent_states.py:50-76
# UNDERSTAND THIS STRUCTURE to extract reports:

class AgentState(MessagesState):
    # ... metadata fields
    # Individual analyst reports (extract these):
    market_report: Annotated[str, "Report from the Market Analyst"]
    sentiment_report: Annotated[str, "Report from the Social Media Analyst"]
    news_report: Annotated[str, "Report from the News Researcher"]
    fundamentals_report: Annotated[str, "Report from the Fundamentals Researcher"]
    # ... debate and decision fields
```

**FOR WORKER:** Extract these 4 report fields from final_state dict after propagate()

### EXCEPTION_HANDLING_PATTERN

```python
# SOURCE: tradingagents/dataflows/alpha_vantage_common.py:70-78
# COPY THIS PATTERN for data fetch errors:

from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError

try:
    # ... API call
    pass
except AlphaVantageRateLimitError:
    # Handle rate limit specifically
    continue  # or retry with backoff
```

**FOR WORKER:** Catch AlphaVantageRateLimitError, LLM API errors, and general exceptions

### CONFIG_MERGE_PATTERN

```python
# SOURCE: main.py:10-21
# COPY THIS PATTERN for config merging:

config = DEFAULT_CONFIG.copy()  # Start with defaults
if job_config:  # Job-specific overrides
    config.update(job_config)  # Shallow merge
```

**FOR WORKER:** Always merge, never replace - preserves required config keys

---

## Files to Change

| File | Action | Justification |
|------|--------|---------------|
| `trading_api/tasks.py` | UPDATE | Replace test stub (lines 50-70) with TradingAgentsGraph execution |
| `trading_api/exceptions.py` | UPDATE | Add TradingAgentsExecutionError for graph failures |

---

## NOT Building (Scope Limits)

- ❌ **Config validation** - Phase 5 dependency, accept any dict for now
- ❌ **Timeout enforcement at graph level** - Phase 6 dependency, Celery handles time limits
- ❌ **Result persistence to disk** - Phase 7 dependency, job_store in-memory for now
- ❌ **Retry logic customization** - Use Celery defaults, advanced retry in Phase 6
- ❌ **Analyst selection per job** - Phase 5 dependency, use default analysts for now
- ❌ **LLM provider switching per job** - Phase 5 dependency, use DEFAULT_CONFIG provider
- ❌ **Progress streaming** - Out of scope per PRD, polling-only
- ❌ **Webhook callbacks** - Out of scope per PRD

---

## Step-by-Step Tasks

### Task 1: UPDATE `trading_api/exceptions.py` (add TradingAgents error)

**ACTION**: ADD custom exception for TradingAgentsGraph execution failures

**IMPLEMENT**: Add this class after InvalidJobRequestError (around line 32):

```python
class TradingAgentsExecutionError(APIException):
    """Exception raised when TradingAgentsGraph execution fails."""

    def __init__(self, ticker: str, date: str, error: str):
        super().__init__(
            message=f"TradingAgents analysis failed for {ticker} on {date}: {error}",
            status_code=500
        )
        self.ticker = ticker
        self.date = date
        self.original_error = error
```

**LOCATION**: `trading_api/exceptions.py` after line 31

**MIRROR**: Existing exception pattern at lines 13-31

**RATIONALE**: Specific exception type for graph execution errors enables better error tracking

**VALIDATE**:
```bash
python -c "from trading_api.exceptions import TradingAgentsExecutionError; e = TradingAgentsExecutionError('NVDA', '2026-02-12', 'Test'); print(e.message)"
```

**EXPECT**: Prints error message with ticker and date

---

### Task 2: UPDATE `trading_api/tasks.py` (import dependencies)

**ACTION**: ADD imports for TradingAgentsGraph and error types

**IMPLEMENT**: Add these imports at the top after existing imports (after line 6):

```python
# TradingAgents imports
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError

# API exceptions
from trading_api.exceptions import TradingAgentsExecutionError
```

**LOCATION**: `trading_api/tasks.py` after line 6 (after existing imports)

**GOTCHA**: Import order matters - standard library, third-party, local

**VALIDATE**:
```bash
python -c "from trading_api.tasks import analyze_stock; print('Imports OK')"
```

**EXPECT**: No import errors

---

### Task 3: UPDATE `trading_api/tasks.py` (replace test stub with real execution)

**ACTION**: REPLACE test stub code (lines 50-88) with TradingAgentsGraph execution

**OLD CODE** (lines 50-88):
```python
        # Phase 2: Simulate work with sleep (5 seconds)
        time.sleep(5)

        # Phase 2: Return test stub data
        result = {
            "decision": "HOLD",
            "final_state": {...},
            "reports": {...}
        }
```

**NEW CODE**:
```python
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
```

**LOCATION**: `trading_api/tasks.py` lines 50-88

**MIRROR**:
- TradingAgentsGraph invocation from `main.py:10-28`
- State extraction from `agent_states.py:50-76`
- Config merge from `main.py:10-21`

**RATIONALE**:
- debug=False avoids trace overhead in worker
- Config merge preserves defaults while allowing overrides
- Extract reports from known final_state keys

**GOTCHA**:
- propagate() returns tuple, not dict - must unpack
- final_state keys may be missing if agent failed - use .get() with default ""
- Don't modify DEFAULT_CONFIG directly - always .copy() first

**VALIDATE**: After Task 4 (need exception handling first)

---

### Task 4: UPDATE `trading_api/tasks.py` (add exception handling)

**ACTION**: WRAP TradingAgentsGraph execution in comprehensive try/except

**IMPLEMENT**: Wrap the code from Task 3 in this try/except structure:

```python
        try:
            # Phase 3: Execute actual TradingAgents analysis

            # Merge job-specific config with defaults
            merged_config = DEFAULT_CONFIG.copy()
            if config:
                merged_config.update(config)

            print(f"Task {self.request.id}: Initializing TradingAgentsGraph")
            ta = TradingAgentsGraph(debug=False, config=merged_config)

            print(f"Task {self.request.id}: Starting propagate() for {ticker} on {date}")
            final_state, decision = ta.propagate(ticker, date)

            print(f"Task {self.request.id}: Analysis complete - Decision: {decision}")

            # Extract reports
            reports = {
                "market": final_state.get("market_report", ""),
                "sentiment": final_state.get("sentiment_report", ""),
                "news": final_state.get("news_report", ""),
                "fundamentals": final_state.get("fundamentals_report", ""),
            }

            result = {
                "decision": decision,
                "final_state": final_state,
                "reports": reports,
            }

        except AlphaVantageRateLimitError as exc:
            # Data provider rate limit hit
            error_msg = f"Alpha Vantage rate limit exceeded: {str(exc)}"
            print(f"Task {self.request.id}: {error_msg}")
            store.update_job_status(job_id, JobStatus.FAILED, error_msg)
            raise TradingAgentsExecutionError(ticker, date, error_msg)

        except KeyError as exc:
            # Missing required data in response
            error_msg = f"Missing required data: {str(exc)}"
            print(f"Task {self.request.id}: {error_msg}")
            store.update_job_status(job_id, JobStatus.FAILED, error_msg)
            raise TradingAgentsExecutionError(ticker, date, error_msg)

        except Exception as exc:
            # Any other error (LLM API, network, graph execution)
            error_msg = f"{type(exc).__name__}: {str(exc)}"
            print(f"Task {self.request.id}: Unexpected error - {error_msg}")
            store.update_job_status(job_id, JobStatus.FAILED, error_msg)
            raise TradingAgentsExecutionError(ticker, date, error_msg)
```

**LOCATION**: `trading_api/tasks.py` lines 50-110 (entire try/except replaces old code)

**MIRROR**: Exception handling pattern from `alpha_vantage_common.py:70-78`

**RATIONALE**:
- Specific exception types enable targeted retry logic (Phase 6)
- AlphaVantageRateLimitError is retryable, KeyError is not
- Log before raising so worker logs show error context
- Update job_store status before raising so API shows failure

**GOTCHA**:
- Must call store.update_job_status() inside each except block BEFORE raising
- Re-raise or raise new exception so Celery marks task as failed
- Generic Exception last (catch-all after specific types)

**VALIDATE**:
```bash
# With Redis and API running, submit a job with invalid ticker
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "INVALID", "date": "2026-02-12"}'

# Worker should log error, job status should be FAILED
```

---

## Testing Strategy

### Manual Testing Checklist

**Prerequisites**:
- Redis running
- API server running (`./run_api.sh`)
- Worker running (`./run_worker.sh`)
- Valid LLM API keys in .env (OPENAI_API_KEY or configured provider)

**Test 1: Submit Real Analysis Job**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2024-05-10"}'

# Save job_id from response
JOB_ID="<paste-job-id>"
```
**Expected**:
- API returns 202 immediately
- Worker logs: "Initializing TradingAgentsGraph"
- Worker logs: "Starting propagate() for NVDA"
- Takes 2-15 minutes (real analysis time)

**Test 2: Poll Status During Execution**
```bash
# Poll every 30 seconds
watch -n 30 "curl -s http://localhost:8000/jobs/$JOB_ID | jq"
```
**Expected**:
- status: "running" (with started_at timestamp)
- After completion: status: "completed" (with completed_at timestamp)

**Test 3: Retrieve Real Results**
```bash
curl -s http://localhost:8000/jobs/$JOB_ID/result | jq
```
**Expected** (verify REAL data, not "[TEST STUB]"):
```json
{
  "decision": "BUY" | "SELL" | "HOLD",
  "reports": {
    "market": "Technical analysis shows MACD golden cross at...",
    "sentiment": "Social sentiment score: 0.72 (bullish)...",
    "news": "Recent announcements include...",
    "fundamentals": "P/E ratio: 45.2, Revenue growth: 24%..."
  },
  "final_state": {
    "company_of_interest": "NVDA",
    "market_report": "...",
    ...full state dict...
  }
}
```

**Test 4: Config Override**
```bash
# Submit with custom config
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AAPL",
    "date": "2024-05-10",
    "config": {
      "max_debate_rounds": 2,
      "llm_provider": "openai",
      "deep_think_llm": "gpt-4"
    }
  }'
```
**Expected**:
- Worker logs show: "Initializing TradingAgentsGraph with config: openai/gpt-4"
- Analysis uses specified LLM model
- More debate rounds (longer execution)

**Test 5: Invalid Ticker (Error Handling)**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NOTREAL", "date": "2024-05-10"}'
```
**Expected**:
- Worker attempts analysis
- Fails during data fetch
- Status becomes "failed" with error message
- GET /jobs/{id} shows: `{"error": "Missing required data: ..."}`

**Test 6: Rate Limit Handling (if using Alpha Vantage)**
```bash
# Submit 10 jobs rapidly
for i in {1..10}; do
  curl -X POST http://localhost:8000/jobs \
    -H "Content-Type: application/json" \
    -d "{\"ticker\": \"STOCK$i\", \"date\": \"2024-05-10\"}" &
done
wait
```
**Expected**:
- First few jobs succeed
- Later jobs may hit Alpha Vantage rate limit (5 calls/min)
- Jobs with rate limit show: `{"error": "Alpha Vantage rate limit exceeded: ..."}`
- Jobs remain in queue, can be retried later

### Edge Cases Checklist

- [ ] Valid ticker with recent date (should have data)
- [ ] Valid ticker with old date (2020 or earlier)
- [ ] Invalid ticker (data fetch should fail gracefully)
- [ ] Weekend date (market closed - should still work with last available data)
- [ ] Future date (no data available yet - should fail with clear error)
- [ ] Config override with invalid LLM model (should fail during graph init)
- [ ] Config override with all valid options (should work)
- [ ] Multiple concurrent jobs for same ticker (should each get fresh data)
- [ ] Job exceeding 30-minute timeout (Celery should terminate, Phase 6 enhances this)

---

## Validation Commands

### Level 1: IMPORTS_CHECK

```bash
# Verify all imports work
python -c "
from trading_api.tasks import analyze_stock
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError
from trading_api.exceptions import TradingAgentsExecutionError
print('All imports successful')
"
```

**EXPECT**: Prints "All imports successful"

---

### Level 2: UNIT_TEST

```bash
# Test config merge logic
python -c "
from tradingagents.default_config import DEFAULT_CONFIG

# Simulate job config override
job_config = {'max_debate_rounds': 2, 'llm_provider': 'anthropic'}

merged = DEFAULT_CONFIG.copy()
merged.update(job_config)

assert merged['max_debate_rounds'] == 2
assert merged['llm_provider'] == 'anthropic'
assert 'data_cache_dir' in merged  # Preserved from defaults
print('Config merge works correctly')
"
```

**EXPECT**: Prints "Config merge works correctly"

---

### Level 3: INTEGRATION_TEST

```bash
# Full end-to-end test with real TradingAgentsGraph
# Requires: Redis, API, Worker all running

# Submit job
JOB_RESPONSE=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2024-05-10"}')

JOB_ID=$(echo $JOB_RESPONSE | python -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo "Job ID: $JOB_ID"

# Wait for completion (real analysis takes 2-15 min)
echo "Waiting for analysis to complete (this may take several minutes)..."
for i in {1..60}; do
    STATUS=$(curl -s http://localhost:8000/jobs/$JOB_ID | python -c "import sys, json; print(json.load(sys.stdin)['status'])")
    echo "Attempt $i: Status = $STATUS"

    if [ "$STATUS" = "completed" ]; then
        echo "✅ Job completed successfully"

        # Verify result has real data (not test stub)
        RESULT=$(curl -s http://localhost:8000/jobs/$JOB_ID/result)
        if echo "$RESULT" | grep -q "TEST STUB"; then
            echo "❌ FAILED: Result contains test stub data"
            exit 1
        fi

        echo "✅ Result contains real analysis data"
        exit 0
    elif [ "$STATUS" = "failed" ]; then
        echo "❌ Job failed"
        curl -s http://localhost:8000/jobs/$JOB_ID | jq '.error'
        exit 1
    fi

    sleep 30  # Poll every 30 seconds
done

echo "❌ Timeout waiting for job completion"
exit 1
```

**EXPECT**: Job completes, result has real data (no "TEST STUB" strings)

---

## Acceptance Criteria

- [ ] TradingAgentsGraph successfully instantiates in worker
- [ ] propagate() executes and returns (final_state, decision) tuple
- [ ] Worker extracts all 4 analyst reports from final_state
- [ ] Decision is real ("BUY"/"SELL"/"HOLD" from LLM, not "HOLD" stub)
- [ ] Reports contain actual analysis text (not "[TEST STUB]")
- [ ] Config override (if provided) merges with DEFAULT_CONFIG
- [ ] AlphaVantageRateLimitError caught and job marked FAILED
- [ ] Generic exceptions caught and job marked FAILED with error message
- [ ] Worker logs show TradingAgentsGraph initialization and propagate start/complete
- [ ] Analysis duration is realistic (2-15 minutes, not 5 seconds)
- [ ] Multiple jobs can run concurrently (each gets own TradingAgentsGraph instance)
- [ ] Job results persist in job_store after completion
- [ ] GET /jobs/{id}/result returns real analyst reports
- [ ] Invalid ticker fails gracefully with clear error message
- [ ] Valid API keys required (job fails if missing/invalid)

---

## Completion Checklist

- [ ] Task 1: exceptions.py updated with TradingAgentsExecutionError
- [ ] Task 2: tasks.py imports added for TradingAgentsGraph
- [ ] Task 3: Test stub replaced with real TradingAgentsGraph execution
- [ ] Task 4: Exception handling wraps execution with specific error types
- [ ] All validation commands pass (Level 1-3)
- [ ] All acceptance criteria met
- [ ] Manual testing checklist completed
- [ ] Real analysis results verified (no test stub data)
- [ ] Error scenarios tested (invalid ticker, rate limits)

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| LLM API rate limits during testing | High | Medium | Use rate limit error handling, retry in Phase 6 |
| Long execution time (>30 min) causes timeout | Low | Medium | Celery time_limit enforces 30-min max, proper in Phase 6 |
| Missing API keys cause worker crashes | Medium | High | Catch exceptions, return clear error messages |
| Data vendor failures (yfinance, Alpha Vantage down) | Medium | High | Catch AlphaVantageRateLimitError and network errors |
| Memory leak from repeated graph instantiation | Medium | Medium | Worker max_tasks_per_child=50 (Phase 2 config) restarts workers |
| Invalid config crashes TradingAgentsGraph | Low | Medium | Phase 5 adds validation, for now catch generic Exception |
| final_state missing expected keys | Low | Medium | Use .get() with default "" when extracting reports |
| Worker OOM from large graph state | Low | High | Monitor worker memory, adjust concurrency if needed |

---

## Notes

**Design Decisions:**

1. **debug=False for worker**: Production mode disables trace overhead that's only useful for interactive debugging.

2. **Config merge with .copy()**: Prevents modifying DEFAULT_CONFIG globally, ensures each job gets isolated config.

3. **Specific exception handling**: AlphaVantageRateLimitError vs generic Exception enables retry logic in Phase 6.

4. **Extract reports from final_state**: TradingAgentsGraph doesn't separate reports in return value, must extract from state dict.

5. **Log before raise**: Worker logs provide debugging context even if exception propagates to Celery.

6. **No config validation**: Phase 5 adds validation, Phase 3 passes through any config dict.

**Integration Notes:**

- TradingAgentsGraph instantiation is expensive (initializes LLMs, memories, tools) - one per task execution
- propagate() execution time varies: 2-5 min typical, up to 15 min for complex analysis
- final_state contains ~10-20 keys, most are strings or dicts from AgentState
- decision is always a string, processed from final_trade_decision by process_signal()
- Graph creates directories if they don't exist (data_cache_dir, results_dir)

**Common Errors and Fixes:**

| Error | Cause | Fix |
|-------|-------|-----|
| "No module named 'tradingagents'" | Worker in wrong venv | Activate same venv as API |
| "OPENAI_API_KEY not found" | Missing .env file | Copy .env.example to .env, add keys |
| "AlphaVantageRateLimitError" | Hit 5 calls/min limit | Wait 1 minute, or switch to yfinance in config |
| "Timeout error" | Job exceeds 30 minutes | Phase 6 handles gracefully, for now just fails |
| KeyError on final_state["market_report"] | Analyst failed silently | Use .get("market_report", "") instead |

**Performance Expectations:**

- Simple ticker (AAPL, NVDA): 2-5 minutes
- Complex ticker (many news articles): 5-10 minutes
- High debate rounds (>3): 10-15 minutes
- Worker concurrency=2: Can process 2 jobs simultaneously
- Memory per worker: ~500MB-1GB (depends on LLM client)
