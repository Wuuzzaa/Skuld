import calendar
import re
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from config_utils import generate_expiry_dates_from_rules
from datetime import date, timedelta

def get_third_friday(year, month):
    """Calculate the third Friday of a given month"""
    # Find the first day of the month
    first_day = date(year, month, 1)
    # Find the first Friday
    days_until_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + timedelta(days=days_until_friday)
    # The third Friday is 14 days later
    third_friday = first_friday + timedelta(days=14)
    return third_friday


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

if __name__ == "__main__":
    expiry_dates = get_option_expiry_dates()
    pass

class Singleton:
    """
    A non-thread-safe helper class to ease implementing singletons.
    This should be used as a decorator -- not a metaclass -- to the
    class that should be a singleton.

    The decorated class can define one `__init__` function that
    takes only the `self` argument. Also, the decorated class cannot be
    inherited from. Other than that, there are no restrictions that apply
    to the decorated class.

    To get the singleton instance, use the `instance` method. Trying
    to use `__call__` will result in a `TypeError` being raised.

    """

    def __init__(self, decorated):
        self._decorated = decorated

    def instance(self):
        """
        Returns the singleton instance. Upon its first call, it creates a
        new instance of the decorated class and calls its `__init__` method.
        On all subsequent calls, the already created instance is returned.

        """
        try:
            return self._instance
        except AttributeError:
            self._instance = self._decorated()
            return self._instance

    def __call__(self):
        raise TypeError('Singletons must be accessed through `instance()`.')

    def __instancecheck__(self, inst):
        return isinstance(inst, self._decorated)