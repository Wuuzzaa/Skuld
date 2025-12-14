import logging
from sqlalchemy import inspect, text, MetaData, Table, Column, Date, Integer
from sqlalchemy.schema import CreateTable
from src.database import get_database_engine

logger = logging.getLogger(__name__)

class SchemaManager:
    def __init__(self):
        self.engine = get_database_engine()
        self.inspector = inspect(self.engine)

    def ensure_history_table(self, table_name: str):
        """
        Ensures that a history table exists for the given source table.
        The history table will have the name {table_name}_History.
        It will have the same schema as the source table, plus:
        - snapshot_date (DATE)
        - snapshot_id (INTEGER PRIMARY KEY AUTOINCREMENT)
        """
        history_table_name = f"{table_name}_History"
        
        if self.inspector.has_table(history_table_name):
            # logger.debug(f"History table {history_table_name} already exists.")
            return

        logger.info(f"Creating history table {history_table_name}...")
        
        if not self.inspector.has_table(table_name):
            logger.error(f"Source table {table_name} does not exist! Cannot create history table.")
            raise ValueError(f"Source table {table_name} does not exist.")

        # Reflect the source table
        metadata = MetaData()
        source_table = Table(table_name, metadata, autoload_with=self.engine)

        # Create the history table definition
        # We copy columns from source_table, but we need to be careful about Primary Keys.
        # The history table's PK should be snapshot_id. The original PKs become normal columns (or part of a composite index if we wanted, but let's keep it simple).
        
        history_columns = []
        for col in source_table.columns:
            # Create a copy of the column, but remove PK constraint and autoincrement
            # We want to store the exact value from the source, so we don't want autoincrement on the ID column if it had one.
            new_col = col.copy()
            new_col.primary_key = False
            new_col.autoincrement = False
            new_col.unique = False # Remove unique constraints as we will have multiple snapshots
            history_columns.append(new_col)

        # Add history-specific columns
        history_columns.append(Column('snapshot_date', Date, nullable=False, index=True))
        history_columns.append(Column('snapshot_id', Integer, primary_key=True, autoincrement=True))

        history_table = Table(history_table_name, metadata, *history_columns)

        # Create the table
        try:
            history_table.create(self.engine)
            logger.info(f"Successfully created history table {history_table_name}")
        except Exception as e:
            logger.error(f"Failed to create history table {history_table_name}: {e}")
            raise

    def create_history_view(self, view_name: str):
        """
        Attempts to create a history view by replacing table references in the original view definition.
        This is a best-effort approach.
        """
        # This is complex to implement robustly without a SQL parser. 
        # For now, we will skip this as per the "User Review Required" section of the plan,
        # relying on the interface to specify physical tables.
        pass
