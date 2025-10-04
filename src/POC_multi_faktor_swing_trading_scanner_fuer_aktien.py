import time
from config import *
import pandas as pd
from finvizfinance.quote import finvizfinance
import re

# force pandas to show all columns in a dataframe
pd.set_option('display.max_columns', None)



"""
Prove of Concept muss noch komplett in die Anwendung eingebaut werden. Hier nur die Idee. Backend Frontend fehlt sowie Datenmodellanpassungen.
"""

def load_finviz_fundamentals(symbols, request_delay=1.0):
    results = {}

    for i, symbol in enumerate(symbols):
        try:
            print(f"Load {symbol} fundamentals from finviz ({i + 1}/{len(SYMBOLS)})...")
            stock = finvizfinance(symbol)
            results[symbol] = stock.ticker_fundament()

        except Exception as e:
            print(f"error loading {symbol}: {e}")
            results[symbol] = None

        # Rate Limiting
        time.sleep(request_delay)

    df = pd.DataFrame(data=results).T.reset_index(names='symbol')
    df = df.rename(columns={col: f'finviz_{col}' for col in df.columns if col != 'symbol'})

    # store files
    df.to_excel('finviz_fundamentals.xlsx')
    df.to_feather('finviz_fundamentals.feather')


def convert_market_cap(value):
    """
    Konvertiert Market Cap Strings (z.B. '998.82M', '97.75B') in Zahlen
    M = Millionen (*1e6)
    B = Milliarden (*1e9)
    """
    if pd.isna(value) or value == '':
        return None

    value = str(value).strip()

    if value.endswith('M'):
        return float(value[:-1]) * 1e6
    elif value.endswith('B'):
        return float(value[:-1]) * 1e9
    else:
        # Falls bereits eine Zahl ohne Suffix
        try:
            return float(value)
        except:
            return None


def extract_percentage_from_brackets(value):
    """
    Extrahiert Prozentwerte aus Klammern (z.B. '0.98 (0.80%)' -> 0.008)
    """
    if pd.isna(value) or value == '' or value == '-':
        return None

    value_str = str(value).strip()

    # Regex um Prozentwert in Klammern zu finden
    match = re.search(r'\(([+-]?\d+\.?\d*)%\)', value_str)

    if match:
        percentage = float(match.group(1))
        return percentage / 100
    else:
        return None

def clean_data(df):
    # finviz_Market Cap => convert M and B to numbers for millions and billions
    df['finviz_Market Cap'] = df['finviz_Market Cap'].apply(convert_market_cap)

    # cast to number
    float_columns = ['finviz_P/E', 'finviz_P/S', 'finviz_P/B', 'finviz_P/FCF', 'finviz_EV/EBITDA']
    df[float_columns] = df[float_columns].apply(pd.to_numeric, errors='coerce')

    # finviz_Perf Half Y => remove % string format and make it a float
    df['finviz_Perf Half Y'] = pd.to_numeric(df['finviz_Perf Half Y'].str.replace('%', ''), errors='coerce') / 100

    # finviz_Dividend TTM => float from strings like "0.98(0.80 %)"
    df['finviz_Dividend TTM'] = df['finviz_Dividend TTM'].apply(extract_percentage_from_brackets)

    return df


# def calculate_decile_scores(df, columns_lower_better, columns_higher_better):
#     """
#     Berechnet Dezil-basierte Scores (1-10) für jede Spalte
#     Beste 10% bekommen 10 Punkte, nächste 10% bekommen 9 Punkte, etc.
#     """
#     score_columns = []
#
#     # Scores für "niedriger ist besser" (umgekehrt)
#     for col in columns_lower_better:
#         if col in df.columns:
#             score_col = f'{col}_score'
#             try:
#                 # Ranking erstellen, dann in Dezile unterteilen
#                 ranked = df[col].rank(method='first', na_option='keep')
#                 # Dezile berechnen und umkehren (niedrigste Werte = höchste Scores)
#                 df[score_col] = pd.qcut(ranked, q=10, labels=False, duplicates='drop')
#                 df[score_col] = 10 - df[score_col]  # Umkehren: 0->10, 1->9, etc.
#                 score_columns.append(score_col)
#             except Exception as e:
#                 print(f"Fehler bei {col}: {e}")
#                 df[score_col] = None
#
#     # Scores für "höher ist besser" (normal)
#     for col in columns_higher_better:
#         if col in df.columns:
#             score_col = f'{col}_score'
#             try:
#                 # Ranking erstellen, dann in Dezile unterteilen
#                 ranked = df[col].rank(method='first', na_option='keep')
#                 # Dezile berechnen (höchste Werte = höchste Scores)
#                 df[score_col] = pd.qcut(ranked, q=10, labels=False, duplicates='drop') + 1
#                 score_columns.append(score_col)
#             except Exception as e:
#                 print(f"Fehler bei {col}: {e}")
#                 df[score_col] = None
#
#     # Totalscore berechnen
#     df['totalscore'] = df[score_columns].sum(axis=1, skipna=True)
#
#     return df

def calculate_percentile_scores(df, columns_lower_better, columns_higher_better, n_top_performance):
    """
    Berechnet Perzentil-basierte Scores (1-100) für jede Spalte
    Beste 1% bekommen 100 Punkte, nächste 1% bekommen 99 Punkte, etc.
    """
    score_columns = []

    # Scores für "niedriger ist besser" (umgekehrt)
    for col in columns_lower_better:
        if col in df.columns:
            score_col = f'{col}_score'
            try:
                # Perzentil-Ranking berechnen (0-100)
                percentile_rank = df[col].rank(method='min', na_option='keep', pct=True) * 100
                # Umkehren: niedrigste Werte = höchste Scores
                df[score_col] = 101 - percentile_rank
                # Auf ganze Zahlen runden und auf 1-100 begrenzen
                df[score_col] = df[score_col].round().clip(1, 100)
                score_columns.append(score_col)
            except Exception as e:
                print(f"Fehler bei {col}: {e}")
                df[score_col] = None

    # Scores für "höher ist besser" (normal)
    for col in columns_higher_better:
        if col in df.columns:
            score_col = f'{col}_score'
            try:
                # Perzentil-Ranking berechnen (0-100)
                percentile_rank = df[col].rank(method='min', na_option='keep', pct=True) * 100
                # Auf ganze Zahlen runden und auf 1-100 begrenzen
                df[score_col] = percentile_rank.round().clip(1, 100)
                score_columns.append(score_col)
            except Exception as e:
                print(f"Fehler bei {col}: {e}")
                df[score_col] = None

    # Totalscore berechnen (Summe aller Score-Spalten)
    df['totalscore'] = df[score_columns].sum(axis=1, skipna=True)

    # Divide totalscore into deciles (1 = best 10%, 10 = worst 10%)
    df['totalscore_decile'] = pd.qcut(df['totalscore'],
                                      q=10,
                                      labels=False,
                                      duplicates='drop') + 1

    # Reverse: highest score = decile 1, lowest score = decile 10
    df['totalscore_decile'] = 11 - df['totalscore_decile']

    # Find top n performers based on finviz_Perf Half Y within decile 1 only
    decile_1_stocks = df[df['totalscore_decile'] == 1]
    top_performers = decile_1_stocks.nlargest(n_top_performance, 'finviz_Perf Half Y').index

    # Create recommendation: True if in top n performers from decile 1
    df['recommendation'] = df.index.isin(top_performers)

    return df


def add_ranking_columns(df, n_top_performance=25):
    columns_lower_better = [
        'finviz_P/E',
        'finviz_P/S',
        'finviz_P/B',
        'finviz_P/FCF',
        'finviz_EV/EBITDA',
    ]

    columns_higher_better = [
        # 'finviz_Perf Half Y', # ignore here its relevant in the next step to filter
        'finviz_Dividend TTM'
    ]

    #df = calculate_decile_scores(df, columns_lower_better, columns_higher_better)
    df = calculate_percentile_scores(df, columns_lower_better, columns_higher_better, n_top_performance)

    return df


def multi_faktor_ranking():
    df = pd.read_feather(
        '../experiments/finviz_fundamentals.feather',
        columns=[
            'symbol',
            'finviz_P/E',
            'finviz_Market Cap',
            'finviz_P/S',
            'finviz_Perf Half Y',
            'finviz_P/B',
            'finviz_P/FCF',
            'finviz_EV/EBITDA',
            'finviz_Dividend TTM',
        ]
    )

    df = clean_data(df)
    df = add_ranking_columns(df)

    # store interim results
    df.to_excel("finviz_multifaktor_ranking.xlsx")
    df.to_feather('finviz_multifaktor_ranking.feather')

    return df


def main():
    df = load_finviz_fundamentals(symbols=SYMBOLS, request_delay=1.0)
    df = multi_faktor_ranking()


if __name__ == '__main__':

    start = time.time()

    #todo some function here
    main()
    end = time.time()
    duration = end - start


    print(f"\nDurchlaufzeit: {duration:.4f} Sekunden")
