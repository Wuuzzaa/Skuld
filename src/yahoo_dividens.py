import logging
import sys
import os
import pandas as pd
from config import TABLE_DIVIDEND_DATA_YAHOO
from src.database import get_postgres_engine, insert_into_table, select_into_dataframe, truncate_table


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