import streamlit as st
from src.custom_logging import show_log_messages

st.subheader("Logs")

show_log_messages()