"""Celery application for TradingAgents background task processing."""

import os
from celery import Celery
from typing import Optional

from tradingagents.default_config import DEFAULT_CONFIG


def create_celery_app() -> Celery:
    """Create and configure Celery application.

    Reads configuration from tradingagents.default_config.DEFAULT_CONFIG,
    which supports environment variable overrides via os.getenv().

    Returns:
        Configured Celery application instance
    """
    celery_app = Celery(
        "tradingagents",
        broker=DEFAULT_CONFIG["celery_broker_url"],
        backend=DEFAULT_CONFIG["celery_result_backend"],
    )

    # Configure Celery from default_config
    celery_app.conf.update(
        task_serializer=DEFAULT_CONFIG["celery_task_serializer"],
        result_serializer=DEFAULT_CONFIG["celery_result_serializer"],
        accept_content=DEFAULT_CONFIG["celery_accept_content"],
        task_time_limit=DEFAULT_CONFIG["celery_task_time_limit"],
        task_soft_time_limit=DEFAULT_CONFIG["celery_task_soft_time_limit"],
        worker_prefetch_multiplier=DEFAULT_CONFIG["celery_worker_prefetch_multiplier"],
        result_expires=DEFAULT_CONFIG["celery_result_expires"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        broker_connection_retry_on_startup=True,
    )

    # Broker transport options for Redis
    celery_app.conf.broker_transport_options = {
        "visibility_timeout": 3600,  # 1 hour
        "socket_keepalive": True,
        "socket_timeout": 10.0,
    }

    return celery_app


# Global Celery app instance (singleton pattern)
_celery_app: Optional[Celery] = None


def get_celery_app() -> Celery:
    """Get the global Celery app instance.

    Returns:
        Celery application instance
    """
    global _celery_app
    if _celery_app is None:
        _celery_app = create_celery_app()
    return _celery_app


# Create app instance for worker discovery
celery_app = get_celery_app()

# Import tasks to ensure they're registered with Celery
# This must happen after celery_app is created to avoid circular imports
import trading_api.tasks  # noqa: F401
