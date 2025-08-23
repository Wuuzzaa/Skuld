# Skuld - Option Trading Analysis Platform

Skuld is a Python-based financial data analysis application that scrapes options data, stock prices, technical indicators, and analyst information to provide comprehensive option trading analysis through a Streamlit web interface.

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

### Critical Requirements
- **Working Directory**: ALWAYS run Python commands from repository root (`/path/to/Skuld/`)
- **Python Path**: Application uses relative imports - commands will fail if run from other directories
- **Network Access**: Data collection requires internet connectivity to external financial APIs

### Environment Setup
- **Python Version**: Python 3.12 (required)
- **Install Dependencies**: `pip install -r requirements.txt` -- takes 2-3 minutes. NEVER CANCEL. Set timeout to 5+ minutes.

### Data Collection Pipeline (main.py)
- **Test Mode**: `python main.py --testmode true --upload_df_google_drive false` -- takes 5-10 minutes but FAILS without network access
- **Production Mode**: `python main.py --testmode false --upload_df_google_drive true` -- takes 15-30 minutes. NEVER CANCEL. Set timeout to 45+ minutes.
- **CRITICAL**: Main script requires internet access to scrape data from:
  - TradingView (scanner.tradingview.com) for options data  
  - Yahoo Finance (fc.yahoo.com) for analyst price targets
  - Other financial data sources
- **In offline environments**: Main script will fail with network connection errors - this is expected behavior

### Streamlit Web Application
- **Local Mode**: `streamlit run app.py -- --local` -- starts immediately, uses local data files
- **Online Mode**: `streamlit run app.py` -- downloads data from Google Drive if available
- **Default Port**: 8501
- **Access**: http://localhost:8501
- **Data Dependency**: App will show "FileNotFoundError" for missing merged_df.feather but navigation still works
- **Pages Available**: Total Data, Filtered Data, Analyst Prices, Spreads, Iron Condors, Multi-Indicator Direction, Log Messages, Dividend Page, Documentation
- **Documentation Page**: Works independently and shows JMS (Joachims Milchmädchenrechnungs Score) calculation details

### Testing
- **Run Tests**: `python -m pytest tests/ -v` -- takes 1-2 minutes. NEVER CANCEL.
- **Test Mode**: Tests require network access and will fail in offline environments
- **Test Coverage**: Single test that runs main.py in test mode with 3 symbols and 3 expiration dates

## Validation Scenarios

After making changes to the codebase, ALWAYS validate with these scenarios:

### 1. Dependency Installation Test
```bash
pip install -r requirements.txt
```
Expected: All packages install without errors (2-3 minutes)

### 2. Streamlit App Launch Test
```bash
streamlit run app.py -- --local
curl -s -o /dev/null -w "%{http_code}" http://localhost:8501
```
Expected: HTTP 200 response, app accessible at localhost:8501
Note: App will show FileNotFoundError for missing data but navigation works correctly

### 3. Configuration Validation
```bash
cd /home/runner/work/Skuld/Skuld
python -c "from config import SYMBOLS, SYMBOLS_EXCHANGE, PATH_DATA; print(f'Loaded {len(SYMBOLS)} symbols'); print('Config OK')"
```
Expected: Prints symbol count and "Config OK"
Note: Must run from repository root directory due to Python import paths

### 4. Module Import Test
```bash
cd /home/runner/work/Skuld/Skuld
python -c "from src.util import create_all_project_folders; create_all_project_folders(); print('Modules OK')"
```
Expected: Creates data folders and prints "Modules OK"
Note: Must run from repository root directory due to Python import paths

## Build and Deployment

### GitHub Actions Workflow
- **File**: `.github/workflows/main.yml` (main workflow - uses Python 3.12)
- **Alternative**: `src/.github/workflows/main.yml` (uses Python 3.9, different branch)
- **Triggers**: 
  - Push to master branch
  - Scheduled: Weekdays at 9:00 and 15:00 UTC
  - Manual workflow dispatch
- **Python Version**: 3.12 (recommended - matches local development)
- **Runtime**: 20-45 minutes depending on data volume. NEVER CANCEL.
- **Requirements**: SERVICE_ACCOUNT_JSON secret for Google Drive access

### Manual Deployment
1. Set up Python 3.12 environment
2. Install dependencies: `pip install -r requirements.txt`
3. Create service account file: `service_account.json` (for Google Drive integration)
4. Run data collection: `python main.py`
5. Launch web app: `streamlit run app.py`

## Common Tasks

### Adding New Financial Symbols
1. Edit `symbols_exchange.xlsx` - add symbol and exchange columns
2. Configuration automatically loads from Excel file via `config.py`
3. No code changes required for new symbols

### Data File Locations
```
data/
├── json/option_data_tradingview/     # Raw scraped option data
├── price_target_df.feather           # Analyst price targets
├── option_data.feather               # Processed option data
├── price_and_indicators.feather      # Stock prices and technical indicators
├── earning_dates.feather             # Earnings calendar data
├── dividend_radar.feather            # Dividend information
└── merged_df.feather                 # Final combined dataset for app
```

### Strategy Documentation Available
- **JMS Score**: "Joachims Milchmädchenrechnungs Score" - proprietary scoring system
- **Calculation**: Expected value based on option delta, stop loss (200% of premium), take profit (60% of max profit)
- **Purpose**: Normalized comparison across different underlyings using Buying Power Reduction (BPR)
- **Access**: Available via Documentation page in Streamlit app (works without data)
- `SYMBOLS`: List of stock symbols loaded from Excel
- `SYMBOLS_EXCHANGE`: Symbol to exchange mapping
- `PATH_DATA`: Base data directory
- `DATAFRAME_DATA_MERGED_COLUMNS`: Columns used in final dataset

### Streamlit Pages Structure
```
pages/
├── total_dataframe.py               # Full dataset view
├── filtered_dataframe.py            # Filtered data view
├── analyst_prices.py                # Analyst price targets
├── spreads.py                       # Option spread analysis
├── iron_condors.py                  # Iron condor strategies
├── strategy_multi_indicator_score_direction.py  # Multi-indicator analysis
├── dividend_page.py                 # Dividend data
├── log_messages.py                  # Application logs
└── documentation.py                 # Strategy documentation
```

## Troubleshooting

### Network Access Issues
- **Symptom**: "Failed to resolve hostname" errors
- **Cause**: Application requires internet access for data scraping
- **Solution**: Run in environment with network access or use existing data files

### Missing Data Files
- **Symptom**: Streamlit app shows errors or empty data
- **Cause**: No processed data files available
- **Solution**: Run `python main.py --testmode true` to generate sample data

### Google Drive Integration Issues
- **Symptom**: Upload/download failures
- **Cause**: Missing or invalid service_account.json
- **Solution**: Obtain valid Google Service Account credentials and place in root directory

### Port Already in Use
- **Symptom**: Streamlit won't start
- **Solution**: `streamlit run app.py --server.port 8502` (use different port)

## Development Guidelines

### Code Style
- No specific linting tools configured
- Follow existing code patterns in the repository
- Use meaningful variable names and docstrings for complex functions

### Testing Changes
1. **Always** test Streamlit app launch after changes to app.py or pages/
2. **Always** test configuration loading after changes to config.py
3. **Always** test module imports after changes to src/ modules
4. Run main.py in test mode if network access available

### Performance Considerations
- Main data collection takes 15-30 minutes - optimize scraping functions carefully
- Feather format used for efficient data storage - maintain compatibility
- Streamlit caching implemented for data loading - respect cache decorators

## Dependencies and Requirements

### Core Dependencies
- **streamlit**: Web application framework
- **pandas**: Data manipulation and analysis
- **requests**: HTTP requests for data scraping
- **tradingview-ta**: TradingView technical analysis
- **yfinance**: Yahoo Finance data
- **yahooquery**: Extended Yahoo Finance capabilities
- **google-api-python-client**: Google Drive integration
- **beautifulsoup4**: Web scraping
- **pyarrow**: Feather file format support

### File Requirements
- `requirements.txt`: All Python dependencies
- `symbols_exchange.xlsx`: Trading symbols and exchanges
- `service_account.json`: Google Drive service account (not in repo)

**CRITICAL TIMING NOTES:**
- **NEVER CANCEL** dependency installation (5+ minutes)
- **NEVER CANCEL** main script execution (45+ minutes)
- **NEVER CANCEL** GitHub Actions workflow (45+ minutes)
- Always set appropriate timeouts for all build and data collection operations