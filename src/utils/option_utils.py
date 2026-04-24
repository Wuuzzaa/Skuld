import pandas as pd
from pandas.tseries.holiday import AbstractHolidayCalendar, Holiday, nearest_workday, GoodFriday

class USOptionHolidayCalendar(AbstractHolidayCalendar):
    """
    Custom holiday calendar for US Options based on NYSE holidays.
    """
    rules = [
        Holiday("New Years Day", month=1, day=1, observance=nearest_workday),
        Holiday("Martin Luther King Jr. Day", month=1, day=1, offset=pd.DateOffset(weekday=0, weeks=2)),
        Holiday("Presidents Day", month=2, day=1, offset=pd.DateOffset(weekday=0, weeks=2)),
        GoodFriday,
        Holiday("Memorial Day", month=5, day=31, offset=pd.DateOffset(weekday=0, weeks=-1)),
        Holiday("Juneteenth", month=6, day=19, observance=nearest_workday),
        Holiday("July 4th", month=7, day=4, observance=nearest_workday),
        Holiday("Labor Day", month=9, day=1, offset=pd.DateOffset(weekday=0, weeks=0)),
        Holiday("Thanksgiving", month=11, day=1, offset=pd.DateOffset(weekday=3, weeks=3)),
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]

def get_expiration_type(expiration_date):
    """
    Classifies the expiration type of an option based on its date.
    
    Logic:
    - Monthly: 3rd Friday of the month. If that Friday is a holiday, the preceding Thursday.
    - Weekly: Every other Friday. If that Friday is a holiday, the preceding Thursday.
    - Daily: Any other day.
    
    Args:
        expiration_date (str or pd.Timestamp): The expiration date of the option.
        
    Returns:
        str: "Monthly", "Weekly", or "Daily".
    """
    date = pd.to_datetime(expiration_date)

    # 1. Calculate the theoretical 3rd Friday of the month
    first_day_of_month = date.replace(day=1)
    # Offset to the first Friday (4 = Friday)
    offset = (4 - first_day_of_month.dayofweek) % 7
    third_friday = first_day_of_month + pd.Timedelta(days=offset + 14)

    # 2. Check for holidays (NYSE)
    cal = USOptionHolidayCalendar()
    # NYSE holidays are fixed; we check the year of the current date
    holidays = cal.holidays(start=date.replace(month=1, day=1), end=date.replace(month=12, day=31))

    # If the 3rd Friday is a holiday, the monthly expiry shifts to the preceding business day (Thursday)
    if third_friday in holidays:
        actual_monthly_expiry = third_friday - pd.Timedelta(days=1)
    else:
        actual_monthly_expiry = third_friday

    if date == actual_monthly_expiry:
        return "Monthly"

    # If it's not a Monthly, check if it's a Friday (Standard Weekly)
    # OR a Thursday if the following Friday is a holiday
    if date.dayofweek == 4:
        return "Weekly"

    # If it's a Thursday, check if the following Friday is a holiday
    if date.dayofweek == 3:
        next_day = date + pd.Timedelta(days=1)
        if next_day in holidays:
            return "Weekly"

    return "Daily"
