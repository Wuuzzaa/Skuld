import streamlit as st
import pandas as pd


def _add_tradingview_link(df:pd.DataFrame, symbol_column='symbol'):
    df['TradingView'] = df[symbol_column].apply(
        lambda x: f'https://www.tradingview.com/symbols/{x}/'
    )
    return df

def _add_tradingview_superchart_link(df:pd.DataFrame, symbol_column='symbol'):
    df['chart'] = df[symbol_column].apply(
        lambda x: f'https://www.tradingview.com/chart/?symbol={x}'
    )
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

    # Default TradingView configuration
    default_config = {
        "TradingView": st.column_config.LinkColumn(
            "TradingView",
            display_text="🔗",
            width="small"
        ),
        "chart": st.column_config.LinkColumn(
            "Chart",
            display_text="📈",
            width="small"
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