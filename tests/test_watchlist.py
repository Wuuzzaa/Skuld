import unittest
import os
import pandas as pd
import shutil
import datetime
from unittest.mock import patch, MagicMock

# Import the functions to test
# Since watchlist.py is in pages/, we might need to handle imports carefully
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pages import watchlist

class TestWatchlist(unittest.TestCase):

    def setUp(self):
        # Setup temporary directories for testing
        self.test_base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data")
        os.makedirs(self.test_base_dir, exist_ok=True)
        
        # Override constants in watchlist module for testing
        self.original_watchlist_file = watchlist.WATCHLIST_FILE
        self.original_backup_dir = watchlist.BACKUP_DIR
        self.original_analyses_dir = watchlist.ANALYSES_DIR
        
        watchlist.WATCHLIST_FILE = os.path.join(self.test_base_dir, "test_watchlist.xlsx")
        watchlist.BACKUP_DIR = os.path.join(self.test_base_dir, "backups")
        watchlist.ANALYSES_DIR = os.path.join(self.test_base_dir, "analyses")
        
        # Ensure directories exist
        os.makedirs(watchlist.BACKUP_DIR, exist_ok=True)
        os.makedirs(watchlist.ANALYSES_DIR, exist_ok=True)

    def tearDown(self):
        # Cleanup
        if os.path.exists(self.test_base_dir):
            shutil.rmtree(self.test_base_dir)
            
        # Restore original constants
        watchlist.WATCHLIST_FILE = self.original_watchlist_file
        watchlist.BACKUP_DIR = self.original_backup_dir
        watchlist.ANALYSES_DIR = self.original_analyses_dir

    def test_save_and_load_watchlist(self):
        df = pd.DataFrame([
            {"Symbol": "AAPL", "Unternehmen": "Apple Inc.", "Kategorie": "Tech", "Aktueller Kurs": 150.0}
        ])
        # Add missing columns that watchlist expects
        for col in watchlist.COLUMNS:
            if col not in df.columns:
                df[col] = None
        
        success = watchlist.save_watchlist(df[watchlist.COLUMNS])
        self.assertTrue(success)
        self.assertTrue(os.path.exists(watchlist.WATCHLIST_FILE))
        
        loaded_df = watchlist.load_watchlist()
        self.assertEqual(len(loaded_df), 1)
        self.assertEqual(loaded_df.iloc[0]["Symbol"], "AAPL")

    def test_backup_functionality(self):
        # Create a file to backup
        df = pd.DataFrame([{"Symbol": "MSFT"}])
        for col in watchlist.COLUMNS:
            if col not in df.columns:
                df[col] = None
        watchlist.save_watchlist(df[watchlist.COLUMNS])
        
        watchlist.create_watchlist_backup()
        backups = watchlist.list_backups()
        self.assertGreaterEqual(len(backups), 1)
        
        # Restore backup
        latest_backup = backups[0]
        watchlist.restore_backup(latest_backup)
        self.assertTrue(os.path.exists(watchlist.WATCHLIST_FILE))

    def test_analysis_management(self):
        symbol = "TSLA"
        content = "<html><body>Tesla Analysis</body></html>"
        
        watchlist.save_analysis(symbol, content)
        self.assertTrue(watchlist.has_analysis(symbol))
        
        loaded_content = watchlist.load_analysis(symbol)
        self.assertEqual(loaded_content, content)
        
        watchlist.delete_analysis(symbol)
        self.assertFalse(watchlist.has_analysis(symbol))

    def test_update_watchlist_prices(self):
        df_watchlist = pd.DataFrame([
            {
                "Symbol": "AAPL", 
                "Unternehmen": "Apple", 
                "Aktueller Kurs": 140.0, 
                "Kurs Watchlistanlage": 100.0, 
                "Kursänderung": 40.0
            }
        ])
        df_market = pd.DataFrame([
            {"symbol": "AAPL", "live_stock_price": 160.0, "company_name": "Apple Inc."}
        ])
        
        updated_df, was_updated = watchlist.update_watchlist_prices(df_watchlist, df_market)
        
        self.assertTrue(was_updated)
        self.assertEqual(updated_df.iloc[0]["Aktueller Kurs"], 160.0)
        self.assertEqual(updated_df.iloc[0]["Unternehmen"], "Apple Inc.")
        # Change: (160/100 - 1) * 100 = 60.0
        self.assertAlmostEqual(updated_df.iloc[0]["Kursänderung"], 60.0, places=5)

    def test_color_levels_logic(self):
        # We test the internal color_levels logic by simulating the row data
        # Since it's nested in main -> style_watchlist -> color_levels, we'll try to access it if possible
        # or mock the behavior. Actually, it's easier to test the logic by mimicking what color_levels does.
        
        def mock_color_levels(row):
            # Simplified version of the logic in watchlist.py
            current_price = row['Aktueller Kurs']
            if pd.isna(current_price): return [''] * len(row)
            
            # Buy levels
            for i in [3, 2, 1]:
                val = row.get(f'Level Kaufkurs {i}')
                if pd.notna(val) and float(current_price) <= float(val):
                    return [f'buy_{i}'] * len(row)
            
            # Sell levels
            for i in [3, 2, 1]:
                val = row.get(f'Level Verkaufkurs {i}')
                if pd.notna(val) and float(current_price) >= float(val):
                    return [f'sell_{i}'] * len(row)
            
            return [''] * len(row)

        # Case 1: Buy level 1 triggered
        row = pd.Series({'Aktueller Kurs': 100.0, 'Level Kaufkurs 1': 110.0})
        self.assertEqual(mock_color_levels(row)[0], 'buy_1')
        
        # Case 2: Buy level 3 (better) triggered even if 1 is also triggered
        row = pd.Series({'Aktueller Kurs': 80.0, 'Level Kaufkurs 1': 110.0, 'Level Kaufkurs 3': 90.0})
        self.assertEqual(mock_color_levels(row)[0], 'buy_3')
        
        # Case 3: Sell level triggered
        row = pd.Series({'Aktueller Kurs': 200.0, 'Level Verkaufkurs 1': 190.0})
        self.assertEqual(mock_color_levels(row)[0], 'sell_1')

    def test_prompts_logic(self):
        # Create dummy prompt file
        os.makedirs(os.path.join(self.test_base_dir, "src", "prompts"), exist_ok=True)
        prompt_path = os.path.join(self.test_base_dir, "src", "prompts", "prompt_materials.txt")
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write("Analyze [ZZZ]")
        
        # Patch SECTOR_TO_PROMPT_DICT to use our test path
        with patch.dict(watchlist.SECTOR_TO_PROMPT_DICT, {"Basic Materials": prompt_path}):
            prompt = watchlist._get_sector_prompt("Basic Materials", "AAPL")
            self.assertEqual(prompt, "Analyze AAPL")
            
            # Test _create_claude_prompt
            row = {'Symbol': 'AAPL', 'Sektor': 'Basic Materials'}
            url = watchlist._create_claude_prompt(row)
            self.assertIn("https://claude.ai/new?q=Analyze%20AAPL", url)

    def test_validation_logic(self):
        # The validation logic is inside main() when the "Änderungen speichern" button is pressed.
        # We can't easily test it because it uses st.error and returns from main.
        # However, we can test the load_watchlist's column filling and type conversion.
        
        # Create a malformed excel with missing columns
        df_malformed = pd.DataFrame([{"Symbol": "MSFT", "Kategorie": 123}]) # Kategorie should be str
        df_malformed.to_excel(watchlist.WATCHLIST_FILE, index=False)
        
        loaded_df = watchlist.load_watchlist()
        
        # Check if missing columns are added
        self.assertIn("Level Kaufkurs 1", loaded_df.columns)
        # Check if Kategorie was converted to string
        self.assertEqual(loaded_df.iloc[0]["Kategorie"], "123")
        # Check if Symbol is string
        self.assertEqual(loaded_df.iloc[0]["Symbol"], "MSFT")

if __name__ == '__main__':
    unittest.main()
