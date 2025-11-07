"""
Logging decorator module for tracking function execution.

This module provides a decorator to log function execution time, parameters,
and results. It has special handling for pandas DataFrames, which are logged
with head() for better readability.

Example:
    Basic usage of the log_function decorator:

        from decorator_log_function import log_function
        import pandas as pd

        @log_function
        def fetch_data(user_id: int) -> pd.DataFrame:
            df = pd.DataFrame({'id': [user_id], 'value': [42]})
            return df

        result = fetch_data(123)
        # Output: [START] fetch_data | Parameters: 123
        # Output: [END] fetch_data | Execution time: 0.001s | Result: DataFrame...

Classes:
    None

Functions:
    log_function: Main decorator for function logging
    _format_params: Helper function to format parameters
    _format_result: Helper function to format results

Author:
    Your Name

Version:
    1.0.0
"""

import logging
import time
import functools
import pandas as pd
from typing import Any


def log_function(func):
    """
    Decorator to log function execution time, parameters, and results.

    This decorator wraps a function and logs:
    - Function name and parameters when the function is called
    - Execution time and result when the function completes
    - Error details if an exception occurs

    DataFrames are logged with head() to show sample data without clutter.
    Large collections (lists, dicts) are truncated to prevent log spam.

    Args:
        func: The function to be decorated.

    Returns:
        The wrapped function with logging capabilities.

    Raises:
        Any exception raised by the decorated function is re-raised after logging.

    Example:
        >>> @log_function
        >>> def calculate_sum(numbers: list) -> int:
        ...     return sum(numbers)
        >>>
        >>> result = calculate_sum([1, 2, 3, 4, 5])
        # Output: [START] calculate_sum | Parameters: [1, 2, 3, 4, 5]
        # Output: [END] calculate_sum | Execution time: 0.001s | Result: 15
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        logger = logging.getLogger(__name__)

        func_name = func.__name__

        # Format parameters
        params_str = _format_params(args, kwargs)

        logger.info(f"[START] {func_name} | Parameters: {params_str}")

        start_time = time.time()

        try:
            result = func(*args, **kwargs)
            elapsed_time = time.time() - start_time

            # Format result
            result_str = _format_result(result)

            logger.info(
                f"[END] {func_name} | Execution time: {elapsed_time:.3f}s | "
                f"Result: {result_str}"
            )

            return result

        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(
                f"[ERROR] {func_name} | Execution time: {elapsed_time:.3f}s | "
                f"Error: {str(e)}",
                exc_info=True
            )
            raise

    return wrapper


def _format_params(args: tuple, kwargs: dict) -> str:
    """
    Format function parameters for logging.

    Intelligently formats parameters to keep logs readable:
    - DataFrames are shown as DataFrame(shape=...)
    - Large collections show length instead of full content
    - Small values are shown as-is

    Args:
        args: Positional arguments from the function call.
        kwargs: Keyword arguments from the function call.

    Returns:
        A formatted string representation of all parameters.

    Example:
        >>> _format_params((123, pd.DataFrame({'a': [1]})), {'name': 'test'})
        "123, DataFrame(shape=(1, 1)), name='test'"
    """
    params = []

    for arg in args:
        if isinstance(arg, pd.DataFrame):
            params.append(f"DataFrame(shape={arg.shape})")
        elif isinstance(arg, (list, tuple)) and len(str(arg)) > 100:
            params.append(f"{type(arg).__name__}(len={len(arg)})")
        elif isinstance(arg, dict) and len(str(arg)) > 100:
            params.append(f"dict(keys={len(arg)})")
        else:
            params.append(repr(arg))

    for key, value in kwargs.items():
        if isinstance(value, pd.DataFrame):
            params.append(f"{key}=DataFrame(shape={value.shape})")
        elif isinstance(value, (list, tuple)) and len(str(value)) > 100:
            params.append(f"{key}={type(value).__name__}(len={len(value)})")
        elif isinstance(value, dict) and len(str(value)) > 100:
            params.append(f"{key}=dict(keys={len(value)})")
        else:
            params.append(f"{key}={repr(value)}")

    return ", ".join(params) if params else "none"


def _format_result(result: Any) -> str:
    """
    Format function result for logging.

    Provides special formatting for different data types:
    - DataFrames are shown with head() and shape info
    - Large collections show first 5 items
    - Other types are shown as-is

    Args:
        result: The return value from the decorated function.

    Returns:
        A formatted string representation of the result.

    Example:
        >>> df = pd.DataFrame({'a': [1, 2, 3]})
        >>> _format_result(df)
        "DataFrame(shape=(3, 1))\\n   a\\n0  1\\n1  2\\n2  3"
    """
    if isinstance(result, pd.DataFrame):
        return (
            f"DataFrame(shape={result.shape})\n"
            f"{result.head().to_string()}"
        )
    elif isinstance(result, (list, tuple)) and len(result) > 5:
        return f"{type(result).__name__}(len={len(result)})\n{result[:5]}"
    elif isinstance(result, dict) and len(result) > 5:
        items = list(result.items())[:5]
        return f"dict(keys={len(result)})\n{dict(items)}"
    else:
        return repr(result)
