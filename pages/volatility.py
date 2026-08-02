"""
Volatility
==========
Four sub-tabs covering different angles of Implied Volatility analysis:

1. IV Rank & IV Percentile  — symbol-level overview sorted by IV Rank
2. IV vs. Realized          — IV/HV ratio + HV Rank/Pctl + Rising/Falling with 5D/1M
3. Highest IV (Strikes)     — individual option strikes with the highest IV (Last Price)
4. IV % Change (Strikes)    — strikes with the biggest IV move vs. yesterday
"""

import logging
import os

import pandas as pd
import streamlit as st

from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.historization import select_timetravel_into_dataframe
from src.logger_config import setup_logging
from src.streamlit_helpers import render_date_filter

setup_logging(component="streamlit", sub_component="volatility", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

st.title("Volatility")
st.caption(
    "Implied Volatility analysis: IV Rank & Percentile, IV vs. Realized Volatility, "
    "Highest IV Strikes, and IV % Change."
)

# ── Date picker (Time-Travel) ─────────────────────────────────────────────────
selected_date = render_date_filter(
    date_query='SELECT date FROM (SELECT date FROM "DatesHistory" UNION SELECT current_date) AS sub ORDER BY date DESC',
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _pct(val: float) -> str:
    """Format a ratio (0–1 range or already %) as percentage string."""
    if pd.isna(val):
        return "—"
    return f"{val:.2f}%"


@st.cache_data(ttl=300)
def _load_timetravel(date, sql_path, params=None):
    return select_timetravel_into_dataframe(date=date, sql_file_path=sql_path, params=params or {})


@st.cache_data(ttl=300)
def _load_live(sql_path, params=None):
    return select_into_dataframe(sql_file_path=sql_path, params=params or {})


def _iv_color(iv_chg):
    """Return a CSS color string for IV change direction."""
    if pd.isna(iv_chg):
        return ""
    return "color: #2ecc71" if iv_chg > 0 else ("color: #e74c3c" if iv_chg < 0 else "")


def _fmt_iv_chg(val):
    if pd.isna(val):
        return "—"
    sign = "+" if val > 0 else ""
    return f"{sign}{val*100:.2f}%"


def _style_iv_chg(df: pd.DataFrame, col: str) -> pd.DataFrame.style:
    """Color iv_chg column green/red."""
    def _color(v):
        if pd.isna(v):
            return ""
        return "color: #2ecc71" if v > 0 else ("color: #e74c3c" if v < 0 else "")
    return df.style.map(_color, subset=[col])


# ═════════════════════════════════════════════════════════════════════════════
# TAB LAYOUT
# ═════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 IV Rank & IV Percentile",
    "⚖️ IV vs. Realized Volatility",
    "🔥 Highest IV (Strikes)",
    "📈 IV % Change (Strikes)",
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — IV Rank & IV Percentile
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    st.subheader("IV Rank & IV Percentile")
    st.markdown(
        "IV Rank reflects the relative position of Implied Volatility compared to the yearly high and low. "
        "IV Percentile is the percentage of days when current IV was lower than today. "
        "**Green IV** = increasing vs. yesterday · **Red IV** = decreasing vs. yesterday."
    )

    with st.expander("Filters", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            min_iv_rank_t1 = st.number_input("Min IV Rank", 0, 100, 0, key="t1_min_ivr")
        with c2:
            max_iv_rank_t1 = st.number_input("Max IV Rank", 0, 100, 100, key="t1_max_ivr")
        with c3:
            min_iv_pctl_t1 = st.number_input("Min IV Percentile", 0, 100, 0, key="t1_min_ivp")
        with c4:
            iv_direction_t1 = st.selectbox("IV Direction", ["All", "Rising ↑", "Falling ↓"], key="t1_dir")

    with st.spinner("Loading IV Rank & Percentile…"):
        sql_t1 = PATH_DATABASE_QUERY_FOLDER / "volatility_iv_rank.sql"
        df1 = _load_timetravel(selected_date, sql_t1)

    if df1.empty:
        st.warning("No data available.")
    else:
        # Apply filters
        mask = (
            (df1["iv_rank"] >= min_iv_rank_t1) &
            (df1["iv_rank"] <= max_iv_rank_t1) &
            (df1["iv_percentile"] >= min_iv_pctl_t1)
        )
        if iv_direction_t1 == "Rising ↑":
            mask &= df1["iv_chg"] > 0
        elif iv_direction_t1 == "Falling ↓":
            mask &= df1["iv_chg"] < 0
        df1_f = df1[mask].copy()

        st.markdown(f"**{len(df1_f)} symbols**")

        # Format for display
        disp1 = df1_f[[
            "symbol", "name", "imp_vol", "iv_chg",
            "hv_30d", "iv_hv_ratio", "iv_rank", "iv_percentile",
            "total_day_volume", "put_volume_pct", "earnings_date"
        ]].copy()
        disp1["earnings_date"] = pd.to_datetime(disp1["earnings_date"], errors="coerce").dt.strftime("%m/%d/%y")

        st.dataframe(
            disp1.style.map(
                lambda v: ("color: #2ecc71" if v > 0 else ("color: #e74c3c" if v < 0 else "")),
                subset=["iv_chg"]
            ),
            column_config={
                "symbol":             st.column_config.TextColumn("Symbol"),
                "name":               st.column_config.TextColumn("Name"),
                "imp_vol":            st.column_config.NumberColumn("Imp Vol", format="%.2f%%"),
                "iv_chg":             st.column_config.NumberColumn("IV Chg", format="%.4f"),
                "hv_30d":             st.column_config.NumberColumn("30D HV", format="%.2f%%"),
                "iv_hv_ratio":        st.column_config.NumberColumn("IV/HV", format="%.2f"),
                "iv_rank":            st.column_config.NumberColumn("IV Rank", format="%.2f%%"),
                "iv_percentile":      st.column_config.NumberColumn("IV Pctl", format="%.0f%%"),
                "total_day_volume":   st.column_config.NumberColumn("Options Vol", format="%d"),
                "put_volume_pct":     st.column_config.NumberColumn("Put Vol %", format="%.1f%%", help="Put volume as % of total options volume"),
                "earnings_date":      st.column_config.TextColumn("Earnings"),
            },
            hide_index=True,
            width="stretch",
        )

    with st.expander("📖 About IV Rank & IV Percentile", expanded=False):
        st.markdown("""
**IV Rank** = `(Current IV − 1Y Low) / (1Y High − 1Y Low) × 100`
- 0% = IV at yearly low · 100% = IV at yearly high
- High IV Rank → good for selling premium (credit spreads, covered calls)

**IV Percentile** = % of trading days in the past year where IV was *lower* than today
- 99% means IV was lower on 99% of all days → historically very elevated

**IV/HV Ratio** = Implied Volatility / 30-Day Historical Volatility
- > 1.0 → options are pricing in more than what has actually happened (premium rich)
- < 1.0 → options are cheap relative to realized moves

**IV Change** = today's IV minus yesterday's IV (absolute, not %)
- Green = IV increased · Red = IV decreased
        """)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — IV vs. Realized Volatility
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.subheader("IV vs. Realized Volatility")
    st.markdown(
        "Ranks securities by IV/HV ratio. "
        "**> 1.0** → options premiums are high (preferred for sellers). "
        "**< 1.0** → options are cheap relative to realized moves (preferred for buyers)."
    )

    subtab_ratio, subtab_rising = st.tabs(["IV/HV Ratio", "Rising / Falling Volatility"])

    # ── Sub-tab: IV/HV Ratio ──────────────────────────────────────────────────
    with subtab_ratio:
        with st.expander("Filters", expanded=True):
            r1, r2, r3, r4 = st.columns(4)
            with r1:
                min_ivhv = st.number_input("Min IV/HV", 0.0, 10.0, 0.0, step=0.1, key="t2r_min_ivhv")
            with r2:
                min_ivr_t2 = st.number_input("Min IV Rank", 0, 100, 0, key="t2r_min_ivr")
            with r3:
                min_ivp_t2 = st.number_input("Min IV Pctl", 0, 100, 0, key="t2r_min_ivp")
            with r4:
                min_hvr_t2 = st.number_input("Min HV Rank", 0, 100, 0, key="t2r_min_hvr")

        with st.spinner("Loading IV/HV Ratio…"):
            sql_t2r = PATH_DATABASE_QUERY_FOLDER / "volatility_iv_hv_ratio.sql"
            df2r = _load_timetravel(selected_date, sql_t2r)

        if df2r.empty:
            st.warning("No data available.")
        else:
            mask2r = (
                (df2r["iv_hv_ratio"].fillna(0) >= min_ivhv) &
                (df2r["iv_rank"].fillna(0) >= min_ivr_t2) &
                (df2r["iv_percentile"].fillna(0) >= min_ivp_t2) &
                (df2r["hv_rank"].fillna(0) >= min_hvr_t2)
            )
            df2r_f = df2r[mask2r].copy()
            st.markdown(f"**{len(df2r_f)} symbols**")

            disp2r = df2r_f[[
                "symbol", "name", "imp_vol", "iv_chg",
                "hv_30d", "iv_hv_ratio",
                "iv_rank", "iv_percentile",
                "hv_rank", "hv_percentile",
                "earnings_date"
            ]].copy()
            disp2r["earnings_date"] = pd.to_datetime(disp2r["earnings_date"], errors="coerce").dt.strftime("%m/%d/%y")

            st.dataframe(
                disp2r.style.map(
                    lambda v: ("color: #2ecc71" if v > 0 else ("color: #e74c3c" if v < 0 else "")),
                    subset=["iv_chg"]
                ),
                column_config={
                    "symbol":        st.column_config.TextColumn("Symbol"),
                    "name":          st.column_config.TextColumn("Name"),
                    "imp_vol":       st.column_config.NumberColumn("Imp Vol", format="%.2f%%"),
                    "iv_chg":        st.column_config.NumberColumn("IV Chg", format="%.4f"),
                    "hv_30d":        st.column_config.NumberColumn("30D HV", format="%.2f%%"),
                    "iv_hv_ratio":   st.column_config.NumberColumn("IV/HV", format="%.2f"),
                    "iv_rank":       st.column_config.NumberColumn("IV Rank", format="%.2f%%"),
                    "iv_percentile": st.column_config.NumberColumn("IV Pctl", format="%.0f%%"),
                    "hv_rank":       st.column_config.NumberColumn("HV Rank", format="%.2f%%"),
                    "hv_percentile": st.column_config.NumberColumn("HV Pctl", format="%.0f%%"),
                    "earnings_date": st.column_config.TextColumn("Earnings"),
                },
                hide_index=True,
                width="stretch",
            )

    # ── Sub-tab: Rising / Falling Volatility ─────────────────────────────────
    with subtab_rising:
        st.markdown(
            "**Rising:** IV increasing, 5D-avg IV ≥ 105% of 1M-avg IV, IV/HV > 1.05. "
            "Good for Long Calls, Long Puts, Debit Spreads.  \n"
            "**Falling:** IV decreasing, 5D-avg IV ≤ 95% of 1M-avg IV. "
            "Good for Credit Spreads, Covered Calls, Iron Condors."
        )

        rf_direction = st.radio("Direction", ["Rising ↑", "Falling ↓"], horizontal=True, key="t2rf_dir")

        with st.spinner("Loading Rising/Falling Volatility…"):
            sql_t2rf = PATH_DATABASE_QUERY_FOLDER / "volatility_rising_falling.sql"
            df2rf = _load_timetravel(selected_date, sql_t2rf)

        if df2rf.empty:
            st.warning("No data available.")
        else:
            if rf_direction == "Rising ↑":
                mask_rf = (
                    (df2rf["iv_direction"] == "rising") &
                    (df2rf["iv_5d_1m_pct"].fillna(0) >= 105) &
                    (df2rf["iv_hv_ratio"].fillna(0) > 1.05) &
                    (df2rf["iv_rank"].fillna(100) < 80) &
                    (df2rf["iv_percentile"].fillna(100) < 80)
                )
            else:
                mask_rf = (
                    (df2rf["iv_direction"] == "falling") &
                    (df2rf["iv_5d_1m_pct"].fillna(100) <= 95)
                )
            df2rf_f = df2rf[mask_rf].copy()

            st.markdown(f"**{len(df2rf_f)} symbols**")

            disp2rf = df2rf_f[[
                "symbol", "name", "imp_vol", "iv_chg",
                "iv_5d_1m_pct", "iv_hv_ratio",
                "iv_rank", "iv_percentile",
                "earnings_date", "total_day_volume", "put_volume_pct"
            ]].copy()
            disp2rf["earnings_date"] = pd.to_datetime(disp2rf["earnings_date"], errors="coerce").dt.strftime("%m/%d/%y")

            st.dataframe(
                disp2rf.style.map(
                    lambda v: ("color: #2ecc71" if v > 0 else ("color: #e74c3c" if v < 0 else "")),
                    subset=["iv_chg"]
                ),
                column_config={
                    "symbol":               st.column_config.TextColumn("Symbol"),
                    "name":                 st.column_config.TextColumn("Name"),
                    "imp_vol":              st.column_config.NumberColumn("Imp Vol", format="%.2f%%"),
                    "iv_chg":               st.column_config.NumberColumn("IV Chg", format="%.4f"),
                    "iv_5d_1m_pct":         st.column_config.NumberColumn("5D/1M IV%", format="%.2f%%"),
                    "iv_hv_ratio":          st.column_config.NumberColumn("IV/HV", format="%.2f"),
                    "iv_rank":              st.column_config.NumberColumn("IV Rank", format="%.2f%%"),
                    "iv_percentile":        st.column_config.NumberColumn("IV Pctl", format="%.0f%%"),
                    "earnings_date":        st.column_config.TextColumn("Earnings"),
                    "total_day_volume":     st.column_config.NumberColumn("Options Vol", format="%d"),
                    "put_volume_pct":       st.column_config.NumberColumn("Put Vol %", format="%.1f%%"),
                },
                hide_index=True,
                width="stretch",
            )

    with st.expander("📖 About IV vs. Realized Volatility", expanded=False):
        st.markdown("""
**IV/HV Ratio** = Implied Volatility / 30-Day Historical (Realized) Volatility
- Much > 1.0 → market expects larger moves than have occurred → premium rich → good for sellers
- Much < 1.0 → market expects calm → options cheap → good for buyers

**HV Rank** = `(Current HV − 1Y Low HV) / (1Y High HV − 1Y Low HV) × 100`

**HV Percentile** = % of days in the past year where HV was *lower* than today

**5D/1M IV%** = 5-day average IV / 1-month average IV × 100
- > 105% → IV has recently been rising above its own monthly average → Rising Volatility signal
- < 95% → IV has recently been falling → Falling Volatility signal
        """)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Highest IV (Strikes)
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.subheader("Highest Implied Volatility — Option Strikes")
    st.markdown(
        "Individual option strikes sorted by Implied Volatility. "
        "Uses **Last Price** instead of Bid/Ask (no Bid/Ask available in this system)."
    )

    with st.expander("Filters", expanded=True):
        h1, h2, h3, h4 = st.columns(4)
        with h1:
            t3_type = st.selectbox("Option Type", ["put", "call", "both"], key="t3_type")
        with h2:
            t3_max_dte = st.number_input("Max DTE", 1, 365, 60, step=5, key="t3_dte")
        with h3:
            t3_rows = st.number_input("Max Rows", 10, 500, 100, step=10, key="t3_rows")
        with h4:
            t3_min_vol = st.number_input("Min Volume", 0, 10000, 10, step=10, key="t3_minvol")

    with st.spinner("Loading highest IV strikes…"):
        sql_t3 = PATH_DATABASE_QUERY_FOLDER / "volatility_highest_iv_strikes.sql"
        frames_t3 = []
        types_to_load = ["put", "call"] if t3_type == "both" else [t3_type]
        for ot in types_to_load:
            _df = _load_live(sql_t3, params={
                "option_type": ot,
                "max_dte": int(t3_max_dte),
                "limit_rows": int(t3_rows),
            })
            frames_t3.append(_df)
        df3 = pd.concat(frames_t3, ignore_index=True) if frames_t3 else pd.DataFrame()

    if df3.empty:
        st.warning("No data available.")
    else:
        df3 = df3[df3["volume"] >= t3_min_vol].copy()
        df3 = df3.sort_values("imp_vol", ascending=False).head(int(t3_rows))
        df3["last_trade"] = pd.to_datetime(df3["last_trade"], errors="coerce").dt.strftime("%m/%d/%y")
        df3["expiration_date"] = pd.to_datetime(df3["expiration_date"], errors="coerce").dt.strftime("%m/%d/%y")

        st.markdown(f"**{len(df3)} strikes**")
        st.dataframe(
            df3[[
                "symbol", "stock_price", "expiration_date", "dte",
                "type", "strike", "moneyness_pct",
                "last_price", "volume", "imp_vol",
                "vega", "delta", "last_trade"
            ]],
            column_config={
                "symbol":          st.column_config.TextColumn("Symbol"),
                "stock_price":     st.column_config.NumberColumn("Price", format="%.2f"),
                "expiration_date": st.column_config.TextColumn("Exp Date"),
                "dte":             st.column_config.NumberColumn("DTE", format="%d"),
                "type":            st.column_config.TextColumn("Type"),
                "strike":          st.column_config.NumberColumn("Strike", format="%.2f"),
                "moneyness_pct":   st.column_config.NumberColumn("Moneyness", format="%.2f%%"),
                "last_price":      st.column_config.NumberColumn("Last", format="%.2f"),
                "volume":          st.column_config.NumberColumn("Volume", format="%d"),
                "imp_vol":         st.column_config.NumberColumn("Imp Vol", format="%.2f%%"),
                "vega":            st.column_config.NumberColumn("Vega", format="%.4f"),
                "delta":           st.column_config.NumberColumn("Delta", format="%.4f"),
                "last_trade":      st.column_config.TextColumn("Last Trade"),
            },
            hide_index=True,
            width="stretch",
        )

    with st.expander("📖 About Highest IV Strikes", expanded=False):
        st.markdown("""
Elevated implied volatility on individual strikes means the market is pricing in a large price swing.
This is often found before earnings announcements or major macro events.

**Moneyness** = `(Strike − Stock Price) / Stock Price × 100`
- Positive = OTM for calls / ITM for puts
- Negative = ITM for calls / OTM for puts

**Note:** This system uses **Last Price** instead of Bid/Ask.
Strikes with no recent trades may show stale Last Prices.
        """)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — IV % Change (Strikes)
# ─────────────────────────────────────────────────────────────────────────────
with tab4:
    st.subheader("Options % Change in Implied Volatility")
    st.markdown(
        "Strikes with the largest IV move compared to yesterday. "
        "A large **increase** means the market expects a bigger price move. "
        "A large **decrease** means the market expects relative calm. "
        "Uses **Last Price** instead of Bid/Ask."
    )

    with st.expander("Filters", expanded=True):
        p1, p2, p3, p4 = st.columns(4)
        with p1:
            t4_dir = st.radio("Direction", ["increase", "decrease"], horizontal=True, key="t4_dir")
        with p2:
            t4_type = st.selectbox("Option Type", ["put", "call", "both"], key="t4_type")
        with p3:
            t4_max_dte = st.number_input("Max DTE", 1, 365, 60, step=5, key="t4_dte")
        with p4:
            t4_rows = st.number_input("Max Rows", 10, 500, 100, step=10, key="t4_rows")

    with st.spinner("Loading IV % Change strikes…"):
        sql_t4 = PATH_DATABASE_QUERY_FOLDER / "volatility_iv_pct_change.sql"
        frames_t4 = []
        types_t4 = ["put", "call"] if t4_type == "both" else [t4_type]
        for ot in types_t4:
            _df = _load_live(sql_t4, params={
                "direction": t4_dir,
                "option_type": ot,
                "max_dte": int(t4_max_dte),
                "limit_rows": int(t4_rows),
            })
            frames_t4.append(_df)
        df4 = pd.concat(frames_t4, ignore_index=True) if frames_t4 else pd.DataFrame()

    if df4.empty:
        st.warning("No data available.")
    else:
        sort_asc = t4_dir == "decrease"
        df4 = df4.sort_values("iv_pct_chg", ascending=sort_asc).head(int(t4_rows))
        df4["last_trade"] = pd.to_datetime(df4["last_trade"], errors="coerce").dt.strftime("%m/%d/%y")
        df4["expiration_date"] = pd.to_datetime(df4["expiration_date"], errors="coerce").dt.strftime("%m/%d/%y")

        st.markdown(f"**{len(df4)} strikes**")
        st.dataframe(
            df4[[
                "symbol", "stock_price", "expiration_date", "dte",
                "type", "strike", "moneyness_pct",
                "last_price", "volume",
                "iv_pct_chg", "imp_vol",
                "vega", "delta", "last_trade"
            ]].style.map(
                lambda v: ("color: #2ecc71" if v > 0 else ("color: #e74c3c" if v < 0 else "")),
                subset=["iv_pct_chg"]
            ),
            column_config={
                "symbol":          st.column_config.TextColumn("Symbol"),
                "stock_price":     st.column_config.NumberColumn("Price", format="%.2f"),
                "expiration_date": st.column_config.TextColumn("Exp Date"),
                "dte":             st.column_config.NumberColumn("DTE", format="%d"),
                "type":            st.column_config.TextColumn("Type"),
                "strike":          st.column_config.NumberColumn("Strike", format="%.2f"),
                "moneyness_pct":   st.column_config.NumberColumn("Moneyness", format="%.2f%%"),
                "last_price":      st.column_config.NumberColumn("Last", format="%.2f"),
                "volume":          st.column_config.NumberColumn("Volume", format="%d"),
                "iv_pct_chg":      st.column_config.NumberColumn("IV %Chg", format="%.2f%%"),
                "imp_vol":         st.column_config.NumberColumn("Imp Vol", format="%.2f%%"),
                "vega":            st.column_config.NumberColumn("Vega", format="%.4f"),
                "delta":           st.column_config.NumberColumn("Delta", format="%.4f"),
                "last_trade":      st.column_config.TextColumn("Last Trade"),
            },
            hide_index=True,
            width="stretch",
        )

    with st.expander("📖 About IV % Change", expanded=False):
        st.markdown("""
**IV % Change** = `(Today's IV − Yesterday's IV) / Yesterday's IV × 100`

A large increase highlights options where the market suddenly anticipates a much larger price swing.
Common triggers: surprise news, earnings pre-announcement, macro events.

A large decrease means IV crush is occurring — the market is calming down.
Common after earnings releases or resolution of uncertainty.

**Use cases:**
- **Large increase** → consider buying options / debit spreads before the move materializes
- **Large decrease** → consider selling premium / credit spreads while IV is still elevated
        """)
