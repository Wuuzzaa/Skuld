import time
import datetime
import os
import re
import pandas as pd
import logging
from typing import Literal
from sqlalchemy import create_engine, text, inspect
from config import PATH_DATABASE_FILE
from src.decorator_log_function import log_function

# logging
logger = logging.getLogger(__name__)


def get_database_engine():
    """
    Creates and returns a SQLAlchemy engine for the SQLite database.
    """
    # return create_engine(f'sqlite:///{PATH_DATABASE_FILE}')
    return create_engine(f'sqlite:///{str(PATH_DATABASE_FILE.absolute())}')


def truncate_table(table_name):
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
    engine = get_database_engine()
    with engine.begin() as connection:
        execute_sql(connection, f"DELETE FROM {table_name}", table_name, "TRUNCATE")

def log_data_change(connection, operation_type, table_name, affected_rows=None, additional_data=None):
    """
    Logs a data change operation to the DataChangeLogs table.
    """
    try:
        timestamp = datetime.datetime.now().isoformat()
        query = text("""
            INSERT INTO DataChangeLogs (timestamp, operation_type, table_name, affected_rows, additional_data)
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
        logger.error(f"Error logging data change: {e}")

def insert_into_table(
        table_name: str,
        dataframe: pd.DataFrame,
        if_exists: Literal["fail", "replace", "append"] = "append"
    ) -> int:
    affected_rows = 0
    start = time.time() 
    try:
        engine = get_database_engine()
        affected_rows = dataframe.to_sql(table_name, engine, if_exists=if_exists, index=False)
        logger.info(f"Successfully saved {affected_rows} rows to the database table {table_name} in {round(time.time() - start,2)}s.")
        
        # Log the operation
        with engine.begin() as connection:
            log_data_change(connection, "INSERT", table_name, affected_rows=affected_rows)
            
    except Exception as e:
        logger.error(f"Error saving to the database table {table_name}: {e}")

    return affected_rows

def execute_sql(connection, sql: str, table_name: str, operation_type: str = "INSERT", additional_data=None):
    """
    Executes a raw SQL statement and logs the data change.
    
    Parameters:
    - connection: SQLAlchemy connection object (must be inside a transaction).
    - sql (str): The raw SQL statement to execute.
    - table_name (str): The name of the table being modified.
    - operation_type (str): The type of operation (INSERT, UPDATE, DELETE).
    """
    try:
        start = time.time()
        result = connection.execute(text(sql))
        affected_rows = result.rowcount
        
        logger.info(f"Successfully executed {operation_type} SQL on {table_name} in {round(time.time() - start, 2)}s. Rows affected: {affected_rows}")
        
        # Log the operation
        log_data_change(connection, operation_type, table_name, affected_rows=affected_rows, additional_data=additional_data)
        
        return affected_rows
    except Exception as e:
        logger.error(f"Error executing SQL on {table_name}: {e}")
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
    df = None
    try:
        #print(f"Executing query: {query} parameters: {params}")
        start = time.time()
        engine = get_database_engine()

        if sql_file_path is not None and os.path.isfile(sql_file_path):
            with open(sql_file_path, 'r') as f:
                sql = f.read()
        elif query is not None:
            sql = query
        else:
            msg = "Either 'query' or 'sql_file_path' must be provided."
            logger.error(msg)
            raise ValueError(msg)

        # If parameters are provided, use text() with bound parameters
        if params:
            sql = text(sql)
            df = pd.read_sql(sql, engine, params=params)
        else:
            df = pd.read_sql(sql, engine)

        logger.debug(f"Query executed successfully in {round(time.time() - start, 2)}s. Top 5 rows:")
    except Exception as e:
        logger.error(f"Error executing query {query}: {e}")

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

def run_migrations():
    """
    Runs the database migration system.
    """
    logger.info("Starting database migration...")
    start = time.time() 
    engine = get_database_engine()
    inspector = inspect(engine)

    with engine.connect() as connection:
        if not inspector.has_table("DbVersion"):
            with connection.begin():
                logger.info("DbVersion table not found. Creating it...")
                with open("db/SQL/tables/create_table/DbVersion.sql", "r") as f:
                    connection.execute(text(f.read()))
                connection.execute(text("INSERT INTO DbVersion (version) VALUES (0)"))
                logger.info("DbVersion table created and initialized with version 0.")

        with connection.begin():
            result = connection.execute(text("SELECT version FROM DbVersion")).fetchone()
            current_version = result[0]
        logger.info(f"Current database version: {current_version}")

        migrations_path = "db/SQL/migrations/"
        if not os.path.exists(migrations_path):
            logger.info(f"Migrations directory not found at {migrations_path}. Skipping migrations.")
            recreate_views()
            return
            
        migration_files = [f for f in os.listdir(migrations_path) if re.match(r"\d+\.sql", f)]
        migration_files.sort(key=lambda x: int(x.split(".")[0]))

        pending_migrations = [f for f in migration_files if int(f.split(".")[0]) > current_version]

        if not pending_migrations:
            logger.info("Database is up to date.")
            recreate_views()
            return

        for migration_file in pending_migrations:
            version = int(migration_file.split(".")[0])
            logger.info(f"Applying migration {migration_file}...")
            try:
                with open(os.path.join(migrations_path, migration_file), "r") as f:
                    sql_script = f.read()
                
                statements = [s.strip() for s in sql_script.split(';') if s.strip()]

                with connection.begin():
                    for statement in statements:
                        connection.execute(text(statement))
                        
                logger.info(f"Migration {migration_file} applied successfully.")
            except Exception as e:
                logger.error(f"Error applying migration {migration_file}: {e}")
                raise

        with connection.begin():
            last_migration_version = int(pending_migrations[-1].split(".")[0])
            connection.execute(text(f"UPDATE DbVersion SET version = {last_migration_version}"))
            logger.info(f"Database version updated to {last_migration_version}.")
    
    # Recreate views after migrations
    recreate_views()

    logger.info(f"Database migration completed in {round(time.time() - start,2)}s")


def recreate_views():
    """
    Recreates all views in the database.
    Handles dependencies by retrying failed view creations until all succeed or no progress is made.
    """
    logger.info("Recreating views...")
    start = time.time()
    engine = get_database_engine()
    
    view_paths = ["db/SQL/views/create_view/history/", "db/SQL/views/create_view/"]
    for views_path in view_paths:
        if not os.path.exists(views_path):
            logger.info(f"Views directory not found at {views_path}. Skipping view recreation.")
            return

        view_files = [f for f in os.listdir(views_path) if f.endswith(".sql")]
    
        pending_views = view_files.copy()
        
        with engine.connect() as connection:
            while pending_views:
                progress_made = False
                failed_views = []
                
                for view_file in pending_views:
                    try:
                        with open(os.path.join(views_path, view_file), "r") as f:
                            sql_script = f.read()
                        
                        # Execute the view creation script
                        # We assume the script contains DROP VIEW IF EXISTS and CREATE VIEW
                        statements = [s.strip() for s in sql_script.split(';') if s.strip()]
                        
                        with connection.begin():
                            for statement in statements:
                                connection.execute(text(statement))
                        
                        # print(f"Successfully created view from {view_file}")
                        progress_made = True
                    except Exception as e:
                        # If it fails, it might be due to missing dependency, so we try again later
                        logger.error(f"Failed to create view {view_file}: {e}")
                        failed_views.append(view_file)
                
                if not progress_made and failed_views:
                    logger.error(f"Error: Could not create the following views due to potential circular dependencies or errors: {failed_views}")
                    # We stop here to avoid infinite loop
                    # Optionally raise an error, but for now just printing
                    break
                
                pending_views = failed_views

        if not pending_views:
            logger.info(f"All views recreated successfully in {round(time.time() - start, 2)}s.")
        else:
            logger.info(f"View recreation finished with errors in {round(time.time() - start, 2)}s.")

def table_exists(table_name: str) -> bool:
    """
    Checks if a table exists in the database.
    """
    engine = get_database_engine()
    inspector = inspect(engine)
    return inspector.has_table(table_name)

def view_exists(view_name: str) -> bool:
    """
    Checks if a view exists in the database.
    """
    engine = get_database_engine()
    inspector = inspect(engine)
    return view_name in inspector.get_view_names()
