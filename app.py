import logging
import sys
import streamlit as st
from src.database import run_migrations
from src.logger_config import setup_logging
from config import *
import os

# # enable logging
# setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
# logger = logging.getLogger(__name__)
# logger.info("Start SKULD")

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
watchlist = st.Page("pages/watchlist.py", title="Watchlist")
spreads = st.Page("pages/spreads.py", title="Spreads")
marrieds = st.Page("pages/married_put_analysis.py", title="Married Puts")
position_insurance = st.Page("pages/position_insurance_tool.py", title="Position Insurance Tool")
multifactor_swingtrading = st.Page('pages/multifactor_swingtrading.py', title="Multifactor Swingtrading")
sector_rotation = st.Page('pages/sector_rotation.py', title="Sector Rotation")
rsl_momentum = st.Page('pages/rsl_momentum.py', title="RSL Momentum")
expected_value = st.Page('pages/expected_value.py', title="Expected Value")
dividend_scanner = st.Page("pages/dividend_scanner.py", title="Dividend Scanner")
zahltagstrategie = st.Page("pages/dividend_screener_zahltagstrategie.py", title="Zahltagstrategie")
data_logs = st.Page("pages/data_change_logs.py", title="Data Logs")
iron_condors = st.Page("pages/iron_condors.py", title="Iron Condors")
earnings_put_scanner = st.Page("pages/earnings_put_scanner.py", title="Earnings Put Scanner")
symbolpage = st.Page("pages/symbolpage.py", title="Symbol Page")
admin_jobs = st.Page("pages/admin_jobs.py", title="Admin - Jobs")

# Set up navigation
page = st.navigation(
    [
        analyst_prices,
        watchlist,
        spreads,
        iron_condors,
        earnings_put_scanner,
        marrieds,
        position_insurance,
        multifactor_swingtrading,
        sector_rotation,
        rsl_momentum,
        expected_value,
        dividend_scanner,
        zahltagstrategie,
        data_logs,
        symbolpage,
        admin_jobs
    ]
)

# Run the selected page
page.run()

# Sidebar: external monitoring link.
# Authelia session cookie is scoped to *.skuld-options.com, so the user is
# already logged in for monitoring.skuld-options.com — no second login needed.
# See ops/MONITORING.md for the full setup.
_monitoring_url = os.getenv("MONITORING_URL", "https://monitoring.skuld-options.com")
with st.sidebar:
    st.divider()
    st.markdown(
        f"[🩺 System Status]({_monitoring_url})",
        help="Live health of all SKULD services. Login is reused via SSO.",
    )

# Footer for all pages
st.divider()
skuld_env = os.getenv('SKULD_ENV', '')
skuld_branch = os.getenv('SKULD_BRANCH', '')
footer_text = f"SKULD Option Viewer - Data analysis tool for option trading strategies. Version: {VERSION}"
if skuld_branch and skuld_env != 'Production':
    footer_text += f" | Branch: {skuld_branch}"
st.caption(footer_text)



