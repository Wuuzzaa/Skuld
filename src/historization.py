import logging
import os
import pathlib
import time
from sqlalchemy import text
from config import HISTORY_ENABLED_TABLES, HISTORY_ENABLED_VIEWS
from src.database import column_exists, drop_all_views, get_database_engine, execute_sql, get_postgres_engine, get_table_key_and_data_columns, mapping_sqlite_to_postgres, pg_migrate_week_to_ISO_week, recreate_views, run_migrations, select_into_dataframe, table_exists, view_exists
from src.decorator_log_function import log_function
from src.data_aging import DataAgingService, get_history_select_statement, is_weekend, is_classified_for_master_data
from src.util import executed_as_github_action

logger = logging.getLogger(__name__)
   
def run_historization_pipeline():
    """
    Orchestrates the historization process for all configured tables.
    """
    if executed_as_github_action():
        logger.info("Skipping Historization on GibHub Actions")
        return
    
    start_time = time.time()
    logger.info("Running Historization Pipeline...")
    _insert_date()

    try:
        for table in HISTORY_ENABLED_TABLES:
            run_daily_historization(
                source_table=table
            )
            pass

        for table in HISTORY_ENABLED_TABLES:
            DataAgingService.run(source_table=table)
            pass

        run_migrations()
        logger.info("Historization Pipeline Completed Successfully.")
    except Exception as e:
        logger.error(f"Historization Pipeline Failed: {e}")
    
    # _create_history_merge_views()
    logger.info(f"Historization Pipeline Finished in {round(time.time() - start_time, 2)}s.")

@log_function
def run_daily_historization(source_table: str):
    """
    Copies data from source_table to history_table with an UPSERT strategy.
    Adds a 'snapshot_date' column with the current date.
    """
    start_time = time.time()
    
    history_table = f"{source_table}HistoryDaily"

    logger.info(f"Starting historization from {source_table} to {history_table}")
    _create_history_tables_and_view_if_not_exist(source_table)

    if is_weekend():
        logger.info("It's weekend, skipping daily historization.")
        return
    
    # delete_sqlite_history(source_table)

    insert_into_daily_history_table(source_table)
    insert_into_master_data_table(source_table)

    duration = time.time() - start_time
    logger.info(f"Historization for {source_table} finished in {duration:.2f}s")

def insert_into_daily_history_table(source_table):

    history_table = f"{source_table}HistoryDaily"
    key_columns, data_columns = get_table_key_and_data_columns(source_table)
    key_column_names = [col['name'] for col in key_columns]
    
    # filter out columns which are classified as master data columns
    data_column_names = []
    for col in data_columns:
        if not is_classified_for_master_data(source_table, col['name']):
            data_column_names.append(col['name'])
    data_columns = []

    if not data_column_names:
        logger.info(f"No data columns to historize for {history_table}, skipping.")
        return

    logger.info(f"Data columns to historize for {history_table}: {data_column_names}")

    data_column_names_str = ", ".join([f'"{c}"' for c in data_column_names])
    key_column_names_str = ", ".join([f'"{c}"' for c in key_column_names])
        
    update_clause = ", ".join([f'"{col}" = excluded."{col}"' for col in data_column_names])
    where_clause = " OR ".join([f'hist."{col}" IS DISTINCT FROM excluded."{col}"' for col in data_column_names])
        
    pg_engine = get_postgres_engine()
    if pg_engine:
        pg_sql = f"""
            INSERT INTO "{history_table}" as hist (snapshot_date, {key_column_names_str}, {data_column_names_str})
            SELECT CURRENT_DATE, {key_column_names_str}, {data_column_names_str}
            FROM "{source_table}"
            ON CONFLICT(snapshot_date, {key_column_names_str}) DO UPDATE SET
            {update_clause}
            WHERE {where_clause}
        """
        with pg_engine.begin() as connection:
            try:
                # Use the new helper function to execute and log
                execute_sql(connection, pg_sql, history_table, "UPSERT", f"Historize data from {source_table} to {history_table}")
                pass
            except Exception as e:
                logger.error(f"Error during historization execution on Postgres: {e}")
                raise e

def insert_into_master_data_table(source_table):

    history_table = f"{source_table}MasterData"
    key_columns, data_columns = get_table_key_and_data_columns(source_table)
    key_column_names = [col['name'] for col in key_columns]
    
    # filter columns which are classified as master data columns
    data_column_names = []
    for col in data_columns:
        if is_classified_for_master_data(source_table, col['name']):
            data_column_names.append(col['name'])
    data_columns = []

    if not data_column_names:
        logger.info(f"No data columns to historize for {history_table}, skipping.")
        return
    
    logger.info(f"Data columns to historize for {history_table}: {data_column_names}")

    data_column_names_str = ", ".join([f'"{c}"' for c in data_column_names])
    key_column_names_str = ", ".join([f'"{c}"' for c in key_column_names])
        
    update_clause = ", ".join([f'"{col}" = excluded."{col}"' for col in data_column_names])
    where_clause = " OR ".join([f'hist."{col}" IS DISTINCT FROM excluded."{col}"' for col in data_column_names])
        
    pg_engine = get_postgres_engine()
    if pg_engine:
        pg_sql = f"""
            INSERT INTO "{history_table}" as hist ({key_column_names_str}, {data_column_names_str})
            SELECT {key_column_names_str}, {data_column_names_str}
            FROM "{source_table}"
            ON CONFLICT({key_column_names_str}) DO UPDATE SET
            {update_clause}
            WHERE {where_clause}
        """
        with pg_engine.begin() as connection:
            try:
                # Use the new helper function to execute and log
                execute_sql(connection, pg_sql, history_table, "UPSERT", f"Historize data from {source_table} to {history_table}")
                pass
            except Exception as e:
                logger.error(f"Error during historization execution on Postgres: {e}")
                raise e

def delete_sqlite_history(source_table):
    daily_table = f"{source_table}HistoryDaily"
    weekly_table = f"{source_table}HistoryWeekly"
    monthly_table = f"{source_table}HistoryMonthly"
    master_table = f"{source_table}MasterData"

    engine = get_database_engine()
    tables = [source_table, daily_table, weekly_table, monthly_table, master_table]
    for table in tables:
        delete_sql = f"""
            DELETE FROM "{table}"
        """
        with engine.begin() as connection:
            try:
                execute_sql(connection, delete_sql, table, "DELETE", f"DELETE data from {table}")
            except Exception as e:
                logger.error(f"Error during execution on SQLite: {e}")     

def delete_postgres_history(source_table):
    if source_table in ["OptionDataYahoo", "OptionDataTradingView", "StockDataBarchart"]:
        daily_table = f"{source_table}HistoryDaily"
        weekly_table = f"{source_table}HistoryWeekly"
        monthly_table = f"{source_table}HistoryMonthly"
        master_table = f"{source_table}MasterData"

        engine = get_postgres_engine()
        tables = [source_table, daily_table, weekly_table, monthly_table, master_table]
        for table in tables:
            delete_sql = f"""
                DELETE FROM "{table}"
            """
            with engine.begin() as connection:
                try:
                    execute_sql(connection, delete_sql, table, "DELETE", f"DELETE data from {table}")
                except Exception as e:
                    logger.error(f"Error during execution on SQLite: {e}")   

def _get_columns(table_name):
    """
    Retrieves the column details for a given table using pragma_table_info.
    Returns a list of dicts: [{'name': 'col1', 'type': 'TEXT'}, ...]
    """
    logger.info(f"Fetching columns for {table_name}")

    with get_postgres_engine().begin() as connection:
        try:
            query = text(f"SELECT DISTINCT column_name AS name, data_type AS type FROM information_schema.columns WHERE table_name = '{table_name}'")
            result = connection.execute(query).fetchall()
            columns = [{"name": row[0], "type": row[1]} for row in result]
            # logger.info(f"Found columns: {columns}")
            return columns
        except Exception as e:
            logger.error(f"Error fetching columns for {table_name}: {e}")
            return []


def _create_history_tables_and_view_if_not_exist(source_table: str):
    """
    Creates the history tables if they do not exist.
    """
    path_sql_create_table_statements = pathlib.Path("db/SQL/tables/create_table/history")
    path_sql_create_table_statements.mkdir(parents=True, exist_ok=True)
    pg_engine = get_postgres_engine()

    if not pg_engine:
        logger.warning("PostgreSQL engine not configured, skipping history table creation in Postgres.")
        return
    
    table = source_table
  
    daily_history_table_name, create_daily_table_sql = _get_daily_history_table_name_create_statement(table)
    # write sql to file "{daily_history_table_name}.sql" to db/SQL/tables/create_table/history/
    with open(f"{path_sql_create_table_statements}/{daily_history_table_name}.sql", "w") as f:
        f.write(create_daily_table_sql)
    if not table_exists(daily_history_table_name):
        with pg_engine.begin() as connection:
            execute_sql(connection, create_daily_table_sql, daily_history_table_name, "CREATE TABLE")
    
    weekly_history_table_name, create_weekly_table_sql = _get_weekly_history_table_name_create_statement(table)
    # write sql to file "{weekly_history_table_name}.sql" to db/SQL/tables/create_table/history/
    with open(f"{path_sql_create_table_statements}/{weekly_history_table_name}.sql", "w") as f:
        f.write(create_weekly_table_sql)
    if not table_exists(weekly_history_table_name):
        with pg_engine.begin() as connection:
            execute_sql(connection, create_weekly_table_sql, weekly_history_table_name, "CREATE TABLE")
    
    monthly_history_table_name, create_monthly_table_sql = _get_monthly_history_table_name_create_statement(table)
    # write sql to file "{monthly_history_table_name}.sql" to db/SQL/tables/create_table/history/
    with open(f"{path_sql_create_table_statements}/{monthly_history_table_name}.sql", "w") as f:
        f.write(create_monthly_table_sql)
    if not table_exists(monthly_history_table_name):
        with pg_engine.begin() as connection:
            execute_sql(connection, create_monthly_table_sql, monthly_history_table_name, "CREATE TABLE")
    
    master_data_table_name, create_master_data_table_sql = _get_master_data_table_name_create_statement(table)
    # write sql to file "{master_data_table_name}.sql" to db/SQL/tables/create_table/history/
    with open(f"{path_sql_create_table_statements}/{master_data_table_name}.sql", "w") as f:
        f.write(create_master_data_table_sql)
    if not table_exists(master_data_table_name):
        with pg_engine.begin() as connection:
            execute_sql(connection, create_master_data_table_sql, master_data_table_name, "CREATE TABLE")
        
    _create_missing_columns_in_history_tables(source_table)
    
    history_view_name = f"{table}History"
    if not view_exists(history_view_name) or True:
        path_sql_create_view_statements = pathlib.Path("db/SQL/views/create_view/history/table_views")
        path_sql_create_view_statements.mkdir(parents=True, exist_ok=True)
        create_view_sql = _get_history_view_create_statement(table)
        with open(f"{path_sql_create_view_statements}/{history_view_name}.sql", "w") as f:
            f.write(create_view_sql)
        with pg_engine.begin() as connection:
            execute_sql(connection, f'DROP VIEW IF EXISTS "{history_view_name}" CASCADE;', history_view_name, "DROP VIEW")
            execute_sql(connection, create_view_sql, history_view_name, "CREATE VIEW")
    
    logger.info(f"Ensured that {daily_history_table_name}, {weekly_history_table_name}, {monthly_history_table_name}, {master_data_table_name} tables exist.")
            

def _create_missing_columns_in_history_tables(source_table: str):
    """
    Checks if there are any missing columns in the history tables compared to the source table and adds them if necessary.
    """

    logger.info(f"Checking for missing columns in history tables for {source_table}")
    history_tables = [f"{source_table}HistoryDaily", f"{source_table}HistoryWeekly", f"{source_table}HistoryMonthly", f"{source_table}MasterData"]
    source_columns = _get_columns(source_table)

    pg_engine = get_postgres_engine()
    if not pg_engine:
        logger.warning("PostgreSQL engine not configured, skipping history table column synchronization.")
        return

    for history_table in history_tables:
        history_columns = _get_columns(history_table)
        missing_columns = [col for col in source_columns if col['name'] not in [hc['name'] for hc in history_columns]]
        
        for col in missing_columns:
            alter_sql = f'ALTER TABLE "{history_table}" ADD COLUMN "{col["name"]}" {col["type"]};'
            with pg_engine.begin() as connection:
                try:
                    execute_sql(connection, alter_sql, history_table, "ALTER TABLE", f"Add missing column {col['name']} to {history_table}")
                except Exception as e:
                    logger.error(f"Error adding missing column {col['name']} to {history_table}: {e}")
                    raise e

def _get_daily_history_table_name_create_statement(table_name: str):
    """
    Retrieves the create statement for the specified daily history table.
    """
    daily_history_table_name = f"{table_name}HistoryDaily"

    create_statement_sql =  f"""
    -- generated by HistorizationService
    CREATE TABLE IF NOT EXISTS "{daily_history_table_name}" (
        snapshot_date DATE NOT NULL,
        {_get_column_definitions_str(table_name)},
        PRIMARY KEY(snapshot_date, {_get_key_columns_str(table_name)})
    );
    """

    return daily_history_table_name, create_statement_sql

def _get_weekly_history_table_name_create_statement(table_name: str):
    """
    Retrieves the create statement for the specified weekly history table.
    """
    weekly_history_table_name = f"{table_name}HistoryWeekly"

    create_statement_sql =  f"""
    -- generated by HistorizationService
    CREATE TABLE IF NOT EXISTS "{weekly_history_table_name}" (
        isoyear INT NOT NULL,
        week INT NOT NULL,
        {_get_column_definitions_str(table_name)},
        PRIMARY KEY(isoyear, week, {_get_key_columns_str(table_name)})
    );
    """
    return weekly_history_table_name, create_statement_sql

def _get_monthly_history_table_name_create_statement(table_name: str):
    """
    Retrieves the create statement for the specified monthly history table.
    """
    monthly_history_table_name = f"{table_name}HistoryMonthly"

    create_statement_sql =  f"""
    -- generated by HistorizationService
    CREATE TABLE IF NOT EXISTS "{monthly_history_table_name}" (
        year INT NOT NULL,
        month INT NOT NULL,
        {_get_column_definitions_str(table_name)},
        PRIMARY KEY(year, month, {_get_key_columns_str(table_name)})
    );
    """

    return monthly_history_table_name, create_statement_sql

def _get_master_data_table_name_create_statement(table_name: str):
    """
    Retrieves the create statement for the specified master data table.
    """
    master_data_table_name = f"{table_name}MasterData"

    create_statement_sql = f"""
    -- generated by HistorizationService
    CREATE TABLE IF NOT EXISTS "{master_data_table_name}" (
        from_date DATE NOT NULL,
        to_date DATE NOT NULL,
        {_get_column_definitions_str(table_name)},
        PRIMARY KEY({_get_key_columns_str(table_name)})
    );
    """
    return master_data_table_name, create_statement_sql

def _get_column_definitions_str(table_name: str):
    """
    Retrieves column definitions for the specified table.
    """
    key_columns, data_columns = get_table_key_and_data_columns(table_name)
    key_column_definitions_str = ",\n\t\t\t".join([f'"{col["name"]}" {col["type"]}' for col in key_columns])
    data_column_definitions_str = ",\n\t\t".join([f'"{col["name"]}" {col["type"]}' for col in data_columns])
    
    column_definitions_str = f"""
        {key_column_definitions_str},
        {data_column_definitions_str}
    """.strip()

    return column_definitions_str

def _get_key_columns_str(table_name: str):
    """
    Retrieves the key columns for the specified table.
    """
    key_columns, _ = get_table_key_and_data_columns(table_name)
    key_columns_str = ", ".join([f'"{col["name"]}"' for col in key_columns])
    return key_columns_str

def _get_data_columns_str(table_name: str):
    """
    Retrieves the key columns for the specified table.
    """
    _, data_columns = get_table_key_and_data_columns(table_name)
    data_columns_str = ", ".join([f'"{col["name"]}"' for col in data_columns])
    return data_columns_str

def _get_history_view_create_statement(table_name: str):
    """
    Create statement for history view of the specified table.
    """
    history_select = get_history_select_statement(table_name, optimized=True)

    create_statement_sql =  f"""
    -- generated by HistorizationService
    CREATE VIEW
        "{table_name}History" AS
    {history_select};
    """
    return create_statement_sql

def _create_history_merge_views():
    view_template_path = 'db/SQL/views/create_view/history/template'
    if not os.path.exists(view_template_path):
        logger.info(f"Views directory not found at {view_template_path}. Skipping view recreation.")
        return

    view_files = [f for f in os.listdir(view_template_path) if f.endswith(".sql")]
      
    for view_template_file in view_files:
        with open(os.path.join(view_template_path, view_template_file), "r") as f:
            sql = f.read()
        for table in HISTORY_ENABLED_TABLES:
           sql = sql.replace(f"<{table}HistorySelect>", get_history_select_statement(table, optimized=True))
        
        with open(f"db/SQL/views/create_view/history/{view_template_file.replace('_template','')}", "w") as f:
            f.write(sql)
    recreate_views()

def _insert_date():
        start_time = time.time()

        if is_weekend():
            logger.info("It's weekend, skipping daily historization.")
            return

        pg_engine = get_postgres_engine()
        if pg_engine:
            with pg_engine.begin() as conn:
    
                insert_sql = f"""
                    INSERT INTO "DatesHistory" (
                        date,
                        year,
                        month,
                        isoyear,
                        week
                    )
                    SELECT
                        CURRENT_DATE                          AS date,
                        EXTRACT(YEAR  FROM CURRENT_DATE)::int AS year,
                        EXTRACT(MONTH FROM CURRENT_DATE)::int AS month,
                        EXTRACT(ISOYEAR  FROM CURRENT_DATE)::int AS year,
                        EXTRACT(WEEK  FROM CURRENT_DATE)::int AS week
                    ON CONFLICT(date) DO NOTHING
                """
                try:
                    affected = execute_sql(conn, insert_sql, 'DatesHistory', 'UPSERT', f"Insert date to DatesHistory")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error inserting new date: {e}")
                    raise e

        logger.info(f"Inserted date to Dates History in {round(time.time() - start_time, 2)}s.")

def migrate_weekly_history_tables():
    """
    Migrates weekly history tables to use ISO year and week.
    """
    pg_engine = get_postgres_engine()

    if column_exists(pg_engine, "DatesHistory", "isoyear"):
        logger.info("PostgreSQL Weekly History table already has isoyear column, skipping migration.")
        return

    drop_all_views(pg_engine)
    
    for table in HISTORY_ENABLED_TABLES:
        weekly_history_table_name, create_weekly_table_sql = _get_weekly_history_table_name_create_statement(table)
        if table_exists(weekly_history_table_name):
            logger.info(f"Migrating {weekly_history_table_name} to ISO year and week...")
            with pg_engine.begin() as connection:
                rename_history_weekly = f'ALTER TABLE "{weekly_history_table_name}" RENAME TO "{weekly_history_table_name}Old";'
                execute_sql(connection, rename_history_weekly, weekly_history_table_name, 'ALTER TABLE', f"RENAME to Old - Migrate {weekly_history_table_name} to ISO year and week")
        
                pg_create_weekly_table_sql = mapping_sqlite_to_postgres(create_weekly_table_sql)
                execute_sql(connection, pg_create_weekly_table_sql, weekly_history_table_name, "CREATE TABLE", f"Migrate {weekly_history_table_name} to ISO year and week")
                rename_weekly_table_column = f'ALTER TABLE "{weekly_history_table_name}" RENAME COLUMN year TO isoyear;'
                execute_sql(connection, rename_weekly_table_column, weekly_history_table_name, 'ALTER TABLE', "RENAME COLUMN to isoyear - Migration to ISO week")
             
                _, data_columns = get_table_key_and_data_columns(table)
                data_columns_str = ", ".join([f'MAX("{col["name"]}") AS "{col["name"]}"' for col in data_columns])  
                insert_sql = f"""
                    INSERT INTO "{weekly_history_table_name}" (
                        isoyear,
                        week,
                        {_get_key_columns_str(table)},
                        {_get_data_columns_str(table)}
                    )
                    SELECT
                        EXTRACT(ISOYEAR FROM dh.date)::int AS isoyear,
                        EXTRACT(WEEK FROM dh.date)::int AS week,
                        { _get_key_columns_str(table) },
                        { data_columns_str }
                    FROM "{weekly_history_table_name}Old" AS old
                    JOIN "DatesHistory" AS dh
                    ON old.year = dh.year AND old.week = dh.week
                    GROUP BY
                        EXTRACT(ISOYEAR FROM dh.date)::int, 
                        EXTRACT(WEEK FROM dh.date)::int,
                        { _get_key_columns_str(table) }
                """
                execute_sql(connection, insert_sql, weekly_history_table_name, 'INSERT', "Migration to ISO week")
                drop_weekly_history_old = f'DROP TABLE "{weekly_history_table_name}Old";'
                execute_sql(connection, drop_weekly_history_old, f"{weekly_history_table_name}Old", 'DROP TABLE', "Migration to ISO week")

    pg_migrate_week_to_ISO_week(pg_engine)
            