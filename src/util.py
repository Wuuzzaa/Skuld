import calendar
import re
from pathlib import Path
from config import FOLDERPATHS
from datetime import date, timedelta


def create_all_project_folders():
    print("Creating all project folders if needed...")

    for folder in FOLDERPATHS:
        folder_path = Path(folder)
        if not folder_path.exists():
            folder_path.mkdir(parents=True, exist_ok=True)
            print(f"Created folder: {folder_path}")
        else:
            print(f"Folder already exists: {folder_path}")


def get_option_expiry_dates():
    today = date.today()
    expiry_dates = set()

    # Monthly expiration dates: Third Friday of the next 4 months
    for i in range(4):
        year = today.year + (today.month + i - 1) // 12  # Adjust the year if the month exceeds 12
        month = (today.month + i - 1) % 12 + 1  # Keep the month between 1 and 12

        # Get the month's calendar weeks
        month_cal = calendar.monthcalendar(year, month)
        # The third Friday is in the third week (if not available, take the fourth week)
        third_friday = month_cal[2][4] if month_cal[2][4] != 0 else month_cal[3][4]
        expiry_date = date(year, month, third_friday)

        if expiry_date >= today:  # Only future dates
            expiry_dates.add(expiry_date)

    # Weekly expiration dates: Every Friday for the next 60 days
    for i in range(60):
        future_date = today + timedelta(days=i)
        if future_date.weekday() == 4:  # Friday
            expiry_dates.add(future_date)

    expiry_dates_list = sorted(int(d.strftime('%Y%m%d')) for d in expiry_dates)

    return expiry_dates_list

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
