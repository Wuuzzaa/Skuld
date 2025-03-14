import streamlit as st
import pandas as pd
import numpy as np

# Title
st.subheader("Filtered View")

df = st.session_state['df']

# Sidebar filters
st.sidebar.header("Filters")

# Numeric column filters
num_cols = df.select_dtypes(include=['float64', 'int64']).columns
filtered_df = df.copy()

for col in num_cols:
    col_min = df[col].min(skipna=True)  # Ignore NaNs when getting min value
    col_max = df[col].max(skipna=True)  # Ignore NaNs when getting max value

    # If all values are NaN, skip this column
    if pd.isna(col_min) or pd.isna(col_max):
        continue

    # If min == max, slightly increase max to avoid slider error
    if col_min == col_max:
        col_max += 1

    min_val, max_val = st.sidebar.slider(
        f"Filter for {col}",
        float(col_min),
        float(col_max),
        (float(col_min), float(col_max)),
    )

    filtered_df = filtered_df[(filtered_df[col] >= min_val) & (filtered_df[col] <= max_val)]

# Categorical column filters
cat_cols = df.select_dtypes(include=['object']).columns

for col in cat_cols:
    unique_values = df[col].dropna().unique()  # Ignore NaN values
    if len(unique_values) > 0:
        selected = st.sidebar.multiselect(f"Select values for {col}", unique_values)
        if selected:
            filtered_df = filtered_df[filtered_df[col].isin(selected)]

# Display filtered DataFrame
st.dataframe(filtered_df, use_container_width=True)
