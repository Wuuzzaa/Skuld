import unittest
import pandas as pd
import time
from sqlalchemy import text
from src.database import insert_into_table, truncate_table, get_database_engine, run_migrations

class TestDatabaseLogging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure migrations are run so the logging table exists
        run_migrations()
        cls.test_table = "TestLoggingTable"
        cls.engine = get_database_engine()
        
        # Create a dummy table for testing
        with cls.engine.begin() as connection:
            connection.execute(text(f"CREATE TABLE IF NOT EXISTS {cls.test_table} (id INTEGER PRIMARY KEY, name TEXT)"))

    @classmethod
    def tearDownClass(cls):
        # Clean up the dummy table
        with cls.engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS {cls.test_table}"))

    def test_logging(self):
        # 1. Test Insert Logging
        df = pd.DataFrame({'id': [1, 2], 'name': ['Alice', 'Bob']})
        insert_into_table(self.test_table, df, if_exists='replace')
        
        # Verify log entry for insert
        with self.engine.connect() as connection:
            result = connection.execute(text(f"SELECT * FROM DataChangeLogs WHERE table_name = '{self.test_table}' AND operation_type = 'INSERT' ORDER BY id DESC LIMIT 1")).fetchone()
            
        self.assertIsNotNone(result, "Insert log entry not found")
        self.assertEqual(result.table_name, self.test_table)
        self.assertEqual(result.operation_type, 'INSERT')
        self.assertEqual(result.affected_rows, 2)
        print(f"Insert Log Verified: {result}")

        # 2. Test Truncate Logging
        truncate_table(self.test_table)
        
        # Verify log entry for truncate
        with self.engine.connect() as connection:
            result = connection.execute(text(f"SELECT * FROM DataChangeLogs WHERE table_name = '{self.test_table}' AND operation_type = 'TRUNCATE' ORDER BY id DESC LIMIT 1")).fetchone()
            
        self.assertIsNotNone(result, "Truncate log entry not found")
        self.assertEqual(result.table_name, self.test_table)
        self.assertEqual(result.operation_type, 'TRUNCATE')
        # Truncate might not return affected rows depending on implementation, but we check it exists
        print(f"Truncate Log Verified: {result}")

if __name__ == '__main__':
    unittest.main()
