import streamlit as st

def log_info(message: str):
    """Fügt eine Info-Meldung dem Log hinzu."""
    if "log_messages" not in st.session_state:
        st.session_state["log_messages"] = []
    st.session_state["log_messages"].append(("info", message))

def log_error(message: str):
    """Fügt eine Error-Meldung dem Log hinzu."""
    if "log_messages" not in st.session_state:
        st.session_state["log_messages"] = []
    st.session_state["log_messages"].append(("error", message))

def log_write(message: str):
    """Fügt eine 'write'-Meldung dem Log hinzu (für z.B. Download-Fortschritt)."""
    if "log_messages" not in st.session_state:
        st.session_state["log_messages"] = []
    st.session_state["log_messages"].append(("write", message))

def show_log_messages():
    """Zeigt alle gesammelten Log-Meldungen an."""
    if "log_messages" not in st.session_state:
        return
    for level, msg in st.session_state["log_messages"]:
        if level == "info":
            st.info(msg)
        elif level == "error":
            st.error(msg)
        else:
            st.write(msg)
