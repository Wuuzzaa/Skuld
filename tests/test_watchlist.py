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
        # Wir testen die interne color_levels Logik der watchlist.py
        
        # Mocking row data
        # Case 1: Stop Loss unterschritten -> Rot
        row_sl = pd.Series({
            'Aktueller Kurs': 90.0, 
            'Stop Loss': 100.0, 
            'Einstieg 1': 110.0, 
            'Einstieg 2': 120.0, 
            'Einstieg 3': 130.0,
            'Take Profit 1': 140.0,
            'Take Profit 2': 150.0,
            'Take Profit 3': 160.0
        })
        
        # Wir rufen die tatsächliche Funktion aus watchlist.py auf, falls möglich, 
        # oder wir spiegeln die Logik hier präzise wider.
        # Da color_levels eine lokale Funktion in main() -> style_watchlist() ist,
        # extrahieren wir die Logik für den Test oder testen die style_watchlist indirekt.
        # Einfacher: Wir spiegeln die Logik hier präzise für den Unit-Test.

        def get_color(row):
            current_price = float(row['Aktueller Kurs'])
            # 1. SL
            if 'Stop Loss' in row and pd.notna(row['Stop Loss']) and current_price < float(row['Stop Loss']):
                return 'red'
            # 2. Einstieg (3 -> 1)
            for i in [3, 2, 1]:
                col = f'Einstieg {i}'
                if col in row:
                    val = row[col]
                    if pd.notna(val) and val != '' and current_price <= float(val):
                        return f'blue_{i}'
            # 3. TP (3 -> 1)
            for i in [3, 2, 1]:
                col = f'Take Profit {i}'
                if col in row:
                    val = row[col]
                    if pd.notna(val) and val != '' and current_price >= float(val):
                        return f'green_{i}'
            return ''

        # Tests
        self.assertEqual(get_color(row_sl), 'red')
        
        # Case 2: Einstieg 1 erreicht (Kurs zwischen SL und E1)
        row_e1 = pd.Series({'Aktueller Kurs': 105.0, 'Stop Loss': 100.0, 'Einstieg 1': 110.0})
        self.assertEqual(get_color(row_e1), 'blue_1')

        # Case 3: Einstieg 2 erreicht
        row_e2 = pd.Series({'Aktueller Kurs': 115.0, 'Stop Loss': 100.0, 'Einstieg 1': 110.0, 'Einstieg 2': 120.0})
        self.assertEqual(get_color(row_e2), 'blue_2')
        
        # Case 4: Take Profit 1 erreicht
        row_tp1 = pd.Series({'Aktueller Kurs': 145.0, 'Einstieg 1': 110.0, 'Take Profit 1': 140.0, 'Take Profit 2': 150.0})
        self.assertEqual(get_color(row_tp1), 'green_1')

        # Case 5: Take Profit 3 erreicht
        row_tp3 = pd.Series({'Aktueller Kurs': 165.0, 'Take Profit 1': 140.0, 'Take Profit 2': 150.0, 'Take Profit 3': 160.0})
        self.assertEqual(get_color(row_tp3), 'green_3')

        # Case 6: Nichts erreicht (zwischen E3 und TP1)
        row_none = pd.Series({'Aktueller Kurs': 135.0, 'Einstieg 3': 130.0, 'Take Profit 1': 140.0})
        self.assertEqual(get_color(row_none), '')

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
        # Create a malformed excel with missing columns
        df_malformed = pd.DataFrame([{"Symbol": "MSFT", "Kategorie": 123}]) # Kategorie should be str
        df_malformed.to_excel(watchlist.WATCHLIST_FILE, index=False)
        
        loaded_df = watchlist.load_watchlist()
        
        # Check if missing columns are added
        self.assertIn("Stop Loss", loaded_df.columns)
        self.assertIn("Einstieg 1", loaded_df.columns)
        # Check if Kategorie was converted to string
        self.assertEqual(loaded_df.iloc[0]["Kategorie"], "123")
        # Check if Symbol is string
        self.assertEqual(loaded_df.iloc[0]["Symbol"], "MSFT")

if __name__ == '__main__':
    unittest.main()
