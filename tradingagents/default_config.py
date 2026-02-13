import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.2",
    "quick_think_llm": "gpt-5-mini",
    "backend_url": os.getenv("BACKEND_URL", "https://api.openai.com/v1"),
    "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
    # Celery Configuration
    "celery_broker_url": os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    "celery_result_backend": os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    "celery_task_serializer": "json",
    "celery_result_serializer": "json",
    "celery_accept_content": ["json"],
    "celery_task_time_limit": 1800,  # 30 minutes hard limit
    "celery_task_soft_time_limit": 1500,  # 25 minutes soft limit
    "celery_worker_prefetch_multiplier": 1,
    "celery_result_expires": 3600,  # 1 hour
}
