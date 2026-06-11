import pandas as pd

try:
    import streamlit as st
except ImportError:
    st = None

from src.database import select_into_dataframe


def _extract_first_column_values(data):
    if data is None:
        return []
    if isinstance(data, pd.DataFrame):
        if data.empty:
            return []
        return data.iloc[:, 0].tolist()
    if isinstance(data, pd.Series):
        return data.tolist()
    if isinstance(data, (list, tuple, set)):
        return list(data)
    return [data]


def render_date_filter(
        date_query: str,
        date_session_key: str = "selected_date",
        date_list_session_key: str = "date_list",
        date_label: str = "Select a Date for Time Travel:",
        date_placeholder: str = "Choose a date...",
        date_index: int = 0,
):
    if st is None:
        raise ImportError("streamlit is required to render Streamlit helpers")

    if date_list_session_key not in st.session_state:
        st.session_state[date_list_session_key] = select_into_dataframe(query=date_query)

    date_options = _extract_first_column_values(st.session_state[date_list_session_key])
    if not date_options:
        raise ValueError("No dates returned for time travel filter.")

    if date_session_key not in st.session_state:
        st.session_state[date_session_key] = date_options[date_index]

    selected_date = st.selectbox(
        date_label,
        options=date_options,
        index=date_index,
        key=date_session_key,
        placeholder=date_placeholder,
    )

    return selected_date


def render_symbol_filter(
        symbol_query: str,
        symbol_session_key: str = "selected_symbol",
        symbol_list_session_key: str = "symbol_list",
        symbol_label: str = "Select a Symbol:",
        symbol_placeholder: str = "Type to search... (e.g., MSFT, AAPL)",
        symbol_index=None,
        include_empty_option: bool = True,
):
    if st is None:
        raise ImportError("streamlit is required to render Streamlit helpers")

    if symbol_list_session_key not in st.session_state:
        st.session_state[symbol_list_session_key] = select_into_dataframe(query=symbol_query)

    symbol_options = _extract_first_column_values(st.session_state[symbol_list_session_key])
    if not symbol_options:
        raise ValueError("No symbols returned for symbol filter.")

    if include_empty_option:
        symbol_options = [""] + symbol_options

    if symbol_index is not None:
        if symbol_index < 0 or symbol_index >= len(symbol_options):
            raise ValueError("symbol_index is out of range for symbol options")
        if symbol_session_key not in st.session_state:
            st.session_state[symbol_session_key] = symbol_options[symbol_index]

    selected_symbol = st.selectbox(
        symbol_label,
        options=symbol_options,
        index=symbol_index if symbol_index is not None else 0,
        key=symbol_session_key,
        placeholder=symbol_placeholder,
    )

    if include_empty_option:
        selected_symbol = selected_symbol or None

    return selected_symbol


def render_time_travel_symbol_filters(
        date_query: str,
        symbol_query: str,
        date_session_key: str = "selected_date",
        symbol_session_key: str = "selected_symbol",
        date_list_session_key: str = "date_list",
        symbol_list_session_key: str = "symbol_list",
        date_label: str = "Select a Date for Time Travel:",
        symbol_label: str = "Select a Symbol:",
        date_placeholder: str = "Choose a date...",
        symbol_placeholder: str = "Type to search... (e.g., MSFT, AAPL)",
        date_index: int = 0,
        symbol_index=None,
):
    selected_date = render_date_filter(
        date_query=date_query,
        date_session_key=date_session_key,
        date_list_session_key=date_list_session_key,
        date_label=date_label,
        date_placeholder=date_placeholder,
        date_index=date_index,
    )

    selected_symbol = render_symbol_filter(
        symbol_query=symbol_query,
        symbol_session_key=symbol_session_key,
        symbol_list_session_key=symbol_list_session_key,
        symbol_label=symbol_label,
        symbol_placeholder=symbol_placeholder,
        symbol_index=symbol_index,
    )

    return selected_date, selected_symbol
