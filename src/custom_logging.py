import streamlit as st
import logging
from config import *

# Initialize log file
logging.basicConfig(
    filename=PATH_APP_LOGFILE,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)


def __log_message(level: str, message: str):
    """Logs a message in Streamlit and writes it to a file."""
    if "log_messages" not in st.session_state:
        st.session_state["log_messages"] = []

    if level != "debug":
        st.session_state["log_messages"].append((level, message))

    # Write to log file
    if level == "info":
        logging.info(message)
    elif level == "error":
        logging.error(message)
    elif level == "write" or level == "debug":
        logging.debug(message)
    else:
        raise ValueError("Invalid log level")


def log_info(message: str):
    __log_message("info", message)


def log_error(message: str):
    __log_message("error", message)


def log_write(message: str):
    """write is streamlite only level it handled the same as debug for file logging"""
    __log_message("write", message)


def log_debug(message: str):
    __log_message("debug", message)


def show_log_messages():
    """Displays all collected log messages in Streamlit."""
    if "log_messages" not in st.session_state:
        return
    for level, msg in st.session_state["log_messages"]:
        if level == "info":
            st.info(msg)
        elif level == "error":
            st.error(msg)
        else:
            st.write(msg)
