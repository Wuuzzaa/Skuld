import time
import datetime
import os
import re
import pandas as pd
import logging
from typing import Literal
from sqlalchemy import create_engine, text, inspect
from config import HISTORY_ENABLED_TABLES, PATH_DATABASE_FILE, SSH_PKEY_PATH, SSH_HOST, SSH_USER, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_PORT, POSTGRES_HOST
import numpy as np

# logging
logger = logging.getLogger(__name__)

_SSH_TUNNEL = None
_POSTGRES_ENGINE = None


def get_database_engine():
    """
    Creates and returns a SQLAlchemy engine for the SQLite database.
    """
    # return create_engine(f'sqlite:///{PATH_DATABASE_FILE}')
    return create_engine(f'sqlite:///{str(PATH_DATABASE_FILE.absolute())}')


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
        _POSTGRES_ENGINE = create_engine(db_url)
        logger.info("Successfully created PostgreSQL engine.")
        return _POSTGRES_ENGINE

    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: \n{e}")
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
            cur.execute(f'TRUNCATE "{table_name}"')
    else:
        execute_sql(connection, f'TRUNCATE "{table_name}"', table_name, "TRUNCATE")

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

        pg_affected = dataframe.to_sql(
                            table_name,
                            connection, 
                            if_exists=if_exists, 
                            index=False,
                            method='multi',
                            chunksize=5000
                        )
        rows_saved = len(dataframe)
        logger.info(f"[PostgreSQL] Successfully saved {rows_saved} rows to {table_name} in {round(time.time() - start_pg, 2)}s.")
        
        log_data_change(connection, "INSERT", table_name, affected_rows=rows_saved)
    except Exception as e:
        logger.error(f"[PostgreSQL] Error saving to table {table_name}: \n{e}")

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

    # conn = get_postgres_engine().raw_connection()
    try:
        with raw_connection.cursor() as cur:
            cur.copy_from(
                buffer,
                table_name,
                sep=',',
                null='',
                columns=columns
            )
        # conn.commit()
    except Exception as e:
            logger.error(f"[PostgreSQL] Error executing SQL on {table_name}: \n{e}")
    # finally:
    #     raw_connection.close()
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
    
    # if connection is SQLite, we execute directly
    if 'sqlite' in str(connection.engine.url):
        try:
            start = time.time()
            result = connection.execute(text(sql))
            affected_rows = result.rowcount
            
            logger.info(f"[SQLite]     Successfully executed {operation_type} SQL on {table_name} in {round(time.time() - start, 2)}s. Rows affected: {affected_rows}")
            
            # Log the operation
            log_data_change(connection, operation_type, table_name, affected_rows=affected_rows, additional_data=additional_data)
            return affected_rows
        except Exception as e:
            logger.error(f"[SQLite]     Error executing SQL on {table_name}: \n{e}")
            raise e
        
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
  
    # Execute on PostgreSQL (Side-by-side test)
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
            if params:
                df = pd.read_sql(text(str(sql)), pg_engine, params=params)
            else:
                df = pd.read_sql(text(str(sql)), pg_engine)
            logger.debug(f"[PostgreSQL] Rows: {len(df)} - Runtime: {round(time.time() - start_pg, 2)}s.")
    except Exception as e:
            logger.error(f"[PostgreSQL] Error executing query: \n{e}")
            logger.error(f"\n{str(sql)}")
    return df

def get_table_key_and_data_columns(table_name):
    """
    Retrieves the key columns and data columns for a specified table.

    Parameters:
    - table_name (str): The name of the table.

    Returns:
    - tuple: A tuple containing two lists: (key_columns, data_columns).
    """
    query = text("""
        SELECT
            p.name AS column_name,
            p.type AS column_type,
            p.pk AS pk
        FROM
            sqlite_schema AS m,
            pragma_table_info(m.name) AS p
        WHERE
            m.type = 'table'
            AND m.name = :table_name
    """)
    
    engine = get_database_engine()
    with engine.connect() as connection:
        result = connection.execute(query, {"table_name": table_name}).fetchall()
    
    key_columns = [{"name": row.column_name, "type": row.column_type} for row in result if row.pk > 0]
    data_columns = [{"name": row.column_name, "type": row.column_type} for row in result if row.pk == 0]
    
    return key_columns, data_columns

def _run_migrations_for_engine(engine):
    """
    Internal helper to run migrations on a specific engine.
    """
    if 'postgresql' in str(engine.url):
        label = "PostgreSQL"
    if 'sqlite' in str(engine.url):
        label = "SQLite"

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
                    return

        with connection.begin():
            result = connection.execute(text('SELECT version FROM "DbVersion"')).fetchone()
            current_version = result[0]
        logger.info(f"[{label}] Current database version: {current_version}")

        migrations_path = "db/SQL/migrations/"
        if not os.path.exists(migrations_path):
            logger.info(f"[{label}] Migrations directory not found at {migrations_path}. Skipping migrations.")
            _recreate_views_for_engine(engine)
            return
            
        migration_files = [f for f in os.listdir(migrations_path) if re.match(r"\d+\.sql", f)]
        migration_files.sort(key=lambda x: int(x.split(".")[0]))

        pending_migrations = [f for f in migration_files if int(f.split(".")[0]) > current_version]

        if not pending_migrations:
            logger.info(f"[{label}] Database is up to date.")
            _recreate_views_for_engine(engine)
            return

        if label == "PostgreSQL":
            drop_all_views(engine)

        for migration_file in pending_migrations:
            logger.info(f"[{label}] Applying migration {migration_file}...")
            try:
                with open(os.path.join(migrations_path, migration_file), "r") as f:
                    sql_script = f.read()
                
                statements = [s.strip() for s in sql_script.split(';') if s.strip()]

                with connection.begin():
                    for statement in statements:
                        if label == "PostgreSQL":
                            statement = mapping_sqlite_to_postgres(statement)
                        connection.execute(text(statement))
                        
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
    _recreate_views_for_engine(engine)
    logger.info(f"[{label}] Migration completed in {round(time.time() - start,2)}s")


def run_migrations():
    """
    Runs the database migration system on both SQLite and PostgreSQL.
    """
    # SQLite
    _run_migrations_for_engine(get_database_engine())
    
    # PostgreSQL
    pg_engine = get_postgres_engine()
    if pg_engine:
        _run_migrations_for_engine(pg_engine)
        # pg_migrations()


def _recreate_views_for_engine(engine):
    """
    Internal helper to recreate views on a specific engine.
    """
    if 'postgresql' in str(engine.url):
        label = "PostgreSQL"
    if 'sqlite' in str(engine.url):
        label = "SQLite"
    logger.info(f"[{label}] Recreating views...")
    start = time.time()

    
    if label == "PostgreSQL":
        view_paths = ["db/SQL/views/PostgreSQL/"]
    else:
        view_paths = ["db/SQL/views/create_view/"]
    for views_path in view_paths:
        if not os.path.exists(views_path):
            logger.info(f"[{label}] Views directory not found at {views_path}. Skipping view recreation.")
            return

        view_files = [f for f in os.listdir(views_path) if f.endswith(".sql")]
        view_files.sort()
    
        pending_views = view_files.copy()
        
        with engine.connect() as connection:
            while pending_views:
                progress_made = False
                failed_views = []
                
                for view_file in pending_views:
                    try:
                        with open(os.path.join(views_path, view_file), "r") as f:
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
        else:
            logger.info(f"[{label}] View recreation finished with errors in {round(time.time() - start, 2)}s.")


def recreate_views():
    """
    Recreates all views in both databases.
    """
    # SQLite
    _recreate_views_for_engine(get_database_engine())
    
    # PostgreSQL
    pg_engine = get_postgres_engine()
    if pg_engine:
        _recreate_views_for_engine(pg_engine)

def table_exists(table_name: str) -> bool:
    """
    Checks if a table exists in the database.
    Returns True only if it exists in ALL active databases (SQLite and Postgres).
    """
    # Check SQLite
    engine = get_database_engine()
    inspector = inspect(engine)
    exists_sqlite = inspector.has_table(table_name)
    
    # Check Postgres
    exists_pg = True
    try:
        pg_engine = get_postgres_engine()
        if pg_engine:
            insp_pg = inspect(pg_engine)
            exists_pg = insp_pg.has_table(table_name)
    except Exception as e:
        logger.error(f"[PostgreSQL] Error checking table existence {table_name}: \n{e}")
        # If we can't check, we assume match sqlite or return False?
        # If we return False, we might trigger creation which might fail if DB is down.
        # But for 'side by side' test, we want to try to create if missing.
        exists_pg = False

    return exists_sqlite and exists_pg

def view_exists(view_name: str) -> bool:
    """
    Checks if a view exists in the database.
    Returns True only if it exists in ALL active databases.
    """
    # Check SQLite
    engine = get_database_engine()
    inspector = inspect(engine)
    exists_sqlite = view_name in inspector.get_view_names()

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

    return exists_sqlite and exists_pg

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
            if not error:
                logger.info(f"[PostgreSQL] Successfully in {round(time.time() - start_pg, 2)}s.")
            else:
                logger.info(f"[PostgreSQL] Completed with some errors in {round(time.time() - start_pg, 2)}s.")
    except Exception as e:
        logger.error(f"[PostgreSQL] Error: \n{e}")

def mapping_sqlite_to_postgres(sql: str) -> str:
    """
    Maps SQLite-specific SQL syntax to PostgreSQL-compatible syntax.
    This is a basic implementation and may need to be extended for complex queries.
    """
    # Example mappings
    mappings = {
        'DATETIME': 'TIMESTAMP',
        'REAL': 'DOUBLE PRECISION',
        'FLOAT': 'DOUBLE PRECISION'
    }
    # print(sql)
    for sqlite_syntax, pg_syntax in mappings.items():
        sql = re.sub(r'\b' + re.escape(sqlite_syntax) + r'\b', pg_syntax, sql, flags=re.IGNORECASE)
        sql = sql.replace(f'"{sqlite_syntax}"', f'"{pg_syntax}"')
    # print(sql)
    return sql

def data_validation():
    tables = select_into_dataframe(query="""
        SELECT
            name
        FROM
            sqlite_schema
        where
            type = 'table'
            and name <> 'sqlite_sequence'
        order by name;
    """)
    for index, row in tables.iterrows():
        table_name = row['name']
        count_df = select_into_dataframe(query=f'SELECT COUNT(*) as cnt FROM "{table_name}"')
        if not count_df.empty:
            count = count_df.iloc[0]['cnt']
            logger.info(f"[SQLite]     Table {table_name} has {count} rows.")
        count_df = select_into_dataframe_pg(query=f'SELECT COUNT(*) as cnt FROM "{table_name}"')
        if not count_df.empty:
            count = count_df.iloc[0]['cnt']
            logger.info(f"[PostgreSQL] Table {table_name} has {count} rows.")

def pg_migrate_week_to_ISO_week(pg_engine):

    if not pg_engine:
        logger.info("PostgreSQL not configured, skipping week to ISO week migration.")
        return
    if column_exists(pg_engine, "DatesHistory", "isoyear"):
        logger.info("PostgreSQL DatesHistory table already has isoyear column, skipping migration.")
        return
    
    with pg_engine.begin() as connection:
        # for table in HISTORY_ENABLED_TABLES:
        #     rename_weekly_table_column = f'ALTER TABLE "{table}HistoryWeekly" RENAME COLUMN year TO isoyear;'
        #     execute_sql(connection, rename_weekly_table_column, f"{table}HistoryWeekly", 'ALTER TABLE', "Migration to ISO week")

        #     update_weekly_table_data = f'''
        #         UPDATE "{table}HistoryWeekly" as weekly
        #         SET isoyear = EXTRACT(ISOYEAR FROM dh.date),
        #             week = EXTRACT(WEEK FROM dh.date)
        #         FROM (SELECT * FROM "DatesHistory" ORDER BY date DESC) AS dh
        #         WHERE weekly.isoyear = dh.year
        #         AND weekly.week = dh.week;
        #     '''
        #     execute_sql(connection, update_weekly_table_data, f"{table}HistoryWeekly", 'INSERT', "Migration to ISO week")
        
        # migrate DatesHistory table
        rename_dates_history = 'ALTER TABLE "DatesHistory" RENAME TO "DatesHistoryOld";'
        execute_sql(connection, rename_dates_history, "DatesHistory", 'ALTER TABLE', "Migration to ISO week")
        
        create_dates_history = """
            Create Table "DatesHistory"(
            date DATE PRIMARY KEY,
            year INT,
            month INT,
            isoyear INT,
            week INT
        );
        """
        execute_sql(connection, create_dates_history, "DatesHistory", 'CREATE TABLE', "Migration to ISO week")
        copy_dates_history = """
            INSERT INTO "DatesHistory" 
            (date, year, month, isoyear, week)
            SELECT
                date,
                EXTRACT(YEAR FROM date) AS year,
                EXTRACT(MONTH FROM date) AS month,
                EXTRACT(ISOYEAR FROM date) AS isoyear,
                EXTRACT(WEEK FROM date) AS week
            FROM "DatesHistoryOld";
        """
        execute_sql(connection, copy_dates_history, "DatesHistory", 'INSERT', "Migration to ISO week")

        drop_dates_history_old = 'DROP TABLE "DatesHistoryOld";'
        execute_sql(connection, drop_dates_history_old, "DatesHistory", 'DROP TABLE', "Migration to ISO week")

def column_exists(engine, table_name, column_name, schema=None):
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name, schema=schema)
    return any(col["name"] == column_name for col in columns)

def drop_all_views(engine):
    """
    Drops all views in database.
    """
    if 'postgresql' in str(engine.url):
        label = "PostgreSQL"
    if 'sqlite' in str(engine.url):
        label = "SQLite    "

    inspector = inspect(engine)
    views = inspector.get_view_names()
    with engine.begin() as connection:
        for view in views:
            try:
                connection.execute(text(f'DROP VIEW IF EXISTS "{view}" CASCADE'))
                logger.info(f"{label} Dropped view {view}.")
            except Exception as e:
                logger.error(f"{label} Error dropping view {view}: \n{e}")
    