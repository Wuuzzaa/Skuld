import logging
import sys
import os
import pandas as pd
from config import TABLE_STOCK_IMPLIED_VOLATILITY_MASSIVE
from src.database import get_postgres_engine, insert_into_table, select_into_dataframe, truncate_table

logger = logging.getLogger(__name__)

def calculate_and_store_stock_implied_volatility():
    logger.info("Calculating and storing stock implied volatility...")

    df = select_into_dataframe(sql_file_path = "db/SQL/query/implied_volatility.sql")

    with get_postgres_engine().begin() as connection:
        # Truncate the target table before inserting new data
        truncate_table(connection, TABLE_STOCK_IMPLIED_VOLATILITY_MASSIVE)

        # Insert the new data into the target table
        insert_into_table(
            connection, 
            TABLE_STOCK_IMPLIED_VOLATILITY_MASSIVE, 
            df, 
            if_exists="append"
        )

