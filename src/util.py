import re
import sys
import threading
import logging
from config import *

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

def log_memory_usage(prefix=""):
    """Logs current memory usage and returns it in MB"""
    memory_mb = 0
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
        logger.info(f"{prefix} Current RSS Memory: {memory_mb:.2f} MB")
        return memory_mb
    except ImportError:
        pass

    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # Linux: ru_maxrss is in kilobytes
        # Mac: ru_maxrss is in bytes
        # We assume Linux for Docker
        memory_mb = usage.ru_maxrss / 1024
        logger.info(f"{prefix} Max RSS Memory: {memory_mb:.2f} MB")

        # Try to get current RSS from /proc/self/status if available
        if os.path.exists('/proc/self/status'):
            with open('/proc/self/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        rss_kb = int(line.split()[1])
                        current_mb = rss_kb/1024
                        logger.info(f"{prefix} Current RSS Memory: {current_mb:.2f} MB")
                        return current_mb
        
        return memory_mb
    except ImportError:
        # resource module is not available on Windows
        logger.warning(f"{prefix} Memory logging not available (resource module missing and psutil not installed)")
        return None
    except Exception as e:
        logger.error(f"{prefix} Error checking memory: {e}")
        return None

    return memory_mb

class MemoryMonitor(threading.Thread):
    """
    Background thread to monitor and log memory usage periodically.
    Useful for debugging OOM crashes where the process dies before logging.
    """
    def __init__(self, interval=2.0):
        super().__init__()
        self.interval = interval
        self.stop_event = threading.Event()
        self.daemon = True  # Daemon thread dies when main thread dies

    def run(self):
        logger.info(f"[Monitor] Starting memory monitor (interval={self.interval}s)...")
        while not self.stop_event.is_set():
            log_memory_usage("[Monitor] ")
            self.stop_event.wait(self.interval)
        logger.info("[Monitor] Memory monitor stopped.")

    def stop(self):
        self.stop_event.set()

def get_option_expiry_dates():
    """
    Get option expiry dates based on enabled collection rules.

    Returns:
        list: List of expiry dates in YYYYMMDD integer format
    """
    print("Generating expiry dates from collection rules...")

    # Get dates from the new rule-based system
    expiry_date_strings = generate_expiry_dates_from_rules()

    # Convert from "YYYY-MM-DD" strings to YYYYMMDD integers
    expiry_dates_int = []
    for date_str in expiry_date_strings:
        # Convert "2024-06-21" to 20240621
        date_int = int(date_str.replace("-", ""))
        expiry_dates_int.append(date_int)

    print(f"Generated {len(expiry_dates_int)} expiry dates from {len([r for r in OPTIONS_COLLECTION_RULES if r.get('enabled')])} enabled rules")

    return sorted(expiry_dates_int)

def opra_to_osi(opra_code):
    """
    Converts an OPRA option code into the standard OSI format.

    OPRA format (used by many APIs and market data providers) looks like:
        OPRA:<SYMBOL><YY><MM><DD><C/P><STRIKE>
        Example: 'OPRA:AAPL250606C110.0'

    OSI format (used by OCC and exchanges) looks like:
        <SYMBOL><YY><MM><DD><C/P><STRIKE (8 digits, implied 3 decimals)>
        Example: 'AAPL250606C00110000'

    Parameters:
        opra_code (str): The OPRA-style option symbol (e.g. 'OPRA:AAPL250606C110.0')

    Returns:
        str: The corresponding OSI code (e.g. 'AAPL250606C00110000')

    Raises:
        ValueError: If the input does not match the expected OPRA format.

    Example:
        >>> opra_to_osi("OPRA:AAPL250606C110.0")
        'AAPL250606C00110000'
    """

    # Remove optional "OPRA:" prefix if present
    if opra_code.startswith("OPRA:"):
        opra_code = opra_code[5:]

    # Extract components: Symbol, Date (YYMMDD), Option Type, and Strike
    match = re.match(r'^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])([\d.]+)$', opra_code)
    if not match:
        raise ValueError("Invalid OPRA format: " + opra_code)

    symbol, year, month, day, opt_type, strike_str = match.groups()

    # Convert strike price to OSI format (e.g. 110.0 → 00110000)
    strike_float = float(strike_str)
    strike_osi = f"{int(strike_float * 1000):08d}"  # 8-digit string with leading zeros

    # Combine parts into OSI format
    osi_code = f"{symbol}{year}{month}{day}{opt_type}{strike_osi}"
    return osi_code

def opra_to_symbol(opra_code):
    """
    Extracts symbol from OPRA option code.

    OPRA format (used by many APIs and market data providers) looks like:
        OPRA:<SYMBOL><YY><MM><DD><C/P><STRIKE>
        Example: 'OPRA:AAPL250606C110.0'

    Parameters:
        opra_code (str): The OPRA-style option symbol (e.g. 'OPRA:AAPL250606C110.0')

    Returns:
        str: The corresponding OSI code (e.g. 'AAPL250606C00110000')

    Raises:
        ValueError: If the input does not match the expected OPRA format.

    Example:
        >>> opra_to_osi("OPRA:AAPL250606C110.0")
        'AAPL'
    """

    # Remove optional "OPRA:" prefix if present
    if opra_code.startswith("OPRA:"):
        opra_code = opra_code[5:]

    # Extract components: Symbol, Date (YYMMDD), Option Type, and Strike
    match = re.match(r'^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])([\d.]+)$', opra_code)
    if not match:
        raise ValueError("Invalid OPRA format: " + opra_code)

    symbol, year, month, day, opt_type, strike_str = match.groups()

    return symbol

def executed_as_github_action():
    return os.getenv('GITHUB_ACTIONS') == 'true'

class Singleton:
    """
    A non-thread-safe helper class to ease implementing singletons.
    This should be used as a decorator -- not a metaclass -- to the
    class that should be a singleton.

    The decorated class can define one `__init__` function that
    takes arguments. The decorated class cannot be inherited from.
    To get the singleton instance, use the `instance(*args, **kwargs)` method.
    Trying to use `__call__` will result in a `TypeError` being raised.
    """

    def __init__(self, decorated):
        self._decorated = decorated
        self._lock = threading.Lock()
        self._instance = None
        self._args = None
        self._kwargs = None

    def instance(self, *args, **kwargs):
        """
        Returns the singleton instance. Upon its first call, it creates a
        new instance of the decorated class and calls its `__init__` method.
        On all subsequent calls, the already created instance is returned.
        """
        with self._lock:
            if self._instance is None:
                self._args = args
                self._kwargs = kwargs
                self._instance = self._decorated(*self._args, **self._kwargs)
            return self._instance

    def __call__(self, *args, **kwargs):
        raise TypeError('Singletons must be accessed through `instance(*args, **kwargs)`.')

    def __instancecheck__(self, inst):
        return isinstance(inst, self._decorated)
    

def get_dataframe_memory_usage(df:pd.DataFrame):
    """Return a DataFrame with memory usage per column and total usage."""
    # Calculate memory usage per column (in bytes)
    memory_per_column = df.memory_usage(deep=True)

    # Total memory usage (including DataFrame overhead)
    total_bytes = memory_per_column.sum()
    total_mb = total_bytes / (1024 ** 2)
    total_gb = total_bytes / (1024 ** 3)

    # Get dtypes for each column (Index has no dtype)
    dtypes = [''] + [str(dtype) for dtype in df.dtypes]

    # Create a DataFrame for memory usage per column
    memory_df = pd.DataFrame({
        "Column": memory_per_column.index,
        "Dtype": dtypes,
        "Bytes": memory_per_column.values,
        "MB": (memory_per_column.values / (1024 ** 2)).round(4),
        "GB": (memory_per_column.values / (1024 ** 3)).round(6),
    })

    # Add total row
    total_row = pd.DataFrame({
        "Column": ["**Total**"],
        "Dtype": [""],
        "Bytes": [total_bytes],
        "MB": [round(total_mb, 4)],
        "GB": [round(total_gb, 6)],
    })

    memory_df = pd.concat([memory_df, total_row], ignore_index=True)

    return memory_df