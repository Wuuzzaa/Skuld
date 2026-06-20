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

    min_timestamp_select = f'SELECT MIN(date) as min_date FROM "{TABLE_DIVIDEND_DATA_YAHOO}History"'
    df = select_into_dataframe(min_timestamp_select)
    if len(df) > 0:
        min_date = df.iloc[0]["min_date"]
    else:
        min_date = '2099-01-01'

    history_dates = select_into_dataframe('SELECT date from "DatesHistory" WHERE date < :min_date  ORDER BY date desc', params={"min_date": min_date})

    for time_travel_date in history_dates["date"]:
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

def calculate_dividend_classification_history_full():
    logger.info("Calculation Yahoo Dividend Classification")

    history_dates = select_into_dataframe('SELECT date from "DatesHistory" ORDER BY date desc')

    for time_travel_date in history_dates["date"]:
        dividend_data = select_timetravel_into_dataframe(time_travel_date, sql_file_path = "db/SQL/query/dividend_classification.sql")
        dividend_data["snapshot_date"] = time_travel_date
    
        # --- Database Persistence ---
        with get_postgres_engine().begin() as connection:
            truncate_table(connection, TABLE_DIVIDEND_DATA_YAHOO)
            insert_into_table(
                connection,
                table_name=f"{TABLE_DIVIDEND_DATA_YAHOO}HistoryDaily",
                dataframe=dividend_data,
                if_exists="append"
            )
        logger.info(f"Saved dividend classification data to database - rows: {len(dividend_data)}")