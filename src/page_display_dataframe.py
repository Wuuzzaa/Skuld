import pandas as pd
import urllib.parse
import os

try:
    import streamlit as st
except ImportError:
    st = None  # API context - streamlit not available

# Mapping: Yahoo Finance sector names → prompt file names
SECTOR_PROMPT_MAP = {
    "Communication Services": "prompt_communication_services.txt",
    "Consumer Cyclical": "prompt_consumer_discretionary.txt",
    "Consumer Defensive": "prompt_consumer_staples.txt",
    "Energy": "prompt_energy.txt",
    "Financial Services": "prompt_financials.txt",
    "Healthcare": "prompt_health_care.txt",
    "Industrials": "prompt_industrials.txt",
    "Technology": "prompt_information_technology.txt",
    "Basic Materials": "prompt_materials.txt",
    "Real Estate": "prompt_real_estate.txt",
    "Utilities": "prompt_utilities.txt",
}

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def _get_sector_prompt(sector, symbol):
    """Loads sector-specific prompt and replaces [ZZZ] with the actual symbol.
    Returns None if sector is unknown or file not found."""
    if not sector or sector not in SECTOR_PROMPT_MAP:
        return None
    filepath = os.path.join(_PROMPTS_DIR, SECTOR_PROMPT_MAP[sector])
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            prompt = f.read()
        return prompt.replace("[ZZZ]", symbol)
    except (FileNotFoundError, IOError):
        return None


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
    elif page == 'iron_condors':
        df['Claude'] = df.apply(_create_claude_prompt_page_iron_condors, axis=1)
    elif page == 'dividend_scanner':
        df['Claude'] = df.apply(_create_claude_prompt_dividend_scanner, axis=1)
    else:
        df['Claude'] = df.apply(_create_claude_prompt_default, axis=1)
    return df

def _get_claude_prompt_header(symbol, company=None):
    company_info = f" ({company})" if company else ""
    return f"""
Erstelle eine kompakte Aktienanalyse für {symbol}{company_info}:
Unternehmen: Geschäftsmodell und Branche (1-2 Sätzen):

Aktuelle News: Wichtigste Entwicklungen der letzten 4 Wochen
Anstehende Events: Earnings, Produktlaunches oder relevante Termine (in 3-7 Sätzen).

Einschätzung (maximal 8 Sätze):
Kauf/Halten/Verkaufen mit Begründung
Aktuelles Kursziel (Analystenkonsens)
Eigenes Kursziel durch Fundamentaldaten, News, Technische Analyse State of the Art.
Wichtigste Chance und größtes Risiko. 

Beurteile folgende Strategie mit Optionen für {symbol} (So viele Sätze wie nötig): 
Gehe besonders auf die Gewinnwahrscheinlichkeit ein. Kombiniere hier fundamental, news, Vola technische indikatoren auf 
maximalem Expertenwissen und gebe eine klare Empfehlung Strategie umsetzen oder nicht ab. 
Begründe deine Entscheidung nachvollziehbar mit KPIs.
"""

def _get_claude_prompt_footer():
    return """
Format: Prägnant, faktenbasiert, keine Füllwörter, max. eine Seite.
Rolle: Aktien und Finanzexperte.
"""

def _create_claude_prompt_page_spreads(row):
    symbol = row['symbol']
    sector = row.get('company_sector')

    strategy_details = f"""
Beurteile zusätzlich folgende Options-Strategie für {symbol}:
Verkaufe einen {row['option_type']} Strike {row['sell_strike']} für eine Prämie von {row['sell_last_option_price']} bei einem Delta
von {row['sell_delta']}. Kaufe einen {row['option_type']} mit Strike {row['buy_strike']}
für eine Prämie von {row['buy_last_option_price']}. Expirationdate ist jeweils {row['expiration_date']}
Gehe besonders auf die Gewinnwahrscheinlichkeit ein und gib eine klare Empfehlung: Strategie umsetzen oder nicht.
"""

    # Try sector-specific prompt + strategy details
    sector_prompt = _get_sector_prompt(sector, symbol)
    if sector_prompt:
        prompt = sector_prompt.strip() + "\n" + strategy_details
        encoded_prompt = urllib.parse.quote(prompt.strip())
        return f'https://claude.ai/new?q={encoded_prompt}'

    # Fallback: generic prompt
    prompt = _get_claude_prompt_header(symbol, row.get('Company'))
    prompt += f"""
Verkaufe einen {row['option_type']} Strike {row['sell_strike']} für eine Prämie von {row['sell_last_option_price']} bei einem Delta
von {row['sell_delta']}. Kaufe einen {row['option_type']} mit Strike {row['buy_strike']}
für eine Prämie von {row['buy_last_option_price']}. Expirationdate ist jeweils {row['expiration_date']}
"""
    prompt += _get_claude_prompt_footer()

    encoded_prompt = urllib.parse.quote(prompt.strip())
    return f'https://claude.ai/new?q={encoded_prompt}'

def _create_claude_prompt_page_iron_condors(row):
    symbol = row['symbol']
    sector = row.get('company_sector')

    strategy_details = f"""
Beurteile zusätzlich folgende Iron Condor Strategie für {symbol}:
Put-Seite: Verkauf Strike {row['sell_strike_put']} (Delta {row['sell_delta_put']}), Kauf Strike {row['buy_strike_put']}. Expiration: {row['expiration_date_put']}
Call-Seite: Verkauf Strike {row['sell_strike_call']} (Delta {row['sell_delta_call']}), Kauf Strike {row['buy_strike_call']}. Expiration: {row['expiration_date_call']}
Gehe besonders auf die Gewinnwahrscheinlichkeit ein und gib eine klare Empfehlung: Strategie umsetzen oder nicht.
"""

    # Try sector-specific prompt + strategy details
    sector_prompt = _get_sector_prompt(sector, symbol)
    if sector_prompt:
        prompt = sector_prompt.strip() + "\n" + strategy_details
        encoded_prompt = urllib.parse.quote(prompt.strip())
        return f'https://claude.ai/new?q={encoded_prompt}'

    # Fallback: generic prompt
    prompt = _get_claude_prompt_header(symbol, row.get('Company'))
    prompt += f"""
Iron Condor Strategie:
Put-Seite: Verkauf Strike {row['sell_strike_put']} (Delta {row['sell_delta_put']}), Kauf Strike {row['buy_strike_put']}. Expiration: {row['expiration_date_put']}
Call-Seite: Verkauf Strike {row['sell_strike_call']} (Delta {row['sell_delta_call']}), Kauf Strike {row['buy_strike_call']}. Expiration: {row['expiration_date_call']}
"""
    prompt += _get_claude_prompt_footer()

    encoded_prompt = urllib.parse.quote(prompt.strip())
    return f'https://claude.ai/new?q={encoded_prompt}'

def _create_claude_prompt_dividend_scanner(row):
    symbol = row['symbol']
    company = row.get('name') or row.get('Company')
    sector = row.get('sector') or row.get('company_sector')

    # Try sector-specific prompt
    sector_prompt = _get_sector_prompt(sector, symbol)
    
    # Context for dividend scanner
    scanner_context = f"""
Aktuelle Kennzahlen aus meinem Screening:
- KGV (P/E): {row.get('trailing_pe', 'N/A')}
- Dividendenrendite: {row.get('dividend_yield', 0)*100:.2f}%
- Payout Ratio: {row.get('payout_ratio', 0)*100:.1f}%
- RSI (14): {row.get('rsi', 'N/A')}
- IV-Rank: {row.get('iv_rank_val', 0)*100:.1f}%

Analysiere die Aktie besonders im Hinblick auf die Nachhaltigkeit der Dividende und ob das aktuelle technische Niveau (RSI, Vola) einen attraktiven Einstieg (Long oder Short Put) rechtfertigt.
"""

    if sector_prompt:
        prompt = sector_prompt.strip() + "\n" + scanner_context
    else:
        prompt = _get_claude_prompt_header(symbol, company) + scanner_context
    
    prompt += _get_claude_prompt_footer()
    
    encoded_prompt = urllib.parse.quote(prompt.strip())
    return f'https://claude.ai/new?q={encoded_prompt}'

def _create_claude_prompt_default(row):
    symbol = row['symbol']
    sector = row.get('company_sector')

    # Try sector-specific prompt
    sector_prompt = _get_sector_prompt(sector, symbol)
    if sector_prompt:
        encoded_prompt = urllib.parse.quote(sector_prompt.strip())
        return f'https://claude.ai/new?q={encoded_prompt}'

    # Fallback: generic prompt
    company = row.get('Company')
    company_info = f" ({company})" if company else ""

    prompt = f"""
Erstelle eine kompakte Aktienanalyse für {symbol}{company_info}:
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

    encoded_prompt = urllib.parse.quote(prompt)
    return f'https://claude.ai/new?q={encoded_prompt}'


def page_display_dataframe(
        df: pd.DataFrame,
        page: str | None = None,
        symbol_column: str = 'symbol',
        column_config: dict | None = None,
        on_select: str = "ignore",
        selection_mode: str = "multi-row"
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
        on_select: Streamlit on_select behavior ("ignore", "rerun", or callable)
        selection_mode: Streamlit selection mode ("single-row", "multi-row")
    """
    df_to_display = df.copy()
    df_to_display = _add_tradingview_link(df_to_display, symbol_column)
    df_to_display = _add_tradingview_superchart_link(df_to_display, symbol_column)
    df_to_display = _add_claude_analysis_link(df_to_display, page)

    if page == "spreads":
        # drop unnecessary columns which where needed for the AI prompt generation
        cols_to_drop = [
            'option_type', 'expiration_date',
            'sell_strike', 'sell_last_option_price', 'sell_delta', 'sell_iv',
            '%_otm', 'sell_theta', 'sell_open_interest', 'sell_expected_move',
            'sell_day_volume', 'sell_last_updated', 'buy_strike', 'buy_last_option_price', 'buy_delta',
            'buy_iv', 'buy_theta', 'buy_open_interest', 'buy_expected_move',
            'buy_day_volume', 'buy_last_updated', 'last_updated_option_data', 'last_updated_stock_data',
            'sell_last_updated_put', 'buy_last_updated_put',
            'sell_last_updated_call', 'buy_last_updated_call',
            'company_industry', 'company_sector', 'historical_volatility_30d',
            'days_to_earnings', 'analyst_mean_target', 'spread_theta',
            'TradingView', 'Chart', 'Claude', 'optionstrat_url'
        ]
        # Only drop columns that exist to avoid errors
        cols_to_drop = [c for c in cols_to_drop if c in df_to_display.columns]
        df_to_display = df_to_display.drop(columns=cols_to_drop)
    elif page == "iron_condors":
        # drop unnecessary columns which where needed for the AI prompt generation
        cols_to_drop = [
            'sell_delta_put', 'sell_delta_call', 
            'expiration_date_put', 'expiration_date_call',
            'close_call',
            'sell_strike_put', 'buy_strike_put',
            'sell_strike_call', 'buy_strike_call',
            'sell_last_option_price_put', 'buy_last_option_price_put',
            'sell_last_option_price_call', 'buy_last_option_price_call',
            'sell_iv_put', 'buy_iv_put', 'sell_iv_call', 'buy_iv_call',
            'sell_theta_put', 'buy_theta_put', 'sell_theta_call', 'buy_theta_call',
            'sell_open_interest_put', 'buy_open_interest_put',
            'sell_open_interest_call', 'buy_open_interest_call',
            'buy_delta_put', 'buy_delta_call',
            'sell_day_volume_put', 'buy_day_volume_put',
            'sell_day_volume_call', 'buy_day_volume_call',
            'sell_last_updated_put', 'buy_last_updated_put',
            'sell_last_updated_call', 'buy_last_updated_call',
            'sell_last_updated', 'buy_last_updated', 'last_updated_option_data', 'last_updated_stock_data',
            'sell_expected_move_put', 'buy_expected_move_put',
            'sell_expected_move_call', 'buy_expected_move_call',
            'historical_volatility_30d_put', 'industry', 'sector',
            'analyst_target', 'total_theta',
            'TradingView', 'Chart', 'Claude', 'optionstrat_url'
        ]
        # Only drop columns that exist to avoid errors
        cols_to_drop = [c for c in cols_to_drop if c in df_to_display.columns]
        df_to_display = df_to_display.drop(columns=cols_to_drop)

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
    for col in df_to_display.columns:
        if df_to_display[col].dtype in ['float64', 'float32']:
            default_config[col] = st.column_config.NumberColumn(
                col,
                format="%.2f"
            )

    # Apply styling: color negative numbers red
    styled_df = df_to_display.style.map(
        lambda val: 'color: #ff4444' if isinstance(val, (int, float)) and val < 0 else '',
        subset=df_to_display.select_dtypes(include=['number']).columns
    )

    # Merge with provided column_config if exists.
    # column_config has a higher priority than the default.
    if column_config:
        default_config.update(column_config)

    return st.dataframe(
        styled_df,
        column_config=default_config,
        hide_index=True,
        width="stretch",
        on_select=on_select,
        selection_mode=selection_mode
        #height="content",
    )