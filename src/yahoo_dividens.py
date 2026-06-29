import logging
import sys
import os
import pandas as pd
from config import TABLE_DIVIDEND_DATA_YAHOO
from src.database import get_postgres_engine, insert_into_table, select_into_dataframe, truncate_table
from src.historization import select_timetravel_into_dataframe


# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logger = logging.getLogger(__name__)

def calculate_dividend_classification():
    logger.info("Calculation Yahoo Dividend Classification")
    dividend_data = select_into_dataframe(sql_file_path = "db/SQL/query/dividend_classification.sql")

    # --- Database Persistence ---
    with get_postgres_engine().begin() as connection:
        truncate_table(connection, TABLE_DIVIDEND_DATA_YAHOO)
        insert_into_table(
            connection,
            table_name=TABLE_DIVIDEND_DATA_YAHOO,
            dataframe=dividend_data,
            if_exists="append"
        )
    logger.info(f"Saved dividend classification data to database - rows: {len(dividend_data)}")

def calculate_dividend_classification_history():
    logger.info("Calculation Yahoo Dividend Classification")

    # min_timestamp_select = f'SELECT MIN(date) as min_date FROM "{TABLE_DIVIDEND_DATA_YAHOO}History"'
    # df = select_into_dataframe(min_timestamp_select)
    # if df and len(df) > 0:
    #     min_date = df.iloc[0]["min_date"]
    # else:
    #     min_date = '2099-01-01'

    history_dates = select_into_dataframe(f'SELECT date from "DatesHistory" as dates WHERE NOT EXISTS (SELECT 1 FROM "{TABLE_DIVIDEND_DATA_YAHOO}History" as hist WHERE dates.date = hist.date) ORDER BY date desc LIMIT 50')

    iteration = 1
    for time_travel_date in history_dates["date"]:
        logger.info(f"Date {time_travel_date} ({iteration} of {len(history_dates)}")
        dividend_data = select_timetravel_into_dataframe(time_travel_date, sql_file_path = "db/SQL/query/dividend_classification.sql")
        dividend_data["snapshot_date"] = time_travel_date
    
        # --- Database Persistence ---
        with get_postgres_engine().begin() as connection:
            # truncate_table(connection, TABLE_DIVIDEND_DATA_YAHOO)
            insert_into_table(
                connection,
                table_name=f"{TABLE_DIVIDEND_DATA_YAHOO}HistoryDaily",
                dataframe=dividend_data,
                if_exists="append"
            )
        logger.info(f"Saved dividend classification data to database - rows: {len(dividend_data)}")
        iteration = iteration + 1

def calculate_dividend_classification_history_full():
    logger.info("Calculation Yahoo Dividend Classification")

    history_dates = select_into_dataframe('SELECT date from "DatesHistory" ORDER BY date desc')

    truncate_table(connection, f"{TABLE_DIVIDEND_DATA_YAHOO}HistoryDaily")
    iteration = 1
    for time_travel_date in history_dates["date"]:
        logger.info(f"Date {time_travel_date} ({iteration} of {len(history_dates)}")
        dividend_data = select_timetravel_into_dataframe(time_travel_date, sql_file_path = "db/SQL/query/dividend_classification.sql")
        dividend_data["snapshot_date"] = time_travel_date
    
        # --- Database Persistence ---
        with get_postgres_engine().begin() as connection:
            insert_into_table(
                connection,
                table_name=f"{TABLE_DIVIDEND_DATA_YAHOO}HistoryDaily",
                dataframe=dividend_data,
                if_exists="append"
            )
        logger.info(f"Saved dividend classification data to database - rows: {len(dividend_data)}")
        iteration = iteration + 1