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
    start = time.time()
    engine = get_database_engine()
    with engine.begin() as connection:
        try:
            connection.execute(text(f"DELETE FROM {table_name}"))
            print(f"Successfully truncated table: {table_name} in {round(time.time() - start,2)}s")
            
            # Log the operation
            log_data_change(connection, "TRUNCATE", table_name, affected_rows=None)
            
        except Exception as e:
            print(f"Error truncating table {table_name}: {e}")

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
        print(f"Error logging data change: {e}")

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
        print(f"Successfully saved {affected_rows} rows to the database table {table_name} in {round(time.time() - start,2)}s.")
        
        # Log the operation
        with engine.begin() as connection:
            log_data_change(connection, "INSERT", table_name, affected_rows=affected_rows)
            
    except Exception as e:
        print(f"Error saving to the database table {table_name}: {e}")

    return affected_rows

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

def run_migrations():
    """
    Runs the database migration system.
    """
    print("Starting database migration...")
    start = time.time() 
    engine = get_database_engine()
    inspector = inspect(engine)

    with engine.connect() as connection:
        if not inspector.has_table("DbVersion"):
            with connection.begin():
                print("DbVersion table not found. Creating it...")
                with open("db/SQL/tables/create_table/DbVersion.sql", "r") as f:
                    connection.execute(text(f.read()))
                connection.execute(text("INSERT INTO DbVersion (version) VALUES (0)"))
                print("DbVersion table created and initialized with version 0.")

        with connection.begin():
            result = connection.execute(text("SELECT version FROM DbVersion")).fetchone()
            current_version = result[0]
        print(f"Current database version: {current_version}")

        migrations_path = "db/SQL/migrations/"
        if not os.path.exists(migrations_path):
            print(f"Migrations directory not found at {migrations_path}. Skipping migrations.")
            return
            
        migration_files = [f for f in os.listdir(migrations_path) if re.match(r"\d+\.sql", f)]
        migration_files.sort(key=lambda x: int(x.split(".")[0]))

        pending_migrations = [f for f in migration_files if int(f.split(".")[0]) > current_version]

        if not pending_migrations:
            print("Database is up to date.")
            return

        for migration_file in pending_migrations:
            version = int(migration_file.split(".")[0])
            print(f"Applying migration {migration_file}...")
            try:
                with open(os.path.join(migrations_path, migration_file), "r") as f:
                    sql_script = f.read()
                
                statements = [s.strip() for s in sql_script.split(';') if s.strip()]

                with connection.begin():
                    for statement in statements:
                        connection.execute(text(statement))
                        
                print(f"Migration {migration_file} applied successfully.")
            except Exception as e:
                print(f"Error applying migration {migration_file}: {e}")
                raise

        with connection.begin():
            last_migration_version = int(pending_migrations[-1].split(".")[0])
            connection.execute(text(f"UPDATE DbVersion SET version = {last_migration_version}"))
            print(f"Database version updated to {last_migration_version}.")
    print(f"Database migration completed in {round(time.time() - start,2)}s")