from typing import Literal
import pandas as pd
from sqlalchemy import create_engine, text, inspect

from config import PATH_DATABASE
import os
import re


def get_database_engine():
    """
    Creates and returns a SQLAlchemy engine for the SQLite database.
    """
    return create_engine(f'sqlite:///{PATH_DATABASE}')


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
        try:
            connection.execute(text(f"DELETE FROM {table_name}"))
            print(f"Successfully truncated table: {table_name}")
        except Exception as e:
            print(f"Error truncating table {table_name}: {e}")

def insert_into_table(
        table_name: str,
        dataframe,
        if_exists: Literal["fail", "replace", "append"] = "append"
    ) -> int:
    affected_rows = 0
    try:
        engine = get_database_engine()
        affected_rows = dataframe.to_sql(table_name, engine, if_exists=if_exists, index=False)
        print(f"Successfully saved {affected_rows} to the database table {table_name}.")
    except Exception as e:
        print(f"Error saving to the database table {table_name}: {e}")

    return affected_rows

def select_into_dataframe(query: str = None, sql_file_path: str = None):
    """
    Executes a SQL query and returns the result as a DataFrame.
    You can provide either a SQL query string or a path to a .sql file.

    Parameters:
    - query (str, optional): SQL query string to execute.
    - sql_file_path (str, optional): Path to a .sql file containing the query.

    Returns:
    - pd.DataFrame: Result of the query.
    """
    df = None
    try:
        engine = get_database_engine()
        if sql_file_path is not None and os.path.isfile(sql_file_path):
            with open(sql_file_path, 'r') as f:
                sql = f.read()
        elif query is not None:
            sql = query
        else:
            raise ValueError("Either 'query' or 'sql_file_path' must be provided.")
        df = pd.read_sql(sql, engine)
        print(df.head())
    except Exception as e:
        print(f"Error executing query {query}: {e}")
    
    return df

def run_migrations():
    """
    Runs the database migration system.
    """
    print("Starting database migration...")
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