import streamlit as st
import pandas as pd
from typing import Dict, Any, List

def init_session_state(defaults: Dict[str, Any]):
    """Initializes streamlit session state with default values if not already present."""
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def reset_to_defaults(defaults: Dict[str, Any]):
    """Resets session state to default values."""
    for key, value in defaults.items():
        st.session_state[key] = value

def filter_by_expiration_type(df: pd.DataFrame, expiration_column: str, show_monthly: bool, show_weekly: bool, show_daily: bool) -> pd.DataFrame:
    """Filters a DataFrame by expiration type (Monthly, Weekly, Daily)."""
    from src.utils.option_utils import get_expiration_type
    
    if df.empty:
        return df
        
    df['exp_type'] = df[expiration_column].apply(get_expiration_type)
    
    allowed_types = []
    if show_monthly: allowed_types.append("Monthly")
    if show_weekly: allowed_types.append("Weekly")
    if show_daily: allowed_types.append("Daily")
    
    return df[df['exp_type'].isin(allowed_types)].drop(columns=['exp_type'])

def display_common_filters(column_config: Dict[str, Any] = None):
    """Displays common filters used in spreads and iron condors pages."""
    # This could be expanded to actually render the widgets, 
    # but since they are sometimes slightly different or in different columns,
    # we might just provide helper functions for specific groups of filters.
    pass
