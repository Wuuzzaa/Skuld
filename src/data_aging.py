import logging
import time
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import text
from config import HISTORY_ENABLED_TABLES
from src.database import execute_sql, get_postgres_engine, get_table_key_and_data_columns, select_into_dataframe
import pathlib
from datetime import date, timedelta

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
        # if not is_monday():
        #     logger.info(f"Data aging skipped - runs only on Mondays.")
        #     return

        logger.info(f"Starting data aging for {source_table}...")
        start_time = time.time()
        
        DataAgingService._insert_key_master_data(source_table)
        DataAgingService._promote_data_to_master_data(source_table)
        # DataAgingService._promote_data_from_weekly_to_monthly(source_table)
        # DataAgingService._promote_data_from_daily_to_weekly(source_table)

        DataAgingService._clean_up_history_tables(source_table)

        end_time = time.time()
        total_duration = int(end_time - start_time)
        logger.info(f"Data aging completed for {source_table} in {total_duration}s ({total_duration / 60:.1f} minutes)")

    def _insert_key_master_data(source_table: str):
        start_time = time.time()
        

        daily_table = f"{source_table}HistoryDaily"  
        weekly_table = f"{source_table}HistoryWeekly"
        monthly_table = f"{source_table}HistoryMonthly"  
        master_data_table = f"{source_table}MasterData" 

        key_columns, _ = get_table_key_and_data_columns(master_data_table)
        key_columns_str = ", ".join([f'"{col["name"]}"' for col in key_columns])

        logger.info(f"Processing {source_table} key {key_columns_str}...")
        # Insert key to master data table
        
        insert_sql = f"""
            INSERT INTO "{master_data_table}" AS ORIGINAL (
                FROM_DATE,
	            TO_DATE,
                {key_columns_str}
            )
            SELECT
                MIN(SNAPSHOT_DATE) AS FROM_DATE,
	            MAX(SNAPSHOT_DATE) AS TO_DATE,
                {key_columns_str}
            FROM "{daily_table}"
            GROUP BY {key_columns_str}
            ON CONFLICT ({key_columns_str}) DO UPDATE
            SET
                FROM_DATE = CASE
                    WHEN ORIGINAL.FROM_DATE IS NULL OR EXCLUDED.FROM_DATE < ORIGINAL.FROM_DATE THEN EXCLUDED.FROM_DATE
                    ELSE ORIGINAL.FROM_DATE
                END,
                TO_DATE = CASE
                    WHEN ORIGINAL.FROM_DATE IS NULL OR EXCLUDED.TO_DATE > ORIGINAL.TO_DATE THEN EXCLUDED.TO_DATE
                    ELSE ORIGINAL.TO_DATE
                END;
        """

        logger.info(f"Start execution: Insert keys to Master Data {master_data_table}")
        pg_engine = get_postgres_engine()
        with pg_engine.begin() as conn:
            execute_sql(conn, insert_sql, master_data_table, 'UPSERT', f"Insert keys to Master Data")

        logger.info(f"Inserted keys to Master Data in {round(time.time() - start_time, 2)}s.")

    def _promote_data_from_daily_to_weekly(source_table: str):
        start_time = time.time()

        pg_engine = get_postgres_engine()
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
            col_type = col['type']

            logger.info(f"Processing {source_table} column {col_name}...")
            if is_classified_for_master_data(source_table, col_name) or is_classified_for_daily(source_table, col_name) or is_classified_for_monthly(source_table, col_name):
                logger.info(f"Skipping column {col_name} as it is not classified for Weekly promotion.")
                continue
            
            history_select = get_history_select_statement(source_table, optimized=True, needed_data_columns=[col_name], min_bucket='weekly')
            # key_columns_not_exist_higher_bucket_str = " AND ".join([f'DAILY."{col["name"]}" = HIGHER_BUCKET."{col["name"]}"' for col in key_columns])
            key_columns_not_exist_higher_bucket_str = " AND ".join([f'SUBQUERY."{col["name"]}" = HIGHER_BUCKET."{col["name"]}"' for col in key_columns])


            with pg_engine.begin() as conn:
                # 1. Promote to Weekly (Insert/Update)
                # We insert the constant value. We primarily use min(val) since min=max.
                
                # pg_promote_sql = f"""
                #     INSERT INTO "{weekly_table}" (
                #         isoyear, week, {key_columns_str}, "{col_name}"
                #     )
                #     SELECT
                #         EXTRACT(ISOYEAR FROM snapshot_date::date)::int as isoyear,
                #         EXTRACT(WEEK FROM snapshot_date::date)::int as week,
                #         {key_columns_str},
                #         MIN("{col_name}") as val
                #     FROM "{daily_table}" AS DAILY
                #     WHERE "{col_name}" IS NOT NULL
                #         -- AND date_trunc('week', snapshot_date::date) < date_trunc('week', CURRENT_DATE) -- exclude current week
                #         AND NOT EXISTS (
                #             SELECT 
                #                 1
                #             FROM ({history_select}) AS HIGHER_BUCKET
                #             WHERE DAILY.snapshot_date = HIGHER_BUCKET.date
                #             AND {key_columns_not_exist_higher_bucket_str}
                #             -- AND DAILY."{col_name}" = HIGHER_BUCKET."{col_name}"
                #             AND "{col_name}" IS NOT NULL
                #         )
                #     GROUP BY isoyear, week, {key_columns_str}
                #     HAVING 
                #         (MIN("{col_name}") = MAX("{col_name}"))
                #     ON CONFLICT(isoyear, week, {key_columns_str}) 
                #     DO UPDATE SET "{col_name}" = excluded."{col_name}"
                # """

                pg_promote_sql = f"""
                    INSERT INTO "{weekly_table}" (
                        isoyear, week, {key_columns_str}, "{col_name}"
                    )
                    SELECT * FROM (
                    SELECT
                        EXTRACT(ISOYEAR FROM snapshot_date::date)::int as isoyear,
                        EXTRACT(WEEK FROM snapshot_date::date)::int as week,
                        {key_columns_str},
                        MIN("{col_name}") as "{col_name}"
                    FROM "{daily_table}" AS DAILY
                    WHERE "{col_name}" IS NOT NULL
                        -- AND date_trunc('week', snapshot_date::date) < date_trunc('week', CURRENT_DATE) -- exclude current week
                    GROUP BY isoyear, week, {key_columns_str}
                    HAVING 
                        (MIN("{col_name}") = MAX("{col_name}"))
                        OR EXISTS(
                            SELECT 1 
                            FROM "DataAgingFieldClassification" AS dac
                            WHERE dac.table_name = '{source_table}' 
                                AND dac.field_name = '{col_name}' 
                                AND dac.tier = 'Weekly'
                        )     
                    ) AS SUBQUERY
                    WHERE NOT EXISTS (
                            SELECT 
                                1
                            FROM ({history_select}) AS HIGHER_BUCKET
                            WHERE SUBQUERY.isoyear = HIGHER_BUCKET.isoyear
                            AND SUBQUERY.week = HIGHER_BUCKET.week
                            AND {key_columns_not_exist_higher_bucket_str}
                            AND SUBQUERY."{col_name}" = HIGHER_BUCKET."{col_name}"
                            AND HIGHER_BUCKET."{col_name}" IS NOT NULL
                        )
                    ON CONFLICT(isoyear, week, {key_columns_str}) 
                    DO UPDATE SET "{col_name}" = excluded."{col_name}"
                """

                if col_type.lower() == 'boolean':
                    pg_promote_sql = pg_promote_sql.replace(f'MIN("{col_name}")', f'BOOL_AND("{col_name}")')
                    pg_promote_sql = pg_promote_sql.replace(f'MAX("{col_name}")', f'BOOL_OR("{col_name}")')
                
                logger.debug(pg_promote_sql)
                try:
                    affected = execute_sql(conn, pg_promote_sql, weekly_table, 'UPSERT', f"Promote column {col_name} from Daily to Weekly")
                    if affected > 0:
                        logger.info(f"[PostgreSQL] Promoted {affected} rows for column {col_name}.")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"[PostgreSQL] Error promoting column {col_name} to Weekly: {e}")
                    continue
                
        logger.info(f"Data promoted from daily to weekly in {round(time.time() - start_time, 2)}s.")

    def _promote_data_from_weekly_to_monthly(source_table: str):
        # if not is_first_weekday_of_month():
        #     logger.info(f"Data aging promotion to month skipped - runs only on first weekday of the month.")
        #     return
        start_time = time.time()
        
        pg_engine = get_postgres_engine()
        table = source_table
 
        daily_table = f"{table}HistoryDaily"
        weekly_table = f"{table}HistoryWeekly"
        monthly_table = f"{table}HistoryMonthly"     
        master_data_table = f"{table}MasterData" 
        history_view = f"{table}History" 
        key_columns, data_columns = get_table_key_and_data_columns(master_data_table)
        key_columns_str = ", ".join([f'"{col["name"]}"' for col in key_columns])

        # key_columns_not_exist_month_str = " AND ".join([f'HISTORY_SELECT."{col["name"]}" = MONTHLY."{col["name"]}"' for col in key_columns])
        # key_columns_not_exist_master_str = " AND ".join([f'HISTORY_SELECT."{col["name"]}" = MASTER_DATA."{col["name"]}"' for col in key_columns])
        key_columns_not_exist_month_str = " AND ".join([f'SUBQUERY."{col["name"]}" = MONTHLY."{col["name"]}"' for col in key_columns])
        key_columns_not_exist_master_str = " AND ".join([f'SUBQUERY."{col["name"]}" = MASTER_DATA."{col["name"]}"' for col in key_columns])


        logger.info(f"Processing {monthly_table}...")     
    

        # We process each data column
        for col in data_columns:
            col_name = col['name']
            history_select = get_history_select_statement(source_table, optimized=False, needed_data_columns=[col_name])
            logger.info(f"Processing {source_table} column {col_name}...")
            if is_classified_for_master_data(source_table, col_name) or is_classified_for_daily(source_table, col_name) or is_classified_for_weekly(source_table, col_name):
                logger.info(f"Skipping column {col_name} as it is not classified for Monthly promotion.")
                continue
  
            with pg_engine.begin() as conn:
                # 1. Promote to Monthly (Insert/Update)
                # We insert the constant value. We primarily use min(val) since min=max.
                
                # promote_sql = f"""
                #     INSERT INTO "{monthly_table}" (
                #         year, month, {key_columns_str}, "{col_name}"
                #     )
                #     SELECT
                #         year,
                #         month,
                #         {key_columns_str},
                #         MIN("{col_name}") as val
                #     FROM ({history_select}) AS HISTORY_SELECT
                #     WHERE "{col_name}" IS NOT NULL
                #         AND NOT EXISTS (
                #             SELECT 
                #                 1 
                #             FROM "{monthly_table}" AS MONTHLY
                #             WHERE HISTORY_SELECT.year = MONTHLY.year
                #             AND HISTORY_SELECT.month = MONTHLY.month
                #             AND {key_columns_not_exist_month_str} 
                #             AND HISTORY_SELECT."{col_name}" = MONTHLY."{col_name}"
                #             AND "{col_name}" IS NOT NULL
                #         )
                #         AND NOT EXISTS (
                #             SELECT 
                #                 1 
                #             FROM "{master_data_table}" AS MASTER_DATA
                #             WHERE {key_columns_not_exist_master_str}
                #             AND HISTORY_SELECT."{col_name}" = MASTER_DATA."{col_name}"
                #             AND "{col_name}" IS NOT NULL
                #         )
                #     GROUP BY year, month, {key_columns_str}
                #     HAVING 
                #         (MIN("{col_name}") = MAX("{col_name}"))
                #     ON CONFLICT(year, month, {key_columns_str}) 
                #     DO UPDATE SET "{col_name}" = excluded."{col_name}"
                # """

                promote_sql = f"""
                    INSERT INTO "{monthly_table}" (
                        year, month, {key_columns_str}, "{col_name}"
                    )
                    SELECT * FROM (
                    SELECT
                        year,
                        month,
                        {key_columns_str},
                        MIN("{col_name}") as "{col_name}"
                    FROM ({history_select}) AS HISTORY_SELECT
                    WHERE "{col_name}" IS NOT NULL
                    GROUP BY year, month, {key_columns_str}
                    HAVING 
                        (MIN("{col_name}") = MAX("{col_name}"))
                        OR EXISTS(
                            SELECT 1 
                            FROM "DataAgingFieldClassification" AS dac
                            WHERE dac.table_name = '{source_table}' 
                                AND dac.field_name = '{col_name}' 
                                AND dac.tier = 'Monthly'
                        )     
                    ) AS SUBQUERY
                    WHERE "{col_name}" IS NOT NULL
                        AND NOT EXISTS (
                            SELECT 
                                1 
                            FROM "{monthly_table}" AS MONTHLY
                            WHERE SUBQUERY.year = MONTHLY.year
                            AND SUBQUERY.month = MONTHLY.month
                            AND {key_columns_not_exist_month_str} 
                            AND SUBQUERY."{col_name}" = MONTHLY."{col_name}"
                            AND MONTHLY."{col_name}" IS NOT NULL
                        )
                        AND NOT EXISTS (
                            SELECT 
                                1 
                            FROM "{master_data_table}" AS MASTER_DATA
                            WHERE {key_columns_not_exist_master_str}
                            AND SUBQUERY."{col_name}" = MASTER_DATA."{col_name}"
                            AND MASTER_DATA."{col_name}" IS NOT NULL
                        )
                    ON CONFLICT(year, month, {key_columns_str}) 
                    DO UPDATE SET "{col_name}" = excluded."{col_name}"
                """
                
                try:
                    affected = execute_sql(conn, promote_sql, monthly_table, 'UPSERT', f"Promote column {col_name} to Monthly")
                    if affected > 0:
                        logger.info(f"[PostgreSQL] Promoted {affected} rows to Monthly for column {col_name}.")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"[PostgreSQL] Error promoting column {col_name} to Monthly: {e}")
                    raise e     

        logger.info(f"Data promoted from weekly to monthly in {round(time.time() - start_time, 2)}s.")

    def _promote_data_to_master_data(source_table: str):
        start_time = time.time()

        pg_engine = get_postgres_engine()
        table = source_table

        daily_table = f"{table}HistoryDaily"
        weekly_table = f"{table}HistoryWeekly"
        monthly_table = f"{table}HistoryMonthly"     
        master_data_table = f"{table}MasterData" 
        history_view = f"{table}History" 
        logger.info(f"Processing {monthly_table}...")     
    
        key_columns, data_columns = get_table_key_and_data_columns(master_data_table)
        key_columns_str = ", ".join([f'"{col["name"]}"' for col in key_columns])
        # key_columns_not_exist_master_str = " AND ".join([f'HISTORY_SELECT."{col["name"]}" = MASTER_DATA."{col["name"]}"' for col in key_columns])
        key_columns_not_exist_master_str = " AND ".join([f'SUBQUERY."{col["name"]}" = MASTER_DATA."{col["name"]}"' for col in key_columns])


        # We process each data column
        for col in data_columns:
            col_name = col['name']
            col_type = col['type']
            if is_classified_for_daily(source_table, col_name) or is_classified_for_weekly(source_table, col_name) or is_classified_for_monthly(source_table, col_name):
                logger.info(f"Skipping column {col_name} as it is not classified for Master Data promotion.")
                continue

            with pg_engine.begin() as conn:
                history_select = get_history_select_statement(source_table, optimized=False, needed_data_columns=[col_name])
                logger.info(f"[PostgreSQL] Processing {source_table} column {col_name}...")
                # 1. Promote to Master Data (Insert/Update)
                # We insert the constant value. We primarily use min(val) since min=max.
                
                # promote_sql = f"""
                #     INSERT INTO "{master_data_table}" (
                #         {key_columns_str}, "{col_name}"
                #     )
                #     SELECT
                #         {key_columns_str},
                #         MIN("{col_name}") as "{col_name}"
                #     FROM ({history_select}) AS HISTORY_SELECT
                #     WHERE "{col_name}" IS NOT NULL
                #         AND NOT EXISTS (
                #             SELECT 
                #                 1 
                #             FROM "{master_data_table}" AS MASTER_DATA
                #             WHERE {key_columns_not_exist_master_str}
                #             --AND  HISTORY_SELECT."{col_name}" = MASTER_DATA."{col_name}"
                #             AND "{col_name}" IS NOT NULL
                #         )
                #     GROUP BY {key_columns_str}
                #     HAVING 
                #         MIN("{col_name}") = MAX("{col_name}")
                #         OR EXISTS(
                #             SELECT 1 
                #             FROM "DataAgingFieldClassification" AS dac
                #             WHERE dac.table_name = '{source_table}' 
                #                 AND dac.field_name = '{col_name}' 
                #                 AND dac.tier = 'Master'
                #         )                
                #     ON CONFLICT({key_columns_str}) 
                #     DO UPDATE SET "{col_name}" = excluded."{col_name}"
                # """

                promote_sql = f"""
                    INSERT INTO "{master_data_table}" (
                        {key_columns_str}, "{col_name}"
                    )
                    SELECT * FROM (
                    SELECT
                        {key_columns_str},
                        MIN("{col_name}") as "{col_name}"
                    FROM ({history_select}) AS HISTORY_SELECT
                    WHERE "{col_name}" IS NOT NULL
                    GROUP BY {key_columns_str}
                    HAVING 
                        MIN("{col_name}") = MAX("{col_name}")
                        OR EXISTS(
                            SELECT 1 
                            FROM "DataAgingFieldClassification" AS dac
                            WHERE dac.table_name = '{source_table}' 
                                AND dac.field_name = '{col_name}' 
                                AND dac.tier = 'Master'
                        )     
                    ) AS SUBQUERY  
                    WHERE NOT EXISTS (
                            SELECT 
                                1 
                            FROM "{master_data_table}" AS MASTER_DATA
                            WHERE {key_columns_not_exist_master_str}
                            AND  SUBQUERY."{col_name}" = MASTER_DATA."{col_name}"
                            AND MASTER_DATA."{col_name}" IS NOT NULL
                        )             
                    ON CONFLICT({key_columns_str}) 
                    DO UPDATE SET "{col_name}" = excluded."{col_name}"
                """

                if col_type.lower() == 'boolean':
                    promote_sql = promote_sql.replace(f'MIN("{col_name}")', f'BOOL_AND("{col_name}")')
                    promote_sql = promote_sql.replace(f'MAX("{col_name}")', f'BOOL_OR("{col_name}")')

                logger.info(f"Start execution: Promote {source_table} column {col_name} to Master Data")
                try:
                    affected = execute_sql(conn, promote_sql, master_data_table, 'UPSERT', f"Promote {source_table} column {col_name} to Master Data")
                    if affected > 0:
                        logger.info(f"[PostgreSQL] Promoted {affected} rows to Master Data for {source_table} column {col_name}.")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"[PostgreSQL] Error promoting {source_table} column {col_name} to Master Data: {e}")
                    continue
                
        logger.info(f"Data promoted to Master Data in {round(time.time() - start_time, 2)}s.")

    def _clean_up_history_tables(source_table: str):
        """
        Cleans up history tables by removing entries that are fully null across all data columns.
        This helps to reduce storage and improve performance.
        """
        pg_engine = get_postgres_engine()

        logger.info(f"Cleaning up history tables for {source_table}")
        # Determine the underlying history tables
        # For simplicity, we assume the naming convention is consistent

        for bucket in ['Daily']: #['Monthly', 'Weekly', 'Daily']:
            table = f"{source_table}History{bucket}"
            key_columns, data_columns = get_table_key_and_data_columns(source_table)
            data_column_names = [col['name'] for col in data_columns]

            key_where_str = " AND ".join([f'original."{col["name"]}" = higher_bucket_data."{col["name"]}"' for col in key_columns])

            # check if data is in higher bucket
            if bucket.lower() == 'daily':
                min_bucket = 'weekly'
                history_where_str = """
                    original.snapshot_date = higher_bucket_data.date
                """
            elif bucket.lower() == 'weekly':
                min_bucket = 'monthly'
                history_where_str = """
                    original.isoyear = higher_bucket_data.isoyear
                    AND original.week = higher_bucket_data.week
                """
            elif bucket.lower() == 'monthly':
                min_bucket = 'master'
                history_where_str = """
                    original.year = higher_bucket_data.year
                    AND original.month = higher_bucket_data.month
                """

            history_select = get_history_select_statement(source_table, optimized=True, min_bucket=min_bucket)
            update_columns = ", ".join([f'"{col}" = CASE WHEN higher_bucket_data."{col}" IS NOT NULL THEN NULL ELSE original."{col}" END' for col in data_column_names])
            null_sql = f"""
                UPDATE "{table}" AS original
                SET {update_columns}
                FROM ({history_select}) AS higher_bucket_data
                WHERE 
                {history_where_str}
                AND {key_where_str}
            """
            logger.info(null_sql)

            logger.info(f"Start execution: NULL columns in {table}")
            with pg_engine.begin() as conn:
                try:
                    affected = execute_sql(conn, null_sql, table, 'UPDATE', f"NULL columns in {table}")
                    if affected > 0:
                        logger.info(f"[PostgreSQL] Nulled columns in {affected} rows from {table}.")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"[PostgreSQL] Error Nulling {table}: {e}")
                    raise e

            # Build the SQL to delete rows where all data columns are NULL
            null_conditions = " AND ".join([f'"{col}" IS NULL' for col in data_column_names])
            delete_sql = f"""
                DELETE FROM "{table}"
                WHERE {null_conditions}
            """

            logger.info(f"Start execution: Clean up NULL rows in {table}")
            with pg_engine.begin() as conn:
                try:
                    affected = execute_sql(conn, delete_sql, table, 'DELETE', f"Clean up NULL rows in {table}")
                    if affected > 0:
                        logger.info(f"[PostgreSQL] Deleted {affected} fully NULL rows from {table}.")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"[PostgreSQL] Error cleaning up {table}: {e}")
                    raise e

            # Build the SQL to clean up dead data on disk
            vacuum_sql = f"""
                VACUUM FULL "{table}"
            """

            logger.info(f"Start execution: Garbage Collector for {table}")
            # Use .connect() instead of .begin() and set isolation_level
            with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                try:
                    affected = execute_sql(conn, vacuum_sql, table, 'VACUUM', f"Clean up dead space for {table}")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"[PostgreSQL] Error cleaning up {table}: {e}")
                    raise e

_DATA_CLASSIFICATION_CACHE = None

def set_data_classification_cache():
    global _DATA_CLASSIFICATION_CACHE
    if _DATA_CLASSIFICATION_CACHE is None:
        df_classification = select_into_dataframe(f"""
            SELECT table_name, field_name, tier
            FROM "DataAgingFieldClassification"
        """)
        
        _DATA_CLASSIFICATION_CACHE = {}
        if not df_classification.empty:
            # Create a nested mapping: {table: {tier: {fields}}}
            for (table, tier), group in df_classification.groupby(['table_name', 'tier']):
                if table not in _DATA_CLASSIFICATION_CACHE:
                    _DATA_CLASSIFICATION_CACHE[table] = {}
                _DATA_CLASSIFICATION_CACHE[table][tier] = set(group['field_name'])

def _check_classification(source_table: str, column_name: str, target_tier: str) -> bool:
    """Internal helper to look up the cache."""
    set_data_classification_cache() # Ensures cache is loaded
    
    table_data = _DATA_CLASSIFICATION_CACHE.get(source_table, {})
    # Look for the specific tier (e.g., 'Master', 'Daily')
    tier_columns = table_data.get(target_tier, set())
    
    return column_name in tier_columns

def is_classified_for_master_data(source_table: str, column_name: str) -> bool:
    return _check_classification(source_table, column_name, 'Master')

def is_classified_for_daily(source_table: str, column_name: str) -> bool:
    return _check_classification(source_table, column_name, 'Daily')

def is_classified_for_weekly(source_table: str, column_name: str) -> bool:
    return _check_classification(source_table, column_name, 'Weekly')   

def is_classified_for_monthly(source_table: str, column_name: str) -> bool:
    return _check_classification(source_table, column_name, 'Monthly')    


def get_history_select_statement(table_name: str, optimized: bool = True, needed_data_columns: list[str] | None = None, min_bucket: str  | None = None) -> str:
    """
    Select statement for history view of the specified table.
    """
    min_bucket =min_bucket.lower() if min_bucket is not None else None
    
    optimized = False

    logger.info(f"Building history select statement for {table_name} with optimized={optimized}, min_bucket={min_bucket}, needed_data_columns={needed_data_columns}")

    buckets = ['daily', 'master'] #['daily', 'weekly', 'monthly', 'master']
    if min_bucket == 'weekly' or min_bucket == 'monthly': # change if weekly or monthly bucket is added
       min_bucket = 'master'

    bucket_map = {
        'daily': "daily",
        'weekly': "weekly",
        'monthly': "monthly",
        'master': "master_data"
    }
    
    # Filter buckets based on min_bucket
    if min_bucket:
        try:
            start_index = buckets.index(min_bucket)
            active_buckets = buckets[start_index:]
        except ValueError:
             # Fallback or error if invalid bucket name passed, treat as no filter or log warning?
             # For now, assuming valid input or defaulting to all if not found is safer, 
             # but strictly following requirement "higher should be considered" implies strict order.
             # Let's assume valid input.
             active_buckets = buckets 
    else:
        active_buckets = buckets

    needed_buckets_for_joins = [b for b in active_buckets if b != 'master']

    key_columns, data_columns = get_table_key_and_data_columns(table_name)
    if needed_data_columns is not None:
        data_columns = [col for col in data_columns if col["name"] in needed_data_columns]
    key_column_definitions_str = ",\n\t\t".join([f'master_data."{col["name"]}"' for col in key_columns])
    data_column_definitions = []
    
    merge_tables = False
    for col in data_columns:
        col_name = col["name"]
        
        # If optimization is on and it's classified as master data, we just take it from master_data
        # OR if min_bucket is 'master', we only have one source anyway.
        if (is_classified_for_master_data(table_name, col["name"]) and optimized) or min_bucket == 'master':
             data_column_definitions.append(f'master_data."{col_name}" as "{col_name}"')
        else:
            merge_tables = True
            # Build coalesce arguments dynamically based on active_buckets
            coalesce_args = []
            for b in active_buckets:
                table_alias = bucket_map[b]
                coalesce_args.append(f'{table_alias}."{col_name}"')
            
            coalesce_str = ",\n                ".join(coalesce_args)
            
            data_column_definitions.append(f"""
            coalesce(
                {coalesce_str}
            ) as "{col_name}"                            
            """.strip()                               
            )
    data_column_definitions_str = ",\n\t\t".join(data_column_definitions)
    
    column_definitions_str = f"""
        {key_column_definitions_str},
        {data_column_definitions_str}
    """.strip()
    
    join_clauses = []

    date_cols = """
        dates.date,
        dates.year,
        dates.month,
        dates.isoyear,
        dates.week
    """
    date_table = '"DatesHistory"'
    
    # if 'daily' in active_buckets or 'weekly' in active_buckets:
    #     date_cols = """
    #         dates.date,
    #         dates.year,
    #         dates.month,
    #         dates.isoyear,
    #         dates.week
    #     """
    #     date_table = '"DatesHistory"'
    # elif 'weekly' in active_buckets:
    #     date_cols = """
    #         dates.date,
    #         dates.year,
    #         dates.month,
    #         dates.isoyear,
    #         dates.week
    #     """    
    #     date_table = '(SELECT MIN(date) as date, year, month, isoyear, week FROM "DatesHistory" GROUP BY year, month, isoyear, week)'
    # elif 'monthly' in active_buckets or 'master' in active_buckets:
    #     date_cols = """
    #         dates.date,
    #         dates.year,
    #         dates.month
    #     """    
    #     date_table = '(SELECT MIN(date) as date, year, month FROM "DatesHistory" GROUP BY year, month)'

    if merge_tables == True:

        if 'daily' in active_buckets:
            key_columns_on_condition_str_daily = " AND ".join([f'master_data."{col["name"]}" = daily."{col["name"]}"' for col in key_columns])
            join_clauses.append(f'LEFT JOIN "{table_name}HistoryDaily" as daily')
            join_clauses.append('ON dates.date = daily.snapshot_date')
            join_clauses.append(f'AND {key_columns_on_condition_str_daily}')
            if needed_data_columns is not None: # Optimization to reduce join size
                not_null_clause = " AND ".join([f'daily."{col["name"]}" IS NOT NULL' for col in data_columns])
                join_clauses.append(f"AND {not_null_clause}")  
            
        if 'weekly' in active_buckets:        
            key_columns_on_condition_str_weekly = " AND ".join([f'master_data."{col["name"]}" = weekly."{col["name"]}"' for col in key_columns])
            join_clauses.append(f'LEFT JOIN "{table_name}HistoryWeekly" as weekly')
            join_clauses.append('ON dates.isoyear = weekly.isoyear')
            join_clauses.append('AND dates.week = weekly.week')
            join_clauses.append(f'AND {key_columns_on_condition_str_weekly}')
            if needed_data_columns is not None: # Optimization to reduce join size
                not_null_clause = " AND ".join([f'weekly."{col["name"]}" IS NOT NULL' for col in data_columns])
                join_clauses.append(f"AND {not_null_clause}")  
            
        if 'monthly' in active_buckets:
            key_columns_on_condition_str_monthly = " AND ".join([f'master_data."{col["name"]}" = monthly."{col["name"]}"' for col in key_columns])
            join_clauses.append(f'LEFT JOIN "{table_name}HistoryMonthly" as monthly')
            join_clauses.append('ON dates.year = monthly.year')
            join_clauses.append('AND dates.month = monthly.month')
            join_clauses.append(f'AND {key_columns_on_condition_str_monthly}')
            if needed_data_columns is not None: # Optimization to reduce join size
                not_null_clause = " AND ".join([f'monthly."{col["name"]}" IS NOT NULL' for col in data_columns])
                join_clauses.append(f"AND {not_null_clause}")

    join_str = "\n        ".join(join_clauses)

    # Always join master data (it's the base for dates/keys)
    select_statement_sql =  f"""
    SELECT
        {date_cols.strip()},
        {column_definitions_str}
    FROM
        {date_table} as dates
        INNER JOIN "{table_name}MasterData" as master_data
        ON dates.date BETWEEN master_data.from_date AND master_data.to_date 
        {join_str}
    """
    # WHERE EXTRACT(ISODOW FROM dates.date) NOT IN (6, 7)
    return select_statement_sql

def get_history_enabled_views():
    
    pattern_search = f" OR ".join([f"sql LIKE '%{table}%' " for table in HISTORY_ENABLED_TABLES])
    history_enabled_views = select_into_dataframe("""
        SELECT name AS view_name
        FROM sqlite_schema
        WHERE type='view' AND {pattern_search}
    """)
    
    return history_enabled_views

def is_first_weekday_of_month(today: date | None = None) -> bool:
    if today is None:
        today = date.today()

    first_day = today.replace(day=1)

    # Advance to the first weekday (Mon–Fri)
    while first_day.weekday() >= 5:  # 5 = Sat, 6 = Sun
        first_day += timedelta(days=1)

    return today == first_day

def is_monday():
    today = date.today()
    return today.weekday() == 0  # 0 = Monday

def is_weekend() -> bool:
    today = date.today()
    return today.weekday() >= 5  # 5 = Sat, 6 = Sun
