# multi_agent_system/utils/validators.py

from typing import Any, Dict, List
from pydantic import ValidationError
from loguru import logger

def validate_dict_with_pydantic_model(data: Dict[str, Any], model: Any) -> Any:
    """
    Validates a dictionary against a Pydantic model.
    Returns the validated model instance or raises a ValidationError.
    """
    try:
        return model(**data)
    except ValidationError as e:
        logger.error(f"Validation error for data against model {model.__name__}: {e}")
        raise
    except TypeError as e:
        logger.error(f"Type error during validation for data against model {model.__name__}: {e}")
        raise

def is_valid_url(url: str) -> bool:
    """Basic URL validation."""
    from urllib.parse import urlparse
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False