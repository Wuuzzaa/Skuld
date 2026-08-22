import logging
import os
import streamlit as st
import pandas as pd
from config import (
    PATH_DATABASE_QUERY_FOLDER,
    IV_CORRECTION_MODE,
    RISK_FREE_RATE,
)
from pages.backtesting.spreads_backtesting import display_spreads_backtesting
from pages.documentation_text.spreads_page_doc import get_spreads_documentation
from src.historization import select_timetravel_into_dataframe
from src.database import select_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe, _create_claude_prompt_page_spreads
from src.spreads_calculation import get_page_spreads_enhanced
from src.streamlit_helpers import render_date_filter
from src.utils.option_utils import get_expiration_type
from src.ui_utils import init_session_state, reset_to_defaults as ui_reset, filter_by_expiration_type
from src.ui_strategy_display import display_strategy_details
from src.options_utils import OptionLeg, StrategyMetrics

# Ensure logfile gets all columns of wide dataframes
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

# Setup logging
setup_logging(component="streamlit", sub_component="spreads_enhanced", log_level=logging.DEBUG, console_output=True)
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
DEFAULT_MAX_RISK = 1000.0  # $ pro Trade; Breite = floor(max_risk / (100 = shares_per_contract))
CONTRACT_MULTIPLIER = 100   # shares_per_contract ist in dieser DB ueberall 100 (Aktien, ETFs, Indizes)
DEFAULT_DELTA_CANDIDATES = 3
DEFAULT_DTE_MIN = 21
DEFAULT_DTE_MAX = 60
DTE_SLIDER_MAX = 90  # feste Obergrenze der DTE-Skala (Termine darueber werden ignoriert)
DEFAULT_OPTION_TYPE = "put"
DEFAULT_MIN_DAY_VOLUME = 20
DEFAULT_MIN_OPEN_INTEREST = 100
DEFAULT_MIN_SELL_IV = 0.3
DEFAULT_MAX_SELL_IV = 0.9
DEFAULT_MIN_MAX_PROFIT = 80.0
DEFAULT_MIN_IV_RANK = 40
DEFAULT_MIN_IV_PERCENTILE = 0
DEFAULT_STRATEGY_TYPE = "credit"
DEFAULT_MIN_TECH_SCORE = 0  # 0 = kein Filter (Score 0-6, richtungsabhaengig)
DEFAULT_SCORE_STYLE = "trend"  # trend (Schule A) | dip (Schule B)
DEFAULT_BORING_ONLY = False  # "Langweilige Aktien" Filter (low-vol, stabile Large-Caps)
DEFAULT_RSI_RANGE = (0, 100)   # aus = ganze Range (filtert nichts)
DEFAULT_STOCH_RANGE = (0, 100)  # aus = ganze Range (filtert nichts)
DEFAULT_ASSET_TYPE = "all"  # all | stock | etf | index
SCORE_STYLE_LABELS = {
    "trend": "Trend / Stärke (nicht überverkauft)",
    "dip": "Dip / Rücksetzer (überverkauft)",
}
ASSET_TYPE_LABELS = {
    "all": "Alle",
    "stock": "Nur Aktien",
    "etf": "Nur ETFs",
    "index": "Nur Indizes (I:...)",
}

# Page header
st.title("Spreads Enhanced")
st.caption(
    "Wie die Spreads-Seite, aber testet pro Symbol mehrere Sell-Strikes am Delta-Ziel "
    "(Delta-Kandidaten) statt nur den einen naechsten. So fallen Symbole nicht mehr raus, "
    "nur weil ihr delta-naechster Strike zufaellig keinen Buy-Partner im Breiten-Fenster hat. "
    "Pro Symbol wird der Kandidat mit dem Delta am naechsten am Ziel angezeigt."
)

# Default values mapping for UI utils (own keys, damit die Original-Spreads-Seite unberuehrt bleibt)
DEFAULTS = {
    'enh_show_monthly': DEFAULT_SHOW_MONTHLY,
    'enh_show_weekly': DEFAULT_SHOW_WEEKLY,
    'enh_show_daily': DEFAULT_SHOW_DAILY,
    'enh_show_only_positiv_expected_value': DEFAULT_SHOW_ONLY_POSITIV_EXPECTED_VALUE,
    'enh_show_only_spreads_with_no_earnings_till_expiration': DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_TILL_EXPIRATION,
    'enh_show_only_spreads_with_no_earnings_warning': DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_WARNING,
    'enh_delta_target': DEFAULT_DELTA_TARGET,
    'enh_max_risk': DEFAULT_MAX_RISK,
    'enh_spread_exact': False,
    'enh_delta_candidates': DEFAULT_DELTA_CANDIDATES,
    'enh_dte_min': DEFAULT_DTE_MIN,
    'enh_dte_max': DEFAULT_DTE_MAX,
    'enh_asset_type': DEFAULT_ASSET_TYPE,
    'enh_sectors': [],  # leer = alle Sektoren
    'enh_option_type': DEFAULT_OPTION_TYPE,
    'enh_min_day_volume': DEFAULT_MIN_DAY_VOLUME,
    'enh_min_open_interest': DEFAULT_MIN_OPEN_INTEREST,
    'enh_min_sell_iv': DEFAULT_MIN_SELL_IV,
    'enh_max_sell_iv': DEFAULT_MAX_SELL_IV,
    'enh_min_max_profit': DEFAULT_MIN_MAX_PROFIT,
    'enh_min_iv_rank': DEFAULT_MIN_IV_RANK,
    'enh_min_iv_percentile': DEFAULT_MIN_IV_PERCENTILE,
    'enh_strategy_type': DEFAULT_STRATEGY_TYPE,
    'enh_min_tech_score': DEFAULT_MIN_TECH_SCORE,
    'enh_score_style': DEFAULT_SCORE_STYLE,
    'enh_boring_only': DEFAULT_BORING_ONLY,
    'enh_rsi_range': DEFAULT_RSI_RANGE,
    'enh_stoch_range': DEFAULT_STOCH_RANGE,
    'enh_iv_correction': IV_CORRECTION_MODE,
    'enh_risk_free_rate': RISK_FREE_RATE * 100,
}

init_session_state(DEFAULTS)


def reset_to_defaults():
    ui_reset(DEFAULTS)


def clear_all_filters():
    """Clears all filters to show all possible results."""
    st.session_state.enh_show_monthly = True
    st.session_state.enh_show_weekly = True
    st.session_state.enh_show_daily = True
    st.session_state.enh_show_only_positiv_expected_value = False
    st.session_state.enh_show_only_spreads_with_no_earnings_till_expiration = False
    st.session_state.enh_show_only_spreads_with_no_earnings_warning = False
    st.session_state.enh_min_day_volume = 0
    st.session_state.enh_min_open_interest = 0
    st.session_state.enh_min_sell_iv = 0.0
    st.session_state.enh_max_sell_iv = 999.0
    st.session_state.enh_min_max_profit = 0.0
    st.session_state.enh_min_iv_rank = 0
    st.session_state.enh_min_iv_percentile = 0
    st.session_state.enh_asset_type = "all"
    st.session_state.enh_sectors = []
    st.session_state.enh_min_tech_score = 0
    st.session_state.enh_score_style = "trend"
    st.session_state.enh_boring_only = False
    st.session_state.enh_rsi_range = (0, 100)
    st.session_state.enh_stoch_range = (0, 100)


def _on_asset_type_change():
    """Wenn auf 'Nur Indizes' gewechselt wird, sinnvolle Index-Defaults setzen.

    Index-Optionen (I:SPX, I:RUT ...) haben ein grobes Strike-Raster und niedrigere IV
    als Einzelaktien. Mit den Aktien-Defaults (Min IV 0.30, exakte Breite) kommt fast
    nichts durch. Multiplier ist ueberall 100 -> Max Risiko 1000$ = bis 10 Punkte Breite.
    """
    if st.session_state.enh_asset_type == "index":
        st.session_state.enh_min_sell_iv = 0.0
        st.session_state.enh_max_risk = 1000.0   # -> Breite bis 10 Punkte
        st.session_state.enh_spread_exact = False
        st.session_state.enh_delta_candidates = 5
        # Indizes haben keine Earnings -> Earnings-Filter stoeren nur
        st.session_state.enh_show_only_spreads_with_no_earnings_till_expiration = False
        st.session_state.enh_show_only_spreads_with_no_earnings_warning = False


selected_date = render_date_filter(
    date_query='select date from (select date from "DatesHistory" union select current_date) as sub ORDER BY date DESC',
)

# Filter with expander section
with st.expander("Configuration and Filters", expanded=True):
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        st.button("Reset to Defaults", on_click=reset_to_defaults, width="stretch")
    with btn_col2:
        st.button("Clear All Filters (Show All)", on_click=clear_all_filters, width="stretch")

    # First row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'expiration_dte_asc.sql'
        dates_df = select_timetravel_into_dataframe(date=selected_date, sql_file_path=sql_file_path)

        filtered_dates_df = filter_by_expiration_type(
            dates_df,
            'expiration_date',
            st.session_state.enh_show_monthly,
            st.session_state.enh_show_weekly,
            st.session_state.enh_show_daily
        )

        # DTE-Range statt Einzeldatum: min/max Tage bis Verfall.
        # Skala fest auf DTE_SLIDER_MAX gedeckelt (sonst reicht sie bis zum entferntesten
        # Index-Termin, z.B. I:SPX bis 2031 -> unbrauchbare Skala).
        _dte_default = (
            int(min(st.session_state.enh_dte_min, DTE_SLIDER_MAX)),
            int(min(st.session_state.enh_dte_max, DTE_SLIDER_MAX)),
        )
        dte_lo, dte_hi = st.slider(
            "DTE-Bereich (Tage bis Verfall)",
            min_value=0,
            max_value=DTE_SLIDER_MAX,
            value=_dte_default,
            step=1,
            key="enh_dte_range",
            help="Zeigt alle Verfallstermine in diesem Tagebereich (kombiniert mit Monthly/Weekly/Daily).",
        )
        st.session_state.enh_dte_min, st.session_state.enh_dte_max = dte_lo, dte_hi

        # Alle Termine im DTE-Fenster (Monthly/Weekly/Daily bereits angewandt)
        range_dates_df = filtered_dates_df[
            (filtered_dates_df['days_to_expiration'] >= dte_lo) &
            (filtered_dates_df['days_to_expiration'] <= dte_hi)
        ]
        expiration_dates = range_dates_df['expiration_date'].tolist()

        if not expiration_dates:
            st.warning(
                "Keine Verfallstermine im gewaehlten DTE-Bereich. "
                "Bereich erweitern oder Monthly/Weekly/Daily anpassen."
            )
            st.stop()

        # Fuer Anzeige/Earnings-Logik: kleinstes Datum als Referenz
        expiration_date = expiration_dates[0]
        st.caption(f"{len(expiration_dates)} Verfallstermin(e) im Bereich {dte_lo}–{dte_hi} DTE")
        logging.debug(f"DTE range {dte_lo}-{dte_hi} -> {len(expiration_dates)} dates")

    with col2:
        default_delta = 0.6 if st.session_state.enh_strategy_type == "debit" else 0.2
        delta_target = st.number_input(
            "Delta Target",
            min_value=0.0,
            max_value=1.0,
            value=default_delta,
            step=0.01,
            key="enh_delta_target_input"
        )
        st.session_state.enh_delta_target = delta_target

    with col3:
        max_risk = st.number_input(
            "Max Risiko / Trade ($)",
            min_value=100.0,
            max_value=20000.0,
            step=100.0,
            format="%.0f",
            key="enh_max_risk",
            help=(
                "Maximales Verlustrisiko pro Trade (worst case = Breite × 100). "
                "1000$ = bis 10 Punkte/Dollar Spread-Breite. Gilt fuer Aktien, ETFs und "
                "Indizes gleich (Multiplier ist ueberall 100). Bei Indizes sind 10 = 10 Punkte."
            ),
        )
        # Breite aus Risiko ableiten: 1 Punkt/Dollar Breite = 100$ Risiko (Multiplier 100)
        spread_width = max(1, int(max_risk // CONTRACT_MULTIPLIER))
        st.caption(f"→ max. Breite {spread_width} (= {spread_width * CONTRACT_MULTIPLIER}$ worst case)")
        spread_exact = st.checkbox(
            "Nur exakt diese Breite",
            key="enh_spread_exact",
            help="Aktiviert: nur Spreads mit genau der abgeleiteten Breite. Deaktiviert: alle Breiten von 1 bis Max.",
        )

    with col4:
        strategy_type = st.selectbox("Strategy Type", ["credit", "debit"], key="enh_strategy_type")

    # Second row
    col5, col6, col7, col8 = st.columns(4)

    with col5:
        option_type = st.selectbox("Option Type", ["put", "call"], key="enh_option_type")

    with col6:
        delta_candidates = st.number_input(
            "Delta-Kandidaten",
            min_value=1,
            max_value=10,
            step=1,
            key="enh_delta_candidates",
            help=(
                "Wie viele Sell-Strikes rund um das Delta-Ziel getestet werden. "
                "1 = wie die klassische Spreads-Seite. Hoehere Werte finden mehr Symbole, "
                "deren delta-naechster Strike keinen Buy-Partner hat."
            ),
        )

    with col7:
        st.checkbox("Show Monthly", key="enh_show_monthly")

    with col8:
        st.checkbox("Show Weekly", key="enh_show_weekly")

    # Third row
    col9, col10, col11, col12 = st.columns(4)

    with col9:
        st.checkbox("Show Daily", key="enh_show_daily")

    with col10:
        st.checkbox(
            "Show only positive expected value",
            key="enh_show_only_positiv_expected_value"
        )

    with col11:
        st.checkbox(
            "No Earnings Till Expiration",
            key="enh_show_only_spreads_with_no_earnings_till_expiration",
            help="Filters out spreads where an earnings date falls between today and expiration"
        )

    with col12:
        st.checkbox(
            "Earnings Warning Filter",
            key="enh_show_only_spreads_with_no_earnings_warning",
            help="Filters out spreads with an earnings warning (earnings shortly before expiration)"
        )

    # Fourth row
    col13, col14, col15, col16 = st.columns(4)

    with col13:
        min_day_volume = st.number_input("Min dayvolume", min_value=0, step=1, key="enh_min_day_volume")

    with col14:
        min_open_interest = st.number_input("Min Open Interest", min_value=0, step=100, key="enh_min_open_interest")

    with col15:
        min_sell_iv = st.number_input("Min sell iv", min_value=0.0, step=0.05, format="%.2f", key="enh_min_sell_iv")

    with col16:
        max_sell_iv = st.number_input("Max sell iv", min_value=0.0, step=0.05, format="%.2f", key="enh_max_sell_iv")

    # Fifth row
    col17, col18, col19, col20 = st.columns(4)

    with col17:
        min_max_profit = st.number_input("Min Max Profit", min_value=0.0, step=1.0, format="%.2f", key="enh_min_max_profit")

    with col18:
        min_iv_rank = st.number_input("Min iv rank", min_value=0, max_value=100, step=1, key="enh_min_iv_rank")

    with col19:
        min_iv_percentile = st.number_input("Min iv percentile", min_value=0, max_value=100, step=1, key="enh_min_iv_percentile")

    with col20:
        # Richtung des Scores aus Option-Typ ableiten:
        #   put  -> Bull Put Spread  -> bullish/neutrales Timing gesucht
        #   call -> Bear Call Spread -> bearish/neutrales Timing gesucht
        _score_dir = "bull" if st.session_state.get("enh_option_type", "put") == "put" else "bear"
        _score_label = "Bull-Put" if _score_dir == "bull" else "Bear-Call"
        min_tech_score = st.number_input(
            f"Min {_score_label}-Score (0=aus)",
            min_value=0,
            max_value=6,
            step=1,
            key="enh_min_tech_score",
            help=(
                f"Filtert nach Anzahl erfüllter technischer Timing-Kriterien (0–6) für ein "
                f"{_score_label}-Setup. Richtung folgt automatisch dem Option-Typ "
                f"(Put=bullish, Call=bearish). Stil (Trend vs. Dip) siehe Schalter daneben. "
                f"Kriterien-Details im Doku-Expander unten. Empfehlung: 3–4 als solides Setup. 0 = kein Filter."
            ),
        )
        st.radio(
            "Score-Stil",
            options=list(SCORE_STYLE_LABELS.keys()),
            format_func=lambda k: SCORE_STYLE_LABELS[k],
            key="enh_score_style",
            help=(
                "Trend/Stärke (Default): Aktie stabil im Trend, NICHT überverkauft — "
                "kein fallendes Messer fangen, ruhige Prämie. "
                "Dip/Rücksetzer: in den überverkauften Rücksetzer verkaufen — höhere Prämie, "
                "aber mehr Risiko. Ändert nur die Score-Kriterien, nicht die Richtung."
            ),
        )
        with st.expander("Was bedeuten die Indikatoren? (Kriterien-Erklärung)"):
            st.markdown("""
Der Score zählt 0–6 erfüllte Timing-Kriterien. **Richtung** folgt dem Option-Typ:
**Put → Bull Put** (bullish), **Call → Bear Call** (bearish, exakt gespiegelt).

**Trend/Stärke (Default, für Prämienverkäufer empfohlen):**

| Kriterium | Bull Put (Put) | Bear Call (Call) | Warum |
|---|---|---|---|
| Kurs vs EMA200 | über | unter | Übergeordneter Trend |
| Kurs vs EMA50 | über | unter | Mittelfristiger Trend intakt |
| RSI 14 | 45–70 | 30–55 | Trendstärke, aber **nicht im Extrem** (>70 überkauft / <30 überverkauft) |
| Stochastic %K | 20–80 | 20–80 | Gesundes Mittelfeld — weder über- noch unterkauft |
| ADX + DI | ADX>18, +DI>−DI | ADX>18, −DI>+DI | Trend hat Substanz **und** zeigt in die richtige Richtung |
| MACD-Histogramm | > 0 | < 0 | Momentum bestätigt die Richtung |

Ziel: Aktie läuft **ruhig im Trend**, ist aber **nicht heißgelaufen** (kein Rücksetzer-Risiko
in der Laufzeit) und **kein fallendes Messer**.

**Dip/Rücksetzer (aggressiver):** verkauft in überverkaufte Schwäche (Bull: RSI 30–45,
Stoch < 20) — höhere Prämie durch erhöhte IV, aber Timing-Risiko wenn der Fall weitergeht.

*RSI-Fenster nach Cardwell "range shift": ein Aufwärtstrend trägt RSI ~40–80, ein
Abwärtstrend ~20–60. Quelle: RSI/Stochastic/ADX/MACD-Grundlagen (Wikipedia).*
""")
        st.markdown("**Direkte Indikator-Filter** (0–100 = aus)")
        st.slider(
            "RSI 14 Bereich",
            min_value=0, max_value=100, step=1,
            key="enh_rsi_range",
            help="Zeigt nur Aktien mit RSI in diesem Bereich. Standard 0–100 = aus. "
                 "Für 'nicht überverkauft' z.B. 40–70 setzen (blendet RSI<40 und >70 aus).",
        )
        st.slider(
            "Stochastic %K Bereich",
            min_value=0, max_value=100, step=1,
            key="enh_stoch_range",
            help="Zeigt nur Aktien mit Stochastik %K in diesem Bereich. Standard 0–100 = aus. "
                 "Für 'nicht überverkauft/überkauft' z.B. 20–80 setzen.",
        )

    st.divider()
    col_iv1, col_iv2, col_iv3 = st.columns(3)
    with col_iv1:
        iv_corr_input = st.text_input("IV Correction (auto, 0.0-1.0)", value=str(st.session_state.enh_iv_correction), key="enh_iv_correction_input")
        if iv_corr_input.lower() == "auto":
            st.session_state.enh_iv_correction = "auto"
        else:
            try:
                st.session_state.enh_iv_correction = float(iv_corr_input)
            except ValueError:
                st.error("Invalid IV Correction. Use 'auto' or a number.")
                st.session_state.enh_iv_correction = 0.0
    with col_iv2:
        st.number_input("Risk-Free Rate %", min_value=0.0, max_value=20.0, step=0.1, format="%.1f", key="enh_risk_free_rate")
    with col_iv3:
        st.info("IV correction mode: 'auto' (Automatic), 0.0-1.0 (Manual reduction), 0.0 (No correction)")

    st.divider()
    col_at1, col_at2 = st.columns([1, 2])
    with col_at1:
        asset_type_key = st.radio(
            "Asset-Typ",
            options=list(ASSET_TYPE_LABELS.keys()),
            format_func=lambda k: ASSET_TYPE_LABELS[k],
            key="enh_asset_type",
            horizontal=False,
            on_change=_on_asset_type_change,
            help=(
                "Aktien = mit Sektor-Fundamentaldaten. ETFs = ohne Fundamentaldaten (z.B. SPY, QQQ). "
                "Indizes = Symbol beginnt mit 'I:' (z.B. I:SPX, I:RUT). "
                "Bei 'Nur Indizes' werden automatisch passende Defaults gesetzt (Min IV 0, Breite bis 10, Delta-Kandidaten 5)."
            ),
        )
        st.checkbox(
            "Nur langweilige Aktien",
            key="enh_boring_only",
            help=(
                "Zeigt nur stabile, träge Large-Caps (Coca-Cola/Pepsi-Typ): "
                "niedriges Beta (≤ 1.0), moderate IV (sell IV ≤ 40%), große Marktkapitalisierung "
                "(≥ $20 Mrd) und defensive/nicht-zyklische Sektoren. "
                "Ideal für ruhige, planbare Prämie ohne Kurssprünge. Greift nur bei Aktien."
            ),
        )
    with col_at2:
        # Sektor-Liste dynamisch laden (nur relevant fuer Aktien)
        try:
            _sectors_df = select_into_dataframe(
                query='SELECT DISTINCT company_sector AS sector FROM "FundamentalData" '
                      "WHERE company_sector IS NOT NULL AND company_sector <> '' ORDER BY company_sector"
            )
            _sector_options = _sectors_df["sector"].dropna().tolist()
        except Exception as exc:  # pragma: no cover - defensive
            logging.warning(f"Konnte Sektorliste nicht laden: {exc}")
            _sector_options = []
        selected_sectors = st.multiselect(
            "Sektoren (leer = alle)",
            options=_sector_options,
            key="enh_sectors",
            help=(
                "Filtert nach Sektor. Leer lassen = alle Sektoren. "
                "Um z.B. Tech auszuschliessen: alle ausser 'Technology' waehlen. "
                "Greift nur bei Aktien (ETFs/Indizes haben keinen Sektor)."
            ),
        )


@st.cache_data(ttl=300)  # 5 Minuten
def _cached_select_into_dataframe(date, sql_file_path, params):
    return select_timetravel_into_dataframe(date=date, sql_file_path=sql_file_path, params=params)


@st.cache_data(ttl=300)  # 5 Minuten
def _cached_select_multidate(date, query, params):
    return select_timetravel_into_dataframe(date=date, query=query, params=params)


@st.cache_data(ttl=300)  # 5 Minuten
def _cached_get_page_spreads_enhanced(cache_key: str, df, strategy_type, iv_correction, risk_free_rate, delta_target):
    return get_page_spreads_enhanced(
        df, strategy_type=strategy_type, iv_correction=iv_correction,
        risk_free_rate=risk_free_rate, delta_target=delta_target,
    )


# Calculate the spread values with a loading indicator
with st.spinner("Calculating spreads..."):
    spread_exact = st.session_state.get("enh_spread_exact", False)

    # Eine Query ueber ALLE Termine im DTE-Range via IN-Liste (:d0, :d1, ...).
    # Vermeidet N DB-Runden und PG-Array-Binding. exp-Filter greift frueh in der CTE.
    exp_placeholders = ", ".join(f":d{i}" for i in range(len(expiration_dates)))
    date_params = {f"d{i}": d for i, d in enumerate(expiration_dates)}

    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'spreads_enhanced_multidate_input.sql'
    with open(sql_file_path, 'r') as _f:
        multidate_sql = _f.read().replace("__EXP_LIST__", exp_placeholders)

    params = {
        "option_type": option_type,
        "delta_target": st.session_state.enh_delta_target,
        "delta_candidates": int(delta_candidates),
        "min_open_interest": min_open_interest,
        "spread_width": spread_width,
        "spread_width_min": spread_width if spread_exact else 1,
        "min_day_volume": min_day_volume,
        "min_iv_rank": min_iv_rank,
        "min_iv_percentile": min_iv_percentile,
        "strategy_type": strategy_type,
        "asset_type": st.session_state.enh_asset_type,
        "score_direction": "bull" if option_type == "put" else "bear",
        "score_style": st.session_state.enh_score_style,
        **date_params,
    }

    df = _cached_select_multidate(date=selected_date, query=multidate_sql, params=params)

    cache_key = (
        f"{selected_date}|{','.join(str(d) for d in expiration_dates)}|{option_type}|{st.session_state.enh_delta_target}|"
        f"{delta_candidates}|{min_open_interest}|{spread_width}|{spread_exact}|{min_day_volume}|"
        f"{min_iv_rank}|{min_iv_percentile}|{strategy_type}|{st.session_state.enh_iv_correction}|"
        f"{st.session_state.enh_risk_free_rate}|{st.session_state.enh_asset_type}|"
        f"{'bull' if option_type == 'put' else 'bear'}|{st.session_state.enh_score_style}"
    )

    logging.debug(f"Loaded {len(df)} rows from DB across {len(expiration_dates)} date(s) in one query")

    spreads_df = _cached_get_page_spreads_enhanced(
        cache_key, df,
        strategy_type=strategy_type,
        iv_correction=st.session_state.enh_iv_correction,
        risk_free_rate=st.session_state.enh_risk_free_rate / 100,
        delta_target=st.session_state.enh_delta_target,
    )

# Apply spread filters
filtered_df = spreads_df.copy()
filter_log: list[tuple[str, int, list[str]]] = []

if filtered_df.empty:
    st.warning("No spreads found for the selected filters. Try a different expiration date or relax the filters.")
    st.stop()


def _apply_filter(df: pd.DataFrame, mask: pd.Series, label: str) -> pd.DataFrame:
    removed = df[~mask]
    if not removed.empty:
        symbols = sorted(removed['symbol'].unique().tolist()) if 'symbol' in removed.columns else []
        filter_log.append((label, len(removed), symbols))
    return df[mask]


# Min max profit
filtered_df = _apply_filter(filtered_df, filtered_df['max_profit'] >= min_max_profit, f"Min Max Profit ≥ {min_max_profit}")

# Only positive expected value
if st.session_state.enh_show_only_positiv_expected_value:
    filtered_df = _apply_filter(filtered_df, filtered_df['expected_value'] >= 0, "Positive Expected Value")

# Only spreads with no earnings till expiration
today = pd.Timestamp.now().normalize()

if st.session_state.enh_show_only_spreads_with_no_earnings_till_expiration:
    # Zeilenweise gegen die jeweilige expiration_date der Zeile (DTE-Range = mehrere Termine)
    _exp = pd.to_datetime(filtered_df['expiration_date']).dt.normalize()
    _earn = pd.to_datetime(filtered_df['earnings_date']).dt.normalize()
    earnings_mask = ~((_earn >= today) & (_earn < _exp))
    filtered_df = _apply_filter(filtered_df, earnings_mask, "No Earnings Till Expiration")

# Earnings Warning Filter
if st.session_state.enh_show_only_spreads_with_no_earnings_warning:
    if 'earnings_warning' in filtered_df.columns:
        earnings_warning_mask = (
            (filtered_df['earnings_warning'] == '') | (filtered_df['earnings_warning'].isna())
        )
        filtered_df = _apply_filter(filtered_df, earnings_warning_mask, "Earnings Warning Filter")

filtered_df.reset_index(drop=True, inplace=True)

# Min sell IV
filtered_df = _apply_filter(filtered_df, filtered_df['sell_iv'] >= min_sell_iv, f"Min Sell IV ≥ {min_sell_iv:.2f}")

# Max sell IV
filtered_df = _apply_filter(filtered_df, filtered_df['sell_iv'] <= max_sell_iv, f"Max Sell IV ≤ {max_sell_iv:.2f}")

# Sektor-Filter (leer = alle). Greift nur bei Aktien mit Sektor; ETFs/Indizes haben keinen.
selected_sectors = st.session_state.get("enh_sectors", []) or []
if selected_sectors and 'company_sector' in filtered_df.columns:
    filtered_df = _apply_filter(
        filtered_df,
        filtered_df['company_sector'].isin(selected_sectors),
        f"Sektor in {', '.join(selected_sectors)}",
    )

# Min Tech-Score Filter (richtungsabhaengig, 0-6)
min_tech_score = st.session_state.get("enh_min_tech_score", 0)
_score_dir = "bull" if option_type == "put" else "bear"
_score_label = "Bull-Put" if _score_dir == "bull" else "Bear-Call"
if min_tech_score > 0 and 'tech_score' in filtered_df.columns:
    filtered_df = _apply_filter(
        filtered_df,
        filtered_df['tech_score'] >= min_tech_score,
        f"{_score_label}-Score ≥ {min_tech_score}/6",
    )

# Direkte Indikator-Filter: RSI + Stochastik-Bereich (0-100 = aus).
# Ermoeglicht z.B. "nicht ueberverkauft" -> RSI 40-70, Stoch 20-80.
_rsi_lo, _rsi_hi = st.session_state.get("enh_rsi_range", (0, 100))
if (_rsi_lo > 0 or _rsi_hi < 100) and 'RSI_14' in filtered_df.columns:
    _rsi = pd.to_numeric(filtered_df['RSI_14'], errors='coerce')
    # NaN (kein Indikator vorhanden) durchlassen statt fälschlich rausfiltern
    rsi_mask = _rsi.isna() | ((_rsi >= _rsi_lo) & (_rsi <= _rsi_hi))
    filtered_df = _apply_filter(filtered_df, rsi_mask, f"RSI 14 in [{_rsi_lo}, {_rsi_hi}]")

_stoch_lo, _stoch_hi = st.session_state.get("enh_stoch_range", (0, 100))
if (_stoch_lo > 0 or _stoch_hi < 100) and 'STOCHk_14_3_1' in filtered_df.columns:
    _stoch = pd.to_numeric(filtered_df['STOCHk_14_3_1'], errors='coerce')
    stoch_mask = _stoch.isna() | ((_stoch >= _stoch_lo) & (_stoch <= _stoch_hi))
    filtered_df = _apply_filter(filtered_df, stoch_mask, f"Stochastik %K in [{_stoch_lo}, {_stoch_hi}]")

# "Langweilige Aktien" Filter: stabile, traege Large-Caps (Coca-Cola/Pepsi-Typ).
# Kriterien: Beta <= 1.0, sell IV <= 40%, Market Cap >= $20 Mrd, defensiver Sektor.
# Beta + Market Cap sind nicht in der Spreads-Query -> per Batch-Query nachladen.
BORING_SECTORS = {
    "Consumer Defensive", "Utilities", "Healthcare",
    "Consumer Staples", "Communication Services",
}
BORING_MAX_BETA = 1.0
BORING_MAX_SELL_IV = 0.40
BORING_MIN_MARKET_CAP = 20_000_000_000  # $20 Mrd


@st.cache_data(ttl=600)
def _load_boring_metrics(symbols: tuple[str, ...]) -> pd.DataFrame:
    """Laedt Beta + Market Cap fuer die Kandidaten-Symbole (fuer 'langweilige Aktien' Filter)."""
    if not symbols:
        return pd.DataFrame(columns=["symbol", "beta", "market_cap"])
    try:
        return select_into_dataframe(
            query=(
                'SELECT symbol, "KeyStats_beta" AS beta, "Summary_marketCap" AS market_cap '
                'FROM "FundamentalData" WHERE symbol = ANY(:syms)'
            ),
            params={"syms": list(symbols)},
        )
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning(f"Konnte Beta/MarketCap nicht laden: {exc}")
        return pd.DataFrame(columns=["symbol", "beta", "market_cap"])


if st.session_state.get("enh_boring_only", False) and not filtered_df.empty:
    _syms = tuple(sorted(filtered_df['symbol'].unique().tolist()))
    _boring = _load_boring_metrics(_syms)
    _beta_map = {}
    _mcap_map = {}
    if not _boring.empty:
        _beta_map = dict(zip(_boring['symbol'], pd.to_numeric(_boring['beta'], errors='coerce')))
        _mcap_map = dict(zip(_boring['symbol'], pd.to_numeric(_boring['market_cap'], errors='coerce')))

    def _is_boring(r) -> bool:
        sym = r['symbol']
        beta = _beta_map.get(sym)
        mcap = _mcap_map.get(sym)
        sector = r.get('company_sector')
        sell_iv = r.get('sell_iv')
        # Beta niedrig (fehlend -> nicht langweilig genug)
        if beta is None or pd.isna(beta) or beta > BORING_MAX_BETA:
            return False
        # IV moderat
        if pd.notnull(sell_iv) and sell_iv > BORING_MAX_SELL_IV:
            return False
        # Grosse Marktkapitalisierung
        if mcap is None or pd.isna(mcap) or mcap < BORING_MIN_MARKET_CAP:
            return False
        # Defensiver / nicht-zyklischer Sektor
        if sector not in BORING_SECTORS:
            return False
        return True

    _boring_mask = filtered_df.apply(_is_boring, axis=1)
    filtered_df = _apply_filter(
        filtered_df, _boring_mask,
        "Nur langweilige Aktien (Beta≤1.0, IV≤40%, MCap≥$20B, defensiv)",
    )

filtered_df.reset_index(drop=True, inplace=True)

# Format 'earnings_date' for display
filtered_df['earnings_date'] = pd.to_datetime(filtered_df['earnings_date']).dt.strftime('%d.%m.%Y')

total_before = len(spreads_df)
total_after = len(filtered_df)
total_removed = total_before - total_after

st.markdown(f"### {total_after} Results")

# Export All button
if not filtered_df.empty:
    export_columns = [
        'symbol', 'Company', 'close', 'option_type',
        'sell_strike', 'sell_last_option_price', 'sell_delta', 'sell_iv', 'sell_theta',
        'sell_open_interest', 'sell_day_volume', 'sell_expected_move',
        'buy_strike', 'buy_last_option_price', 'buy_delta', 'buy_iv', 'buy_theta',
        'buy_open_interest', 'buy_day_volume', 'buy_expected_move',
        'spread_width', 'net_credit', 'max_profit', 'max_profit%', 'risk_reward',
        'break_even', 'break_even%', 'bpr', 'profit_to_bpr',
        'expected_value', 'APDI', 'APDI_EV',
        'iv_rank', 'iv_percentile', 'iv_correction_factor',
        'spread_theta', '%_otm', 'days_to_expiration',
        'earnings_date', 'earnings_warning',
        'company_sector', 'company_industry', 'analyst_mean_target',
    ]
    available_cols = [c for c in export_columns if c in filtered_df.columns]
    export_df = filtered_df[available_cols]
    csv_data = export_df.to_csv(index=False)
    st.download_button(
        label=f"⬇️ Export All ({len(filtered_df)} trades) as CSV",
        data=csv_data,
        file_name=f"spreads_enhanced_{option_type}_{spread_width}w_{expiration_date}.csv",
        mime="text/csv",
    )

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
    page='spreads_enhanced',
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

        # Verfallsdatum + DTE prominent zeigen — bei DTE-Range sind mehrere Termine gemischt
        _exp_disp = pd.to_datetime(row['expiration_date']).strftime('%d.%m.%Y (%A)')
        _dte_disp = int(row['days_to_expiration']) if pd.notnull(row.get('days_to_expiration')) else '—'
        _at_disp = row.get('asset_type', '')
        st.info(
            f"**{row['symbol']}**  ·  Verfall: **{_exp_disp}**  ·  **{_dte_disp} DTE**  "
            f"·  Breite {int(row.get('spread_width', 0))}  ·  {row.get('option_type','')}/{strategy_type}"
            + (f"  ·  {_at_disp}" if _at_disp else "")
        )

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

        @st.cache_data(ttl=300)
        def _load_tech_indicators(symbol: str) -> dict:
            try:
                df = select_into_dataframe(
                    query=(
                        'SELECT "STOCHk_14_3_1", "STOCHd_14_3_1", "STOCHh_14_3_1", '
                        '"RSI_14", "EMA_50", "EMA_200", "MACDh_12_26_9", '
                        '"ADX_10", "DMP_10", "DMN_10" '
                        'FROM "TechnicalIndicatorsCalculated" WHERE symbol = :sym LIMIT 1'
                    ),
                    params={"sym": symbol}
                )
                if not df.empty:
                    return df.iloc[0].to_dict()
            except Exception as exc:
                logger.warning(f"Tech indicators load failed for {symbol}: {exc}")
            return {}

        @st.cache_data(ttl=300)
        def _load_fundamental(symbol: str) -> dict:
            try:
                fd_df = select_into_dataframe(
                    query=(
                        'SELECT "FinData_currentRatio", "FinData_debtToEquity", "FinData_returnOnEquity", '
                        '"FinData_revenueGrowth", "FinData_recommendationKey", "KeyStats_shortPercentOfFloat", '
                        '"KeyStats_beta", "FinData_profitMargins", "FinData_grossMargins", "FreeCashFlow" '
                        'FROM "FundamentalData" WHERE symbol = :sym LIMIT 1'
                    ),
                    params={"sym": symbol}
                )
                if not fd_df.empty:
                    return fd_df.iloc[0].to_dict()
            except Exception as exc:
                logger.warning(f"Fundamental load failed for {symbol}: {exc}")
            return {}

        extra_info = {
            'iv_rank': row.get('iv_rank'),
            'iv_percentile': row.get('iv_percentile'),
            'company_sector': row.get('company_sector'),
            'company_industry': row.get('company_industry'),
            'analyst_mean_target': row.get('analyst_mean_target'),
            'close': row.get('close'),
            'optionstrat_url': row.get('optionstrat_url'),
            'Claude': _create_claude_prompt_page_spreads(row),
            'tech_indicators': _load_tech_indicators(row['symbol']),
            'tech_score_direction': "bull" if row.get('option_type') == 'put' else "bear",
            'tech_score_style': st.session_state.get("enh_score_style", "trend"),
            # Sicherheitspuffer: wie weit darf der Kurs laufen bis Short-Strike / Break-Even?
            'sell_strike': row.get('sell_strike'),
            'break_even': row.get('break_even'),
            'is_put': row.get('option_type') == 'put',
            'fundamental': _load_fundamental(row['symbol']),
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
