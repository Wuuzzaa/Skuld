"""Trade Journal — Flex Query Trades Report auswerten. Nichts wird gespeichert."""

import io
import csv
import logging
import os
from datetime import datetime

import pandas as pd
import streamlit as st

logger = logging.getLogger(os.path.basename(__file__))

# ── Parser ────────────────────────────────────────────────────────────────────

def _parse_trades_csv(content: str) -> pd.DataFrame:
    """Parst IBKR/CapTrader Flex Query Trades Report CSV."""
    reader = csv.reader(io.StringIO(content))
    rows = []
    header = []
    for row in reader:
        if not row:
            continue
        clean = [c.strip().strip('"') for c in row]
        if not header:
            header = clean
            continue
        if len(clean) < len(header):
            clean += [""] * (len(header) - len(clean))
        rows.append(dict(zip(header, clean)))

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Spalten normalisieren
    col_map = {
        "ClientAccountID": "account",
        "Symbol":          "symbol_raw",
        "Description":     "description",
        "AssetClass":      "asset_class",
        "TradeDate":       "trade_date",
        "Quantity":        "quantity",
        "TradePrice":      "trade_price",
        "IBCommission":    "commission",
        "NetCash":         "net_cash",
        "Open/CloseIndicator": "open_close",
        "FifoPnlRealized": "pnl_realized",
        "Strike":          "strike",
        "Expiry":          "expiry",
        "Put/Call":        "put_call",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # Nur Optionen
    if "asset_class" in df.columns:
        df = df[df["asset_class"] == "OPT"].copy()

    for col in ["quantity", "trade_price", "commission", "net_cash", "pnl_realized"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d", errors="coerce")

    if "expiry" in df.columns:
        df["expiry"] = pd.to_datetime(df["expiry"], format="%Y%m%d", errors="coerce")

    # Underlying aus symbol_raw
    if "symbol_raw" in df.columns:
        import re
        df["underlying"] = df["symbol_raw"].apply(
            lambda s: re.match(r"^([A-Z0-9]{1,6})\s+", str(s)).group(1).strip()
            if re.match(r"^([A-Z0-9]{1,6})\s+", str(s)) else str(s).strip()
        )

    return df


# ── Trade-Gruppen-Erkennung ───────────────────────────────────────────────────

def _detect_strategy(legs: list[dict]) -> str:
    """Erkennt Strategie aus den Legs eines Trades."""
    puts  = [l for l in legs if l.get("put_call") == "P"]
    calls = [l for l in legs if l.get("put_call") == "C"]
    sells = [l for l in legs if l.get("quantity", 0) < 0]
    buys  = [l for l in legs if l.get("quantity", 0) > 0]

    n = len(legs)
    np_, nc = len(puts), len(calls)

    if n == 1:
        if np_ == 1:
            return "Short Put" if legs[0].get("quantity", 0) < 0 else "Long Put"
        if nc == 1:
            return "Short Call" if legs[0].get("quantity", 0) < 0 else "Long Call"

    if n == 2:
        if np_ == 2:
            sell_put = next((l for l in puts if l.get("quantity", 0) < 0), None)
            buy_put  = next((l for l in puts if l.get("quantity", 0) > 0), None)
            if sell_put and buy_put:
                return "Bull Put Spread"
        if nc == 2:
            sell_call = next((l for l in calls if l.get("quantity", 0) < 0), None)
            buy_call  = next((l for l in calls if l.get("quantity", 0) > 0), None)
            if sell_call and buy_call:
                return "Bear Call Spread"
        if np_ == 1 and nc == 1:
            if len(sells) == 2:
                return "Short Strangle"
            if len(sells) == 1 and len(buys) == 1:
                return "Risk Reversal"

    if n == 4 and np_ == 2 and nc == 2:
        return "Iron Condor"

    if n == 3:
        if np_ == 2 and nc == 1:
            return "Jade Lizard"
        if np_ == 1 and nc == 2:
            return "Reverse Jade Lizard"

    return f"{n}-Leg Strategie"


def _build_trades(df: pd.DataFrame) -> pd.DataFrame:
    """
    Gruppiert Legs zu Trades. Schließungs-Legs (C) tragen den realisierten P&L.
    Gruppen-Schlüssel: underlying + expiry + trade_date (gleicher Tag = zusammengehöriger Trade).
    """
    if df.empty:
        return pd.DataFrame()

    records = []

    # Gruppiere nach underlying + expiry + trade_date
    group_cols = ["underlying", "expiry", "trade_date"]
    missing = [c for c in group_cols if c not in df.columns]
    if missing:
        return pd.DataFrame()

    for (underlying, expiry, trade_date), grp in df.groupby(group_cols, dropna=False):
        legs = grp.to_dict("records")
        strategy  = _detect_strategy(legs)
        pnl       = grp["pnl_realized"].sum() if "pnl_realized" in grp.columns else 0
        commission = grp["commission"].sum() if "commission" in grp.columns else 0
        net_cash  = grp["net_cash"].sum() if "net_cash" in grp.columns else 0
        open_close = "O" if all(l.get("open_close") == "O" for l in legs) else \
                     "C" if all(l.get("open_close") == "C" for l in legs) else "O+C"

        # Beine-String
        leg_parts = []
        for l in sorted(legs, key=lambda x: (x.get("put_call",""), float(x.get("strike", 0) or 0))):
            qty  = int(l.get("quantity", 0))
            pc   = l.get("put_call", "?")
            sk   = l.get("strike", "?")
            act  = "Sell" if qty < 0 else "Buy"
            leg_parts.append(f"{act} {sk}{pc}")
        beine = " / ".join(leg_parts)

        records.append({
            "Underlying":  underlying,
            "Strategie":   strategy,
            "Verfall":     expiry.strftime("%Y-%m-%d") if pd.notna(expiry) else "",
            "Datum":       trade_date.strftime("%Y-%m-%d") if pd.notna(trade_date) else "",
            "O/C":         open_close,
            "Beine":       beine,
            "P&L $":       round(pnl, 2),
            "Provision $": round(commission, 2),
            "Net P&L $":   round(pnl + commission, 2),
            "Net Cash $":  round(net_cash, 2),
            "_legs":       len(legs),
        })

    out = pd.DataFrame(records)
    if not out.empty and "Datum" in out.columns:
        out = out.sort_values("Datum", ascending=False)
    return out


# ── Styling ───────────────────────────────────────────────────────────────────

def _style_trades(df: pd.DataFrame):
    def _pnl(col):
        return ["color:#34d399;font-weight:700" if v > 0
                else ("color:#ef4444;font-weight:700" if v < 0 else "color:#94a3b8")
                for v in col]

    style = df.style.apply(_pnl, subset=["Net P&L $"])
    if "P&L $" in df.columns:
        style = style.apply(_pnl, subset=["P&L $"])
    return style.format({
        "P&L $":       "${:+.2f}",
        "Provision $": "${:.2f}",
        "Net P&L $":   "${:+.2f}",
        "Net Cash $":  "${:+.2f}",
    })


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.title("Trade Journal")
    st.caption("Flex Query Trades Report hochladen → P&L Auswertung. Nichts wird gespeichert.")

    # ── Upload ────────────────────────────────────────────────────────────────
    uploaded = st.file_uploader(
        "Trades Report CSV (IBKR/CapTrader Flex Query)",
        type=["csv"],
        key="tj_csv",
        help="Flex Query → Report-Typ: Trades → Felder: Symbol, TradeDate, Quantity, "
             "TradePrice, IBCommission, NetCash, Open/CloseIndicator, FifoPnlRealized, "
             "Strike, Expiry, Put/Call → Format: CSV",
    )

    if uploaded is None:
        st.info("CSV hochladen um fortzufahren.")
        with st.expander("Wie erstelle ich den Report in CapTrader?"):
            st.markdown("""
1. **CapTrader Client Portal** → Berichte → Flex Queries → Neu erstellen
2. **Report-Typ:** Trades
3. **Felder:** Symbol, Description, AssetClass, TradeDate, Quantity, TradePrice,
   IBCommission, NetCash, Open/CloseIndicator, FifoPnlRealized, Strike, Expiry, Put/Call
4. **Format:** CSV · **Zeitraum:** Custom (z.B. letztes Jahr)
5. Report speichern → Ausführen → CSV herunterladen
""")
        return

    content = uploaded.read().decode("utf-8", errors="replace")
    raw_df  = _parse_trades_csv(content)

    if raw_df.empty:
        st.error("Keine Optionen gefunden — prüfe ob das CSV das richtige Format hat.")
        return

    trades_df = _build_trades(raw_df)
    if trades_df.empty:
        st.error("Keine Trades rekonstruiert.")
        return

    # ── Filter ────────────────────────────────────────────────────────────────
    with st.expander("Filter", expanded=True):
        f1, f2, f3 = st.columns(3)
        with f1:
            all_syms     = sorted(trades_df["Underlying"].dropna().unique())
            sel_syms     = st.multiselect("Underlying", all_syms, key="tj_syms")
        with f2:
            all_strats   = sorted(trades_df["Strategie"].dropna().unique())
            sel_strats   = st.multiselect("Strategie", all_strats, key="tj_strats")
        with f3:
            oc_opts      = ["Alle", "Nur geschlossene (C)", "Nur offene (O)"]
            sel_oc       = st.radio("Status", oc_opts, horizontal=True, key="tj_oc")

    filt = trades_df.copy()
    if sel_syms:
        filt = filt[filt["Underlying"].isin(sel_syms)]
    if sel_strats:
        filt = filt[filt["Strategie"].isin(sel_strats)]
    if sel_oc == "Nur geschlossene (C)":
        filt = filt[filt["O/C"].str.contains("C")]
    elif sel_oc == "Nur offene (O)":
        filt = filt[filt["O/C"] == "O"]

    # ── KPI-Kacheln ──────────────────────────────────────────────────────────
    closed = filt[filt["O/C"].str.contains("C")]
    total_pnl    = closed["Net P&L $"].sum()
    winners      = closed[closed["Net P&L $"] > 0]
    losers       = closed[closed["Net P&L $"] < 0]
    win_rate     = len(winners) / len(closed) * 100 if len(closed) > 0 else 0
    avg_win      = winners["Net P&L $"].mean() if not winners.empty else 0
    avg_loss     = losers["Net P&L $"].mean() if not losers.empty else 0
    total_comm   = filt["Provision $"].sum()

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Net P&L",       f"${total_pnl:+,.2f}")
    k2.metric("Trades",         len(closed))
    k3.metric("Trefferquote",   f"{win_rate:.0f}%")
    k4.metric("Ø Gewinner",     f"${avg_win:+.2f}")
    k5.metric("Ø Verlierer",    f"${avg_loss:+.2f}")
    k6.metric("Provisionen",    f"${total_comm:.2f}")

    st.divider()

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_trades, tab_sym, tab_strat, tab_timeline = st.tabs([
        "Alle Trades", "Nach Symbol", "Nach Strategie", "Timeline"
    ])

    with tab_trades:
        disp_cols = ["Datum", "Underlying", "Strategie", "Verfall", "O/C",
                     "Beine", "P&L $", "Provision $", "Net P&L $"]
        show = filt[[c for c in disp_cols if c in filt.columns]].copy()
        event = st.dataframe(
            _style_trades(show),
            hide_index=True,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            key="tj_table",
        )
        sel = event.selection.rows if hasattr(event, "selection") else []
        if sel:
            row = filt.iloc[sel[0]]
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Underlying", row["Underlying"])
            c2.metric("Strategie",  row["Strategie"])
            c3.metric("Net P&L",    f"${row['Net P&L $']:+.2f}")
            c4.metric("Verfall",    row["Verfall"])
            st.code(row["Beine"], language=None)

    with tab_sym:
        if closed.empty:
            st.info("Keine geschlossenen Trades.")
        else:
            sym_df = (
                closed.groupby("Underlying")
                .agg(
                    Trades=("Net P&L $", "count"),
                    **{"Net P&L $": ("Net P&L $", "sum")},
                    **{"Ø P&L $": ("Net P&L $", "mean")},
                    Gewinner=("Net P&L $", lambda x: (x > 0).sum()),
                    Verlierer=("Net P&L $", lambda x: (x < 0).sum()),
                )
                .reset_index()
                .sort_values("Net P&L $", ascending=False)
            )
            sym_df["Win%"] = (sym_df["Gewinner"] / sym_df["Trades"] * 100).round(0)
            sym_df["Net P&L $"] = sym_df["Net P&L $"].round(2)
            sym_df["Ø P&L $"]   = sym_df["Ø P&L $"].round(2)

            def _pnl_color(col):
                return ["color:#34d399;font-weight:700" if v > 0
                        else ("color:#ef4444;font-weight:700" if v < 0 else "")
                        for v in col]

            st.dataframe(
                sym_df.style
                .apply(_pnl_color, subset=["Net P&L $", "Ø P&L $"])
                .format({"Net P&L $": "${:+.2f}", "Ø P&L $": "${:+.2f}", "Win%": "{:.0f}%"}),
                hide_index=True,
                use_container_width=True,
            )

    with tab_strat:
        if closed.empty:
            st.info("Keine geschlossenen Trades.")
        else:
            strat_df = (
                closed.groupby("Strategie")
                .agg(
                    Trades=("Net P&L $", "count"),
                    **{"Net P&L $": ("Net P&L $", "sum")},
                    **{"Ø P&L $": ("Net P&L $", "mean")},
                    Gewinner=("Net P&L $", lambda x: (x > 0).sum()),
                    Verlierer=("Net P&L $", lambda x: (x < 0).sum()),
                )
                .reset_index()
                .sort_values("Net P&L $", ascending=False)
            )
            strat_df["Win%"] = (strat_df["Gewinner"] / strat_df["Trades"] * 100).round(0)
            strat_df["Net P&L $"] = strat_df["Net P&L $"].round(2)
            strat_df["Ø P&L $"]   = strat_df["Ø P&L $"].round(2)
            st.dataframe(
                strat_df.style
                .apply(_pnl_color, subset=["Net P&L $", "Ø P&L $"])
                .format({"Net P&L $": "${:+.2f}", "Ø P&L $": "${:+.2f}", "Win%": "{:.0f}%"}),
                hide_index=True,
                use_container_width=True,
            )

    with tab_timeline:
        if closed.empty:
            st.info("Keine geschlossenen Trades.")
        else:
            tl = closed.copy()
            tl["Datum"] = pd.to_datetime(tl["Datum"], errors="coerce")
            tl = tl.dropna(subset=["Datum"]).sort_values("Datum")
            tl["Kumulativer P&L $"] = tl["Net P&L $"].cumsum()

            st.markdown("**Kumulativer P&L über Zeit**")
            st.line_chart(tl.set_index("Datum")["Kumulativer P&L $"])

            st.markdown("**P&L pro Trade**")
            bar = tl[["Datum", "Underlying", "Net P&L $"]].copy()
            bar["Label"] = bar["Datum"].dt.strftime("%m-%d") + " " + bar["Underlying"]
            st.bar_chart(bar.set_index("Label")["Net P&L $"])


if __name__ == "__main__":
    main()
