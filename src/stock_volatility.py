import logging
import sys
import os
import pandas as pd
from config import TABLE_STOCK_IMPLIED_VOLATILITY_MASSIVE
from src.database import execute_sql, get_postgres_engine, insert_into_table, select_into_dataframe, truncate_table

logger = logging.getLogger(__name__)

def calculate_and_store_stock_implied_volatility():
    logger.info("Calculating and storing stock implied volatility...")

    df = select_into_dataframe(sql_file_path = "db/SQL/query/calculate_implied_volatility.sql")

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

def calculate_and_store_stock_implied_volatility_history():
    sql_file_path = "db/SQL/query/calculate_implied_volatility_history.sql"
    logger.info("Calculating and storing stock implied volatility history using SQL file: " + sql_file_path)
    vola_history_table_name = f"{TABLE_STOCK_IMPLIED_VOLATILITY_MASSIVE}HistoryDaily"
    try:
        if sql_file_path is not None and os.path.isfile(sql_file_path):
            with open(sql_file_path, 'r') as f:
                select = f.read()
        else:
            msg = "'sql_file_path' must be provided."
            logger.error(msg)
            raise ValueError(msg)

        sql = f"""
            INSERT INTO "{vola_history_table_name}"
            {select}
        """       

        with get_postgres_engine().begin() as connection:
            truncate_table(connection, vola_history_table_name)
            execute_sql(connection, sql, vola_history_table_name, "INSERT", "Calculating and storing stock implied volatility history")
            logger.info(f"[PostgreSQL] Successfully executed SQL query and stored implied volatility history.")

    except Exception as e:
        logger.error(f"[PostgreSQL] Error executing query: \n{e}")
        logger.error(f"\n{str(sql)}")
        raise e
