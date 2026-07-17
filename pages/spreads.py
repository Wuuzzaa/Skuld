import logging
import os
import streamlit as st
import pandas as pd
from config import (
    PATH_DATABASE_QUERY_FOLDER,
    IV_CORRECTION_MODE,
    RISK_FREE_RATE,
    DEEPSEEK_MODEL,
)
from pages.backtesting.spreads_backtesting import display_spreads_backtesting
from pages.documentation_text.spreads_page_doc import get_spreads_documentation
from src.database import select_into_dataframe
from src.historization import select_timetravel_into_dataframe
from src.llm_client import LLMClient, LLMProviderError
from src.live_market_research import build_live_research_bundle
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe, _create_claude_prompt_page_spreads
from src.spreads_ai_analysis import (
    build_bulk_spreads_prompt,
    parse_spreads_ranking_table,
    estimate_deepseek_cost,
)
from src.spreads_calculation import get_page_spreads
from src.streamlit_helpers import render_date_filter
from src.utils.option_utils import get_expiration_type
from src.ui_utils import init_session_state, reset_to_defaults as ui_reset, filter_by_expiration_type
from src.ui_strategy_display import display_strategy_details
from src.options_utils import OptionLeg, StrategyMetrics

# Ensure logfile gets all columns of wide dataframes
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

# Setup logging
setup_logging(component="streamlit", sub_component="spreads", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

# Constants for default values
DEFAULT_SHOW_MONTHLY = True
DEFAULT_SHOW_WEEKLY = False
DEFAULT_SHOW_DAILY = False
DEFAULT_SHOW_ONLY_POSITIV_EXPECTED_VALUE = True
DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_TILL_EXPIRATION = True
DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_WARNING = True
DEFAULT_DELTA_TARGET = 0.2
DEFAULT_SPREAD_WIDTH = 5
DEFAULT_OPTION_TYPE = "put"
DEFAULT_MIN_DAY_VOLUME = 20
DEFAULT_MIN_OPEN_INTEREST = 100
DEFAULT_MIN_SELL_IV = 0.3
DEFAULT_MAX_SELL_IV = 0.9
DEFAULT_MIN_MAX_PROFIT = 80.0
DEFAULT_MIN_IV_RANK = 0
DEFAULT_MIN_IV_PERCENTILE = 0
DEFAULT_STRATEGY_TYPE = "credit"

# Page header
st.title("Spreads")

# Default values mapping for UI utils
DEFAULTS = {
    'show_monthly': DEFAULT_SHOW_MONTHLY,
    'show_weekly': DEFAULT_SHOW_WEEKLY,
    'show_daily': DEFAULT_SHOW_DAILY,
    'show_only_positiv_expected_value': DEFAULT_SHOW_ONLY_POSITIV_EXPECTED_VALUE,
    'show_only_spreads_with_no_earnings_till_expiration': DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_TILL_EXPIRATION,
    'show_only_spreads_with_no_earnings_warning': DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_WARNING,
    'delta_target': DEFAULT_DELTA_TARGET,
    'spread_width': DEFAULT_SPREAD_WIDTH,
    'option_type': DEFAULT_OPTION_TYPE,
    'min_day_volume': DEFAULT_MIN_DAY_VOLUME,
    'min_open_interest': DEFAULT_MIN_OPEN_INTEREST,
    'min_sell_iv': DEFAULT_MIN_SELL_IV,
    'max_sell_iv': DEFAULT_MAX_SELL_IV,
    'min_max_profit': DEFAULT_MIN_MAX_PROFIT,
    'min_iv_rank': DEFAULT_MIN_IV_RANK,
    'min_iv_percentile': DEFAULT_MIN_IV_PERCENTILE,
    'strategy_type': DEFAULT_STRATEGY_TYPE,
    'iv_correction': IV_CORRECTION_MODE,
    'risk_free_rate': RISK_FREE_RATE * 100  # stored as percentage for UI (e.g. 3.0 = 3%)
}

init_session_state(DEFAULTS)


def reset_to_defaults():
    ui_reset(DEFAULTS)


def clear_all_filters():
    """
    Clears all filters to show all possible results.
    """
    st.session_state.show_monthly = True
    st.session_state.show_weekly = True
    st.session_state.show_daily = True
    st.session_state.show_only_positiv_expected_value = False
    st.session_state.show_only_spreads_with_no_earnings_till_expiration = False
    st.session_state.show_only_spreads_with_no_earnings_warning = False
    st.session_state.min_day_volume = 0
    st.session_state.min_open_interest = 0
    st.session_state.min_sell_iv = 0.0
    st.session_state.max_sell_iv = 999.0
    st.session_state.min_max_profit = 0.0
    st.session_state.min_iv_rank = 0
    st.session_state.min_iv_percentile = 0

selected_date = render_date_filter(
    date_query='select date from (select date from "DatesHistory" union select current_date) as sub ORDER BY date DESC',
)

# Filter with expander section
with st.expander("Configuration and Filters", expanded=True):
    # Action buttons
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        st.button("Reset to Defaults", on_click=reset_to_defaults, width="stretch")
    with btn_col2:
        st.button("Clear All Filters (Show All)", on_click=clear_all_filters, width="stretch")

    # First row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # Load expiration dates
        sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'expiration_dte_asc.sql'
        dates_df = select_timetravel_into_dataframe(date=selected_date, sql_file_path=sql_file_path)

        # Filter dates_df based on checkbox states
        filtered_dates_df = filter_by_expiration_type(
            dates_df, 
            'expiration_date', 
            st.session_state.show_monthly, 
            st.session_state.show_weekly, 
            st.session_state.show_daily
        )

        # DTE labels ("5 DTE - Friday 2026-01-16 - Monthly/Weekly/Daily")
        dte_labels = [
            (
                f"{int(row['days_to_expiration'])} DTE - "
                f"{pd.to_datetime(row['expiration_date']).strftime('%A')}  "
                f"{row['expiration_date']} - "
                f"{get_expiration_type(row['expiration_date'])}"
            )
            for _, row in filtered_dates_df.iterrows()
        ]

        if not dte_labels:
            st.warning("No expiration dates match the selected filters.")
            st.stop()

        # Selectbox with DTE labels
        selected_label = st.selectbox("Expiration Date", dte_labels, index=min(1, len(dte_labels)-1))

        # Extract selected expiration date from DTE label
        selected_index = dte_labels.index(selected_label)
        expiration_date = filtered_dates_df.iloc[selected_index]['expiration_date']
        logging.debug(f"Extracted selected expiration date: {expiration_date}")

    with col2:
        # Suggest different delta for debit
        default_delta = 0.6 if st.session_state.strategy_type == "debit" else 0.2
        delta_target = st.number_input(
            "Delta Target",
            min_value=0.0,
            max_value=1.0,
            value=default_delta,
            step=0.01,
            key="delta_target_input"
        )
        # We need to handle the session state correctly if it was already set
        st.session_state.delta_target = delta_target

    with col3:
        spread_width = st.number_input(
            "Spread Width",
            min_value=1,
            max_value=20,
            step=1,
            key="spread_width"
        )

    with col4:
        strategy_type = st.selectbox("Strategy Type", ["credit", "debit"], key="strategy_type")

    # Second row
    col5, col6, col7, col8 = st.columns(4)

    with col5:
        option_type = st.selectbox("Option Type", ["put", "call"], key="option_type")

    with col6:
        st.checkbox("Show Monthly", key="show_monthly")

    with col7:
        st.checkbox("Show Weekly", key="show_weekly")

    with col8:
        st.checkbox("Show Daily", key="show_daily")

    # Third row
    col9, col10, col11, col12 = st.columns(4)

    with col9:
        st.checkbox(
            "Show only positive expected value",
            key="show_only_positiv_expected_value"
        )

    with col10:
        st.checkbox(
            "No Earnings Till Expiration",
            key="show_only_spreads_with_no_earnings_till_expiration",
            help="Filters out spreads where an earnings date falls between today and expiration"
        )

    with col11:
        st.checkbox(
            "Earnings Warning Filter",
            key="show_only_spreads_with_no_earnings_warning",
            help="Filters out spreads with an earnings warning (earnings shortly before expiration)"
        )

    # Fourth row
    col13, col14, col15, col16 = st.columns(4)

    with col13:
        min_day_volume = st.number_input(
            "Min dayvolume",
            min_value=0,
            step=1,
            key="min_day_volume"
        )

    with col14:
        min_open_interest = st.number_input(
            "Min Open Interest",
            min_value=0,
            step=100,
            key="min_open_interest"
        )

    with col15:
        min_sell_iv = st.number_input(
            "Min sell iv",
            min_value=0.0,
            step=0.05,
            format="%.2f",
            key="min_sell_iv"
        )

    # Fifth row
    col17, col18, col19, col20 = st.columns(4)

    with col17:
        max_sell_iv = st.number_input(
            "Max sell iv",
            min_value=0.0,
            step=0.05,
            format="%.2f",
            key="max_sell_iv"
        )

    with col18:
        min_max_profit = st.number_input(
            "Min Max Profit",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            key="min_max_profit"
        )

    with col19:
        min_iv_rank = st.number_input(
            "Min iv rank",
            min_value=0,
            max_value=100,
            step=1,
            key="min_iv_rank"
        )

    with col20:
        min_iv_percentile = st.number_input(
            "Min iv percentile",
            min_value=0,
            max_value=100,
            step=1,
            key="min_iv_percentile"
        )

    st.divider()
    col_iv1, col_iv2, col_iv3 = st.columns(3)
    with col_iv1:
        iv_corr_input = st.text_input("IV Correction (auto, 0.0-1.0)", value=str(st.session_state.iv_correction), key="iv_correction_input")
        if iv_corr_input.lower() == "auto":
            st.session_state.iv_correction = "auto"
        else:
            try:
                st.session_state.iv_correction = float(iv_corr_input)
            except ValueError:
                st.error("Invalid IV Correction. Use 'auto' or a number.")
                st.session_state.iv_correction = 0.0
    with col_iv2:
        st.number_input("Risk-Free Rate %", min_value=0.0, max_value=20.0, step=0.1, format="%.1f", key="risk_free_rate")
    with col_iv3:
        st.info("IV correction mode: 'auto' (Automatic), 0.0-1.0 (Manual reduction), 0.0 (No correction)")

@st.cache_data(ttl=300)  # 5 Minuten
def _cached_select_into_dataframe(date, sql_file_path, params):
    return select_timetravel_into_dataframe(date=date, sql_file_path=sql_file_path, params=params)


@st.cache_data(ttl=300)  # 5 Minuten
def _cached_get_page_spreads(df, strategy_type, iv_correction, risk_free_rate):
    return get_page_spreads(df, strategy_type=strategy_type, iv_correction=iv_correction, risk_free_rate=risk_free_rate)


# Calculate the spread values with a loading indicator
with st.spinner("Calculating spreads..."):
    params = {
        "expiration_date": expiration_date,
        "option_type": option_type,
        "delta_target": st.session_state.delta_target,
        "min_open_interest": min_open_interest,
        "spread_width": spread_width,
        "min_day_volume": min_day_volume,
        "min_iv_rank": min_iv_rank,
        "min_iv_percentile": min_iv_percentile,
        "strategy_type": strategy_type
    }

    logging.debug(f"Params for database query: {params}")

    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'spreads_input.sql'
    df = _cached_select_into_dataframe(date=selected_date, sql_file_path=sql_file_path, params=params)
    # logging.debug(f"Input data head: {df.head()}")

    spreads_df = _cached_get_page_spreads(df, strategy_type=strategy_type, iv_correction=st.session_state.iv_correction, risk_free_rate=st.session_state.risk_free_rate / 100)
    # logging.debug(f"Calculated spreads head: {spreads_df.head()}")

# Apply spread filters
filtered_df = spreads_df.copy()
filter_log: list[tuple[str, int, list[str]]] = []  # (filter_name, removed_count, removed_symbols)

def _apply_filter(df: pd.DataFrame, mask: pd.Series, label: str) -> pd.DataFrame:
    removed = df[~mask]
    if not removed.empty:
        symbols = sorted(removed['symbol'].unique().tolist()) if 'symbol' in removed.columns else []
        filter_log.append((label, len(removed), symbols))
    return df[mask]

# Min max profit
filtered_df = _apply_filter(
    filtered_df,
    filtered_df['max_profit'] >= min_max_profit,
    f"Min Max Profit ≥ {min_max_profit}"
)

# Only positive expected value
if st.session_state.show_only_positiv_expected_value:
    filtered_df = _apply_filter(
        filtered_df,
        filtered_df['expected_value'] >= 0,
        "Positive Expected Value"
    )

# Only spreads with no earnings till expiration
today = pd.Timestamp.now().normalize()
expiration_date_ts = pd.Timestamp(expiration_date).normalize()

if st.session_state.show_only_spreads_with_no_earnings_till_expiration:
    earnings_mask = ~(
        (pd.to_datetime(filtered_df['earnings_date']).dt.normalize() >= today) &
        (pd.to_datetime(filtered_df['earnings_date']).dt.normalize() < expiration_date_ts)
    )
    filtered_df = _apply_filter(filtered_df, earnings_mask, "No Earnings Till Expiration")

# Earnings Warning Filter
if st.session_state.show_only_spreads_with_no_earnings_warning:
    if 'earnings_warning' in filtered_df.columns:
        earnings_warning_mask = (
            (filtered_df['earnings_warning'] == '') | (filtered_df['earnings_warning'].isna())
        )
        filtered_df = _apply_filter(filtered_df, earnings_warning_mask, "Earnings Warning Filter")

# Reset index to ensure the zebra style works on the dataframe
filtered_df.reset_index(drop=True, inplace=True)

# Min sell IV
filtered_df = _apply_filter(
    filtered_df,
    filtered_df['sell_iv'] >= min_sell_iv,
    f"Min Sell IV ≥ {min_sell_iv:.2f}"
)

# Max sell IV
filtered_df = _apply_filter(
    filtered_df,
    filtered_df['sell_iv'] <= max_sell_iv,
    f"Max Sell IV ≤ {max_sell_iv:.2f}"
)

# Re-reset index after all filters are applied
filtered_df.reset_index(drop=True, inplace=True)

# Format 'earnings_date' for display (do this AFTER all calculations and filtering)
filtered_df['earnings_date'] = pd.to_datetime(filtered_df['earnings_date']).dt.strftime('%d.%m.%Y')

# Pre-format columns that we want to show in details but not in the main table
# This ensures they are available in 'row' even after page_display_dataframe might have dropped them from display
# Actually page_display_dataframe creates a copy for display, so filtered_df remains intact.

total_before = len(spreads_df)
total_after = len(filtered_df)
total_removed = total_before - total_after

st.markdown(f"### {total_after} Results")

if "spreads_deepseek_result" not in st.session_state:
    st.session_state.spreads_deepseek_result = ""
if "spreads_deepseek_error" not in st.session_state:
    st.session_state.spreads_deepseek_error = ""
if "spreads_deepseek_usage" not in st.session_state:
    st.session_state.spreads_deepseek_usage = {}
if "spreads_deepseek_model" not in st.session_state:
    st.session_state.spreads_deepseek_model = DEEPSEEK_MODEL
if "spreads_deepseek_ranking_rows" not in st.session_state:
    st.session_state.spreads_deepseek_ranking_rows = []
if "spreads_deepseek_summary" not in st.session_state:
    st.session_state.spreads_deepseek_summary = ""
if "spreads_deepseek_sources_rows" not in st.session_state:
    st.session_state.spreads_deepseek_sources_rows = []
if "spreads_deepseek_article_quality_rows" not in st.session_state:
    st.session_state.spreads_deepseek_article_quality_rows = []

# Export All button - downloads all filtered spreads with full details as CSV
if not filtered_df.empty:
    export_columns = [
        'symbol', 'Company', 'close', 'option_type',
        'sell_strike', 'sell_last_option_price', 'sell_delta', 'sell_iv', 'sell_theta',
        'sell_open_interest', 'sell_day_volume', 'sell_expected_move',
        'buy_strike', 'buy_last_option_price', 'buy_delta', 'buy_iv', 'buy_theta',
        'buy_open_interest', 'buy_day_volume', 'buy_expected_move',
        'spread_width', 'max_profit', 'bpr', 'profit_to_bpr',
        'expected_value', 'APDI', 'APDI_EV',
        'iv_rank', 'iv_percentile', 'iv_correction_factor',
        'spread_theta', '%_otm', 'days_to_expiration',
        'earnings_date', 'earnings_warning',
        'company_sector', 'company_industry', 'analyst_mean_target',
    ]
    # Only include columns that actually exist in the dataframe
    available_cols = [c for c in export_columns if c in filtered_df.columns]
    export_df = filtered_df[available_cols]
    csv_data = export_df.to_csv(index=False)
    st.download_button(
        label=f"⬇️ Export All ({len(filtered_df)} trades) as CSV",
        data=csv_data,
        file_name=f"spreads_{option_type}_{spread_width}w_{expiration_date}.csv",
        mime="text/csv",
    )

if not filtered_df.empty:
    with st.expander("DeepSeek Bulk Analyse (Test)", expanded=False):
        st.caption(
            "Sendet mehrere gefilterte Spreads in einem Request an DeepSeek. "
            "Gut fuer einen ersten End-to-End Test."
        )

        max_spreads = st.number_input(
            "Anzahl Spreads fuer Analyse",
            min_value=1,
            max_value=len(filtered_df),
            value=min(25, len(filtered_df)),
            step=1,
            key="deepseek_spreads_limit",
        )
        model_name = st.text_input(
            "DeepSeek Model",
            value=st.session_state.spreads_deepseek_model,
            key="deepseek_spreads_model",
            help="Default kommt aus DEEPSEEK_MODEL in .env",
        )
        enable_live_research = st.checkbox(
            "Live News + Live Price aus dem Internet einbeziehen",
            value=True,
            key="deepseek_enable_live_research",
            help="Macht die Analyse realistischer, aber langsamer.",
        )
        deep_research_mode = st.checkbox(
            "Deep Research Mode (mehr Web-Quellen)",
            value=False,
            key="deepseek_deep_research_mode",
            help="Nutzt zusaetzlich breitere Web-News-Suche pro Symbol und mehr Marktkontext.",
        )
        include_article_content = st.checkbox(
            "Artikel-Inhalte lesen (langsamer)",
            value=False,
            key="deepseek_include_article_content",
            help="Liest den Inhalt von News-Links (nicht nur Headlines) und nutzt Auszuege im Prompt.",
        )
        headlines_per_symbol = st.number_input(
            "News pro Symbol",
            min_value=1,
            max_value=5,
            value=4 if deep_research_mode else 3,
            step=1,
            key="deepseek_headlines_per_symbol",
        )
        max_articles_per_symbol = st.number_input(
            "Artikel pro Symbol lesen",
            min_value=0,
            max_value=3,
            value=1 if include_article_content else 0,
            step=1,
            key="deepseek_max_articles_per_symbol",
            help="Mehr Artikel = mehr Laufzeit und mehr Tokens.",
        )

        if st.button("DeepSeek Analyse starten", width="stretch"):
            st.session_state.spreads_deepseek_error = ""
            st.session_state.spreads_deepseek_ranking_rows = []
            st.session_state.spreads_deepseek_summary = ""
            st.session_state.spreads_deepseek_sources_rows = []
            st.session_state.spreads_deepseek_article_quality_rows = []
            with st.spinner("DeepSeek analysiert die Spreads..."):
                try:
                    df_for_ai = filtered_df.head(int(max_spreads)).copy()
                    live_context = ""
                    if enable_live_research:
                        with st.status("Lade Live News und Preise...", expanded=False):
                            live_context, source_rows, article_quality_rows = build_live_research_bundle(
                                symbols=df_for_ai["symbol"].astype(str).tolist(),
                                max_headlines=int(headlines_per_symbol),
                                deep_research=deep_research_mode,
                                include_article_content=include_article_content,
                                max_articles_per_symbol=int(max_articles_per_symbol),
                            )
                            st.session_state.spreads_deepseek_sources_rows = source_rows
                            st.session_state.spreads_deepseek_article_quality_rows = article_quality_rows

                    prompt = build_bulk_spreads_prompt(
                        df_for_ai,
                        selected_date=selected_date,
                        expiration_date=expiration_date,
                        strategy_type=strategy_type,
                        option_type=option_type,
                        live_research_context=live_context,
                    )
                    system_prompt = (
                        "Du bist ein institutioneller Aktien- und Optionsanalyst. "
                        "Arbeite strukturiert, benenne Unsicherheiten klar und gib konkrete Handlungsentscheidungen."
                    )

                    response = LLMClient().chat_completion(
                        provider="deepseek",
                        system_prompt=system_prompt,
                        user_prompt=prompt,
                        model=model_name.strip() or DEEPSEEK_MODEL,
                        temperature=0.15,
                        max_tokens=7000,
                    )

                    st.session_state.spreads_deepseek_result = response.text
                    st.session_state.spreads_deepseek_usage = response.usage
                    st.session_state.spreads_deepseek_model = response.model

                    ranking_df, overall_summary = parse_spreads_ranking_table(response.text)
                    st.session_state.spreads_deepseek_ranking_rows = ranking_df.to_dict(orient="records")
                    st.session_state.spreads_deepseek_summary = overall_summary
                except LLMProviderError as exc:
                    st.session_state.spreads_deepseek_error = str(exc)

        if st.session_state.spreads_deepseek_error:
            st.error(st.session_state.spreads_deepseek_error)

        if st.session_state.spreads_deepseek_result:
            usage = st.session_state.spreads_deepseek_usage or {}
            prompt_tokens = usage.get("prompt_tokens", "N/A")
            completion_tokens = usage.get("completion_tokens", "N/A")
            total_tokens = usage.get("total_tokens", "N/A")
            st.info(
                f"Model: {st.session_state.spreads_deepseek_model} | "
                f"Prompt Tokens: {prompt_tokens} | "
                f"Completion Tokens: {completion_tokens} | "
                f"Total: {total_tokens}"
            )

            cost = estimate_deepseek_cost(
                usage=usage,
                model=str(st.session_state.spreads_deepseek_model or ""),
            )
            st.caption(
                "Kosten (geschaetzt): "
                f"Cache-Hit ${cost['cost_cache_hit_usd']:.6f} | "
                f"Cache-Miss ${cost['cost_cache_miss_usd']:.6f}"
            )

            if st.session_state.spreads_deepseek_summary:
                st.markdown("#### Kurzfazit")
                st.write(st.session_state.spreads_deepseek_summary)

            if enable_live_research:
                mode_text = "Deep" if deep_research_mode else "Light"
                st.caption(f"Research Mode: {mode_text}")

            ranking_rows = st.session_state.spreads_deepseek_ranking_rows or []
            if ranking_rows:
                st.markdown("#### Ranking")
                ranking_df = pd.DataFrame(ranking_rows)
                st.dataframe(ranking_df, hide_index=True, width="stretch")
            else:
                st.warning("Die DeepSeek-Antwort konnte nicht als Ranking-Tabelle geparst werden.")

            source_rows = st.session_state.spreads_deepseek_sources_rows or []
            if source_rows:
                st.markdown("#### Quellen-Transparenz je Symbol")
                quality_rows = st.session_state.spreads_deepseek_article_quality_rows or []
                if quality_rows:
                    st.caption("Artikel-Lesequalitaet je Symbol")
                    quality_df = pd.DataFrame(quality_rows)
                    st.dataframe(quality_df, hide_index=True, width="stretch")
                with st.expander(f"Verwendete Quellen anzeigen ({len(source_rows)})", expanded=False):
                    sources_df = pd.DataFrame(source_rows)
                    st.dataframe(
                        sources_df,
                        hide_index=True,
                        width="stretch",
                        column_config={
                            "URL": st.column_config.LinkColumn(
                                "URL",
                                help="Originalquelle",
                                display_text="Open",
                            )
                        },
                    )

            with st.expander("Rohantwort (optional)", expanded=False):
                st.markdown(st.session_state.spreads_deepseek_result)

# Optionstrat URL configuration
column_config = {
    "optionstrat_url": st.column_config.LinkColumn(
        label="",
        help="OptionStrat",
        display_text="🎯",
    )
}

# Display final dataframe
event = page_display_dataframe(
    filtered_df, 
    page='spreads', 
    symbol_column='symbol', 
    column_config=column_config,
    on_select="rerun",
    selection_mode="single-row"
)

# Leg Details View
if not filtered_df.empty:
    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows:
        selected_idx = selected_rows[0]
        row = filtered_df.iloc[selected_idx]

        st.divider()
        
        is_credit = strategy_type == "credit"
        
        legs = [
            OptionLeg(
                strike=row['sell_strike'], premium=row['sell_last_option_price'],
                is_call=row['option_type'] == 'call', is_long=not is_credit,
                delta=row.get('sell_delta'), iv=row.get('sell_iv'),
                theta=row.get('sell_theta'), oi=row.get('sell_open_interest'),
                volume=row.get('sell_day_volume'), expected_move=row.get('sell_expected_move'),
                last_updated_massive=row.get('sell_last_updated'),
                last_updated_option_data=row.get('last_updated_option_data'),
                last_updated_stock_data=row.get('last_updated_stock_data'),
                bs_price=row.get('sell_bs_price')
            ),
            OptionLeg(
                strike=row['buy_strike'], premium=row['buy_last_option_price'],
                is_call=row['option_type'] == 'call', is_long=is_credit,
                delta=row.get('buy_delta'), iv=row.get('buy_iv'),
                theta=row.get('buy_theta'), oi=row.get('buy_open_interest'),
                volume=row.get('buy_day_volume'), expected_move=row.get('buy_expected_move'),
                last_updated_massive=row.get('buy_last_updated'),
                last_updated_option_data=row.get('last_updated_option_data'),
                last_updated_stock_data=row.get('last_updated_stock_data'),
                bs_price=row.get('buy_bs_price')
            )
        ]

        metrics = StrategyMetrics(
            max_profit=row['max_profit'],
            max_loss=row['max_loss'] if 'max_loss' in row else row['bpr'],
            bpr=row['bpr'],
            expected_value=row['expected_value'],
            total_theta=row.get('spread_theta', 0),
            profit_to_bpr=row.get('profit_to_bpr', 0),
            apdi=row.get('APDI', 0),
            apdi_ev=row.get('APDI_EV', 0),
            iv_correction_factor=row.get('iv_correction_factor', 1),
            corrected_volatility=row.get('corrected_volatility', row.get('sell_iv', 0))
        )

        extra_info = {
            'iv_rank': row.get('iv_rank'),
            'iv_percentile': row.get('iv_percentile'),
            'company_sector': row.get('company_sector'),
            'company_industry': row.get('company_industry'),
            'analyst_mean_target': row.get('analyst_mean_target'),
            'close': row.get('close'),
            'optionstrat_url': row.get('optionstrat_url'),
            'Claude': _create_claude_prompt_page_spreads(row)
        }

        display_strategy_details(row['symbol'], row.get('Company', 'N/A'), legs, metrics, extra_info)
        display_spreads_backtesting(selected_date, row)
    else:
        st.caption("💡 Klicke auf eine Zeile in der Tabelle, um die Details der einzelnen Legs zu sehen.")

if filter_log:
    _total_removed_syms = sum(len(syms) for _, _, syms in filter_log)
    with st.expander(f"Filter Log — {total_removed} removed ({_total_removed_syms} symbols)", expanded=False):
        for filter_name, removed_count, symbols in filter_log:
            st.markdown(f"**{filter_name}** — {removed_count} spreads removed")
            if symbols:
                st.caption(", ".join(symbols))

# Show documentation
with st.expander("📖 Documentation - Fields Overview", expanded=False):
    st.markdown(get_spreads_documentation())