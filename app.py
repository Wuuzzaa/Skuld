import logging
import sys
import streamlit as st
from src.logger_config import setup_logging
from config import *

# enable logging
setup_logging(log_file=PATH_LOG_FILE, log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(__name__)
logger.info("Start SKULD")

# Check if "--local" is passed as a command-line argument
# start in terminal with: streamlit run app.py -- --local
# note the -- --local NOT --local this would be interpreted as a streamlit argument
use_local_data = "--local" in sys.argv

# Layout
st.set_page_config(layout="wide")

# Titel
st.title("SKULD - Option Viewer")

# Check if database exists (created by cronjob)
if not PATH_DATABASE_FILE.exists():
    st.error("""
    ⚠️ Database not found!
    
    The database is created automatically by the scheduled data collection process.
    Please wait for the next scheduled run (10:00 or 16:00 CET) or contact the administrator.
    """)
    st.info(f"Expected database location: `{PATH_DATABASE_FILE}`")
    st.stop()

logger.info(f"✓ Database found at: {PATH_DATABASE_FILE}")

# Define pages
analyst_prices = st.Page("pages/analyst_prices.py", title="Analyst Prices")
spreads = st.Page("pages/spreads.py", title="Spreads")
marrieds = st.Page("pages/married_put_analysis.py", title="Married Puts")
multifactor_swingtrading = st.Page('pages/multifactor_swingtrading.py', title="Multifactor Swingtrading")
DataLogs = st.Page('pages/data_change_logs.py', title="Data Logs")

# Set up navigation
page = st.navigation(
    [
        analyst_prices,
        spreads,
        marrieds,
        multifactor_swingtrading, 
        DataLogs
    ]
)

# Run the selected page
page.run()

# Footer for all pages
st.divider()
st.caption(f"SKULD Option Viewer - Data analysis tool for option trading strategies. Version: {VERSION}")
