import requests
import time
import re
from bs4 import BeautifulSoup
from config import *

#todo in main aufrufen
#todo in datenmodell einbinden

"""
================================================================================
ZUSAMMENFASSUNG ALLER OPTIONS-DATEN
================================================================================
Symbol  historical_volatilityimplied_volatility  iv_high             iv_low              iv_percentile       iv_rank             open_int_30d        put_call_oi_ratio   put_call_vol_ratio  todays_open_interesttodays_volume       volume_avg_30d      
--------------------------------------------------------------------------------
A       27.59%              29.38%              59.03%              21.99%              45%                 19.95%              31,668              0.72                0.25                28,035              169                 1,255               
AA      38.05%              55.39%              100.57%             39.15%              84%                 26.44%              333,056             0.85                0.81                328,936             30,707              23,357              
AAL     36.68%              53.80%              97.36%              35.00%              75%                 30.15%              3,105,697           1.82                1.51                2,970,066           129,254             127,055             
AAPL    24.84%              24.41%              65.20%              15.97%              38%                 17.15%              5,674,393           0.68                0.38                5,815,209           1,253,094           1,130,220           
AAT     24.08%              174.74%             174.74%             24.46%              99%                 100.00%             321                 0.19                0.00                362                 2                   10                  
ABBV    16.51%              23.06%              51.27%              17.68%              42%                 16.01%              325,360             0.71                0.85                326,332             16,105              14,360              
ABEV    20.17%              60.88%              248.79%             21.30%              68%                 17.40%              77,835              0.69                0.00                79,152              90                  323                 
ABM     22.09%              30.55%              57.53%              19.41%              33%                 29.21%              1,110               0.42                0.00                781                 4                   118                 
ABR     24.22%              39.10%              74.86%              18.09%              52%                 37.01%              226,676             1.03                0.35                228,117             12,295              8,980               
ABT     15.82%              25.81%              42.50%              13.95%              86%                 41.53%              190,263             0.76                0.30                175,250             12,917              8,459               
ACHR    44.65%              79.64%              170.98%             42.24%              34%                 29.05%              970,516             0.32                0.35                1,040,157           75,324              87,543              
ACN     23.49%              30.34%              46.36%              17.15%              63%                 45.15%              139,678             0.79                0.83                173,882             27,230              24,059              
ACNB    24.19%              85.72%              85.72%              24.43%              99%                 100.00%             466                 65.57               0.00                466                 1                   1                   
ADC     14.36%              21.02%              36.31%              12.99%              68%                 34.46%              4,521               0.30                0.47                4,128               75                  74                  
ADI     22.57%              30.24%              70.75%              23.01%              41%                 15.15%              97,815              0.73                1.45                93,768              4,241               4,228               

"""

def _parse_barchart(df):
    # Prozentwerte als float (0.x) speichern
    percent_cols = [
        'historical_volatility', 'implied_volatility', 'iv_high', 'iv_low',
        'iv_percentile', 'iv_rank'
    ]
    for col in percent_cols:
        df[col] = df[col].str.replace('%', '').astype(float) / 100

    # Kommas aus Zahlen entfernen und als int speichern
    int_cols = [
        'open_int_30d', 'todays_open_interest', 'todays_volume', 'volume_avg_30d'
    ]
    for col in int_cols:
        df[col] = df[col].str.replace(',', '').astype(int)

    # put_call_vol_ratio and put_call_oi_ratio as float from object
    for col in ["put_call_vol_ratio", "put_call_oi_ratio"]:
        df[col] = df[col].astype(float)

    return df


def _get_all_options_data(symbol):
    """
    Holt ALLE Options-Daten durch intelligente Label-Suche (mit Anti-Detection)
    """


    url = f"https://www.barchart.com/stocks/quotes/{symbol}/overview"

    # Erweiterte Headers um als echter Browser zu erscheinen
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,de;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }

    # Session für Cookie-Persistenz
    session = requests.Session()
    session.headers.update(headers)

    try:
        # # Erst die Hauptseite besuchen (wie ein echter Benutzer)
        # main_page = session.get("https://www.barchart.com", timeout=15)
        # time.sleep(1)  # Kurze Pause

        # Dann die spezifische Symbol-Seite
        response = session.get(url, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Suche nach Options Overview Sektion
        options_data = {
            "symbol": symbol}

        # Methode 1: Suche nach Label-Value Paaren
        label_value_pairs = _find_label_value_pairs(soup)
        options_data.update(label_value_pairs)

        # Methode 2: Spezifische Tabellen-Suche
        table_data = _find_table_data(soup)
        options_data.update(table_data)

        return options_data

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            print(f"    🚫 403 Forbidden für {symbol} - Rate Limiting erkannt")
            return {
                "symbol": symbol,
                "error": "403_forbidden",
                "retry_needed": True}
        else:
            print(f"    ❌ HTTP Fehler {e.response.status_code} für {symbol}")
            return {
                "symbol": symbol,
                "error": f"http_{e.response.status_code}"}
    except Exception as e:
        print(f"    ❌ Allgemeiner Fehler bei {symbol}: {e}")
        return {
            "symbol": symbol,
            "error": str(e)}


def _find_label_value_pairs(soup):
    """
    Findet Label-Value Paare durch Text-Analyse
    """
    results = {}

    # Bekannte Labels die wir suchen
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

    # Suche in verschiedenen Container-Strukturen
    containers = [
        soup.find_all('div', class_='barchart-content-block'),
        soup.find_all('li'),
        soup.find_all('tr'),
        soup.find_all('div', class_=re.compile(r'options|overview', re.I))
    ]

    for container_group in containers:
        for container in container_group:
            text_content = container.get_text()

            for label, key in target_labels.items():
                if key not in results:  # Nur wenn noch nicht gefunden
                    value = _extract_value_near_label(container, label)
                    if value:
                        results[key] = value
                        print(f"    ✓ {label}: {value}")

    return results


def _extract_value_near_label(container, label):
    """
    Extrahiert Wert der nahe einem Label steht
    """
    text = container.get_text()

    # Pattern: Label gefolgt von Wert
    patterns = [
        rf'{re.escape(label)}\s*[:\s]*([0-9.,]+%?)',
        rf'{re.escape(label)}\s*[:\s]*([0-9.,]+[KMB]?)',
        rf'([0-9.,]+%?)\s*{re.escape(label)}',  # Wert vor Label
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # Suche in Geschwister-Elementen
    spans = container.find_all('span')
    for i, span in enumerate(spans):
        if label.lower() in span.get_text().lower():
            # Schaue in nachfolgenden spans
            for j in range(i + 1, min(i + 4, len(spans))):
                next_span = spans[j]
                text = next_span.get_text().strip()
                if re.match(r'^[0-9.,]+[%KMB]?$', text):
                    return text

    return None


def _find_table_data(soup):
    """
    Findet Daten in Tabellen-Strukturen
    """
    results = {}

    # Suche nach Tabellen mit Options-Daten
    tables = soup.find_all('table')

    for table in tables:
        rows = table.find_all('tr')

        for row in rows:
            cells = row.find_all(['td', 'th'])

            if len(cells) >= 2:
                label = cells[0].get_text().strip()
                value = cells[1].get_text().strip()

                # Mappe bekannte Labels
                label_mapping = {
                    'Implied Volatility': 'implied_volatility',
                    'Historical Volatility': 'historical_volatility',
                    'IV Percentile': 'iv_percentile',
                    'Put/Call Vol Ratio': 'put_call_vol_ratio'
                }

                if label in label_mapping and re.match(r'^[0-9.,]+[%]?$', value):
                    results[label_mapping[label]] = value

    return results


def scrape_barchart(testmode):
    """
    Holt komplette Daten für mehrere Symbole (mit Retry-Logic)
    """

    # check testmode
    if testmode:
        symbols = SYMBOLS[:5]
    else:
        symbols = SYMBOLS

    all_results = []
    retry_list = []

    for i, symbol in enumerate(symbols):
        print(f"\nVerarbeite {symbol} ({i + 1}/{len(symbols)})")
        print("-" * 40)

        symbol_data = _get_all_options_data(symbol)

        # Check für 403 Errors
        if symbol_data.get('error') == '403_forbidden':
            retry_list.append(symbol)
            print(f"  ⏳ {symbol}: Wird später wiederholt (403 Error)")
        else:
            all_results.append(symbol_data)

            # Zeige gefundene Daten
            found_count = len([k for k in symbol_data.keys() if k not in ['symbol', 'error']])
            if 'error' in symbol_data:
                print(f"  ✗ {symbol}: Fehler - {symbol_data['error']}")
            else:
                print(f"  ✓ {symbol}: {found_count} Felder gefunden")

        pause_time = 1
        print(f"    💤 Pause: {pause_time:.1f}s")
        time.sleep(pause_time)

    # Retry für 403 Errors mit längeren Pausen
    if retry_list:
        print(f"\n🔄 RETRY für {len(retry_list)} Symbole mit 403 Errors...")
        print("Warte 30 Sekunden vor Retry...")
        time.sleep(30)

        for symbol in retry_list:
            print(f"\nRetry: {symbol}")
            symbol_data = _get_all_options_data(symbol)
            all_results.append(symbol_data)

            found_count = len([k for k in symbol_data.keys() if k not in ['symbol', 'error']])
            if 'error' in symbol_data:
                print(f"  ✗ {symbol}: Fehler - {symbol_data['error']}")
            else:
                print(f"  ✓ {symbol}: {found_count} Felder gefunden")

            # Sehr lange Pause beim Retry
            time.sleep(10)

    # results as dataframe
    df = pd.DataFrame(all_results)

    # parsen
    df = _parse_barchart(df)

    # store dataframe
    df.to_feather(PATH_DATAFRAME_BARCHART_FEATHER)


# Test mit Timer
if __name__ == "__main__":
    import datetime
    pd.set_option('display.max_columns', None)

    start_time = time.time()
    start_datetime = datetime.datetime.now()

    print(f"🚀 Start: {start_datetime.strftime('%H:%M:%S')}")
    print("=" * 60)
    print("VOLLSTÄNDIGE OPTIONS-DATEN EXTRAKTION")
    print("=" * 60)

    scrape_barchart(testmode=True)

    # Timer-Statistiken
    total_duration = time.time() - start_time
    end_datetime = datetime.datetime.now()

    print(f"\n⏱️  GESAMT: {total_duration:.2f}s ")
