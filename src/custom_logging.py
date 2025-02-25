import streamlit as st

def log_info(message: str):
    """Add an info message to the log."""
    if "log_messages" not in st.session_state:
        st.session_state["log_messages"] = []
    st.session_state["log_messages"].append(("info", message))

def log_error(message: str):
    """Add an error message to the log."""
    if "log_messages" not in st.session_state:
        st.session_state["log_messages"] = []
    st.session_state["log_messages"].append(("error", message))

def log_write(message: str):
    """Add a 'write' message to the log (e.g., for download progress)."""
    if "log_messages" not in st.session_state:
        st.session_state["log_messages"] = []
    st.session_state["log_messages"].append(("write", message))

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
