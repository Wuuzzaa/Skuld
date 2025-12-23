import logging
import time
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import text
from config import HISTORY_ENABLED_TABLES
from src.database import get_database_engine, execute_sql, get_table_key_and_data_columns, select_into_dataframe, table_exists, view_exists
import pathlib

logger = logging.getLogger(__name__)

class DataAgingService:

    @staticmethod
    def run(source_table: str):
        """
        Analyzes the columns of the daily history table (OptionDataYahooHistoryDaily).
        If a column is unchanged for a full week (days_difference = 6) or unchanged and expired,
        it is promoted to the weekly history view (OptionDataYahooHistoryWeekly) and
        nulled out in the daily table.
        """
        logger.info("Starting data aging for {source_table}...")
        start_time = time.time()
        
        DataAgingService._promote_data_from_daily_to_weekly(source_table)
        DataAgingService._promote_data_from_weekly_to_monthly(source_table)
        DataAgingService._promote_data_to_master_data(source_table)

        end_time = time.time()
        total_duration = int(end_time - start_time)
        logger.info(f"Data aging completed for {source_table} in {total_duration}s ({total_duration / 60:.1f} minutes)")
    
    def run2():
        """
        Analyzes the columns of the daily history table (OptionDataYahooHistoryDaily).
        If a column is unchanged for a full week (days_difference = 6) or unchanged and expired,
        it is promoted to the weekly history view (OptionDataYahooHistoryWeekly) and
        nulled out in the daily table.
        """
        logger.info("Starting data aging...")
        start_time = time.time()
        
        # get history tables
        history_tables = select_into_dataframe("SELECT name FROM sqlite_schema WHERE type='table' AND name LIKE '%HistoryDaily'")

        engine = get_database_engine()
  
        for _, row in history_tables.iterrows():
            source_table = row['name']
            target_table = source_table.replace("Daily", "Weekly")     
            master_data_table = source_table.replace("HistoryDaily", "MasterData")
            logger.info(f"Processing {source_table}...")     
        
            key_columns, data_columns = get_table_key_and_data_columns(master_data_table)
            key_columns_str = ", ".join([f'"{col["name"]}"' for col in key_columns])

            # We process each data column
            for col in data_columns:
                with engine.begin() as conn:
                    col_name = col['name']
                    logger.info(f"Processing {source_table} column {col_name}...")
                    # 1. Promote to Weekly (Insert/Update)
                    # We insert the constant value. We primarily use min(val) since min=max.
                    
                    promote_sql = f"""
                        INSERT INTO {target_table} (
                            year, week, {key_columns_str}, "{col_name}"
                        )
                        SELECT
                            strftime('%Y', snapshot_date) as year,
                            strftime('%W', snapshot_date) as week,
                            {key_columns_str},
                            min("{col_name}") as val
                        FROM {source_table}
                        WHERE "{col_name}" IS NOT NULL
                        GROUP BY strftime('%Y-%W', snapshot_date), {key_columns_str}
                        HAVING 
                            (min("{col_name}") = max("{col_name}")) AND
                            (
                                (CAST((JULIANDAY(MAX(snapshot_date)) - JULIANDAY(MIN(snapshot_date))) AS INTEGER) = 6)
                            )
                        ON CONFLICT(year, week, {key_columns_str}) 
                        DO UPDATE SET "{col_name}" = excluded."{col_name}"
                    """
                    
                    try:
                        result = conn.execute(text(promote_sql))
                        affected = result.rowcount
                        if affected > 0:
                            logger.info(f"Promoted {affected} rows for column {col_name}.")
                    except Exception as e:
                        conn.rollback()
                        logger.error(f"Error promoting column {col_name}: {e}")
                        continue
                    
                    # 2. Null out in Daily
                    # Only if the column is nullable in source
        
                    null_out_sql = f"""
                        UPDATE {source_table}
                        SET "{col_name}" = NULL
                        WHERE ROWID IN (
                            SELECT d.ROWID
                            FROM {source_table} d
                            JOIN (
                                SELECT {key_columns_str}, strftime('%W-%Y', snapshot_date) as wk_grp
                                FROM {source_table}
                                WHERE "{col_name}" IS NOT NULL
                                GROUP BY {key_columns_str}, strftime('%W-%Y', snapshot_date)
                                HAVING 
                                    (min("{col_name}") = max("{col_name}")) AND
                                    (
                                        (CAST((JULIANDAY(MAX(snapshot_date)) - JULIANDAY(MIN(snapshot_date))) AS INTEGER) = 6)
                                    )
                            ) g ON """ + " AND ".join([f'd."{key_col["name"]}" = g."{key_col["name"]}"' for key_col in key_columns]) + f"""
                            WHERE d."{col_name}" IS NOT NULL
                            AND strftime('%W-%Y', d.snapshot_date) = g.wk_grp
                        )
                    """
                    try:
                        
                        result = conn.execute(text(null_out_sql))
                        if result.rowcount > 0:
                            logger.info(f"Nulled out {result.rowcount} rows for column {col_name} in Daily table.")
                    except Exception as e:
                        conn.rollback()
                        logger.error(f"Error nulling out column {col_name}: {e}")

        logger.info(f"Data aging process_batch completed in {round(time.time() - start_time, 2)}s.")

    def _promote_data_from_daily_to_weekly(source_table: str):
        start_time = time.time()

        engine = get_database_engine()
        table = source_table

        daily_table = f"{table}HistoryDaily"
        weekly_table = f"{table}HistoryWeekly"     
        master_data_table = f"{table}MasterData" 
        logger.info(f"Processing {weekly_table}...")     
    
        key_columns, data_columns = get_table_key_and_data_columns(master_data_table)
        key_columns_str = ", ".join([f'"{col["name"]}"' for col in key_columns])

        # We process each data column
        for col in data_columns:
            with engine.begin() as conn:
                col_name = col['name']
                logger.info(f"Processing {source_table} column {col_name}...")
                # 1. Promote to Weekly (Insert/Update)
                # We insert the constant value. We primarily use min(val) since min=max.
                
                promote_sql = f"""
                    INSERT INTO {weekly_table} (
                        year, week, {key_columns_str}, "{col_name}"
                    )
                    SELECT
                        strftime('%Y', snapshot_date) as year,
                        strftime('%W', snapshot_date) as week,
                        {key_columns_str},
                        min("{col_name}") as val
                    FROM {daily_table}
                    WHERE "{col_name}" IS NOT NULL
                        AND strftime('%Y-%W', snapshot_date) < strftime('%Y-%W', 'now') -- exclude current week
                        AND ({key_columns_str}) NOT IN (
                            SELECT 
                                {key_columns_str} 
                            FROM {master_data_table} 
                            WHERE "{col_name}" IS NOT NULL
                        )
                    GROUP BY strftime('%W-%Y', snapshot_date), {key_columns_str}
                    HAVING 
                        (min("{col_name}") = max("{col_name}"))
                    ON CONFLICT(year, week, {key_columns_str}) 
                    DO UPDATE SET "{col_name}" = excluded."{col_name}"
                """
                
                try:
                    affected = execute_sql(conn, promote_sql, weekly_table, 'UPSERT', f"Promote column {col_name} from Daily to Weekly")
                    if affected > 0:
                        logger.info(f"Promoted {affected} rows for column {col_name}.")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error promoting column {col_name} to Weekly: {e}")
                    continue
                
                # 2. Null out in Daily
    
                null_out_sql = f"""
                    UPDATE {daily_table}
                    SET "{col_name}" = NULL
                    WHERE 
                    "{col_name}" IS NOT NULL
                    AND ( 
                        CAST(strftime('%Y', snapshot_date) AS INT), 
                        CAST(strftime('%W', snapshot_date) as INT),
                        {key_columns_str}
                    ) IN (
                        SELECT
                            year,
                            week,
                            {key_columns_str}
                        FROM {weekly_table} 
                        WHERE "{col_name}" IS NOT NULL
                    )          
                """
                try:
                    affected = execute_sql(conn, null_out_sql, daily_table, 'UPDATE', f"Null out column {col_name} in Daily after promotion to Weekly")
                    if affected > 0:
                        logger.info(f"Nulled out {affected} rows for column {col_name} in Daily table.")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error nulling out column {col_name}: {e}")
        logger.info(f"Data promoted from daily to weekly in {round(time.time() - start_time, 2)}s.")

    def _promote_data_from_weekly_to_monthly(source_table: str):
        start_time = time.time()
        
        engine = get_database_engine()
        table = source_table
 
        daily_table = f"{table}HistoryDaily"
        weekly_table = f"{table}HistoryWeekly"
        monthly_table = f"{table}HistoryMonthly"     
        master_data_table = f"{table}MasterData" 
        history_view = f"{table}History" 
        logger.info(f"Processing {monthly_table}...")     
    
        key_columns, data_columns = get_table_key_and_data_columns(master_data_table)
        key_columns_str = ", ".join([f'"{col["name"]}"' for col in key_columns])

        # We process each data column
        for col in data_columns:
            with engine.begin() as conn:
                col_name = col['name']
                logger.info(f"Processing {source_table} column {col_name}...")
                # 1. Promote to Monthly (Insert/Update)
                # We insert the constant value. We primarily use min(val) since min=max.
                
                promote_sql = f"""
                    INSERT INTO {monthly_table} (
                        year, month, {key_columns_str}, "{col_name}"
                    )
                    SELECT
                        strftime('%Y', date) as year,
                        strftime('%m', date) as month,
                        {key_columns_str},
                        min("{col_name}") as val
                    FROM {history_view}
                    WHERE "{col_name}" IS NOT NULL
                        AND strftime('%Y-%m', date) < strftime('%Y-%m', 'now') -- exclude current month
                        AND (year, month, {key_columns_str}) NOT IN (
                            SELECT 
                                year, 
                                month, 
                                {key_columns_str} 
                            FROM {monthly_table} 
                            WHERE "{col_name}" IS NOT NULL
                        )
                        AND ({key_columns_str}) NOT IN (
                            SELECT 
                                {key_columns_str} 
                            FROM {master_data_table} 
                            WHERE "{col_name}" IS NOT NULL
                        )
                    GROUP BY strftime('%Y-%m', date), {key_columns_str}
                    HAVING 
                        (min("{col_name}") = max("{col_name}"))
                    ON CONFLICT(year, month, {key_columns_str}) 
                    DO UPDATE SET "{col_name}" = excluded."{col_name}"
                """
                
                try:
                    affected = execute_sql(conn, promote_sql, monthly_table, 'UPSERT', f"Promote column {col_name} from Weekly to Monthly")
                    if affected > 0:
                        logger.info(f"Promoted {affected} rows to Monthly for column {col_name}.")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error promoting column {col_name} to Monthly: {e}")
                    continue
                
                # 2. Null out in Weekly

                null_out_sql = f"""
                    UPDATE {weekly_table}
                    SET "{col_name}" = NULL
                    WHERE 
                    "{col_name}" IS NOT NULL
                    AND ( 
                        year, 
                        week,
                        {key_columns_str}
                    ) IN (
                        SELECT
                            CAST(strftime('%Y', date) AS INT) AS ayear,
                            CAST(strftime('%W', date) AS INT) AS aweek,
                            {", ".join([f'a."{key_col["name"]}"' for key_col in key_columns])}
                        FROM {history_view} AS a 
                        LEFT OUTER JOIN {monthly_table} AS b
                        ON ayear = b.year AND CAST(strftime('%m', date) AS INT) = b.month 
                            AND {" AND ".join([f'a."{key_col["name"]}" = b."{key_col["name"]}"' for key_col in key_columns])}
                        GROUP BY ayear, aweek, {", ".join([f'a."{key_col["name"]}"' for key_col in key_columns])}
                        HAVING MIN(COALESCE(b."{col_name}",-99999)) = MAX(b."{col_name}")
                    )          
                """
                try:
                    affected = execute_sql(conn, null_out_sql, weekly_table, 'UPDATE', f"Null out column {col_name} in Weekly after promotion to Monthly")
                    if affected > 0:
                        logger.info(f"Nulled out {affected} rows for column {col_name} in Weekly table.")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error nulling out column {col_name}: {e}")
        logger.info(f"Data promoted from weekly to monthly in {round(time.time() - start_time, 2)}s.")

    def _promote_data_to_master_data(source_table: str):
        start_time = time.time()
        
        engine = get_database_engine()
        table = source_table

        daily_table = f"{table}HistoryDaily"
        weekly_table = f"{table}HistoryWeekly"
        monthly_table = f"{table}HistoryMonthly"     
        master_data_table = f"{table}MasterData" 
        history_view = f"{table}History" 
        logger.info(f"Processing {monthly_table}...")     
    
        key_columns, data_columns = get_table_key_and_data_columns(master_data_table)
        key_columns_str = ", ".join([f'"{col["name"]}"' for col in key_columns])

        # We process each data column
        for col in data_columns:
            with engine.begin() as conn:
                col_name = col['name']
                logger.info(f"Processing {source_table} column {col_name}...")
                # 1. Promote to Master Data (Insert/Update)
                # We insert the constant value. We primarily use min(val) since min=max.
                
                promote_sql = f"""
                    INSERT INTO {master_data_table} (
                        {key_columns_str}, "{col_name}"
                    )
                    SELECT
                        {key_columns_str},
                        min("{col_name}") as val
                    FROM {history_view}
                    WHERE "{col_name}" IS NOT NULL
                        AND ({key_columns_str}) NOT IN (
                            SELECT 
                                {key_columns_str} 
                            FROM {master_data_table} 
                            WHERE "{col_name}" IS NOT NULL
                        )
                    GROUP BY {key_columns_str}
                    HAVING 
                        (min("{col_name}") = max("{col_name}"))
                        AND ( 
                            min(date) < date('now', '-365 days')
                            OR EXISTS(
                                SELECT * 
                                FROM "DataAgingFieldClassification" 
                                WHERE table_name = '{source_table}' 
                                  AND field_name = '{col_name}' 
                                  AND tier = 'Master'
                            )
                        )
                    ON CONFLICT({key_columns_str}) 
                    DO UPDATE SET "{col_name}" = excluded."{col_name}"
                """
                
                try:
                    affected = execute_sql(conn, promote_sql, master_data_table, 'UPSERT', f"Promote column {col_name} to Master Data")
                    if affected > 0:
                        logger.info(f"Promoted {affected} rows to Master Data for {source_table} column {col_name}.")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error promoting {source_table} column {col_name} to Master Data: {e}")
                    continue
                
                # 2. Null out in Monthly

                null_out_sql = f"""
                    UPDATE {monthly_table}
                    SET "{col_name}" = NULL
                    WHERE 
                    "{col_name}" IS NOT NULL
                    AND (
                        {key_columns_str}
                    ) IN (
                        SELECT
                            {key_columns_str}
                        FROM {master_data_table} 
                        WHERE "{col_name}" IS NOT NULL
                    )          
                """
                try:
                    affected = execute_sql(conn, null_out_sql, monthly_table, 'UPDATE', f"Null out column {col_name} in Monthly after promotion to Master Data")
                    if affected > 0:
                        logger.info(f"Nulled out {affected} rows for column {col_name} in {monthly_table}.")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error nulling out {monthly_table} column {col_name}: {e}")

                null_out_sql = f"""
                    UPDATE {weekly_table}
                    SET "{col_name}" = NULL
                    WHERE 
                    "{col_name}" IS NOT NULL
                    AND (
                        {key_columns_str}
                    ) IN (
                        SELECT
                            {key_columns_str}
                        FROM {master_data_table} 
                        WHERE "{col_name}" IS NOT NULL
                    )          
                """
                try:
                    affected = execute_sql(conn, null_out_sql, weekly_table, 'UPDATE', f"Null out column {col_name} in Weekly after promotion to Master Data")
                    if affected > 0:
                        logger.info(f"Nulled out {affected} rows for column {col_name} in {weekly_table}.")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error nulling out {monthly_table} column {col_name}: {e}")

                null_out_sql = f"""
                    UPDATE {daily_table}
                    SET "{col_name}" = NULL
                    WHERE 
                    "{col_name}" IS NOT NULL
                    AND (
                        {key_columns_str}
                    ) IN (
                        SELECT
                            {key_columns_str}
                        FROM {master_data_table} 
                        WHERE "{col_name}" IS NOT NULL
                    )          
                """
                try:
                    affected = execute_sql(conn, null_out_sql, daily_table, 'UPDATE', f"Null out column {col_name} in Daily after promotion to Master Data")
                    if affected > 0:
                        logger.info(f"Nulled out {affected} rows for column {col_name} in {weekly_table}.")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error nulling out {monthly_table} column {col_name}: {e}")
        logger.info(f"Data promoted to Master Data in {round(time.time() - start_time, 2)}s.")