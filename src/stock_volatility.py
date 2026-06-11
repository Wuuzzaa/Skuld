import logging
import sys
import os
import time
import threading
import pandas as pd
from sqlalchemy import create_engine, text
from config import TABLE_STOCK_HISTORICAL_VOLATILITY_YAHOO, TABLE_STOCK_IMPLIED_VOLATILITY_MASSIVE, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB
from src.database import execute_sql, get_postgres_engine, insert_into_table, select_into_dataframe, truncate_table

logger = logging.getLogger(__name__)


def _create_monitor_engine():
    """Create a separate, lightweight engine for the SQL monitor (not from the shared pool)."""
    db_url = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    return create_engine(db_url, pool_size=1, max_overflow=0)


class SQLProgressMonitor(threading.Thread):
    """Background thread that checks pg_stat_activity to confirm a long-running query is still active."""

    def __init__(self, query_snippet, interval=60):
        super().__init__(daemon=True)
        self.query_snippet = query_snippet
        self.interval = interval
        self.stop_event = threading.Event()
        self.start_time = time.time()
        self._engine = None

    def run(self):
        try:
            self._engine = _create_monitor_engine()
        except Exception as e:
            logger.warning(f"[SQL Monitor] Could not create monitor engine: {e}")
            return

        while not self.stop_event.is_set():
            self.stop_event.wait(self.interval)
            if self.stop_event.is_set():
                break
            elapsed = int(time.time() - self.start_time)
            elapsed_str = f"{elapsed // 3600}h {(elapsed % 3600) // 60}m" if elapsed >= 3600 else f"{elapsed // 60}m {elapsed % 60}s"
            try:
                with self._engine.connect() as conn:
                    result = conn.execute(text(
                        "SELECT pid, state, now() - query_start AS duration "
                        "FROM pg_stat_activity "
                        "WHERE state = 'active' AND query LIKE :snippet "
                        "ORDER BY query_start LIMIT 1"
                    ), {"snippet": f"%{self.query_snippet}%"})
                    row = result.fetchone()
                    if row:
                        logger.info(f"[SQL Monitor] Query still running (PID: {row[0]}, PG duration: {row[2]}, elapsed: {elapsed_str})")
                    else:
                        logger.info(f"[SQL Monitor] No active query found matching '{self.query_snippet}' (elapsed: {elapsed_str}) - may have just finished")
            except Exception as e:
                logger.warning(f"[SQL Monitor] Could not check pg_stat_activity (elapsed: {elapsed_str}): {e}")

        if self._engine:
            self._engine.dispose()

    def stop(self):
        self.stop_event.set()

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
            logger.info(f"Truncating {vola_history_table_name}...")
            truncate_table(connection, vola_history_table_name)
            logger.info(f"Executing INSERT INTO {vola_history_table_name} (this is a single large SQL operation, may take 30-60+ min)...")

            # Start background monitor to confirm Postgres is still working
            monitor = SQLProgressMonitor(vola_history_table_name, interval=60)
            monitor.start()
            try:
                execute_sql(connection, sql, vola_history_table_name, "INSERT", "Calculating and storing stock implied volatility history")
            finally:
                monitor.stop()
                monitor.join(timeout=5)

            logger.info(f"Successfully stored implied volatility history into {vola_history_table_name}.")

    except Exception as e:
        logger.error(f"[PostgreSQL] Error executing query: \n{e}")
        logger.error(f"\n{str(sql)}")
        raise e

def calculate_and_store_stock_historical_volatility():
    logger.info("Calculating and storing stock historical volatility...")

    df = select_into_dataframe(sql_file_path = "db/SQL/query/calculate_historical_volatility.sql")

    with get_postgres_engine().begin() as connection:
        # Truncate the target table before inserting new data
        truncate_table(connection, TABLE_STOCK_HISTORICAL_VOLATILITY_YAHOO)

        # Insert the new data into the target table
        insert_into_table(
            connection, 
            TABLE_STOCK_HISTORICAL_VOLATILITY_YAHOO, 
            df, 
            if_exists="append"
        )

def calculate_and_store_stock_historical_volatility_history():
    sql_file_path = "db/SQL/query/calculate_historical_volatility_history.sql"
    logger.info("Calculating and storing stock historical volatility history using SQL file: " + sql_file_path)
    vola_history_table_name = f"{TABLE_STOCK_HISTORICAL_VOLATILITY_YAHOO}HistoryDaily"
    try:
        if sql_file_path is not None and os.path.isfile(sql_file_path):
            with open(sql_file_path, 'r') as f:
                select = f.read()
        else:
            msg = "'sql_file_path' must be provided."
            logger.error(msg)
            raise ValueError(msg)

        # get history dates from "DatesHistory" table
        history_dates = select_into_dataframe('SELECT date FROM "DatesHistory" ORDER BY date ASC')
        
        # loop through history dates and replace placeholder in SQL with actual date
        with get_postgres_engine().begin() as connection:
            logger.info(f"Truncating {vola_history_table_name}...")
            truncate_table(connection, vola_history_table_name)

            for date in history_dates['date']:
                logger.info(f"Calculating historical volatility for date: {date}")
                select_with_date = select.replace("HISTORY_DATE", f"'{date}'")

                sql = f"""
                    INSERT INTO "{vola_history_table_name}"
                    (snapshot_date, symbol, historical_volatility_30d)
                    WITH select_with_date AS (
                        {select_with_date}
                    )
                    SELECT
                    DATE('{date}') AS snapshot_date, 
                    symbol,
                    historical_volatility_30d
                    FROM select_with_date AS subquery
                """

                # Start background monitor to confirm Postgres is still working
                monitor = SQLProgressMonitor(vola_history_table_name, interval=60)
                monitor.start()
                try:
                    execute_sql(connection, sql, vola_history_table_name, "INSERT", "Calculating and storing stock historical volatility history")
                finally:
                    monitor.stop()
                    monitor.join(timeout=5)

            logger.info(f"Successfully stored historical volatility history into {vola_history_table_name}.")

    except Exception as e:
        logger.error(f"[PostgreSQL] Error executing query: \n{e}")
        logger.error(f"\n{str(sql)}")
        raise e