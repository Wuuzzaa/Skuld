import time
import os
import re
import pandas as pd
import sqlite3
from typing import Literal
from sqlalchemy import create_engine, text, inspect
from config import PATH_DATABASE_FILE, PATH_DATABASE_QUERY_FOLDER

# Global variable for the in-memory engine
_in_memory_engine = None
_in_memory_initialized = False


def get_database_engine():
    """
    Creates and returns an SQLAlchemy engine for the SQLite database.
    """
    return create_engine(f'sqlite:///{str(PATH_DATABASE_FILE.absolute())}')


def get_in_memory_engine():
    """
    Returns a singleton in-memory SQLAlchemy engine.
    The database is loaded once and reused for all subsequent calls.
    """
    global _in_memory_engine, _in_memory_initialized

    if _in_memory_engine is None:
        print("Creating in-memory database engine...")
        _in_memory_engine = create_engine('sqlite:///:memory:')
        _in_memory_initialized = False

    if not _in_memory_initialized:
        _load_database_into_memory()
        _in_memory_initialized = True

    return _in_memory_engine


def _load_database_into_memory():
    """
    Loads the entire database from disk into memory using SQLite's backup API.
    This is much faster and more reliable than copying tables individually.
    """
    print(f"Loading database from {PATH_DATABASE_FILE} into memory...")
    start = time.time()

    # Get raw connections from engines
    source_conn = sqlite3.connect(str(PATH_DATABASE_FILE.absolute()))

    # Get the actual sqlite3.Connection from SQLAlchemy's connection pool
    target_conn_wrapper = _in_memory_engine.raw_connection()
    target_conn = target_conn_wrapper.driver_connection

    # Use SQLite's backup API to copy the entire database
    source_conn.backup(target_conn)
    source_conn.close()
    target_conn_wrapper.close()

    print(f"Database loaded into memory in {round(time.time() - start, 2)}s")

def reload_in_memory_database():
    """
    Forces a reload of the in-memory database from disk.
    Call this after making changes to the database file.
    """
    global _in_memory_initialized
    _in_memory_initialized = False
    get_in_memory_engine()

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
        except Exception as e:
            print(f"Error truncating table {table_name}: {e}")

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
        print(f"Successfully saved {affected_rows} to the database table {table_name} in {round(time.time() - start,2)}s.")
    except Exception as e:
        print(f"Error saving to the database table {table_name}: {e}")

    return affected_rows


def select_into_dataframe(
        query: str = None,
        sql_file_path: str = None,
        params: dict = None,
        use_in_memory: bool = True
):
    """
    Executes a SQL query and returns the result as a DataFrame.

    Parameters:
    - query (str, optional): SQL query string to execute.
    - sql_file_path (str, optional): Path to a .sql file containing the query.
    - params (dict, optional): Dictionary of parameters to bind to the query.
    - use_in_memory (bool): If True, uses the in-memory database for faster reads. Default: True.

    Returns:
    - pd.DataFrame: Result of the query.
    """
    df = None
    try:
        print(f"Executing query: {query} parameters: {params}")
        start = time.time()

        # Use in-memory engine for reads by default
        engine = get_in_memory_engine() if use_in_memory else get_database_engine()

        if sql_file_path is not None and os.path.isfile(sql_file_path):
            with open(sql_file_path, 'r') as f:
                sql = f.read()
        elif query is not None:
            sql = query
        else:
            raise ValueError("Either 'query' or 'sql_file_path' must be provided.")

        # If parameters are provided, use text() with bound parameters
        if params:
            sql = text(sql)
            df = pd.read_sql(sql, engine, params=params)
        else:
            df = pd.read_sql(sql, engine)

        print(f"Query executed successfully in {round(time.time() - start, 2)}s. Top 5 rows:")
        print(f"Dataframe shape: {df.shape}")
        print(df.head())
    except Exception as e:
        print(f"Error executing query {query}: {e}")

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


if __name__ == "__main__":
    """
    Benchmark comparing file-based vs in-memory database queries.
    """
    print("=" * 80)
    print("DATABASE QUERY BENCHMARK: File-based vs In-Memory")
    print("=" * 80)

    # Get all SQL query files using relative path from current file
    query_files = list(PATH_DATABASE_QUERY_FOLDER.glob("*.sql"))

    if not query_files:
        print(f"No query files found in {PATH_DATABASE_QUERY_FOLDER}")
        print(f"Looking for: {PATH_DATABASE_QUERY_FOLDER.absolute()}")
        exit(1)

    print(f"\nFound {len(query_files)} query files to benchmark")
    print(f"Query directory: {PATH_DATABASE_QUERY_FOLDER.absolute()}\n")

    # Pre-load in-memory database before benchmark starts (for fair comparison)
    print("Pre-loading in-memory database...")
    get_in_memory_engine()
    print("In-memory database ready!\n")

    results = []

    for sql_file in sorted(query_files):
        query_name = sql_file.name

        # ignore query with parameter
        if query_name == "spreads_input.sql":
            continue

        print(f"\n{'─' * 80}")
        print(f"Testing: {query_name}")
        print(f"{'─' * 80}")

        # Benchmark file-based query
        print("\n[File-based]")
        start_file = time.time()
        df_file = select_into_dataframe(sql_file_path=str(sql_file), use_in_memory=False)
        time_file = time.time() - start_file

        # Benchmark in-memory query
        print("\n[In-Memory]")
        start_memory = time.time()
        df_memory = select_into_dataframe(sql_file_path=str(sql_file), use_in_memory=True)
        time_memory = time.time() - start_memory

        # Calculate speedup
        speedup = time_file / time_memory if time_memory > 0 else 0

        results.append({
            'query': query_name,
            'file_time': time_file,
            'memory_time': time_memory,
            'speedup': speedup,
            'rows': len(df_memory) if df_memory is not None else 0
        })

        print(f"\n📊 Results for {query_name}:")
        print(f"   File-based:  {time_file:.4f}s")
        print(f"   In-Memory:   {time_memory:.4f}s")
        print(f"   Speedup:     {speedup:.2f}x faster")
        print(f"   Rows:        {len(df_memory) if df_memory is not None else 0}")

    # Summary
    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    print(f"\n{'Query':<40} {'File (s)':<12} {'Memory (s)':<12} {'Speedup':<10} {'Rows':<10}")
    print("─" * 80)

    for r in results:
        print(
            f"{r['query']:<40} {r['file_time']:<12.4f} {r['memory_time']:<12.4f} {r['speedup']:<10.2f}x {r['rows']:<10}")

    # Overall statistics
    avg_speedup = sum(r['speedup'] for r in results) / len(results) if results else 0
    total_file_time = sum(r['file_time'] for r in results)
    total_memory_time = sum(r['memory_time'] for r in results)

    print("─" * 80)
    print(
        f"{'TOTAL':<40} {total_file_time:<12.4f} {total_memory_time:<12.4f} {total_file_time / total_memory_time if total_memory_time > 0 else 0:<10.2f}x")
    print(f"\nAverage Speedup: {avg_speedup:.2f}x")
    print(
        f"Time Saved: {total_file_time - total_memory_time:.4f}s ({((total_file_time - total_memory_time) / total_file_time * 100):.1f}%)")
    print("=" * 80)