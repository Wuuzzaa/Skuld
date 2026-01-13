import logging
import os
import pathlib
import time
from sqlalchemy import text
from config import HISTORY_ENABLED_TABLES, HISTORY_ENABLED_VIEWS
from src.database import get_database_engine, execute_sql, get_postgres_engine, get_table_key_and_data_columns, recreate_views, select_into_dataframe, table_exists, view_exists
from src.decorator_log_function import log_function
from src.data_aging import DataAgingService, get_history_select_statement, is_classified_for_master_data
from src.util import executed_as_github_action

logger = logging.getLogger(__name__)

class HistorizationService:
    @staticmethod
    def _get_columns(connection, table_name):
        """
        Retrieves the column details for a given table using pragma_table_info.
        Returns a list of dicts: [{'name': 'col1', 'type': 'TEXT'}, ...]
        """
        logger.info(f"Fetching columns for {table_name}")
        try:
             # Using pragma_table_info directly
            query = text(f"SELECT name, type FROM pragma_table_info('{table_name}')")
            result = connection.execute(query).fetchall()
            columns = [{"name": row[0], "type": row[1]} for row in result]
            # logger.info(f"Found columns: {columns}")
            return columns
        except Exception as e:
            logger.error(f"Error fetching columns for {table_name}: {e}")
            return []

    @staticmethod
    @log_function
    def run_daily_historization(source_table: str):
        """
        Copies data from source_table to history_table with an UPSERT strategy.
        Adds a 'snapshot_date' column with the current date.
        """
        start_time = time.time()
        
        history_table = f"{source_table}HistoryDaily"
        key_columns, _ = get_table_key_and_data_columns(source_table)
        key_column_names = [col['name'] for col in key_columns]

        logger.info(f"Starting historization from {source_table} to {history_table}")
        _create_history_tables_and_view_if_not_exist(source_table)

        engine = get_database_engine()
        with engine.begin() as connection:
            # 1. Get columns from source table
            source_columns = HistorizationService._get_columns(connection, source_table)
            if not source_columns:
                logger.error(f"Source table {source_table} not found or has no columns.")
                return

            column_names = [col['name'] for col in source_columns]
            
            # 2. Build the SQL statement
            # Target columns: snapshot_date + original columns
            target_cols_str = "snapshot_date, " + ", ".join([f'"{c}"' for c in column_names])
            select_cols_str = ", ".join([f'"{c}"' for c in column_names])
            
            # Update clause for UPSERT
            # Exclude conflict keys from the update set
            update_set = []
            for col in column_names:
                if col not in key_column_names:
                    update_set.append(f'"{col}" = excluded."{col}"')
            
            update_clause = ", ".join(update_set)
            conflict_target = ", ".join([f'"{k}"' for k in key_column_names])
            
            sqllite_sql = f"""
                INSERT INTO "{history_table}" ({target_cols_str})
                SELECT date('now'), {select_cols_str}
                FROM "{source_table}"
                WHERE 1=1 -- needed because of Parsing Ambiguity. Check SQLite documentation
                ON CONFLICT(snapshot_date, {conflict_target}) DO UPDATE SET
                {update_clause}
            """

            pg_sql = f"""
                INSERT INTO "{history_table}" ({target_cols_str})
                SELECT CURRENT_DATE, {select_cols_str}
                FROM "{source_table}"
                WHERE 1=1 -- needed because of Parsing Ambiguity. Check SQLite documentation
                ON CONFLICT(snapshot_date, {conflict_target}) DO UPDATE SET
                {update_clause}
            """
            
            # 3. Execute
            try:
                # Use the new helper function to execute and log
                execute_sql(connection, sqllite_sql, history_table, "UPSERT", f"Historize data from {source_table} to {history_table}")
            except Exception as e:
                logger.error(f"Error during historization execution on SQLite: {e}")
                raise e

        pg_engine = get_postgres_engine()
        if pg_engine:
            with pg_engine.begin() as connection:
                try:
                    # Use the new helper function to execute and log
                    execute_sql(connection, pg_sql, history_table, "UPSERT", f"Historize data from {source_table} to {history_table}")
                except Exception as e:
                    logger.error(f"Error during historization execution on Postgres: {e}")
                    raise e

        # DataAgingService.run(source_table=source_table)
        duration = time.time() - start_time
        logger.info(f"Historization for {source_table} finished in {duration:.2f}s")

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
            HistorizationService.run_daily_historization(
                source_table=table
            )
        logger.info("Historization Pipeline Completed Successfully.")
    except Exception as e:
        logger.error(f"Historization Pipeline Failed: {e}")
    
    # _create_history_merge_views()

    logger.info(f"Historization Pipeline Finished in {round(time.time() - start_time, 2)}s.")

def _create_history_tables_and_view_if_not_exist(source_table: str):
    """
    Creates the history tables if they do not exist.
    """
    path_sql_create_table_statements = pathlib.Path("db/SQL/tables/create_table/history")
    path_sql_create_table_statements.mkdir(parents=True, exist_ok=True)
    engine = get_database_engine()
    pg_engine = get_postgres_engine()
    table = source_table
  
    daily_history_table_name, create_daily_table_sql = _get_daily_history_table_name_create_statement(table)
    if not table_exists(daily_history_table_name):
        # write sql to file "{daily_history_table_name}.sql" to db/SQL/tables/create_table/history/
        with open(f"{path_sql_create_table_statements}/{daily_history_table_name}.sql", "w") as f:
            f.write(create_daily_table_sql)
        with engine.begin() as connection:
            execute_sql(connection, create_daily_table_sql, daily_history_table_name, "CREATE TABLE")
    
    weekly_history_table_name, create_weekly_table_sql = _get_weekly_history_table_name_create_statement(table)
    if not table_exists(weekly_history_table_name):
        # write sql to file "{weekly_history_table_name}.sql" to db/SQL/tables/create_table/history/
        with open(f"{path_sql_create_table_statements}/{weekly_history_table_name}.sql", "w") as f:
            f.write(create_weekly_table_sql)
        with engine.begin() as connection:
            execute_sql(connection, create_weekly_table_sql, weekly_history_table_name, "CREATE TABLE")
    
    monthly_history_table_name, create_monthly_table_sql = _get_monthly_history_table_name_create_statement(table)
    if not table_exists(monthly_history_table_name):
        # write sql to file "{monthly_history_table_name}.sql" to db/SQL/tables/create_table/history/
        with open(f"{path_sql_create_table_statements}/{monthly_history_table_name}.sql", "w") as f:
            f.write(create_monthly_table_sql)
        with engine.begin() as connection:
            execute_sql(connection, create_monthly_table_sql, monthly_history_table_name, "CREATE TABLE")
    
    master_data_table_name, create_master_data_table_sql = _get_master_data_table_name_create_statement(table)
    if not table_exists(master_data_table_name):
        # write sql to file "{master_data_table_name}.sql" to db/SQL/tables/create_table/history/
        with open(f"{path_sql_create_table_statements}/{master_data_table_name}.sql", "w") as f:
            f.write(create_master_data_table_sql)
        with engine.begin() as connection:
            execute_sql(connection, create_master_data_table_sql, master_data_table_name, "CREATE TABLE")
        
    history_view_name = f"{table}History"
    if not view_exists(history_view_name) or True:
        path_sql_create_view_statements = pathlib.Path("db/SQL/views/create_view/history/table_views")
        path_sql_create_view_statements.mkdir(parents=True, exist_ok=True)
        create_view_sql = _get_history_view_create_statement(table)
        with open(f"{path_sql_create_view_statements}/{history_view_name}.sql", "w") as f:
            f.write(create_view_sql)
        with engine.begin() as connection:
            execute_sql(connection, f'DROP VIEW IF EXISTS "{history_view_name}";', history_view_name, "DROP VIEW")
            execute_sql(connection, create_view_sql, history_view_name, "CREATE VIEW")
        if pg_engine:
            with pg_engine.begin() as connection:
                execute_sql(connection, f'DROP VIEW IF EXISTS "{history_view_name}" CASCADE;', history_view_name, "DROP VIEW")
                execute_sql(connection, create_view_sql, history_view_name, "CREATE VIEW")
    logger.info(f"Ensured that {daily_history_table_name}, {weekly_history_table_name}, {monthly_history_table_name}, {master_data_table_name} tables exist.")
            

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
        year INT NOT NULL,
        week INT NOT NULL,
        {_get_column_definitions_str(table_name)},
        PRIMARY KEY(year, week, {_get_key_columns_str(table_name)})
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
        
        engine = get_database_engine()

        with engine.begin() as conn:
 
            insert_sql = f"""
                INSERT INTO "DatesHistory" (
                    date,
                    year,
                    month,
                    week
                )
                SELECT
                    DATE('now') as date,
                    STRFTIME('%Y', DATE('now')) as year,
                    STRFTIME('%m', DATE('now')) as month,
                    STRFTIME('%W', DATE('now')) as week
                ON CONFLICT(date) DO NOTHING
            """
            try:
                affected = execute_sql(conn, insert_sql, 'DatesHistory', 'UPSERT', f"Insert date to DatesHistory")
            except Exception as e:
                conn.rollback()
                logger.error(f"Error inserting new date: {e}")

        pg_engine = get_postgres_engine()
        if pg_engine:
            with pg_engine.begin() as conn:
    
                insert_sql = f"""
                    INSERT INTO "DatesHistory" (
                        date,
                        year,
                        month,
                        week
                    )
                    SELECT
                        CURRENT_DATE                          AS date,
                        EXTRACT(YEAR  FROM CURRENT_DATE)::int AS year,
                        EXTRACT(MONTH FROM CURRENT_DATE)::int AS month,
                        EXTRACT(WEEK  FROM CURRENT_DATE)::int AS week
                    ON CONFLICT(date) DO NOTHING
                """
                try:
                    affected = execute_sql(conn, insert_sql, 'DatesHistory', 'UPSERT', f"Insert date to DatesHistory")
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error inserting new date: {e}")

        logger.info(f"Inserted date to Dates History in {round(time.time() - start_time, 2)}s.")