import requests
import time
import re
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
from config import *

"""
================================================================================
BARCHART OPTIONS DATA SCRAPER
================================================================================
Scrapes options data from Barchart overview pages for multiple symbols.
Returns a DataFrame with all available options metrics.

Fields extracted:
- historical_volatility: 30-day historical volatility (float)
- implied_volatility: Current implied volatility (float)
- iv_high: Highest IV in past year (float)
- iv_low: Lowest IV in past year (float)
- iv_percentile: IV percentile rank (float)
- iv_rank: IV rank (float)
- put_call_vol_ratio: Put/Call volume ratio (float)
- put_call_oi_ratio: Put/Call open interest ratio (float)
- todays_volume: Total options volume today (int)
- volume_avg_30d: Average daily volume (30 days) (int)
- todays_open_interest: Total open interest today (int)
- open_int_30d: Average open interest (30 days) (int)
================================================================================
"""


def _get_browser_headers():
    """Returns headers to mimic a real browser"""
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0'
    }


def _extract_value_near_label(container, label):
    """
    Extracts numeric value near a label in HTML container.
    Returns None if not found.
    """
    text = container.get_text()

    # Try multiple patterns to find value near label
    patterns = [
        rf'{re.escape(label)}\s*[:\s]*([0-9.,]+%?)',  # Label: Value
        rf'{re.escape(label)}\s*[:\s]*([0-9.,]+[KMB]?)',  # Label: 123K/M/B
        rf'([0-9.,]+%?)\s*{re.escape(label)}',  # Value Label
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # Search in sibling span elements
    spans = container.find_all('span')
    for i, span in enumerate(spans):
        if label.lower() in span.get_text().lower():
            # Check following spans for numeric value
            for j in range(i + 1, min(i + 4, len(spans))):
                next_text = spans[j].get_text().strip()
                if re.match(r'^[0-9.,]+[%KMB]?$', next_text):
                    return next_text

    return None


def _find_options_data(soup):
    """
    Searches for options data in HTML soup using label-value pattern matching.
    Returns dictionary with found values, None for missing fields.
    """
    # Define all target fields with their labels
    target_labels = {
        'Implied Volatility': 'implied_volatility',
        'Historical Volatility': 'historical_volatility',
        'IV Percentile': 'iv_percentile',
        'IV Rank': 'iv_rank',
        'IV High': 'iv_high',
        'IV Low': 'iv_low',
        'Put/Call Vol Ratio': 'put_call_vol_ratio',
        'Put/Call OI Ratio': 'put_call_oi_ratio',
        "Today's Volume": 'todays_volume',
        'Volume Avg (30-Day)': 'volume_avg_30d',
        "Today's Open Interest": 'todays_open_interest',
        'Open Int (30-Day)': 'open_int_30d'
    }

    # Initialize all fields with None
    results = {key: None for key in target_labels.values()}

    # Search in different container types
    containers = []
    containers.extend(soup.find_all('div', class_='barchart-content-block'))
    containers.extend(soup.find_all('li'))
    containers.extend(soup.find_all('tr'))
    containers.extend(soup.find_all('div', class_=re.compile(r'options|overview', re.I)))

    # Extract values from containers
    for container in containers:
        for label, key in target_labels.items():
            if results[key] is None:  # Only if not found yet
                value = _extract_value_near_label(container, label)
                if value:
                    results[key] = value

    # Also check tables
    for table in soup.find_all('table'):
        for row in table.find_all('tr'):
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                label = cells[0].get_text().strip()
                value = cells[1].get_text().strip()

                for target_label, key in target_labels.items():
                    if target_label in label and results[key] is None:
                        if re.match(r'^[0-9.,]+[%KMB]?$', value):
                            results[key] = value

    return results


def _scrape_symbol(symbol):
    """
    Scrapes options data for a single symbol.
    Returns dictionary with symbol and all available data fields.
    """
    url = f"https://www.barchart.com/stocks/quotes/{symbol}/overview"

    try:
        response = requests.get(url, headers=_get_browser_headers(), timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        options_data = _find_options_data(soup)

        # Add symbol to results
        options_data['symbol'] = symbol

        # Count found fields
        found = sum(1 for v in options_data.values() if v is not None and v != symbol)
        print(f"  ✓ {symbol}: {found}/12 fields found")

        return options_data

    except requests.exceptions.RequestException as e:
        print(f"  ✗ {symbol}: Request failed - {str(e)}")
        return {
            'symbol': symbol, **{k: None for k in [
                'implied_volatility', 'historical_volatility', 'iv_percentile',
                'iv_rank', 'iv_high', 'iv_low', 'put_call_vol_ratio',
                'put_call_oi_ratio', 'todays_volume', 'volume_avg_30d',
                'todays_open_interest', 'open_int_30d'
            ]}}
    except Exception as e:
        print(f"  ✗ {symbol}: Parsing failed - {str(e)}")
        return {
            'symbol': symbol, **{k: None for k in [
                'implied_volatility', 'historical_volatility', 'iv_percentile',
                'iv_rank', 'iv_high', 'iv_low', 'put_call_vol_ratio',
                'put_call_oi_ratio', 'todays_volume', 'volume_avg_30d',
                'todays_open_interest', 'open_int_30d'
            ]}}

# Helper function: safely parse percentage strings
def parse_percent(x):
    if isinstance(x, str):
        x = x.strip().replace('%', '')
        if x in ['', '.', '-', 'None', 'nan']:
            return np.nan
        try:
            return float(x) / 100
        except ValueError:
            return np.nan
    elif pd.notna(x):
        return float(x)
    return np.nan

# Helper function: safely parse comma-separated ints
def parse_int(x):
    if isinstance(x, str):
        x = x.replace(',', '').strip()
        if x in ['', '.', '-', 'None', 'nan']:
            return np.nan
        try:
            return int(x)
        except ValueError:
            return np.nan
    elif isinstance(x, (int, float)):
        return int(x)
    return np.nan


def _parse_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Parses string values in DataFrame to appropriate data types.
    Handles missing or malformed values gracefully.
    """

    # Columns
    percent_cols = [
        'historical_volatility',
        'implied_volatility',
        'iv_high',
        'iv_low',
        'iv_percentile',
        'iv_rank'
    ]
    int_cols = [
        'open_int_30d',
        'todays_open_interest',
        'todays_volume',
        'volume_avg_30d'
    ]
    ratio_cols = [
        'put_call_vol_ratio',
        'put_call_oi_ratio'
    ]

    # Apply conversions
    for col in percent_cols:
        df[col] = df[col].apply(parse_percent)

    for col in int_cols:
        df[col] = df[col].apply(parse_int)

    for col in ratio_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df

def _scrape(symbols, delay_seconds):
    results = []

    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {symbol}")

        symbol_data = _scrape_symbol(symbol)
        results.append(symbol_data)

        # Pause between requests to avoid rate limiting
        if i < len(symbols):
            time.sleep(delay_seconds)

    df = pd.DataFrame(results)

    return df


def scrape_barchart(testmode=False, delay_seconds=0):
    """
    Main function to scrape options data for all symbols.

    Args:
        testmode (bool): If True, only process first 5 symbols

    Returns:
        pd.DataFrame: DataFrame with all scraped options data
    """
    symbols = SYMBOLS[:5] if testmode else SYMBOLS

    print(f"\n{'=' * 60}")
    print(f"BARCHART OPTIONS DATA SCRAPER")
    print(f"{'=' * 60}")
    print(f"Processing {len(symbols)} symbols...\n")

    # scrape
    df = _scrape(symbols, delay_seconds)

    # # debug store before parse
    # df.to_feather(PATH_DATAFRAME_BARCHART_FEATHER_PRE_PARSE)
    # df = pd.read_feather(PATH_DATAFRAME_BARCHART_FEATHER_PRE_PARSE)

    # Parse to correct data types
    df = _parse_dataframe(df)

    # Save to feather format
    df.to_feather(PATH_DATAFRAME_BARCHART_FEATHER)

    print(f"\n{'=' * 60}")
    print(f"✓ Completed! Data saved to {PATH_DATAFRAME_BARCHART_FEATHER}")
    print(f"{'=' * 60}\n")

    return df


if __name__ == "__main__":
    import datetime

    testmode = False
    delay_seconds = 0

    PATH_DATAFRAME_BARCHART_FEATHER_PRE_PARSE = "barchart_pre_parse.feather"
    PATH_DATAFRAME_BARCHART_FEATHER = "barchart.feather"

    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)

    start_time = time.time()
    start_dt = datetime.datetime.now()

    print(f"🚀 Started at: {start_dt.strftime('%H:%M:%S')}")

    df = scrape_barchart(testmode=testmode, delay_seconds=delay_seconds)

    # Show results
    print("\nResults preview:")
    print(df.head())
    print(f"\nDataFrame shape: {df.shape}")
    print(f"\nMissing values per column:")
    print(df.isnull().sum())

    elapsed = time.time() - start_time
    print(f"\n⏱️  Total time: {elapsed:.2f}s ({elapsed / len(df):.2f}s per symbol)")