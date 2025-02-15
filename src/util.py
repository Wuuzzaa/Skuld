import os
import calendar
from config import FOLDERPATHS
from datetime import date, timedelta

def create_all_project_folders():
    print("Creating all project folders if needed...")

    for folder in FOLDERPATHS:
        directory = os.path.dirname(folder)

        if directory and not os.path.exists(directory):
            print("Creating folder {}".format(folder))
            os.makedirs(directory)


def get_option_expiry_dates():
    today = date.today()
    expiry_dates = set()

    # Monthly expiration dates: Third Friday of the next 12 months
    for i in range(12):
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

    #expiry_dates_list = [int(d.strftime('%Y%m%d')) for d in sorted(expiry_dates)]
    expiry_dates_list = sorted(int(d.strftime('%Y%m%d')) for d in expiry_dates)
    print('expiry_dates:')
    print(expiry_dates_list)

    return expiry_dates_list
