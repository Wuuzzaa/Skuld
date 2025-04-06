import calendar
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
