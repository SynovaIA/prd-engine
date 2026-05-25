from typing import Callable, TypeVar, Any
from functools import wraps
import asyncio
from prd_engine.core.config import get_settings
from prd_engine.observability.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

T = TypeVar("T")


def with_retry(
    max_retries: int = None,
    backoff_base: float = None,
    exceptions: tuple = (Exception,),
):
    """
    Decorator for adding retry logic to async functions.
    
    Implements exponential backoff with configurable parameters.
    
    Args:
        max_retries: Maximum number of retry attempts (default from settings)
        backoff_base: Base for exponential backoff in seconds (default from settings)
        exceptions: Tuple of exception types to catch and retry
    
    Example:
        @with_retry(max_retries=3, backoff_base=2.0)
        async def fetch_data():
            ...
    """
    max_retries = max_retries or settings.max_retries
    backoff_base = backoff_base or settings.retry_backoff_base

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            "retry_exhausted",
                            function=func.__name__,
                            attempts=max_retries + 1,
                            error=str(e),
                        )
                        raise

                    wait_time = backoff_base**attempt
                    logger.warning(
                        "retry_attempt",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_seconds=wait_time,
                        error=str(e),
                    )

                    await asyncio.sleep(wait_time)

            raise last_exception

        return wrapper

    return decorator


class RetryHandler:
    """Programmatic retry handler for workflow operations."""

    def __init__(
        self,
        max_retries: int = None,
        backoff_base: float = None,
    ):
        self.max_retries = max_retries or settings.max_retries
        self.backoff_base = backoff_base or settings.retry_backoff_base

    async def execute_with_retry(
        self,
        func: Callable[..., Any],
        *args: Any,
        exceptions: tuple = (Exception,),
        **kwargs: Any,
    ) -> Any:
        """Execute a function with retry logic."""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except exceptions as e:
                last_exception = e

                if attempt == self.max_retries:
                    logger.error(
                        "retry_handler_exhausted",
                        function=func.__name__,
                        attempts=self.max_retries + 1,
                        error=str(e),
                    )
                    raise

                wait_time = self.backoff_base**attempt
                logger.warning(
                    "retry_handler_attempt",
                    function=func.__name__,
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    wait_seconds=wait_time,
                    error=str(e),
                )

                await asyncio.sleep(wait_time)

        raise last_exception
