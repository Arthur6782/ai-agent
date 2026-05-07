"""
utils/retry.py
==============
Exponential-backoff retry decorator for any callable.

Usage
-----
    from utils.retry import retry_on_failure
    import requests

    @retry_on_failure(max_retries=3, delay=1.5, exceptions=(requests.RequestException,))
    def fetch_data(url: str) -> dict:
        ...

Parameters
----------
max_retries   – how many times to retry after the first failure
               (total attempts = max_retries + 1)
delay         – initial wait before the first retry (seconds)
backoff       – multiplier applied on each subsequent wait
               (default 2.0 → delays: delay, delay*2, delay*4 …)
exceptions    – tuple of exception types that trigger a retry;
               all others propagate immediately
"""

import logging
import time
import functools
import inspect
from typing import Callable, Type, TypeVar

F = TypeVar("F", bound=Callable)

logger = logging.getLogger(__name__)


def retry_on_failure(
    max_retries: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """
    Decorator factory: wrap a function with exponential-backoff retry logic.

    Only the listed `exceptions` are caught.  Any other exception type
    propagates immediately without retrying.
    """
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")
    if delay < 0:
        raise ValueError("delay must be >= 0")

    def decorator(func: F) -> F:
        _log = logging.getLogger(func.__module__ or __name__)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc: BaseException | None = None
            total_attempts = max_retries + 1

            for attempt in range(total_attempts):
                try:
                    return func(*args, **kwargs)

                except exceptions as exc:
                    last_exc = exc
                    is_last = attempt == max_retries

                    if is_last:
                        _log.error(
                            "[retry] %s — all %d attempt(s) failed. "
                            "Last error: %s: %s",
                            func.__qualname__,
                            total_attempts,
                            type(exc).__name__,
                            exc,
                        )
                    else:
                        wait = delay * (backoff ** attempt)
                        _log.warning(
                            "[retry] %s — attempt %d/%d failed (%s: %s). "
                            "Retrying in %.2fs…",
                            func.__qualname__,
                            attempt + 1,
                            total_attempts,
                            type(exc).__name__,
                            exc,
                            wait,
                        )
                        time.sleep(wait)

            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
