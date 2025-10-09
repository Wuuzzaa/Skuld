from src.database import select_into_dataframe
from src.spreads_calculation import get_spreads
from src.custom_logging import *

# Titel
st.subheader("Spreads")

# Create a layout with multiple columns
col_epiration_date, col_delta_target, col_spread_width = st.columns(3)

# expiration date
with col_epiration_date:
    expiration_dates_sql = """
        SELECT DISTINCT expiration_date
        FROM OptionDataMerged
        ORDER BY expiration_date; \
    """

    expiration_dates = select_into_dataframe(expiration_dates_sql)
    expiration_date = st.selectbox("Expiration Date", expiration_dates)

# delta target
with col_delta_target:
    delta_target = st.number_input("Delta Target", min_value=0.0, max_value=1.0, value=0.2, step=0.01)

# spread width
with col_spread_width:
    spread_width = st.number_input("Spread Width", min_value=1, max_value=20, value=5, step=1)

# calculate the spread values with a loading indicator
with st.status("Calculating... Please wait.", expanded=True) as status:
    sql_query = """
    SELECT
            symbol,
            expiration_date,
            "option-type",
            strike,
            ask,
            bid,
            delta,
            iv,
            theta,
            close,
            earnings_date,
            days_to_expiration
    FROM
            OptionDataMerged
    WHERE
        expiration_date = :expiration_date;
    """

    df = select_into_dataframe(query=sql_query, params={"expiration_date": expiration_date})

    spreads_df = get_spreads(df, delta_target, spread_width)

    status.update(label="Calculation complete!", state="complete", expanded=True)

# Dynamically extract unique values for symbol and option_type from calculated spreads_df
unique_symbols = sorted(spreads_df['symbol'].unique())
unique_option_types = sorted(spreads_df['option_type'].unique())

col_symbol, col_option_type = st.columns(2)

# symbol
with col_symbol:
    symbol = st.selectbox("Symbol", ["All Symbols"] + unique_symbols)

# option type
with col_option_type:
    option_type = st.selectbox("Option Type", ["Put and Call"] + unique_option_types)

# Apply filters if specific values are selected
# let it on "All" "" does not work
if symbol != "All Symbols":
    spreads_df = spreads_df[spreads_df['symbol'] == symbol]

if option_type != "Put and Call":
    spreads_df = spreads_df[spreads_df['option_type'] == option_type]

# Show the filtered spreads
log_info(f"Spreads calculated for: {expiration_date}, delta {delta_target}, spread width {spread_width}, symbol {symbol}, option type {option_type}")
st.dataframe(spreads_df, use_container_width=True)
