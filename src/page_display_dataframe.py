import streamlit as st
import pandas as pd
import urllib.parse


def _add_tradingview_link(df:pd.DataFrame, symbol_column='symbol'):
    df['TradingView'] = df[symbol_column].apply(
        lambda x: f'https://www.tradingview.com/symbols/{x}/'
    )
    return df

def _add_tradingview_superchart_link(df:pd.DataFrame, symbol_column='symbol'):
    df['Chart'] = df[symbol_column].apply(
        lambda x: f'https://www.tradingview.com/chart/?symbol={x}'
    )
    return df


def _add_claude_analysis_link(df: pd.DataFrame, symbol_column='symbol'):
    """Adds Claude AI analysis link with pre-filled prompt"""

    def create_claude_prompt(symbol):
        prompt = f"""
            Erstelle eine kompakte Aktienanalyse für {symbol}:
            Unternehmen: Geschäftsmodell und Branche in 1-2 Sätzen
            Aktuelle News: Wichtigste Entwicklungen der letzten 4 Wochen
            Anstehende Events: Earnings, Produktlaunches oder relevante Termine
            Einschätzung:
            
            Kauf/Halten/Verkaufen mit Begründung
            Aktuelles Kursziel (Analystenkonsens)
            Wichtigste Chance und größtes Risiko
            
            Format: Prägnant, faktenbasiert, keine Füllwörter, max. eine Seite.
        """
        # URL-encode the prompt
        encoded_prompt = urllib.parse.quote(prompt)
        return f'https://claude.ai/new?q={encoded_prompt}'

    df['Claude'] = df[symbol_column].apply(create_claude_prompt)
    return df



def page_display_dataframe(
    df: pd.DataFrame,
    symbol_column='symbol',
    column_config: dict = None
):
    """
    Displays DataFrame with TradingView links configured.
    All float columns are formatted to 2 decimal places by default.

    Args:
        df: DataFrame
        symbol_column: Name of the column containing symbols (default: 'symbol')
        column_config: Optional dictionary of column configurations to merge with TradingView config.
                        These settings have higher priority than the default settings.
    """
    df = _add_tradingview_link(df, symbol_column)
    df = _add_tradingview_superchart_link(df, symbol_column)
    df = _add_claude_analysis_link(df, symbol_column)

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