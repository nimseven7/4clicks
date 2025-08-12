"""Utility functions for handling exceptions in API routes."""

import logging
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

from fastapi import HTTPException

from app.exceptions.exceptions import AppException

logger = logging.getLogger(__name__)

T = TypeVar("T")


def handle_service_exceptions(
    func: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T]]:
    """
    Decorator to handle service exceptions and convert them to HTTP exceptions.

    This decorator should be used on router endpoint functions to automatically
    convert application exceptions to appropriate HTTP responses.
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return await func(*args, **kwargs)
        except AppException as e:
            logger.warning(f"Application exception in {func.__name__}: {e.message}")
            raise HTTPException(status_code=e.status_code, detail=e.message)
        except HTTPException:
            # Re-raise HTTPExceptions as they are already properly formatted
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True
            )
            raise HTTPException(
                status_code=500, detail=f"Internal server error: {str(e)}"
            )

    return wrapper


async def execute_with_error_handling(
    operation: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any
) -> T:
    """
    Execute an operation with proper error handling.

    This function can be used directly in router endpoints for more fine-grained control.
    """
    try:
        return await operation(*args, **kwargs)
    except AppException as e:
        logger.warning(f"Application exception: {e.message}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
