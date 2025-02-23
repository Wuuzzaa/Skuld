import streamlit as st

# Titel
st.subheader("Total DataFrame")

df = st.session_state['df']
st.dataframe(df, use_container_width=True)