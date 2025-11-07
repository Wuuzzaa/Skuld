import time
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

    engine = create_engine(f'sqlite:///{str(PATH_DATABASE_FILE.absolute())}')
    return engine

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
            duration = round(time.time() - start, 2)
            print(f"Successfully truncated table: {table_name} in {duration}s")
            connection.close()
            _write_table_log(
            table_name=table_name,
            action="TRUNCATE",
            duration_seconds=duration,
            success=True
        )            

        except Exception as e:
            duration = round(time.time() - start, 2)
            print(f"Error truncating table {table_name}: {e}")
            connection.close()
            _write_table_log(
                table_name=table_name,
                action="TRUNCATE",
                duration_seconds=duration,
                success=False
            )         

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
        duration = round(time.time() - start, 2) 
        print(f"Successfully saved {affected_rows} rows to the database table {table_name} in {duration}s.")
        _write_table_log(
            table_name=table_name,
            action="INSERT",
            details=f"if_exists={if_exists}",
            duration_seconds=duration,
            success=True,
            rows_affected=affected_rows
        )
    except Exception as e:
        duration = round(time.time() - start, 2)
        print(f"Error saving to the database table {table_name}: {e}")
        _write_table_log(
            table_name=table_name,
            action="INSERT",
            details=f"if_exists={if_exists}",
            duration_seconds=duration,
            success=False,
            rows_affected=affected_rows,
            error_message=str(e)
        )

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

def _write_table_log(
    table_name: str,
    action: str,
    duration_seconds: float,
    success: bool,
    rows_affected: int = None,
    details: str = None,
    error_message: str = None,
    additional_info: str = None
):
    engine = get_database_engine()
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO TableLog
                (table_name, action, details, duration_seconds, success, rows_affected, error_message, additional_info)
                VALUES (:table_name, :action, :details, :duration_seconds, :success, :rows_affected, :error_message, :additional_info)
            """), {
                "table_name": table_name,
                "action": action,
                "details": details,
                "duration_seconds": duration_seconds,
                # SQLite speichert Booleans als 0/1
                "success": 1 if success else 0,
                "rows_affected": rows_affected,
                "error_message": error_message,
                "additional_info": additional_info
            })
    except Exception as log_err:
        logger.error(f"Failed to write TableLog for {table_name} ({action}): {log_err}")

def last_modified_time_of_table(table_name: str, action: Literal["INSERT", "TRUNCATE"] = "") -> pd.Timestamp:
    """
    Returns the last modified time of a table based on the TableLog entries.
    If no entries exist, returns None.
    """
    engine = get_database_engine()
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT MAX(timestamp) as last_modified
                FROM TableLog
                WHERE table_name = :table_name AND success = 1
                   {f'AND action = :action' if action else ''}
            """), {"table_name": table_name}).fetchone()
            if result and result['last_modified']:
                return pd.to_datetime(result['last_modified'])
    except Exception as e:
        logger.error(f"Error fetching last modified time for table {table_name}: {e}")
    return None