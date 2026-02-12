# Feature: Per-Job Configuration System

## Summary

Implementing per-job configuration override system that allows N8N workflows to customize LLM models, debate rounds, analyst selection, and other TradingAgentsGraph parameters via the POST /jobs config field. Phase 2-3 accept config dict but don't validate or document it. Phase 5 adds config validation using Pydantic schemas, merges job config with DEFAULT_CONFIG safely, makes Ollama URL environment-configurable (fixes hardcoded localhost), documents all supported config options in OpenAPI schema, and validates config before job submission to fail fast with clear error messages.

## User Story

As a N8N workflow developer
I want to customize TradingAgents analysis parameters per job
So that I can use different LLM models, debate depths, and analyst combinations for different trading strategies

## Metadata

| Field            | Value                                             |
|------------------|---------------------------------------------------|
| Type             | ENHANCEMENT                                       |
| Complexity       | MEDIUM                                            |
| Systems Affected | trading_api/models.py, tasks.py, default_config   |
| Dependencies     | Phase 3 complete (TradingAgentsGraph integrated)  |
| Estimated Tasks  | 5                                                 |
| PRD Phase        | Phase 5: Configuration System                     |

## Files to Change

| File | Action | Justification |
|------|--------|---------------|
| `trading_api/models.py` | UPDATE | Add JobConfigSchema Pydantic model for validation |
| `trading_api/main.py` | UPDATE | Validate config before job creation |
| `tradingagents/default_config.py` | UPDATE | Make Ollama URL env-configurable |
| `tradingagents/llm_clients/ollama_client.py` | UPDATE | Use backend_url from config instead of hardcoded localhost |
| `.env.example` | UPDATE | Document OLLAMA_BASE_URL variable |

## Tasks

### Task 1: CREATE JobConfigSchema Pydantic model

Add to `trading_api/models.py`:

```python
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
```

Update JobRequest to use validated schema:

```python
class JobRequest(BaseModel):
    ticker: str = Field(...)
    date: str = Field(...)
    config: Optional[JobConfigSchema] = None  # Changed from Dict[str, Any]
```

### Task 2: ADD config validation in API endpoint

Update `trading_api/main.py` POST /jobs:

```python
@app.post("/jobs", ...)
async def create_job(request: JobRequest) -> JobResponse:
    store = get_job_store()
    
    # Pydantic already validated config schema
    # Convert to dict for storage
    config_dict = request.config.model_dump() if request.config else None
    
    job_id = store.create_job(
        ticker=request.ticker,
        date=request.date,
        config=config_dict,
    )
    
    # Dispatch with validated config
    task = analyze_stock.delay(job_id, request.ticker, request.date, config_dict)
    
    # ... rest of endpoint
```

### Task 3: UPDATE default_config.py for Ollama URL

Change:
```python
"backend_url": "https://api.openai.com/v1",
```

To:
```python
"backend_url": os.getenv("BACKEND_URL", "https://api.openai.com/v1"),
"ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
```

### Task 4: FIX Ollama client hardcoded localhost

In `tradingagents/llm_clients/ollama_client.py`, change:

```python
# OLD:
llm_kwargs["base_url"] = "http://localhost:11434"

# NEW:
ollama_url = self.kwargs.get("ollama_base_url") or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
llm_kwargs["base_url"] = ollama_url
```

### Task 5: DOCUMENT configuration options

Add to `.env.example`:

```bash
# TradingAgents Configuration
OLLAMA_BASE_URL=http://ollama:11434
BACKEND_URL=https://api.openai.com/v1

# Per-Job Config Options (via API POST /jobs):
# - llm_provider: openai|anthropic|google|xai|ollama|openrouter
# - deep_think_llm: model name for complex reasoning
# - quick_think_llm: model name for quick tasks
# - max_debate_rounds: 1-5 (default: 1)
# - selected_analysts: ["market", "social", "news", "fundamentals"]
```

## Testing

**Test 1: Valid config override**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "NVDA",
    "date": "2024-05-10",
    "config": {
      "llm_provider": "openai",
      "deep_think_llm": "gpt-4",
      "max_debate_rounds": 2
    }
  }'
```
Expected: 202 Accepted, config validated

**Test 2: Invalid config (fails validation)**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "NVDA",
    "date": "2024-05-10",
    "config": {
      "llm_provider": "invalid_provider",
      "max_debate_rounds": 10
    }
  }'
```
Expected: 422 Validation Error with details

**Test 3: Ollama URL override in Docker**
```bash
docker-compose up
# Ollama should resolve to ollama:11434 (not localhost)
```

## Acceptance Criteria

- [ ] JobConfigSchema validates all config options
- [ ] Invalid config returns 422 with clear error message
- [ ] Valid config overrides merge with DEFAULT_CONFIG
- [ ] Ollama URL configurable via OLLAMA_BASE_URL env var
- [ ] OpenAPI docs show config schema with examples
- [ ] Docker Compose uses ollama:11434 (not localhost)
- [ ] Local development still works with localhost
- [ ] Config validation happens before job creation
- [ ] All supported options documented in .env.example

