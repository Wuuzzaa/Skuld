import streamlit as st
import pandas as pd


def _add_tradingview_link(df:pd.DataFrame, symbol_column='symbol'):
    """
    Adds a TradingView link column to the DataFrame.

    Args:
        df: DataFrame
        symbol_column: Name of the column containing symbols (default: 'Symbol')

    Returns:
        DataFrame with TradingView column
    """
    df['TradingView'] = df[symbol_column].apply(
        lambda x: f'https://www.tradingview.com/symbols/{x}/'
    )
    return df


def page_display_dataframe_with_trading_view_link(df:pd.DataFrame, symbol_column='symbol'):
    """
    Displays DataFrame with TradingView links configured.

    Args:
        df: DataFrame
        symbol_column: Name of the column containing symbols (default: 'Symbol')
    """
    df = _add_tradingview_link(df, symbol_column)

    st.dataframe(
        df,
        column_config={
            "TradingView": st.column_config.LinkColumn(
                "TradingView",
                display_text="🔗"
            )
        },
        hide_index=True,
        use_container_width=True
    )