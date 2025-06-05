# multi_agent_system/utils/helpers.py

import asyncio
from typing import Callable, Any
from functools import wraps
from loguru import logger

def async_run_blocking(func: Callable) -> Callable:
    """
    Decorator to run a synchronous function in a separate thread,
    making it non-blocking for asyncio event loop.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)
    return wrapper

def load_yaml_config(filepath: str) -> dict:
    """Loads a YAML configuration file."""
    import yaml
    try:
        with open(filepath, 'r') as f:
            config = yaml.safe_load(f)
        logger.info(f"Loaded YAML config from: {filepath}")
        return config
    except FileNotFoundError:
        logger.error(f"Config file not found: {filepath}")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file {filepath}: {e}")
        raise

# Extend settings to load agent configs more easily
from config.settings import Settings
Settings.load_agent_config = load_yaml_config # Monkey patch for easy access in agents