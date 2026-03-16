import time
import datetime
import os
import re
import pandas as pd
import logging
from typing import Literal
from sqlalchemy import create_engine, text, inspect
from config import HISTORY_ENABLED_TABLES, SSH_PKEY_PATH, SSH_HOST, SSH_USER, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_PORT, POSTGRES_HOST, TABLE_STOCK_IMPLIED_VOLATILITY_MASSIVE, TABLE_STOCK_PRICES_YAHOO
import numpy as np
import hashlib

from src.decorator_log_function import log_function

# logging
logger = logging.getLogger(__name__)

_SSH_TUNNEL = None
_POSTGRES_ENGINE = None

def get_postgres_engine():
    """
    Creates and returns a SQLAlchemy engine for the PostgreSQL database via SSH tunnel.
    Singleton pattern to avoid recreating tunnel/engine.
    """
    global _SSH_TUNNEL, _POSTGRES_ENGINE
    
    if not POSTGRES_DB:
        logger.info(f"PostgreSQL not configured")
        return None

    if _POSTGRES_ENGINE:
        # We could add a check here if the tunnel is still active
        return _POSTGRES_ENGINE

    try:
        db_host = POSTGRES_HOST
        db_port = POSTGRES_PORT

        if SSH_PKEY_PATH:
            from sshtunnel import SSHTunnelForwarder
            if not _SSH_TUNNEL:
                logger.info(f"Establishing SSH Tunnel to {SSH_HOST}...")
                # On macOS/Linux, the default key path is usually ~/.ssh/id_rsa
                # Using expanduser to handle the home directory (~) correctly
                SSH_PKEY = os.path.expanduser(SSH_PKEY_PATH) 
                _SSH_TUNNEL = SSHTunnelForwarder(
                    (SSH_HOST, 22),
                    ssh_username=SSH_USER,
                    ssh_pkey=SSH_PKEY,
                    remote_bind_address=('localhost', int(POSTGRES_PORT)) 
                )
                _SSH_TUNNEL.start()
                logger.info(f"SSH Tunnel established. Local bind port: {_SSH_TUNNEL.local_bind_port}")
            
            db_host = "127.0.0.1"
            db_port = _SSH_TUNNEL.local_bind_port

        # Create Engine
        db_url = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{db_host}:{db_port}/{POSTGRES_DB}"
        _POSTGRES_ENGINE = create_engine(
            db_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        logger.info("Successfully created PostgreSQL engine.")
        return _POSTGRES_ENGINE

    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: \n{e}")
        raise e
        return None


def truncate_table(connection, table_name: str):
    """
    Deletes all rows from a specified table in the database.

    This function executes a 'DELETE FROM' statement within a transaction
    to ensure atomicity. It includes error handling for cases where the
    table might not exist.

    Parameters:
    - engine (sqlalchemy.engine.Engine): The SQLAlchemy engine instance
      for database connection.
    - table_name (str): The name of the table to truncate.
    """

    if hasattr(connection, 'cursor'):
        with connection.cursor() as cur:
            cur.execute(f'DELETE FROM "{table_name}"')
    else:
        execute_sql(connection, f'DELETE FROM "{table_name}"', table_name, "TRUNCATE")

def log_data_change(connection, operation_type, table_name, affected_rows=None, additional_data=None):
    """
    Logs a data change operation to the DataChangeLogs table.
    """
    try:
        timestamp = datetime.datetime.now().isoformat()
        query = text("""
            INSERT INTO "DataChangeLogs" (timestamp, operation_type, table_name, affected_rows, additional_data)
            VALUES (:timestamp, :operation_type, :table_name, :affected_rows, :additional_data)
        """)
        connection.execute(query, {
            "timestamp": timestamp,
            "operation_type": operation_type,
            "table_name": table_name,
            "affected_rows": affected_rows,
            "additional_data": additional_data
        })
    except Exception as e:
        logger.error(f"Error logging data change: \n{e}")
        raise e

def insert_into_table(
        connection,
        table_name: str,
        dataframe: pd.DataFrame,
        if_exists: Literal["fail", "replace", "append"] = "append"
    ) -> int:

    try:

        start_pg = time.time()
        # Postgres tends to be stricter, so we catch errors but don't stop the flow
        dataframe = dataframe.replace("None", np.nan)

        try:
            # 1. Get the list of columns currently in the database table
            inspector = inspect(connection)
            existing_columns = [col['name'] for col in inspector.get_columns(table_name)]

            # 2. Identify the common columns between your DataFrame and the SQL table
            columns_to_keep = [col for col in dataframe.columns if col in existing_columns]

            # 3. Filter the DataFrame
            dataframe = dataframe[columns_to_keep]
        except Exception as e:
            logger.info(f"{table_name} does not exist: \n{e}")

        # 4. Perform the insertion
        pg_affected = dataframe.to_sql(
                            table_name,
                            connection, 
                            if_exists=if_exists, 
                            index=False,
                            method='multi',
                            chunksize=500
                        )
        rows_saved = len(dataframe)
        logger.info(f"[PostgreSQL] Successfully saved {rows_saved} rows to {table_name} in {round(time.time() - start_pg, 2)}s.")
        
        log_data_change(connection, "INSERT", table_name, affected_rows=rows_saved)
    except Exception as e:
        logger.error(f"[PostgreSQL] Error saving to table {table_name}: \n{e}")
        raise e

    return rows_saved

def insert_into_table_bulk(
        raw_connection,
        table_name: str,
        dataframe: pd.DataFrame,
        if_exists: Literal["fail", "replace", "append"] = "append"
    ) -> int:   
    start = time.time()
    dataframe = dataframe.replace("None", np.nan)
    from io import StringIO

    buffer = StringIO()
    dataframe.to_csv(buffer, index=False, header=False)
    buffer.seek(0)

    columns = list(dataframe.columns)

    try:
        with raw_connection.cursor() as cur:
            cur.copy_from(
                buffer,
                table_name,
                sep=',',
                null='',
                columns=columns
            )
    except Exception as e:
        logger.error(f"[PostgreSQL] Error executing SQL on {table_name}: \n{e}")
        raise e
    rows_saved = len(dataframe)
    logger.info(f"[PostgreSQL] Successfully saved {rows_saved} rows to {table_name} in {round(time.time() - start, 2)}s.")
    
def execute_sql(connection, sql: str, table_name: str, operation_type: str = "INSERT", additional_data=None):
    """
    Executes a raw SQL statement and logs the data change.
    
    Parameters:
    - connection: SQLAlchemy connection object (must be inside a transaction).
    - sql (str): The raw SQL statement to execute.
    - table_name (str): The name of the table being modified.
    - operation_type (str): The type of operation (INSERT, UPDATE, DELETE).
    """
    logger.debug(f"SQL Statement for {additional_data}:\n{text(sql)}")
        
    if 'postgresql' in str(connection.engine.url):
        # Execute on PostgreSQL (Side-by-side test)
        try:
            start_pg = time.time()
            pg_result = connection.execute(text(sql))
            pg_affected = pg_result.rowcount
            
            logger.info(f"[PostgreSQL] Successfully executed {operation_type} SQL on {table_name} in {round(time.time() - start_pg, 2)}s. Rows affected: {pg_affected}")
            log_data_change(connection, operation_type, table_name, affected_rows=pg_affected, additional_data=additional_data)
            return pg_affected
        except Exception as e:
            logger.error(f"[PostgreSQL] Error executing SQL on {table_name}: \n{e}")
            raise e

@log_function
def select_into_dataframe(query: str = None, sql_file_path: str = None, params: dict = None):
    """
    Executes a SQL query and returns the result as a DataFrame.
    You can provide either a SQL query string or a path to a .sql file.

    Parameters:
    - query (str, optional): SQL query string to execute.
    - sql_file_path (str, optional): Path to a .sql file containing the query.
    - params (dict, optional): Dictionary of parameters to bind to the query (e.g., {'expiration_date': '2026-08-21'})

    Returns:
    - pd.DataFrame: Result of the query.
    """
    df = select_into_dataframe_pg(query=query, sql_file_path=sql_file_path, params=params)

    return df


def select_into_dataframe_pg(query: str = None, sql_file_path: str = None, params: dict = None):
    """
    Executes a SQL query and returns the result as a DataFrame.
    You can provide either a SQL query string or a path to a .sql file.

    Parameters:
    - query (str, optional): SQL query string to execute.
    - sql_file_path (str, optional): Path to a .sql file containing the query.
    - params (dict, optional): Dictionary of parameters to bind to the query (e.g., {'expiration_date': '2026-08-21'})

    Returns:
    - pd.DataFrame: Result of the query.
    """
    df = None
  
    try:
        if sql_file_path is not None and os.path.isfile(sql_file_path):
            with open(sql_file_path, 'r') as f:
                sql = f.read()
        elif query is not None:
            sql = query
        else:
            msg = "Either 'query' or 'sql_file_path' must be provided."
            logger.error(msg)
            raise ValueError(msg)

        pg_engine = get_postgres_engine()
        if pg_engine:
            start_pg = time.time()
            with pg_engine.connect() as conn:
                if params:
                    df = pd.read_sql(text(str(sql)), conn, params=params)
                else:
                    df = pd.read_sql(text(str(sql)), conn)
            logger.debug(f"[PostgreSQL] Rows: {len(df)} - Runtime: {round(time.time() - start_pg, 2)}s.")
    except Exception as e:
        logger.error(f"[PostgreSQL] Error executing query: \n{e}")
        logger.error(f"\n{str(sql)}")
        raise e
    return df

def get_table_key_and_data_columns(table_name):
    """
    Retrieves the key columns and data columns for a specified table.

    Parameters:
    - table_name (str): The name of the table.

    Returns:
    - tuple: A tuple containing two lists: (key_columns, data_columns).
    """
    
    columns = get_columns(table_name)

    key_columns = [{"name": row["name"], "type": row["type"]} for row in columns if row["is_key"] == True]
    data_columns = [{"name": row["name"], "type": row["type"]} for row in columns if row["is_key"] == False]
    
    return key_columns, data_columns

def get_columns(table_name):
    """
    Retrieves the column details for a given table using pragma_table_info.
    Returns a list of dicts: [{'name': 'col1', 'type': 'TEXT'}, ...]
    """
    logger.info(f"Fetching columns for {table_name}")

    with get_postgres_engine().begin() as connection:
        try:
            query = text(f"""
                        SELECT 
                            cols.column_name, 
                            UPPER(cols.data_type) AS data_type,
                            CASE 
                                WHEN kcu.column_name IS NOT NULL THEN true 
                                ELSE false 
                            END AS is_key
                        FROM information_schema.columns cols
                        LEFT JOIN information_schema.key_column_usage kcu 
                            ON cols.table_name = kcu.table_name 
                            AND cols.column_name = kcu.column_name
                            AND cols.table_schema = kcu.table_schema
                        WHERE cols.table_name = '{table_name}'
                        ORDER BY cols.ordinal_position;
                         """)
            result = connection.execute(query).fetchall()
            columns = [{"name": row.column_name, "type": row.data_type, "is_key": row.is_key} for row in result]
            # logger.info(f"Found columns: {columns}")
            return columns
        except Exception as e:
            logger.error(f"Error fetching columns for {table_name}: {e}")
            return []

def _run_migrations_for_engine(engine):
    """
    Internal helper to run migrations on a specific engine.
    """
    if 'postgresql' in str(engine.url):
        label = "PostgreSQL"

    logger.info(f"Starting {label} migration...")
    start = time.time()

    inspector = inspect(engine)

    with engine.connect() as connection:
        if not inspector.has_table('DbVersion'):
            with connection.begin():
                logger.info(f"[{label}] DbVersion table not found. Creating it...")
                try:
                    with open("db/SQL/tables/create_table/DbVersion.sql", "r") as f:
                        connection.execute(text(f.read()))
                    connection.execute(text('INSERT INTO "DbVersion" (version) VALUES (0)'))
                    logger.info(f"[{label}] DbVersion table created and initialized with version 0.")
                except Exception as e:
                    logger.error(f"[{label}] Error initializing DbVersion: \n{e}")
                    # If this fails (e.g. invalid SQL for Postgres), we might stop here for this engine
                    raise e

        with connection.begin():
            result = connection.execute(text('SELECT version FROM "DbVersion"')).fetchone()
            current_version = result[0]
        logger.info(f"[{label}] Current database version: {current_version}")

        migrations_path = "db/SQL/migrations/"
        if not os.path.exists(migrations_path):
            logger.info(f"[{label}] Migrations directory not found at {migrations_path}. Skipping migrations.")
            _recreate_views_connection(connection)
            connection.commit()  # Ensure any pending transactions are committed before
            return
            
        migration_files = [f for f in os.listdir(migrations_path) if re.match(r"\d+\.sql", f)]
        migration_files.sort(key=lambda x: int(x.split(".")[0]))

        pending_migrations = [f for f in migration_files if int(f.split(".")[0]) > current_version]

        if not pending_migrations:
            logger.info(f"[{label}] Database is up to date.")
            _recreate_views_connection(connection)
            connection.commit()  # Ensure any pending transactions are committed before
            return

        drop_all_views(engine)
        # with connection.begin():
        #     for table in HISTORY_ENABLED_TABLES:
        #         pass
        #         change_column_data_types(connection, table)

        for migration_file in pending_migrations:
            logger.info(f"[{label}] Applying migration {migration_file}...")
            last_migration_version = int(pending_migrations[-1].split(".")[0])

            try:
                with open(os.path.join(migrations_path, migration_file), "r") as f:
                    sql_script = f.read()
                
                statements = [s.strip() for s in sql_script.split(';') if s.strip()]

                with connection.begin():
                    for statement in statements:
                        try:
                            connection.execute(text(statement))
                        except Exception as e:
                            logger.error(f"[{label}] Error applying migration {migration_file}: \n{e}")
                            if not 'duplicate column' in e:
                                raise e
                        
                logger.info(f"[{label}] Migration {migration_file} applied successfully.")
            except Exception as e:
                logger.error(f"[{label}] Error applying migration {migration_file}: \n{e}")
                raise e
            
        with connection.begin():
            if pending_migrations:
                last_migration_version = int(pending_migrations[-1].split(".")[0])
                connection.execute(text(f'UPDATE "DbVersion" SET version = {last_migration_version}'))
                logger.info(f"[{label}] Database version updated to {last_migration_version}.")
    
        # Recreate views after migrations
        _recreate_views_connection(connection)
    logger.info(f"[{label}] Migration completed in {round(time.time() - start,2)}s")


def run_migrations():
    """
    Runs the database migration system on PostgreSQL.
    """
    # PostgreSQL
    pg_engine = get_postgres_engine()
    if pg_engine:
        _run_migrations_for_engine(pg_engine)
        # pg_migrations()


def _get_missing_expected_views(inspector):
    expected_views = {
        "OptionData",
        "FundamentalData",
        "OptionDataMerged",
        "OptionPricingMetrics",
        "StockData",
    }
    existing_views = set(inspector.get_view_names())
    return sorted(expected_views - existing_views)

def _recreate_views_connection(connection):
    """
    Internal helper to recreate views on a specific engine.
    """
    if 'postgresql' in str(connection.engine.url):
        label = "PostgreSQL"
    logger.info(f"[{label}] Recreating views...")
    start = time.time()

    
    if label == "PostgreSQL":
        view_path = "db/SQL/views/PostgreSQL/"

    if not os.path.exists(view_path):
        logger.info(f"[{label}] Views directory not found at {view_path}. Skipping view recreation.")
        return

    view_files = [f for f in os.listdir(view_path) if f.endswith(".sql")]
    view_files.sort()

    pending_views = view_files.copy()
    
    hash_value = calculate_view_hash(view_path, view_files)
    db_hash_value = get_db_view_hash_conn(connection)
    missing_views = _get_missing_expected_views(inspect(connection.engine))

    if db_hash_value == hash_value and not missing_views:
        logger.info(f"[{label}] Views are up to date. Skipping recreation.")
        return

    if missing_views:
        logger.warning(f"[{label}] Expected views missing despite stored view hash: {missing_views}. Recreating views.")
    
    drop_all_views(connection.engine)
    while pending_views:
        progress_made = False
        failed_views = []
        
        for view_file in pending_views:
            try:
                with open(os.path.join(view_path, view_file), "r") as f:
                    sql_script = f.read()
                
                statements = [s.strip() for s in sql_script.split(';') if s.strip()]
                
                with connection.begin():
                    for statement in statements:
                        connection.execute(text(statement))
                
                progress_made = True
            except Exception as e:
                logger.error(f"[{label}] Failed to create view {view_file}: \n{e}")
                failed_views.append(view_file)
        
        if not progress_made and failed_views:
            logger.error(f"[{label}] Error: Could not create the following views due to potential circular dependencies or errors: {failed_views}")
            break
        
        pending_views = failed_views
    
    if not pending_views:
        logger.info(f"[{label}] All views recreated successfully in {round(time.time() - start, 2)}s.")
        execute_sql(connection, f'UPDATE "DbVersion" SET view_hash = \'{hash_value}\'', "DbVersion", "UPDATE", "Update view hash after recreation")
    else:
        logger.info(f"[{label}] View recreation finished with errors in {round(time.time() - start, 2)}s.")
        execute_sql(connection, f'UPDATE "DbVersion" SET view_hash = NULL', "DbVersion", "UPDATE", "Update view hash after recreation")
        raise Exception(f"Failed to recreate some views in {label}: {pending_views}")

def calculate_view_hash(views_path, view_files):
    hasher = hashlib.sha256()
    
    # Sorting ensures the order of concatenation is always the same
    for view_file in sorted(view_files):
        try:
            file_path = os.path.join(views_path, view_file)
            
            # Using newline='' and then encoding ensures 
            # all platforms hash the same string.
            with open(file_path, "r", encoding="utf-8", newline='') as f:
                content = f.read().replace('\r\n', '\n') 
                hasher.update(content.encode("utf-8"))
                
        except Exception as e:
            logger.error(f"Error reading view file {view_file}: \n{e}")
            raise e
            
    hash_value = hasher.hexdigest()
    logger.info(f"Calculated view hash: {hash_value}")
    return hash_value

def get_db_view_hash_conn(connection):
    with connection.begin():
        result = connection.execute(text('SELECT view_hash FROM "DbVersion"')).fetchone()
        current_view_hash = result[0] if result else None
    logger.info(f"Current database view hash: {current_view_hash}")
    return current_view_hash

def recreate_views():
    """
    Recreates all views in both databases.
    """
    # PostgreSQL
    pg_engine = get_postgres_engine()
    with pg_engine.connect() as connection:
        _recreate_views_connection(connection)

def table_exists(table_name: str) -> bool:
    """
    Checks if a table exists in the database.
    Returns True only if it exists in active databases.
    """

    # Check Postgres
    exists_pg = True
    try:
        pg_engine = get_postgres_engine()
        if pg_engine:
            insp_pg = inspect(pg_engine)
            exists_pg = insp_pg.has_table(table_name)
    except Exception as e:
        logger.error(f"[PostgreSQL] Error checking table existence {table_name}: \n{e}")
        # If we return False, we might trigger creation which might fail if DB is down.
        # But for 'side by side' test, we want to try to create if missing.
        exists_pg = False

    return exists_pg

def view_exists(view_name: str) -> bool:
    """
    Checks if a view exists in the database.
    Returns True only if it exists in active databases.
    """
    # Check Postgres
    exists_pg = True
    try:
        pg_engine = get_postgres_engine()
        if pg_engine:
            insp_pg = inspect(pg_engine)
            exists_pg = view_name in insp_pg.get_view_names()
    except Exception as e:
        logger.error(f"[PostgreSQL] Error checking view existence {view_name}: \n{e}")
        exists_pg = False

    return exists_pg

def pg_migrations():
    sql_script = """
    ALTER TABLE "DataChangeLogs" DROP Column id; 
    ALTER TABLE "OptionDataMassive" ALTER COLUMN expiration_date TYPE date USING expiration_date::date;
    """
        # ALTER TABLE "OptionDataYahoo" RENAME COLUMN contractSymbol TO "contractSymbol";
    error = None
    try:
        pg_engine = get_postgres_engine()
        if pg_engine:
            start_pg = time.time()
            statements = [s.strip() for s in sql_script.split(';') if s.strip()]
            for statement in statements:
                with pg_engine.begin() as connection:
                    try:
                        connection.execute(text(statement))
                    except Exception as e:
                        error = True
                        logger.warning(f"[PostgreSQL] statement '{statement}': \n{e}")
                        raise e
            if not error:
                logger.info(f"[PostgreSQL] Successfully in {round(time.time() - start_pg, 2)}s.")
            else:
                logger.info(f"[PostgreSQL] Completed with some errors in {round(time.time() - start_pg, 2)}s.")
    except Exception as e:
        logger.error(f"[PostgreSQL] Error: \n{e}")
        raise e

def column_exists(engine, table_name, column_name, schema=None):
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name, schema=schema)
    return any(col["name"] == column_name for col in columns)

def drop_all_views(engine):
    """
    Drops all standard and materialized views in PostgreSQL database.
    """
    label = "PostgreSQL"
    inspector = inspect(engine)
    
    # 1. Get standard views
    views = inspector.get_view_names()
    
    # 2. Get materialized views (Postgres specific)
    m_views = []
    if 'postgresql' in str(engine.url):
        # SQLAlchemy 1.4/2.0+ has this method
        if hasattr(inspector, 'get_materialized_view_names'):
            m_views = inspector.get_materialized_view_names()
    
    with engine.begin() as connection:
        # Drop standard views
        for view in views:
            try:
                connection.execute(text(f'DROP VIEW IF EXISTS "{view}" CASCADE'))
                logger.info(f"{label} Dropped view: {view}")
            except Exception as e:
                logger.error(f"{label} Error dropping view {view}: {e}")

        # Drop materialized views
        for m_view in m_views:
            try:
                connection.execute(text(f'DROP MATERIALIZED VIEW IF EXISTS "{m_view}" CASCADE'))
                logger.info(f"{label} Dropped materialized view: {m_view}")
            except Exception as e:
                logger.error(f"{label} Error dropping materialized view {m_view}: {e}")
    
def change_column_data_types(conn, table):
    if 'OptionDataMassive' in table:
        
        try:
            for massive_table in ["OptionDataMassive", "OptionDataMassiveHistoryDaily", "OptionDataMassiveHistoryWeekly", "OptionDataMassiveHistoryMonthly", "OptionDataMassiveMasterData"]:
                # double precision to real
                # for col in ["strike_price", "implied_volatility", "greeks_delta", "greeks_gamma", "greeks_theta", "greeks_vega", "day_change", "day_change_percent", "day_close", "day_high", "day_low", "day_open", "day_previous_close", "day_volume", "day_vwap"]:
                for col in ["strike_price", "day_change", "day_change_percent", "day_close", "day_high", "day_low", "day_open", "day_previous_close", "day_volume", "day_vwap"]:
                
                    alter_statement = f'''ALTER TABLE "{massive_table}" ALTER COLUMN "{col}" TYPE real USING (
                                                                                                            CASE 
                                                                                                                WHEN abs("{col}") < 1e-37 THEN 0 
                                                                                                                ELSE "{col}" 
                                                                                                            END
                                                                                                        )::real'''
                    # execute_sql(conn, alter_statement, massive_table, 'ALTER', f"Change {col} column data type from double precision to real {massive_table}")
                # Bigint to int
                for col in ["open_interest"]:
                    alter_statement = f'ALTER TABLE "{massive_table}" ALTER COLUMN "{col}" TYPE integer'
                    # execute_sql(conn, alter_statement, massive_table, 'ALTER', f"Change {col} column data type from bigint to int {massive_table}")
                # Bigint to smallint
                for col in ["shares_per_contract"]:
                    alter_statement = f'ALTER TABLE "{massive_table}" ALTER COLUMN "{col}" TYPE smallint'
                    # execute_sql(conn, alter_statement, massive_table, 'ALTER', f"Change {col} column data type from bigint to smallint {massive_table}")
                # text to date
                for col in ["expiration_date"]:
                    alter_statement = f'ALTER TABLE "{massive_table}" ALTER COLUMN "{col}" TYPE date USING expiration_date::date'
                    execute_sql(conn, alter_statement, massive_table, 'ALTER', f"Change {col} column data type from text to date {massive_table}")

        except Exception as e:
            logger.warning(f"Error during column data type change: {e}")
            raise e
    
    try:
        for hist_table in ["DatesHistory", f"{table}HistoryWeekly"]:
            # int to smallint
            for col in ["isoyear", "week"]:
                alter_statement = f'ALTER TABLE "{hist_table}" ALTER COLUMN "{col}" TYPE smallint'
                # execute_sql(conn, alter_statement, hist_table, 'ALTER', f"Change {col} column data type from int to smallint {hist_table}")
        for hist_table in ["DatesHistory", f"{table}HistoryMonthly"]:
            # int to smallint
            for col in ["year", "month"]:
                alter_statement = f'ALTER TABLE "{hist_table}" ALTER COLUMN "{col}" TYPE smallint'
                # execute_sql(conn, alter_statement, hist_table, 'ALTER', f"Change {col} column data type from int to smallint {hist_table}")
    except Exception as e:
        logger.warning(f"Error during column data type change: {e}")
        raise e