"""Retry utilities with exponential backoff for robust operation handling"""

import functools
import logging
import random
import time
from typing import Any, Callable, Optional, Tuple, Type, Union

logger = logging.getLogger(__name__)


class RetryError(Exception):
    """Exception raised when all retry attempts fail"""
    def __init__(self, message: str, last_exception: Optional[Exception] = None, attempts: int = 0):
        self.message = message
        self.last_exception = last_exception
        self.attempts = attempts
        super().__init__(message)


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int, float], None]] = None
) -> Callable:
    """Decorator for retrying functions with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay between retries in seconds (default: 60.0)
        exponential_base: Base for exponential calculation (default: 2.0)
        jitter: Add random jitter to prevent thundering herd (default: True)
        exceptions: Tuple of exceptions to catch and retry (default: all Exceptions)
        on_retry: Optional callback function(exception, attempt, delay) called before each retry
    
    Returns:
        Decorated function with retry logic
    
    Example:
        @retry_with_backoff(max_retries=3, exceptions=(requests.RequestException,))
        def fetch_data(url):
            return requests.get(url)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"{func.__name__} failed after {max_retries + 1} attempts: {e}")
                        raise RetryError(
                            f"Operation {func.__name__} failed after {max_retries + 1} attempts",
                            last_exception=e,
                            attempts=max_retries + 1
                        ) from e
                    
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    
                    # Add jitter (±25% of delay)
                    if jitter:
                        delay = delay * (0.75 + random.random() * 0.5)
                    
                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    
                    if on_retry:
                        on_retry(e, attempt + 1, delay)
                    
                    time.sleep(delay)
            
            # Should not reach here, but just in case
            raise RetryError(
                f"Operation {func.__name__} failed after {max_retries + 1} attempts",
                last_exception=last_exception,
                attempts=max_retries + 1
            )
        
        return wrapper
    return decorator


class RetryContext:
    """Context manager for retrying operations with backoff
    
    Example:
        with RetryContext(max_retries=3) as retry:
            for attempt in retry:
                try:
                    result = make_api_call()
                    break
                except RequestException as e:
                    retry.record_failure(e)
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.attempt = 0
        self.last_exception: Optional[Exception] = None
        self._should_retry = True
    
    def __enter__(self) -> 'RetryContext':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False
    
    def __iter__(self):
        return self
    
    def __next__(self) -> int:
        if not self._should_retry:
            raise StopIteration
        
        if self.attempt > self.max_retries:
            if self.last_exception:
                raise RetryError(
                    f"Operation failed after {self.attempt} attempts",
                    last_exception=self.last_exception,
                    attempts=self.attempt
                )
            raise StopIteration
        
        current_attempt = self.attempt
        self.attempt += 1
        return current_attempt
    
    def record_failure(self, exception: Exception):
        """Record a failed attempt and wait before next retry"""
        self.last_exception = exception
        
        if self.attempt > self.max_retries:
            raise RetryError(
                f"Operation failed after {self.attempt} attempts",
                last_exception=exception,
                attempts=self.attempt
            )
        
        delay = min(self.base_delay * (self.exponential_base ** (self.attempt - 1)), self.max_delay)
        
        if self.jitter:
            delay = delay * (0.75 + random.random() * 0.5)
        
        logger.warning(f"Attempt {self.attempt - 1}/{self.max_retries + 1} failed: {exception}. Retrying in {delay:.1f}s...")
        time.sleep(delay)
    
    def success(self):
        """Mark operation as successful, stopping retry loop"""
        self._should_retry = False


# Pre-configured retry decorators for common use cases

def retry_api_call(func: Callable) -> Callable:
    """Retry decorator pre-configured for HTTP API calls"""
    import requests
    return retry_with_backoff(
        max_retries=3,
        base_delay=1.0,
        max_delay=30.0,
        exceptions=(requests.RequestException, ConnectionError, TimeoutError)
    )(func)


def retry_git_operation(func: Callable) -> Callable:
    """Retry decorator pre-configured for Git operations"""
    import subprocess
    return retry_with_backoff(
        max_retries=2,
        base_delay=0.5,
        max_delay=5.0,
        exceptions=(subprocess.CalledProcessError, OSError)
    )(func)


def retry_file_operation(func: Callable) -> Callable:
    """Retry decorator pre-configured for file I/O operations"""
    return retry_with_backoff(
        max_retries=3,
        base_delay=0.5,
        max_delay=5.0,
        exceptions=(IOError, OSError, PermissionError)
    )(func)
