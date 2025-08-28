from config import (
    SYMBOL_SELECTION,
    OPTIONS_COLLECTION_RULES,
    SYMBOLS,
    SYMBOLS_EXCHANGE,
)
from datetime import datetime, timedelta


def get_symbols_from_config():
    """Get symbols based on SYMBOL_SELECTION configuration"""
    mode = SYMBOL_SELECTION["mode"]
    
    if mode == "all":
        symbols = SYMBOLS
    elif mode == "list":
        symbols = SYMBOL_SELECTION["symbols"]
    elif mode == "file":
        # TODO: Implement file-based symbol loading
        symbols = SYMBOLS
    elif mode == "max":
        # New mode: take first N symbols from all available
        max_count = SYMBOL_SELECTION.get("max_symbols", 10)
        symbols = SYMBOLS[:max_count]
    else:
        symbols = SYMBOLS
    
    # Apply max_symbols limit if use_max_limit is True (unless mode is already "list")
    if SYMBOL_SELECTION.get("use_max_limit", False) and mode != "list":
        max_count = SYMBOL_SELECTION.get("max_symbols", 10)
        symbols = symbols[:max_count]
    
    return symbols


def get_filtered_symbols_with_logging(context_name="Processing"):
    """
    Get filtered symbols based on new simplified configuration.
    
    Args:
        context_name (str): Context for logging
    
    Returns:
        list: symbols_list
    """
    symbols = get_symbols_from_config()
    print(f"Using {len(symbols)} symbols for {context_name}")
    return symbols


def get_filtered_symbols_and_dates_with_logging(expiry_dates=None, context_name="Processing"):
    """
    Get filtered symbols and expiry dates based on new simplified configuration.
    
    Args:
        expiry_dates (list): List of expiry dates to filter
        context_name (str): Context for logging
    
    Returns:
        tuple: (symbols_list, filtered_expiry_dates)
    """
    symbols = get_symbols_from_config()
    print(f"Using {len(symbols)} symbols for {context_name}")
    
    # If expiry_dates provided, filter them; otherwise generate from rules
    if expiry_dates:
        filtered_expiry_dates = filter_expiry_dates_by_rules(expiry_dates)
    else:
        filtered_expiry_dates = generate_expiry_dates_from_rules()
    
    return symbols, filtered_expiry_dates


def filter_expiry_dates_by_rules(expiry_dates):
    """
    Filter expiry dates based on enabled OPTIONS_COLLECTION_RULES.
    
    Args:
        expiry_dates (list): List of expiry date strings
    
    Returns:
        list: Filtered list of expiry dates
    """
    if not expiry_dates:
        return []
    
    today = datetime.now().date()
    filtered_dates = []
    
    for date_str in expiry_dates:
        try:
            expiry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            days_until_expiry = (expiry_date - today).days
            
            # Check if date falls within any enabled rule
            for rule in OPTIONS_COLLECTION_RULES:
                if rule["enabled"]:
                    min_days, max_days = rule["days_range"]
                    if min_days <= days_until_expiry <= max_days:
                        filtered_dates.append(date_str)
                        break  # Found matching rule, no need to check others
                        
        except ValueError:
            print(f"WARNING: Invalid date format: {date_str}")
            continue
    
    return filtered_dates


def generate_expiry_dates_from_rules():
    """
    Generate expiry dates based on the new OPTIONS_COLLECTION_RULES.
    
    Returns:
        list: List of expiry dates (strings in YYYY-MM-DD format)
    """
    today = datetime.now().date()
    all_dates = set()
    
    print("Generating expiry dates from active rules")
    
    # Process each enabled rule
    for rule in OPTIONS_COLLECTION_RULES:
        if not rule["enabled"]:
            print(f"Skipping disabled rule: {rule['name']}")
            continue
            
        print(f"Processing rule: {rule['name']} ({rule['days_range'][0]}-{rule['days_range'][1]} days, {rule['frequency']})")
        
        min_days, max_days = rule["days_range"]
        frequency = rule["frequency"]
        
        start_date = today + timedelta(days=min_days)
        end_date = today + timedelta(days=max_days)
        
        if frequency == "every_friday":
            _add_weekly_options(all_dates, start_date, end_date)
        elif frequency == "monthly_3rd_friday":
            _add_monthly_third_fridays(all_dates, start_date, end_date)
        elif frequency == "quarterly_3rd_friday":
            _add_quarterly_third_fridays(all_dates, start_date, end_date)
        else:
            print(f"WARNING: Unknown frequency '{frequency}' in rule '{rule['name']}'")
    
    # Convert to sorted list and return as strings
    sorted_dates = sorted(all_dates)
    print(f"Generated {len(sorted_dates)} total expiry dates")
    return [date.strftime("%Y-%m-%d") for date in sorted_dates]


def _add_weekly_options(dates_set, start_date, end_date):
    """Add all Fridays between start_date and end_date"""
    current = start_date
    
    # Find first Friday on or after start_date
    while current.weekday() != 4:  # 4 = Friday
        current += timedelta(days=1)
        if current > end_date:
            return
    
    # Add all Fridays in the range
    while current <= end_date:
        dates_set.add(current)
        current += timedelta(days=7)  # Next Friday


def _add_monthly_third_fridays(dates_set, start_date, end_date):
    """Add third Friday of each month between start_date and end_date"""
    current_month = start_date.replace(day=1)
    
    while current_month <= end_date:
        third_friday = find_third_friday(current_month.year, current_month.month)
        if start_date <= third_friday <= end_date:
            dates_set.add(third_friday)
        current_month = _next_month(current_month)


def _add_quarterly_third_fridays(dates_set, start_date, end_date):
    """Add third Friday of quarterly months (March, June, September, December)"""
    quarterly_months = [3, 6, 9, 12]
    
    # Find starting year and quarter
    current_year = start_date.year
    current_month = start_date.month
    
    # Find first quarterly month on or after start_date
    next_quarterly_month = None
    for month in quarterly_months:
        if month >= current_month:
            next_quarterly_month = month
            break
    
    if next_quarterly_month is None:
        # Need to go to next year
        current_year += 1
        next_quarterly_month = quarterly_months[0]
    
    # Add quarterly third Fridays
    while True:
        quarterly_date = datetime(current_year, next_quarterly_month, 1).date()
        if quarterly_date > end_date:
            break
            
        third_friday = find_third_friday(current_year, next_quarterly_month)
        if start_date <= third_friday <= end_date:
            dates_set.add(third_friday)
        
        # Move to next quarter
        quarter_index = quarterly_months.index(next_quarterly_month)
        if quarter_index == 3:  # December, move to next year
            current_year += 1
            next_quarterly_month = quarterly_months[0]
        else:
            next_quarterly_month = quarterly_months[quarter_index + 1]


def find_third_friday(year, month):
    """Find the third Friday of a given month"""
    # First day of the month
    first_day = datetime(year, month, 1).date()
    
    # Find first Friday
    first_friday = first_day
    while first_friday.weekday() != 4:  # 4 = Friday
        first_friday += timedelta(days=1)
    
    # Third Friday is 14 days later
    third_friday = first_friday + timedelta(days=14)
    return third_friday


def _next_month(date):
    """Get the first day of the next month"""
    if date.month == 12:
        return date.replace(year=date.year + 1, month=1)
    else:
        return date.replace(month=date.month + 1)