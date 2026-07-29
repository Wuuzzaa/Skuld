"""Universe — Aktienuniversum als interaktive Treemap (Issue #60)

Zeigt alle Symbole gruppiert nach Sektor/Branche.
Farbe = Tagesperformance (rot/grün wie Finviz).
Größe = Market Cap.
Drilldown: Sektor → Branche → Einzeltitel.
"""

import logging
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.logger_config import setup_logging

setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))

# ── Session state ─────────────────────────────────────────────────────────────
for key, default in [
    ("universe_df", None),
    ("universe_drilldown_sector", None),
    ("universe_drilldown_industry", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Page header ───────────────────────────────────────────────────────────────
st.title("Aktienuniversum")
st.caption("Alle Titel im Überblick — nach Sektor und Branche. Größe = Market Cap · Farbe = Tagesperformance.")

# ── Filter ────────────────────────────────────────────────────────────────────
with st.expander("🔍 Filter", expanded=True):
    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    with fc1:
        groupby = st.radio("Gruppierung", ["Sektor", "Branche"], horizontal=True, key="uni_groupby")
    with fc2:
        min_cap = st.selectbox(
            "Min Market Cap",
            options=[0, 0.3, 1, 2, 10, 50, 100, 200],
            index=0,
            format_func=lambda x: "Alle" if x == 0 else f"{x}B+",
            key="uni_min_cap",
        )
    with fc3:
        options_filter = st.radio("Optionen", ["Alle", "Nur mit Optionen"], horizontal=True, key="uni_options")
    with fc4:
        size_metric = st.radio("Größe", ["Market Cap", "Gleich"], horizontal=True, key="uni_size")
    with fc5:
        color_metric = st.radio("Farbe", ["Tagesperformance", "52W-Performance"], horizontal=True, key="uni_color")

load_btn = st.button("🔄 Universum laden", type="primary")

# ── Load data ─────────────────────────────────────────────────────────────────
if load_btn or st.session_state["universe_df"] is None:
    with st.spinner("Lade Universum…"):
        try:
            sql_path = PATH_DATABASE_QUERY_FOLDER / "universe_treemap.sql"
            raw = select_into_dataframe(sql_file_path=sql_path, params={})
            if raw is not None and not raw.empty:
                for col in ["stock_price", "prev_close", "price_change_pct", "market_cap_b",
                            "iv_rank", "trailing_pe", "beta", "change_52w",
                            "week52_low", "week52_high", "volume", "avg_volume"]:
                    if col in raw.columns:
                        raw[col] = pd.to_numeric(raw[col], errors="coerce")
                st.session_state["universe_df"] = raw
                st.session_state["universe_drilldown_sector"] = None
                st.session_state["universe_drilldown_industry"] = None
            else:
                st.warning("Keine Daten gefunden.")
        except Exception as e:
            st.error(f"Fehler: {e}")
            logger.error(e, exc_info=True)

if st.session_state["universe_df"] is None:
    st.stop()

# ── Filter anwenden ───────────────────────────────────────────────────────────
df = st.session_state["universe_df"].copy()

if min_cap > 0:
    df = df[df["market_cap_b"].isna() | (df["market_cap_b"] >= min_cap)]
if options_filter == "Nur mit Optionen":
    df = df[df["has_options"] == True]

# Drilldown-Breadcrumb + Zurück-Button
drill_sector   = st.session_state["universe_drilldown_sector"]
drill_industry = st.session_state["universe_drilldown_industry"]

crumbs = ["🌍 Alle"]
if drill_sector:
    crumbs.append(drill_sector)
if drill_industry:
    crumbs.append(drill_industry)

bc1, bc2 = st.columns([5, 1])
with bc1:
    st.markdown(" › ".join(f"**{c}**" for c in crumbs))
with bc2:
    if drill_sector and st.button("⬅ Zurück", key="uni_back"):
        if drill_industry:
            st.session_state["universe_drilldown_industry"] = None
        else:
            st.session_state["universe_drilldown_sector"] = None
        st.rerun()

# Drilldown-Filter
if drill_industry:
    df = df[df["company_industry"] == drill_industry]
elif drill_sector:
    df = df[df["company_sector"] == drill_sector]

st.caption(f"{len(df)} Titel · Market Cap gesamt: {df['market_cap_b'].sum():,.0f}B")

# ── Treemap bauen ─────────────────────────────────────────────────────────────
def _color_scale(val):
    """Clamp performance auf ±5% für Farbskala."""
    if pd.isna(val):
        return 0.0
    return float(np.clip(val, -5, 5))


def _fmt_cap(v):
    if pd.isna(v): return "—"
    if v >= 1000: return f"{v/1000:.1f}T"
    return f"{v:.1f}B"


def _fmt_pct(v):
    if pd.isna(v): return "—"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.2f}%"


# Farb-Spalte wählen
color_col = "price_change_pct" if color_metric == "Tagesperformance" else "change_52w"
color_label = "Tagesperf. %" if color_metric == "Tagesperformance" else "52W %"

df["_color_val"] = df[color_col].apply(_color_scale)
df["_size_val"]  = df["market_cap_b"].fillna(0.1) if size_metric == "Market Cap" else 1.0
df["_size_val"]  = df["_size_val"].clip(lower=0.01)

# Gruppierungsebene
if drill_industry or groupby == "Branche":
    # Einzelne Symbole zeigen
    group_col   = "symbol"
    parent_col  = "company_industry" if not drill_industry else None
    label_fn    = lambda r: (
        f"{r['symbol']}<br>"
        f"<span style='font-size:10px'>{_fmt_pct(r[color_col])}</span>"
    )
else:
    if drill_sector:
        group_col  = "company_industry"
        parent_col = "company_sector"
    else:
        group_col  = "company_sector"
        parent_col = None
    label_fn = None

# Aggregieren für Sektor/Branche-Ebene
if group_col in ("company_sector", "company_industry"):
    agg = df.groupby(group_col, dropna=False).agg(
        _size_val =("_size_val", "sum"),
        _color_val=(color_col,   lambda x: x.dropna().mean() if not x.dropna().empty else 0),
        count     =("symbol",    "count"),
    ).reset_index()
    agg["label_text"] = agg[group_col]
    agg["hover_text"] = agg.apply(
        lambda r: (
            f"<b>{r[group_col]}</b><br>"
            f"Titel: {r['count']}<br>"
            f"{color_label}: {_fmt_pct(r['_color_val'])}<br>"
            f"Market Cap: {_fmt_cap(r['_size_val'])}"
        ), axis=1
    )
    ids     = agg[group_col].tolist()
    labels  = agg["label_text"].tolist()
    parents = [""] * len(agg)
    values  = agg["_size_val"].tolist()
    colors  = agg["_color_val"].tolist()
    hovers  = agg["hover_text"].tolist()
    custom  = [[None, None, None, None]] * len(agg)

else:
    # Symbol-Ebene
    ids     = df["symbol"].tolist()
    labels  = df["symbol"].tolist()
    parents = (df["company_industry"].fillna("Unbekannt").tolist()
               if drill_sector and not drill_industry
               else [""] * len(df))
    values  = df["_size_val"].tolist()
    colors  = df["_color_val"].tolist()
    hovers  = df.apply(lambda r: (
        f"<b>{r['symbol']}</b> — {r.get('company_name','')}<br>"
        f"Sektor: {r.get('company_sector','—')}<br>"
        f"Branche: {r.get('company_industry','—')}<br>"
        f"Kurs: {r['stock_price']:.2f}<br>"
        f"Tagesperf.: {_fmt_pct(r.get('price_change_pct'))}<br>"
        f"52W: {_fmt_pct(r.get('change_52w'))}<br>"
        f"Market Cap: {_fmt_cap(r.get('market_cap_b'))}<br>"
        f"IV Rank: {r['iv_rank']:.0f}%" if pd.notna(r.get('iv_rank')) else f"IV Rank: —<br>"
        + f"Optionen: {'✅' if r.get('has_options') else '—'}"
    ), axis=1).tolist()
    custom = df[["stock_price", "price_change_pct", "market_cap_b", "iv_rank"]].values.tolist()

# Plotly Treemap
fig = go.Figure(go.Treemap(
    ids      = ids,
    labels   = labels,
    parents  = parents,
    values   = values,
    customdata = custom,
    hovertext  = hovers,
    hoverinfo  = "text",
    marker=dict(
        colors    = colors,
        colorscale=[
            [0.0,  "#7f1d1d"],
            [0.2,  "#dc2626"],
            [0.4,  "#ef4444"],
            [0.48, "#6b7280"],
            [0.52, "#6b7280"],
            [0.6,  "#16a34a"],
            [0.8,  "#15803d"],
            [1.0,  "#14532d"],
        ],
        cmid      = 0,
        cmin      = -5,
        cmax      = 5,
        showscale = True,
        colorbar  = dict(
            title      = color_label,
            ticksuffix = "%",
            thickness  = 14,
            len        = 0.6,
            tickvals   = [-5, -2.5, 0, 2.5, 5],
            ticktext   = ["≤−5%", "−2.5%", "0%", "+2.5%", "≥+5%"],
        ),
    ),
    textinfo     = "label",
    textfont     = dict(size=12, color="white"),
    pathbar      = dict(visible=True),
    tiling       = dict(packing="squarify", pad=2),
))

fig.update_layout(
    height          = 620,
    margin          = dict(l=0, r=0, t=30, b=0),
    paper_bgcolor   = "rgba(0,0,0,0)",
    font            = dict(color="#e2e8f0"),
    treemapcolorway = None,
)

# Click-Event für Drilldown
event = st.plotly_chart(
    fig,
    use_container_width=True,
    on_select="rerun",
    key="uni_treemap",
)

# Drilldown-Logik: auf Kachel geklickt
if event and hasattr(event, "selection") and event.selection:
    pts = event.selection.get("points", [])
    if pts:
        clicked_label = pts[0].get("label") or pts[0].get("id")
        if clicked_label:
            if not drill_sector:
                # Klick auf Sektor → Sektor-Drilldown
                if clicked_label in df["company_sector"].values:
                    st.session_state["universe_drilldown_sector"] = clicked_label
                    st.rerun()
            elif not drill_industry:
                # Klick auf Branche → Branchen-Drilldown
                if clicked_label in df["company_industry"].values:
                    st.session_state["universe_drilldown_industry"] = clicked_label
                    st.rerun()

# ── Detail-Tabelle unter der Treemap ─────────────────────────────────────────
st.divider()

# Spalten-Filter über der Tabelle
tbl1, tbl2, tbl3 = st.columns([2, 2, 1])
with tbl1:
    search = st.text_input("🔍 Symbol / Name suchen", key="uni_search", placeholder="z.B. AAPL oder Apple")
with tbl2:
    sort_col = st.selectbox("Sortieren nach", ["Market Cap", "Tagesperf. %", "52W %", "IV Rank", "Symbol"], key="uni_sort")
with tbl3:
    sort_asc = st.toggle("Aufsteigend", value=False, key="uni_sort_asc")

view = df.copy()
if search:
    mask = (
        view["symbol"].str.contains(search, case=False, na=False) |
        view["company_name"].str.contains(search, case=False, na=False)
    )
    view = view[mask]

sort_map = {
    "Market Cap":    "market_cap_b",
    "Tagesperf. %":  "price_change_pct",
    "52W %":         "change_52w",
    "IV Rank":       "iv_rank",
    "Symbol":        "symbol",
}
view = view.sort_values(sort_map[sort_col], ascending=sort_asc, na_position="last")

def _pct_cell(v):
    if pd.isna(v): return "—"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.2f}%"

disp = pd.DataFrame({
    "Symbol":    view["symbol"],
    "Name":      view["company_name"].fillna("—").str.slice(0, 30),
    "Sektor":    view["company_sector"].fillna("—"),
    "Branche":   view["company_industry"].fillna("—"),
    "Kurs ($)":  view["stock_price"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
    "Tag %":     view["price_change_pct"].apply(_pct_cell),
    "52W %":     view["change_52w"].apply(lambda v: _pct_cell(v * 100) if pd.notna(v) else "—"),
    "MktCap $B": view["market_cap_b"].apply(lambda v: f"{v:.1f}B" if pd.notna(v) else "—"),
    "IV Rank":   view["iv_rank"].apply(lambda v: f"{v:.0f}%" if pd.notna(v) else "—"),
    "P/E":       view["trailing_pe"].apply(lambda v: f"{v:.1f}" if pd.notna(v) else "—"),
    "Beta":      view["beta"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
    "Optionen":  view["has_options"].apply(lambda v: "✅" if v else "—"),
})

def _highlight_pct(row):
    try:
        val = float(row["Tag %"].replace("%", "").replace("+", ""))
    except Exception:
        return [""] * len(row)
    if val >= 2:
        return ["background-color: rgba(20,83,45,0.30)"] * len(row)
    if val >= 0.5:
        return ["background-color: rgba(20,83,45,0.15)"] * len(row)
    if val <= -2:
        return ["background-color: rgba(127,29,29,0.30)"] * len(row)
    if val <= -0.5:
        return ["background-color: rgba(127,29,29,0.15)"] * len(row)
    return [""] * len(row)

styled = disp.style.apply(_highlight_pct, axis=1).hide(axis="index")

tbl_event = st.dataframe(
    styled,
    use_container_width=True,
    height=min(600, 40 + 35 * len(disp)),
    selection_mode="single-row",
    on_select="rerun",
    key="uni_table",
)
st.caption(f"{len(disp)} Titel angezeigt")

# ── Kurzinfo bei Zeilen-Klick ─────────────────────────────────────────────────
sel = tbl_event.selection.rows if hasattr(tbl_event, "selection") else []
if sel:
    r = view.iloc[disp.index[sel[0]]] if hasattr(disp, "index") else view.iloc[sel[0]]

    st.divider()
    change_val = r.get("price_change_pct")
    change_str = _pct_cell(change_val)
    if pd.notna(change_val):
        _clr = "#22c55e" if change_val >= 0 else "#ef4444"
    else:
        _clr = "#9ca3af"

    w52lo  = r.get("week52_low")
    w52hi  = r.get("week52_high")
    w52str = (f"{w52lo:.2f} – {w52hi:.2f}" if pd.notna(w52lo) and pd.notna(w52hi) else "—")

    st.markdown(
        f"<div style='background:rgba(255,255,255,0.04);border-radius:10px;padding:14px 18px;'>"
        f"<span style='font-size:22px;font-weight:800;color:#f1f5f9;'>{r['symbol']}</span>"
        f"&nbsp;&nbsp;<span style='font-size:14px;color:#94a3b8;'>{r.get('company_name','')}</span>"
        f"<br><span style='font-size:13px;color:#94a3b8;'>{r.get('company_sector','—')} · {r.get('company_industry','—')}</span>"
        f"<br><span style='font-size:20px;font-weight:700;color:#f1f5f9;'>{r['stock_price']:.2f}</span>"
        f"&nbsp;<span style='font-size:16px;font-weight:600;color:{_clr};'>{change_str}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Market Cap", f"{r['market_cap_b']:.1f}B" if pd.notna(r.get("market_cap_b")) else "—")
    m2.metric("IV Rank",    f"{r['iv_rank']:.0f}%" if pd.notna(r.get("iv_rank")) else "—")
    m3.metric("P/E",        f"{r['trailing_pe']:.1f}" if pd.notna(r.get("trailing_pe")) else "—")
    m4.metric("Beta",       f"{r['beta']:.2f}" if pd.notna(r.get("beta")) else "—")
    m5.metric("52W Range",  w52str)
    m6.metric("Optionen",   "✅ Ja" if r.get("has_options") else "—")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Aktienuniversum · Issue #60 · Daten: StockData + OptionDataMassive")
