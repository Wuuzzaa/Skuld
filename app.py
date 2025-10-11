from src.google_drive_download import load_updated_data, load_updated_database
from src.custom_logging import *
import sys

# Check if "--local" is passed as a command-line argument
# start in terminal with: streamlit run app.py -- --local
# note the -- --local NOT --local this would be interpreted as a streamlit argument
use_local_data = "--local" in sys.argv

# Layout
st.set_page_config(layout="wide")

# Titel
st.title("SKULD - Option Viewer")

# Ensure database is available (download if needed)
@st.cache_data(ttl=1800, show_spinner="Checking for database updates...")
def ensure_database_available():
    """Downloads the database from Google Drive if needed."""
    if not use_local_data:
        return load_updated_database()
    return True

ensure_database_available()

# Define pages
analyst_prices = st.Page("pages/analyst_prices.py", title="Analyst Prices")
spreads = st.Page("pages/spreads.py", title="Spreads")
marrieds = st.Page("pages/married_put_analysis.py", title="Married Puts")

# Set up navigation
page = st.navigation(
    [
        analyst_prices,
        spreads,
        marrieds
    ]
)

# Run the selected page
page.run()
