import calendar
import re
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from config_utils import validate_config
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
    today = date.today()
    expiry_dates = set()
    active_mode = validate_config()

    if active_mode == "GENERAL_TEST_MODE":
        # Standardlogik, aber am Ende auf GENERAL_TEST_MODE_MAX_EXPIRY_DATES begrenzen
        # (z.B. Standard-Optionen + ggf. LEAPS, je nach gewünschtem Verhalten)
        # Hier: Standard-Optionen
        # Monthly expiration dates
        for i in range(STANDARD_MONTHLY_OPTIONS_MONTHS):
            year = today.year + (today.month + i - 1) // 12  # Adjust the year if the month exceeds 12
            month = (today.month + i - 1) % 12 + 1  # Keep the month between 1 and 12

            expiry_date = get_third_friday(year, month)

            if expiry_date >= today:  # Only future dates
                expiry_dates.add(expiry_date)

        # Weekly expiration dates
        for i in range(STANDARD_WEEKLY_OPTIONS_DAYS):
            future_date = today + timedelta(days=i)
            if future_date.weekday() == 4:  # Friday
                expiry_dates.add(future_date)

        expiry_dates_list = sorted(expiry_dates)
        # Begrenzen auf die gewünschte Anzahl
        expiry_dates_list = expiry_dates_list[:GENERAL_TEST_MODE_MAX_EXPIRY_DATES]

        return [int(d.strftime('%Y%m%d')) for d in expiry_dates_list]

    elif active_mode == "EXTENDED_LEAPS_MODE":
        # All Fridays in the range from MIN_DAYS to MAX_DAYS
        for i in range(MARRIED_PUT_EXTENDED_LEAPS_MIN_DAYS, MARRIED_PUT_EXTENDED_LEAPS_MAX_DAYS + 1):
            future_date = today + timedelta(days=i)
            if future_date.weekday() == 4:  # Friday
                expiry_dates.add(future_date)

        # Zusätzliche dritte Freitage: erster dritter Freitag nach 180 und 360 Tagen
        for target_days in [180, 360]:
            target_date = today + timedelta(days=target_days)

            # Starte im Zielmonat und suche nach dem ersten dritten Freitag nach target_date
            current_month = target_date.month
            current_year = target_date.year

            found = False
            while not found:
                # Hole den dritten Freitag des aktuellen Monats
                expiry_date = get_third_friday(current_year, current_month)

                # Wenn dieser dritte Freitag nach dem Zieltermin liegt, haben wir unser Ablaufdatum gefunden
                if expiry_date > target_date:
                    expiry_dates.add(expiry_date)
                    found = True
                else:
                    # Gehe zum nächsten Monat
                    current_month += 1
                    if current_month > 12:
                        current_month = 1
                        current_year += 1

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

if __name__ == "__main__":
    expiry_dates = get_option_expiry_dates()
    pass
