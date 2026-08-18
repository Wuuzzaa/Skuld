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
universe = st.Page("pages/universe.py", title="Universum")
delta_portfolio = st.Page("pages/delta_portfolio.py", title="Delta Portfolio")
watchlist = st.Page("pages/watchlist.py", title="Watchlist")
spreads = st.Page("pages/spreads.py", title="Spreads")
spreads_enhanced = st.Page("pages/spreads_enhanced.py", title="Spreads Enhanced")
marrieds = st.Page("pages/married_put_analysis.py", title="Married Puts")
position_insurance = st.Page("pages/position_insurance_tool.py", title="Position Insurance Tool")
multifactor_swingtrading = st.Page('pages/multifactor_swingtrading.py', title="Multifactor Swingtrading")
sector_rotation = st.Page('pages/sector_rotation.py', title="Sector Rotation")
rsl_momentum = st.Page('pages/rsl_momentum.py', title="RSL Momentum")
expected_value = st.Page('pages/expected_value.py', title="Expected Value")
dividend_scanner = st.Page("pages/dividend_scanner.py", title="Dividend Scanner")
option_strategy_finder = st.Page("pages/option_strategy_finder.py", title="Option Strategy Finder")
crash_hedge_finder = st.Page("pages/crash_hedge_finder.py", title="Crash Hedge Finder")
index_short_put = st.Page("pages/index_short_put.py", title="Index Short Put")
zahltagstrategie = st.Page("pages/dividend_screener_zahltagstrategie.py", title="Zahltagstrategie")
data_logs = st.Page("pages/data_change_logs.py", title="Data Logs")
iron_condors = st.Page("pages/iron_condors.py", title="Iron Condors")
iron_condors_enhanced = st.Page("pages/iron_condors_enhanced.py", title="Iron Condors Enhanced")
short_strangle = st.Page("pages/short_strangle.py", title="Short Strangle")
jade_lizard = st.Page("pages/jade_lizard.py", title="Jade Lizard")
earnings_put_scanner = st.Page("pages/earnings_put_scanner.py", title="Earnings Put Scanner")
covered_call_scanner = st.Page("pages/covered_call_scanner.py", title="ITM Covered Call Scanner")
volatility = st.Page("pages/volatility.py", title="Volatility")
roll_and_screen = st.Page("pages/roll_and_screen.py", title="Roll & Screen")
symbolpage = st.Page("pages/symbolpage.py", title="Symbol Page")
admin_jobs = st.Page("pages/admin_jobs.py", title="Admin - Jobs")

# Set up navigation
page = st.navigation(
    [
        analyst_prices,
        universe,
        delta_portfolio,
        watchlist,
        spreads,
        spreads_enhanced,
        iron_condors,
        iron_condors_enhanced,
        short_strangle,
        jade_lizard,
        earnings_put_scanner,
        covered_call_scanner,
        volatility,
        roll_and_screen,
        marrieds,
        position_insurance,
        multifactor_swingtrading,
        sector_rotation,
        rsl_momentum,
        expected_value,
        dividend_scanner,
        option_strategy_finder,
        crash_hedge_finder,
        index_short_put,
        zahltagstrategie,
        data_logs,
        symbolpage,
        admin_jobs
    ]
)

# Run the selected page
page.run()

# Footer for all pages
st.divider()
skuld_env = os.getenv('SKULD_ENV', '')
skuld_branch = os.getenv('SKULD_BRANCH', '')
footer_text = f"SKULD Option Viewer - Data analysis tool for option trading strategies. Version: {VERSION}"
if skuld_branch and skuld_env != 'Production':
    footer_text += f" | Branch: {skuld_branch}"
st.caption(footer_text)
