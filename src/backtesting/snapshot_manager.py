import logging
import datetime
from typing import List, Dict
from sqlalchemy import text
from src.database import get_database_engine
from src.backtesting.interface import BacktestStrategy, DataRequirement
from src.backtesting.schema_manager import SchemaManager

logger = logging.getLogger(__name__)

class SnapshotManager:
    def __init__(self):
        self.strategies: List[BacktestStrategy] = []
        self.schema_manager = SchemaManager()
        self.engine = get_database_engine()

    def register_strategy(self, strategy: BacktestStrategy):
        self.strategies.append(strategy)

    def perform_snapshot(self):
        """
        Collects requirements from all registered strategies, aggregates them by table,
        and performs snapshots into history tables.
        """
        logger.info("Starting data snapshot process...")
        
        # 1. Collect and Aggregate Requirements
        requirements_by_table: Dict[str, List[DataRequirement]] = {}
        
        for strategy in self.strategies:
            try:
                reqs = strategy.get_data_requirements()
                for req in reqs:
                    if req.source_table not in requirements_by_table:
                        requirements_by_table[req.source_table] = []
                    requirements_by_table[req.source_table].append(req)
            except Exception as e:
                logger.error(f"Error getting requirements from strategy {strategy}: {e}")

        # 2. Process each table
        for table_name, reqs in requirements_by_table.items():
            self._process_table_snapshot(table_name, reqs)
            
        logger.info("Data snapshot process completed.")

    def _process_table_snapshot(self, table_name: str, reqs: List[DataRequirement]):
        logger.info(f"Processing snapshot for table: {table_name}")
        
        # Ensure history table exists
        try:
            self.schema_manager.ensure_history_table(table_name)
        except Exception as e:
            logger.error(f"Skipping snapshot for {table_name} due to schema error: {e}")
            return

        # Build Filter Condition
        # We combine all filters with OR. 
        # If any req has filter_condition=None, it means "All Rows", so we don't filter.
        
        conditions = []
        select_all = False
        
        for req in reqs:
            if req.filter_condition is None:
                select_all = True
                break
            conditions.append(f"({req.filter_condition})")
        
        where_clause = ""
        if not select_all and conditions:
            where_clause = "WHERE " + " OR ".join(conditions)
        elif not select_all and not conditions:
            # Should not happen if reqs is not empty, but if it is, we select nothing?
            # If we have requirements but no conditions and not select_all, it implies we have requirements with empty conditions?
            # Actually if reqs is not empty, we iterate.
            # If all reqs have conditions, we join them.
            pass

        # Construct the INSERT query
        # We select * from source.
        # We add current date as snapshot_date.
        # snapshot_id is auto-generated.
        
        # We need to list columns explicitly to match the history table schema (excluding snapshot_id)
        # OR we can rely on the order if we are careful.
        # Safer to list columns.
        
        # Get columns from source table
        inspector = self.schema_manager.inspector
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        
        # Construct column list string
        cols_str = ", ".join(columns)
        
        # History table has cols_str + snapshot_date. snapshot_id is auto.
        
        query = f"""
            INSERT INTO {table_name}_History ({cols_str}, snapshot_date)
            SELECT DISTINCT {cols_str}, DATE('now')
            FROM {table_name}
            {where_clause}
        """
        
        # Execute
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text(query))
                logger.info(f"Snapshotted {result.rowcount} rows from {table_name} to {table_name}_History")
        except Exception as e:
            logger.error(f"Error executing snapshot for {table_name}: {e}")
            # logger.debug(f"Query was: {query}")
