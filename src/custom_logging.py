import streamlit as st
from datetime import datetime

def log_info(message: str):
    """Add an info message to the log with a timestamp."""
    if "log_messages" not in st.session_state:
        st.session_state["log_messages"] = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state["log_messages"].append(("info", f"[{timestamp}] {message}"))

def log_error(message: str):
    """Add an error message to the log with a timestamp."""
    if "log_messages" not in st.session_state:
        st.session_state["log_messages"] = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state["log_messages"].append(("error", f"[{timestamp}] {message}"))

def log_write(message: str):
    """Add a 'write' message to the log (e.g., for download progress) with a timestamp."""
    if "log_messages" not in st.session_state:
        st.session_state["log_messages"] = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state["log_messages"].append(("write", f"[{timestamp}] {message}"))

def show_log_messages():
    """Display all collected log messages."""
    if "log_messages" not in st.session_state:
        return
    for level, msg in st.session_state["log_messages"]:
        if level == "info":
            st.info(msg)
        elif level == "error":
            st.error(msg)
        else:
            st.write(msg)
