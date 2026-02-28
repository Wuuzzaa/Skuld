import logging
import sys
import streamlit as st
from src.database import run_migrations
from src.logger_config import setup_logging
from config import *
import os

# enable logging
setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(__name__)
logger.info("Start SKULD")

# run_migrations()

# Check if "--local" is passed as a command-line argument
# start in terminal with: streamlit run app.py -- --local
# note the -- --local NOT --local this would be interpreted as a streamlit argument
use_local_data = "--local" in sys.argv

# Layout
st.set_page_config(layout="wide")


# Titel
st.title("SKULD - Option Viewer")

# Define pages
analyst_prices = st.Page("pages/analyst_prices.py", title="Analyst Prices")
spreads = st.Page("pages/spreads.py", title="Spreads")
marrieds = st.Page("pages/married_put_analysis.py", title="Married Puts")
multifactor_swingtrading = st.Page('pages/multifactor_swingtrading.py', title="Multifactor Swingtrading")
expected_value = st.Page('pages/expected_value.py', title="Expected Value")
position_insurance = st.Page('pages/position_insurance_tool.py', title="Position Insurance Tool")
smart_finder = st.Page('pages/smart_finder.py', title="Smart Finder")
call_income_simulator = st.Page('pages/call_income_simulator.py', title="Call Income Simulator")
married_put_finder = st.Page('pages/married_put_finder.py', title="Married Put Finder")
data_logs = st.Page("pages/data_change_logs.py", title="Data Logs")
symbolpage = st.Page("pages/symbolpage.py", title="Symbol Page")

# Set up navigation
page = st.navigation(
    [
        analyst_prices,
        spreads,
        marrieds,
        position_insurance,
        smart_finder,
        call_income_simulator,
        married_put_finder,
        multifactor_swingtrading,
        expected_value,
        data_logs,
        symbolpage
    ]
)

# Run the selected page
page.run()

# Footer for all pages
st.divider()
st.caption(f"SKULD Option Viewer - Data analysis tool for option trading strategies. Version: {VERSION}")
