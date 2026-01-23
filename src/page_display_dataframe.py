import streamlit as st
import pandas as pd
import urllib.parse


def _add_tradingview_link(df:pd.DataFrame, symbol_column='symbol') -> pd.DataFrame:
    df['TradingView'] = df[symbol_column].apply(
        lambda x: f'https://www.tradingview.com/symbols/{x}/'
    )
    return df

def _add_tradingview_superchart_link(df:pd.DataFrame, symbol_column='symbol') -> pd.DataFrame:
    df['Chart'] = df[symbol_column].apply(
        lambda x: f'https://www.tradingview.com/chart/?symbol={x}'
    )
    return df


def _add_claude_analysis_link(df: pd.DataFrame, page=None) -> pd.DataFrame:
    """Adds Claude AI analysis link with pre-filled prompt"""
    if page is None:
        df['Claude'] = df.apply(_create_claude_prompt_default, axis=1)
    elif page == 'spreads':
        df['Claude'] = df.apply(_create_claude_prompt_page_spreads, axis=1)
    else:
        raise ValueError('Page not recognized')
    return df

def _create_claude_prompt_page_spreads(row):
    prompt = f"""
Erstelle eine kompakte Aktienanalyse für {row['symbol']}:
Unternehmen: Geschäftsmodell und Branche (1-2 Sätzen):

Aktuelle News: Wichtigste Entwicklungen der letzten 4 Wochen
Anstehende Events: Earnings, Produktlaunches oder relevante Termine (in 3-7 Sätzen).

Einschätzung (maximal 8 Sätze):
Kauf/Halten/Verkaufen mit Begründung
Aktuelles Kursziel (Analystenkonsens)
Eigenes Kursziel durch Fundamentaldaten, News, Technische Analyse State of the Art.
Wichtigste Chance und größtes Risiko. 

Beurteile folgende Strategie mit Optionen für {row['symbol']} (So viele Sätze wie nötig): 
Gehe besonders auf die Gewinnwahrscheinlichkeit ein. Kombiniere hier fundamental, news, Vola technische indikatoren auf 
maximalem Expertenwissen und gebe eine klare Empfehlung Strategie umsetzen oder nicht ab. 
Begründe deine Entscheidung nachvollziehbar mit KPIs.

Verkaufe einen {row['option_type']} Strike {row['sell_strike']} für eine Prämie von {row['sell_last_option_price']} bei einem Delta 
von {row['sell_delta']}. Kaufe einen {row['option_type']} mit Strike {row['buy_strike']}
für eine Prämie von {row['buy_last_option_price']}. Expirationdate ist jeweils {row['expiration_date']}

Format: Prägnant, faktenbasiert, keine Füllwörter, max. eine Seite.
Rolle: Aktien und Finanzexperte.
    """

    # URL-encode the prompt
    encoded_prompt = urllib.parse.quote(prompt)
    return f'https://claude.ai/new?q={encoded_prompt}'

def _create_claude_prompt_default(row):
    symbol = row['symbol']

    prompt = f"""
Erstelle eine kompakte Aktienanalyse für {symbol}:
Unternehmen: Geschäftsmodell und Branche in 1-2 Sätzen
Aktuelle News: Wichtigste Entwicklungen der letzten 4 Wochen
Anstehende Events: Earnings, Produktlaunches oder relevante Termine
Einschätzung:

Kauf/Halten/Verkaufen mit Begründung
Aktuelles Kursziel (Analystenkonsens)
Eigenes Kursziel durch Fundamentaldaten, News, Technische Analyse State of the Art
Wichtigste Chance und größtes Risiko

Format: Prägnant, faktenbasiert, keine Füllwörter, max. eine Seite.
    """

    # URL-encode the prompt
    encoded_prompt = urllib.parse.quote(prompt)
    return f'https://claude.ai/new?q={encoded_prompt}'

def page_display_dataframe(
    df: pd.DataFrame,
    page: str | None = None,
    symbol_column: str = 'symbol',
    column_config: dict | None = None
):
    """
    Displays DataFrame with TradingView links configured.
    All float columns are formatted to 2 decimal places by default.

    Args:
        df: DataFrame
        symbol_column: Name of the column containing symbols (default: 'symbol')
        column_config: Optional dictionary of column configurations to merge with TradingView config.
                        These settings have higher priority than the default settings.
        page: String with the name of the page. Used for selecting the optimal prompt.
    """
    df = _add_tradingview_link(df, symbol_column)
    df = _add_tradingview_superchart_link(df, symbol_column)
    df = _add_claude_analysis_link(df, page)

    if page == "spreads":
        # drop unnecessary columns which where needed for the AI prompt generation
        df = df.drop(columns=['option_type', 'expiration_date'])

    # default configuration
    default_config = {
        "TradingView": st.column_config.LinkColumn(
            label="",
            help="TradingView Symbolinfo",
            display_text="📊",
        ),
        "Chart": st.column_config.LinkColumn(
            label="",
            help="TradingView Superchart",
            display_text="📈",
        ),
        "Claude": st.column_config.LinkColumn(
            label="",
            help="Analyze with Claude AI",
            display_text="🤖",
        )
    }

    # Auto-format all float columns to 2 decimal places
    for col in df.columns:
        if df[col].dtype in ['float64', 'float32']:
            default_config[col] = st.column_config.NumberColumn(
                col,
                format="%.2f"
            )

    # Color negative numbers red
    df = df.style.map(
        lambda val: 'color: red' if val < 0 else '',
        subset=df.select_dtypes(include=['number']).columns
    )

    # Merge with provided column_config if exists.
    # column_config has a higher priority than the default.
    if column_config:
        default_config.update(column_config)

    st.dataframe(
        df,
        column_config=default_config,
        hide_index=True,
        use_container_width=True
    )