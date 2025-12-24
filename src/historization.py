import logging
import time
from sqlalchemy import text
from src.database import get_database_engine, execute_sql
from src.decorator_log_function import log_function
from src.util import log_memory_usage

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
            logger.info(f"Found columns: {columns}")
            return columns
        except Exception as e:
            logger.error(f"Error fetching columns for {table_name}: {e}")
            return []

    @staticmethod
    @log_function
    def run_daily_historization(source_table: str, history_table: str, conflict_keys: list[str]):
        """
        Copies data from source_table to history_table with an UPSERT strategy.
        Adds a 'snapshot_date' column with the current date.
        """
        start_time = time.time()
        logger.info(f"Starting historization from {source_table} to {history_table}")
        
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
            select_cols_str = "date('now'), " + ", ".join([f'"{c}"' for c in column_names])
            
            # Update clause for UPSERT
            # Exclude conflict keys from the update set
            update_set = []
            for col in column_names:
                if col not in conflict_keys:
                    update_set.append(f'"{col}" = excluded."{col}"')
            
            update_clause = ", ".join(update_set)
            conflict_target = ", ".join([f'"{k}"' for k in conflict_keys])
            
            sql = f"""
                INSERT INTO "{history_table}" ({target_cols_str})
                SELECT {select_cols_str}
                FROM "{source_table}"
                WHERE 1=1
                ON CONFLICT(snapshot_date, {conflict_target}) DO UPDATE SET
                {update_clause}
            """
            
            # 3. Execute
            try:
                # Use the new helper function to execute and log
                execute_sql(connection, sql, history_table, "UPSERT")
            except Exception as e:
                logger.error(f"Error during historization execution: {e}")
                raise e

        duration = time.time() - start_time
        logger.info(f"Historization finished in {duration:.2f}s")

def run_historization_pipeline():
    """
    Orchestrates the historization process for all configured tables.
    """
    logger.info("Running Historization Pipeline...")
    log_memory_usage("[MEM] Start Historization: ")
    try:
        # OptionDataYahoo configuration
        HistorizationService.run_daily_historization(
            source_table="OptionDataYahoo",
            history_table="OptionDataYahooHistoryDaily",
            conflict_keys=["contractSymbol"]
        )
        log_memory_usage("[MEM] After OptionDataYahoo Historization: ")

        # OptionDataTradingView configuration
        HistorizationService.run_daily_historization(
            source_table="OptionDataTradingView",
            history_table="OptionDataTradingViewHistoryDaily",
            conflict_keys=["option_osi"]
        )
        log_memory_usage("[MEM] After OptionDataTradingView Historization: ")
        logger.info("Historization Pipeline Completed Successfully.")
    except Exception as e:
        logger.error(f"Historization Pipeline Failed: {e}")
