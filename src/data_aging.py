import logging
import time
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import text
from config import HISTORY_ENABLED_TABLES
from src.database import get_database_engine, execute_sql, get_table_key_and_data_columns, select_into_dataframe
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

        # only run on mondays
        if datetime.now().weekday() != 0:
            logger.info(f"Data aging skipped - runs only on Mondays.")
            return

        logger.info(f"Starting data aging for {source_table}...")
        start_time = time.time()
        
        DataAgingService._insert_key_master_data(source_table)
        DataAgingService._promote_data_from_daily_to_weekly(source_table)
        DataAgingService._promote_data_from_weekly_to_monthly(source_table)
        DataAgingService._promote_data_to_master_data(source_table)

        DataAgingService._clean_up_history_tables(source_table)

        end_time = time.time()
        total_duration = int(end_time - start_time)
        logger.info(f"Data aging completed for {source_table} in {total_duration}s ({total_duration / 60:.1f} minutes)")

    def _insert_key_master_data(source_table: str):
        start_time = time.time()
        
        engine = get_database_engine()

        daily_table = f"{source_table}HistoryDaily"    
        master_data_table = f"{source_table}MasterData" 

        key_columns, _ = get_table_key_and_data_columns(master_data_table)
        key_columns_str = ", ".join([f'"{col["name"]}"' for col in key_columns])

        # We process each data column

        with engine.begin() as conn:
            logger.info(f"Processing {source_table} key {key_columns_str}...")
            # Insert key to master data table
            
            insert_sql = f"""
                INSERT INTO {master_data_table} (
                    {key_columns_str}
                )
                SELECT DISTINCT
                    {key_columns_str}
                FROM ({daily_table})
                WHERE 1=1 -- needed because of Parsing Ambiguity. Check SQLite documentation
                ON CONFLICT({key_columns_str})
                DO NOTHING
            """
            
            try:
                affected = execute_sql(conn, insert_sql, master_data_table, 'UPSERT', f"Insert keys to Master Data")
            except Exception as e:
                conn.rollback()
                logger.error(f"Error inserting keys to Master Data: {e}")
            
        logger.info(f"Inserted keys to Master Data in {round(time.time() - start_time, 2)}s.")

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
            col_name = col['name']
            logger.info(f"Processing {source_table} column {col_name}...")
            if is_classified_for_master_data(source_table, col_name):
                logger.info(f"Skipping column {col_name} as it is not classified for Weekly promotion.")
                continue

            with engine.begin() as conn:
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
                
                if affected > 0:
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
        history_select = get_history_select_statement(source_table, optimized=False)
        logger.info(f"Processing {monthly_table}...")     
    
        key_columns, data_columns = get_table_key_and_data_columns(master_data_table)
        key_columns_str = ", ".join([f'"{col["name"]}"' for col in key_columns])

        # We process each data column
        for col in data_columns:
            col_name = col['name']
            logger.info(f"Processing {source_table} column {col_name}...")
            if is_classified_for_master_data(source_table, col_name):
                logger.info(f"Skipping column {col_name} as it is not classified for Monthly promotion.")
                continue
            with engine.begin() as conn:
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
                    FROM ({history_select})
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
                
                if affected > 0:
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
                            FROM ({history_select}) AS a 
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
        history_select = get_history_select_statement(source_table, optimized=False)
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
                    FROM ({history_select})
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
                
                if affected > 0:
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

    def _clean_up_history_tables(source_table: str):
        """
        Cleans up history tables by removing entries that are fully null across all data columns.
        This helps to reduce storage and improve performance.
        """
        engine = get_database_engine()

        logger.info(f"Cleaning up history tables for {source_table}")
        # Determine the underlying history tables
        # For simplicity, we assume the naming convention is consistent
        daily_table = f"{source_table}HistoryDaily"
        weekly_table = f"{source_table}HistoryWeekly"
        monthly_table = f"{source_table}HistoryMonthly"

        for table in [daily_table, weekly_table, monthly_table]:
            key_columns, data_columns = get_table_key_and_data_columns(source_table)
            data_column_names = [col['name'] for col in data_columns]

            # Build the SQL to delete rows where all data columns are NULL
            null_conditions = " AND ".join([f'"{col}" IS NULL' for col in data_column_names])
            delete_sql = f"""
                DELETE FROM {table}
                WHERE {null_conditions}
            """

            with engine.begin() as conn:
                try:
                    affected = execute_sql(conn, delete_sql, table, 'DELETE', f"Clean up null rows in {table}")
                    if affected > 0:
                        logger.info(f"Deleted {affected} fully null rows from {table}.")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error cleaning up {table}: {e}")

_MASTER_DATA_CLASSIFICATION_CACHE = None

def is_classified_for_master_data(source_table: str, column_name: str) -> bool:
    global _MASTER_DATA_CLASSIFICATION_CACHE
    if _MASTER_DATA_CLASSIFICATION_CACHE is None:
        classification_check_sql = select_into_dataframe(f"""
            SELECT table_name, field_name
            FROM DataAgingFieldClassification
            WHERE tier = 'Master'
        """)
        
        _MASTER_DATA_CLASSIFICATION_CACHE = {}
        if not classification_check_sql.empty:
            # Group by table_name and create sets of field_names
            grouped = classification_check_sql.groupby('table_name')['field_name'].apply(set)
            _MASTER_DATA_CLASSIFICATION_CACHE = grouped.to_dict()
        
    return source_table in _MASTER_DATA_CLASSIFICATION_CACHE and column_name in _MASTER_DATA_CLASSIFICATION_CACHE[source_table]     

def get_history_select_statement(table_name: str, optimized: bool = True):
    """
    Select statement for history view of the specified table.
    """

    key_columns, data_columns = get_table_key_and_data_columns(table_name)
    key_column_definitions_str = ",\n\t\t".join([f'master_data."{col["name"]}"' for col in key_columns])
    data_column_definitions = []
    for col in data_columns:
        col_name = col["name"]
        if is_classified_for_master_data(table_name, col["name"]) and optimized:
            data_column_definitions.append(f'master_data."{col_name}" as "{col_name}"')
        else:
            data_column_definitions.append(f"""
            coalesce(
                daily."{col["name"]}",
                weekly."{col["name"]}",
                monthly."{col["name"]}",
                master_data."{col["name"]}"  
            ) as "{col_name}"                            
            """.strip()                               
            )
    data_column_definitions_str = ",\n\t\t".join(data_column_definitions)
    
    column_definitions_str = f"""
        {key_column_definitions_str},
        {data_column_definitions_str}
    """.strip()
    
    key_columns, _ = get_table_key_and_data_columns(table_name)
    key_columns_on_condition_str_daily = " AND ".join([f'master_data."{col["name"]}" = daily."{col["name"]}"' for col in key_columns])
    key_columns_on_condition_str_weekly = " AND ".join([f'master_data."{col["name"]}" = weekly."{col["name"]}"' for col in key_columns])
    key_columns_on_condition_str_monthly = " AND ".join([f'master_data."{col["name"]}" = monthly."{col["name"]}"' for col in key_columns])

    select_statement_sql =  f"""
    SELECT
        dates.date,
        {column_definitions_str}
    FROM
        "DatesHistory" as dates
        CROSS JOIN "{table_name}MasterData" as master_data 
        LEFT JOIN "{table_name}HistoryDaily" as daily
        ON dates.date = daily.snapshot_date
        AND {key_columns_on_condition_str_daily}
        LEFT JOIN "{table_name}HistoryWeekly" as weekly 
        ON dates.year = weekly.year
        AND dates.week = weekly.week
        AND {key_columns_on_condition_str_weekly}
        LEFT JOIN "{table_name}HistoryMonthly" as monthly 
        ON dates.year = monthly.year
        AND dates.month = monthly.month
        AND {key_columns_on_condition_str_monthly}
    """
    return select_statement_sql

def get_history_enabled_views():
    
    pattern_search = f" OR ".join([f"sql LIKE '%{table}%' " for table in HISTORY_ENABLED_TABLES])
    history_enabled_views = select_into_dataframe("""
        SELECT name AS view_name
        FROM sqlite_schema
        WHERE type='view' AND {pattern_search}
    """)
    
    return history_enabled_views

