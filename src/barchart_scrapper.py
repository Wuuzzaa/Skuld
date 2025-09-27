import requests
import time
import re
from bs4 import BeautifulSoup
from config import *


def get_all_options_data(symbol):
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
        # Erst die Hauptseite besuchen (wie ein echter Benutzer)
        main_page = session.get("https://www.barchart.com", timeout=15)
        time.sleep(1)  # Kurze Pause

        # Dann die spezifische Symbol-Seite
        response = session.get(url, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Suche nach Options Overview Sektion
        options_data = {
            "symbol": symbol}

        # Methode 1: Suche nach Label-Value Paaren
        label_value_pairs = find_label_value_pairs(soup)
        options_data.update(label_value_pairs)

        # Methode 2: Spezifische Tabellen-Suche
        table_data = find_table_data(soup)
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


def find_label_value_pairs(soup):
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
                    value = extract_value_near_label(container, label)
                    if value:
                        results[key] = value
                        print(f"    ✓ {label}: {value}")

    return results


def extract_value_near_label(container, label):
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


def find_table_data(soup):
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


def get_multiple_symbols_complete(symbols):
    """
    Holt komplette Daten für mehrere Symbole (mit Retry-Logic)
    """
    all_results = []
    retry_list = []

    for i, symbol in enumerate(symbols):
        print(f"\nVerarbeite {symbol} ({i + 1}/{len(symbols)})")
        print("-" * 40)

        symbol_data = get_all_options_data(symbol)

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

        # Längere Pause zwischen Anfragen um Rate Limiting zu vermeiden
        pause_time = 2.0 + (i * 0.1)  # Graduell längere Pausen
        print(f"    💤 Pause: {pause_time:.1f}s")
        time.sleep(pause_time)

    # Retry für 403 Errors mit längeren Pausen
    if retry_list:
        print(f"\n🔄 RETRY für {len(retry_list)} Symbole mit 403 Errors...")
        print("Warte 30 Sekunden vor Retry...")
        time.sleep(30)

        for symbol in retry_list:
            print(f"\nRetry: {symbol}")
            symbol_data = get_all_options_data(symbol)
            all_results.append(symbol_data)

            found_count = len([k for k in symbol_data.keys() if k not in ['symbol', 'error']])
            if 'error' in symbol_data:
                print(f"  ✗ {symbol}: Fehler - {symbol_data['error']}")
            else:
                print(f"  ✓ {symbol}: {found_count} Felder gefunden")

            # Sehr lange Pause beim Retry
            time.sleep(10)

    return all_results


def print_summary_table(results):
    """
    Zeigt Zusammenfassung aller Ergebnisse als Tabelle
    """
    print("\n" + "=" * 80)
    print("ZUSAMMENFASSUNG ALLER OPTIONS-DATEN")
    print("=" * 80)

    # Alle möglichen Keys sammeln
    all_keys = set()
    for result in results:
        all_keys.update(result.keys())
    all_keys.discard('symbol')
    all_keys.discard('error')

    # Header
    print(f"{'Symbol':<8}", end="")
    for key in sorted(all_keys):
        print(f"{key:<20}", end="")
    print()
    print("-" * 80)

    # Daten
    for result in results:
        symbol = result.get('symbol', 'Unknown')
        print(f"{symbol:<8}", end="")

        for key in sorted(all_keys):
            value = result.get(key, 'N/A')
            print(f"{str(value):<20}", end="")
        print()


# Test mit Timer
if __name__ == "__main__":
    import datetime

    start_time = time.time()
    start_datetime = datetime.datetime.now()

    print(f"🚀 Start: {start_datetime.strftime('%H:%M:%S')}")
    print("=" * 60)
    print("VOLLSTÄNDIGE OPTIONS-DATEN EXTRAKTION")
    print("=" * 60)

    results = get_multiple_symbols_complete(SYMBOLS)

    # Zeige detaillierte Ergebnisse
    print_summary_table(results)

    # Timer-Statistiken
    total_duration = time.time() - start_time
    end_datetime = datetime.datetime.now()

    print(f"\n⏱️  GESAMT: {total_duration:.2f}s für {len(results)} Symbole")
    print(f"⏱️  Durchschnitt: {total_duration / len(results):.2f}s pro Symbol")
    print(f"🏁 Ende: {end_datetime.strftime('%H:%M:%S')}")

    # Datenqualität-Check
    successful_symbols = [r for r in results if 'error' not in r]
    if successful_symbols:
        avg_fields = sum(len(r) - 1 for r in successful_symbols) / len(successful_symbols)  # -1 für 'symbol' key
        print(f"📊 Durchschnittlich {avg_fields:.1f} Datenfelder pro Symbol gefunden")

    # Hochrechnung
    projected_time = (total_duration / len(results)) * 1000
    projected_minutes = projected_time / 60
    print(f"📈 Hochrechnung für 1000 Symbole: ~{projected_minutes:.1f} Minuten")