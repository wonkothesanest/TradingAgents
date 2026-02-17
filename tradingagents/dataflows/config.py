import tradingagents.default_config as default_config
from typing import Dict, Optional
import threading

# Thread-local storage for config to prevent corruption in Celery forked workers
# Each worker process/thread maintains its own isolated config
_thread_local = threading.local()


def initialize_config():
    """Initialize the configuration with default values.

    Uses thread-local storage to ensure each Celery worker has isolated config.
    This prevents the global state corruption that occurs when workers fork.
    """
    if not hasattr(_thread_local, 'config') or _thread_local.config is None:
        _thread_local.config = default_config.DEFAULT_CONFIG.copy()


def set_config(config: Dict):
    """Update the configuration with custom values.

    Args:
        config: Dictionary of configuration overrides
    """
    # Ensure thread-local config is initialized
    if not hasattr(_thread_local, 'config') or _thread_local.config is None:
        initialize_config()

    if config is None or not isinstance(config, dict):
        print(f"WARNING: set_config() called with invalid config: {type(config)}")
        return

    # Update the thread-local config
    _thread_local.config.update(config)


def get_config() -> Dict:
    """Get the current configuration.

    Returns:
        Dictionary containing current configuration
    """
    # Ensure thread-local config is initialized
    if not hasattr(_thread_local, 'config') or _thread_local.config is None:
        initialize_config()

    # Return a copy to prevent external modifications
    return _thread_local.config.copy()


# Initialize config when module is first imported
initialize_config()
