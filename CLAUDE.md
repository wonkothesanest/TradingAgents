# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TradingAgents is a multi-agent LLM financial trading framework built with LangGraph. It simulates a trading firm with specialized agents (analysts, researchers, traders, risk management) that collaborate to make trading decisions.

## Development Commands

### Setup
```bash
# Create virtual environment
conda create -n tradingagents python=3.13
conda activate tradingagents

# Install dependencies
pip install -r requirements.txt

# Or install in editable mode for development
pip install -e .

# Copy environment variables template
cp .env.example .env
# Then fill in your API keys in .env
```

### Running the System

**CLI Interface:**
```bash
# Interactive CLI with prompts for ticker, date, LLM selection, etc.
python -m cli.main

# Or using installed script
tradingagents
```

**Python API:**
```bash
# Run the example script
python main.py
```

**Basic Python Usage:**
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"  # or google, anthropic, xai, openrouter, ollama
config["deep_think_llm"] = "gpt-5.2"
config["quick_think_llm"] = "gpt-5-mini"

ta = TradingAgentsGraph(debug=True, config=config)
state, decision = ta.propagate("NVDA", "2026-01-15")
```

## Architecture

### Core Components

**1. TradingAgentsGraph** (`tradingagents/graph/trading_graph.py`)
   - Main orchestrator that initializes and coordinates all agents
   - Built on LangGraph for flexible agent workflow management
   - Methods:
     - `propagate(ticker, date)` - Run full trading decision workflow
     - `reflect_and_remember(returns)` - Learn from past decisions

**2. Agent Teams** (`tradingagents/agents/`)
   - **Analysts** (`analysts/`) - Specialized analysis agents:
     - Market/Technical Analyst - Charts, indicators (MACD, RSI)
     - Sentiment Analyst - Social media sentiment
     - News Analyst - Global news and macro events
     - Fundamentals Analyst - Company financials
   - **Researchers** (`researchers/`) - Debate agents:
     - Bull Researcher - Argues for buying
     - Bear Researcher - Argues for selling
     - Engage in structured debates to evaluate risk/reward
   - **Trader** (`trader/`) - Makes final trade decisions based on all inputs
   - **Risk Management** (`risk_mgmt/`) - Evaluates portfolio risk
   - **Portfolio Manager** (`managers/`) - Approves/rejects trades

**3. LLM Clients** (`tradingagents/llm_clients/`)
   - Multi-provider architecture with unified interface
   - Supported providers: OpenAI, Google (Gemini), Anthropic (Claude), xAI (Grok), OpenRouter, Ollama
   - Factory pattern: `create_llm_client(provider, model, **kwargs)`
   - Each provider has specific thinking/reasoning configurations

**4. Data Flows** (`tradingagents/dataflows/`)
   - Data fetching and caching layer
   - Supports multiple data vendors: Alpha Vantage, yfinance
   - Tools for stock data, indicators, fundamentals, news, etc.
   - Configurable via `data_vendors` config key

**5. Graph Modules** (`tradingagents/graph/`)
   - `setup.py` - Graph initialization and node construction
   - `conditional_logic.py` - Routing logic between agents
   - `propagation.py` - Main execution flow
   - `reflection.py` - Learning from past decisions
   - `signal_processing.py` - Result parsing and formatting

### Agent Workflow

```
Input (ticker, date)
  → Analysts run in parallel (market, sentiment, news, fundamentals)
  → Researchers debate (bull vs bear, multiple rounds)
  → Trader synthesizes information
  → Risk Management evaluates
  → Portfolio Manager approves/rejects
  → Output (trading decision)
```

### State Management

The system uses LangGraph state management with typed state classes:
- `AgentState` - Main state shared across all agents
- `InvestDebateState` - State for researcher debate rounds
- `RiskDebateState` - State for risk management discussions

Memory systems track past decisions:
- `bull_memory`, `bear_memory`, `trader_memory` - Agent-specific memories
- Memories persist across runs to improve future decisions

## Configuration

All configuration is in `tradingagents/default_config.py`:

**LLM Settings:**
- `llm_provider` - Provider name (openai, google, anthropic, xai, openrouter, ollama)
- `deep_think_llm` - Model for complex reasoning tasks
- `quick_think_llm` - Model for quick/simple tasks
- `backend_url` - Optional custom API endpoint
- Provider-specific thinking configs (e.g., `google_thinking_level`, `openai_reasoning_effort`)

**Debate Settings:**
- `max_debate_rounds` - Rounds of bull/bear debate (default: 1)
- `max_risk_discuss_rounds` - Rounds of risk discussion (default: 1)

**Data Vendor Settings:**
- `data_vendors` - Category-level vendor selection
- `tool_vendors` - Tool-level vendor overrides

**Directory Settings:**
- `project_dir` - Project root
- `results_dir` - Where to save results (default: ./results)
- `data_cache_dir` - Data cache location

## Environment Variables

Required API keys (set in `.env` or environment):
```bash
# LLM Providers (set the one you use)
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
ANTHROPIC_API_KEY=...
XAI_API_KEY=...
OPENROUTER_API_KEY=...

# Data Provider (optional, yfinance works without keys)
ALPHA_VANTAGE_API_KEY=...

# Results Directory (optional)
TRADINGAGENTS_RESULTS_DIR=./results
```

## Key Design Patterns

### Multi-Provider LLM Support
The system uses a factory pattern with provider-specific clients that all implement `BaseLLMClient`. This allows seamless switching between providers by changing config.

### LangGraph Integration
Agents are implemented as LangGraph nodes with:
- Tool binding for data access
- State management for information flow
- Conditional routing between agents
- Checkpointing for memory persistence

### Agent Specialization
Each agent has a specific role and prompt template optimized for that role. Agents collaborate through structured state passing rather than direct communication.

### Debate-Driven Decision Making
Multiple rounds of structured debate between opposing viewpoints (bull/bear) ensure balanced analysis before decisions.

## Important Files

- `main.py` - Simple example of Python API usage
- `cli/main.py` - Interactive CLI interface (48KB, handles all CLI logic)
- `tradingagents/graph/trading_graph.py` - Main graph orchestrator
- `tradingagents/default_config.py` - Configuration defaults
- `tradingagents/agents/utils/agent_utils.py` - Shared agent utilities and tools
- `tradingagents/llm_clients/factory.py` - LLM client factory

## CLI Features

The CLI (`python -m cli.main`) provides:
- Interactive prompts for ticker selection, date, LLM choice
- Real-time progress display as agents work
- Visualization of analyst reports, debates, and final decisions
- Results saved to configured results directory

## Notes for Development

### Adding New Agents
1. Create agent module in appropriate subdirectory under `tradingagents/agents/`
2. Define agent function that takes state and returns updated state
3. Add agent to graph in `tradingagents/graph/setup.py`
4. Update conditional logic in `conditional_logic.py` if needed

### Adding New LLM Providers
1. Create provider client in `tradingagents/llm_clients/` inheriting from `BaseLLMClient`
2. Add provider to factory in `factory.py`
3. Add provider-specific config options to `default_config.py`
4. Update validators in `validators.py`

### Data Vendor Configuration
The system uses a two-tier configuration:
- Category-level: Set default vendor for tool categories (e.g., all fundamental data)
- Tool-level: Override specific tools to use different vendors

This is abstracted through tool functions in `agent_utils.py` that route to the correct vendor implementation.

### Memory and Learning
Agents can reflect on past decisions using `reflect_and_remember(returns)`. This stores experiences in agent-specific memories and adjusts future behavior. Memory is persisted in the data cache directory.
