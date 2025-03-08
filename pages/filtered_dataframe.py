import streamlit as st

# Titel
st.subheader("Gefilterte Ansicht")

df = st.session_state['df']

# Filteroptionen bereitstellen
st.sidebar.header("Filter")

# Filter für numerische Spalten
num_cols = df.select_dtypes(include=['float64', 'int64']).columns
filtered_df = df.copy()
for col in num_cols:
    min_val, max_val = st.sidebar.slider(
        f"Filter für {col}",
        float(df[col].min()),
        float(df[col].max()),
        (float(df[col].min()), float(df[col].max())),
    )
    filtered_df = filtered_df[(filtered_df[col] >= min_val) & (filtered_df[col] <= max_val)]

# Filter für kategorische Spalten
cat_cols = df.select_dtypes(include=['object']).columns
for col in cat_cols:
    selected = st.sidebar.multiselect(f"Werte für {col} auswählen", df[col].unique())
    if selected:
        filtered_df = filtered_df[filtered_df[col].isin(selected)]

# Gefilterter DataFrame anzeigen
st.dataframe(filtered_df, use_container_width=True)