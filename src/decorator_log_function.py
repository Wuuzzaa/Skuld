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
from typing import Any
import pandas as pd


# Configure logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Add handler if not already present
if not logger.handlers:
    logger.addHandler(console_handler)


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
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            )
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

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


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    """
    Examples demonstrating the log_function decorator.

    Run this module directly to see example outputs:
    $ python decorator_log_function.py
    """

    @log_function
    def fetch_user_data(user_id: int, limit: int = 10) -> pd.DataFrame:
        """Fetch user data and return as DataFrame."""
        time.sleep(0.2)
        df = pd.DataFrame({
            'user_id': [user_id] * limit,
            'value': range(limit),
            'timestamp': pd.date_range('2025-01-01', periods=limit)
        })
        return df

    @log_function
    def process_dataframe(df: pd.DataFrame, multiplier: float = 2.0) -> pd.DataFrame:
        """Process DataFrame by multiplying values."""
        time.sleep(0.15)
        df_copy = df.copy()
        df_copy['value'] = df_copy['value'] * multiplier
        return df_copy

    @log_function
    def calculate_statistics(values: list) -> dict:
        """Calculate statistics from a list of values."""
        time.sleep(0.1)
        return {
            'sum': sum(values),
            'mean': sum(values) / len(values),
            'min': min(values),
            'max': max(values),
            'count': len(values)
        }

    @log_function
    def transform_data(
        df: pd.DataFrame,
        column_name: str,
        operation: str = 'multiply',
        factor: float = 2.0
    ) -> pd.DataFrame:
        """Transform DataFrame column with specified operation."""
        time.sleep(0.1)
        df_copy = df.copy()
        if operation == 'multiply':
            df_copy[column_name] = df_copy[column_name] * factor
        elif operation == 'add':
            df_copy[column_name] = df_copy[column_name] + factor
        return df_copy

    # Example 1: Function returning DataFrame
    print("\n=== Example 1: Fetch User Data ===")
    user_df = fetch_user_data(user_id=456, limit=5)

    # Example 2: Function processing DataFrame
    print("\n=== Example 2: Process DataFrame ===")
    processed_df = process_dataframe(user_df, multiplier=3.0)

    # Example 3: Function with simple types
    print("\n=== Example 3: Calculate Statistics ===")
    stats = calculate_statistics([10, 20, 30, 40, 50])

    # Example 4: Function with multiple parameters
    print("\n=== Example 4: Transform Data ===")
    transformed_df = transform_data(
        user_df,
        column_name='value',
        operation='add',
        factor=100
    )