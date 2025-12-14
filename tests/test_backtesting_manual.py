import logging
import pandas as pd
from sqlalchemy import text, inspect
from src.database import get_database_engine, insert_into_table
from src.backtesting.snapshot_manager import SnapshotManager
from src.backtesting.dummy_strategy import DummyStrategy

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_backtesting_snapshot():
    engine = get_database_engine()
    table_name = "Test_Backtesting_Source"
    
    # 1. Setup: Create Source Table and Insert Data
    logger.info("Setting up test data...")
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        conn.execute(text(f"DROP TABLE IF EXISTS {table_name}_History"))
        conn.execute(text(f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY, name TEXT, value INTEGER)"))
    
    data = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "name": ["A", "B", "C", "D"],
        "value": [5, 15, 25, 5]
    })
    insert_into_table(table_name, data)
    
    # 2. Run Snapshot
    logger.info("Running snapshot...")
    strategy = DummyStrategy(table_name=table_name)
    manager = SnapshotManager()
    manager.register_strategy(strategy)
    manager.perform_snapshot()
    
    # 3. Verify
    logger.info("Verifying results...")
    inspector = inspect(engine)
    
    # Check History Table Exists
    if not inspector.has_table(f"{table_name}_History"):
        logger.error("History table was not created!")
        return False
        
    # Check Content
    # Strategy filters for value > 10, so we expect ID 2 and 3.
    df_history = pd.read_sql(f"SELECT * FROM {table_name}_History", engine)
    logger.info(f"History Table Content:\n{df_history}")
    
    if len(df_history) != 2:
        logger.error(f"Expected 2 rows, got {len(df_history)}")
        return False
        
    if not all(df_history['value'] > 10):
        logger.error("Filter condition failed!")
        return False
        
    if 'snapshot_date' not in df_history.columns:
        logger.error("snapshot_date column missing!")
        return False
        
    logger.info("Test PASSED!")
    
    # Cleanup
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        conn.execute(text(f"DROP TABLE IF EXISTS {table_name}_History"))
        
    return True

if __name__ == "__main__":
    test_backtesting_snapshot()
