import io
import json
import zipfile

import pandas as pd
import streamlit as st

from src.sector_rotation import (
    RotationParameters,
    SECTOR_ETFS,
    build_latest_sector_snapshot,
    build_sector_rotation_query,
    build_rotation_figure,
    calculate_sector_rotation,
    load_sector_rotation_price_history,
    required_history_length,
)


@st.cache_data(ttl=3600)
def load_rotation_dataset(parameters: RotationParameters):
    price_history = load_sector_rotation_price_history(parameters)
    rotation_data = calculate_sector_rotation(price_history, parameters)
    return price_history, rotation_data


st.subheader("S&P 500 Sektorrotation")
st.caption("Benchmark: SPY. Sektoren werden ueber die SPDR Sector ETFs abgebildet.")
st.info(
    "Aktuell ist nur eine kurze Historie verfuegbar. Deshalb nutzt die Seite standardmaessig kuerzere Fenster "
    "(WMA 5 / 15), damit RS-Ratio und RS-Momentum mit etwa 50 Handelstagen berechenbar bleiben."
)

with st.expander("Parameter", expanded=True):
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        price_column = st.selectbox(
            "Kursbasis",
            options=["adjclose", "close"],
            index=0,
            help="adjclose ist fuer ETF-Historien robuster bei Dividenden und Splits.",
        )
        short_window = st.slider(
            "Kurzer WMA",
            min_value=3,
            max_value=12,
            value=5,
            help="Kurze Glaettung fuer RS-Ratio und RS-Momentum. Kleinere Werte reagieren schneller, groessere Werte stabilisieren das Signal.",
        )

    with col2:
        long_window = st.slider(
            "Langer WMA",
            min_value=8,
            max_value=30,
            value=15,
            help="Langfristige Referenz fuer die Normierung des RS-Signals. Hoehere Werte machen die Matrix traeger, aber robuster.",
        )
        volatility_window = st.slider(
            "HV-Fenster",
            min_value=10,
            max_value=30,
            value=20,
            help="Anzahl der Handelstage fuer die historische Volatilitaet. Kleinere Fenster machen die Farbgebung nervoeser.",
        )

    with col3:
        volatility_threshold_low = st.number_input(
            "HV Schwelle Gruen/Orange",
            min_value=0.05,
            max_value=0.50,
            value=0.15,
            step=0.01,
            format="%.2f",
            help="Unterhalb dieser annualisierten Volatilitaet wird ein Sektor als ruhig beziehungsweise Gruen markiert.",
        )
        volatility_threshold_high = st.number_input(
            "HV Schwelle Orange/Rot",
            min_value=0.10,
            max_value=1.00,
            value=0.30,
            step=0.01,
            format="%.2f",
            help="Oberhalb dieser annualisierten Volatilitaet wird der Sektor rot dargestellt. Dazwischen liegt Orange.",
        )

    with col4:
        lookback_days = st.slider(
            "Lookback Tage",
            min_value=50,
            max_value=240,
            value=120,
            step=10,
            help="So weit wird aus dem History-View geladen. Mehr Lookback hilft nur, wenn die Datenhistorie im Backend auch wirklich vorhanden ist.",
        )
        tail_days = st.slider(
            "Tail im Chart",
            min_value=3,
            max_value=12,
            value=6,
            help="Wie viele der letzten Beobachtungen je Sektor als Spur im Koordinatensystem gezeigt werden.",
        )

parameters = RotationParameters(
    price_column=price_column,
    short_window=short_window,
    long_window=long_window,
    volatility_window=volatility_window,
    volatility_threshold_low=volatility_threshold_low,
    volatility_threshold_high=volatility_threshold_high,
    lookback_days=lookback_days,
    tail_days=tail_days,
)

min_history_needed = required_history_length(parameters)

if parameters.long_window <= parameters.short_window:
    st.error("Der lange WMA muss groesser als der kurze WMA sein.")
    st.stop()

with st.spinner("Lade Kursdaten und berechne RS-Ratio / RS-Momentum..."):
    price_history, rotation_data = load_rotation_dataset(parameters)

available_symbols = set(price_history["symbol"].unique()) if not price_history.empty else set()
missing_symbols = [symbol for symbol in SECTOR_ETFS if symbol not in available_symbols]

history_lengths = (
    price_history.groupby("symbol")["date"].nunique().to_dict()
    if not price_history.empty and "date" in price_history.columns
    else {}
)
benchmark_history = int(history_lengths.get(parameters.benchmark_symbol, 0))

benchmark_dates = (
    price_history.loc[price_history["symbol"] == parameters.benchmark_symbol, "date"]
    if not price_history.empty
    else []
)
benchmark_start_date = benchmark_dates.min() if len(benchmark_dates) else None
benchmark_end_date = benchmark_dates.max() if len(benchmark_dates) else None

available_sector_symbols = [symbol for symbol in SECTOR_ETFS if symbol in available_symbols]
relevant_symbols = [parameters.benchmark_symbol, *available_sector_symbols]
common_available_history = (
    min(int(history_lengths.get(symbol, 0)) for symbol in relevant_symbols)
    if relevant_symbols
    else 0
)

if price_history.empty:
    st.error("Es wurden keine Daten aus dem View StockPricesYahooHistory geladen.")
    st.stop()

if missing_symbols:
    st.warning(
        "Fuer folgende Sektor-ETFs fehlen Daten im View StockPricesYahooHistory: "
        + ", ".join(missing_symbols)
    )

if benchmark_history < min_history_needed:
    st.error(
        f"Fuer {parameters.benchmark_symbol} stehen nur {benchmark_history} Handelstage zur Verfuegung. "
        f"Mit den aktuellen Parametern werden mindestens {min_history_needed} Tage benoetigt."
    )
    st.stop()

if rotation_data.empty:
    st.error(
        "Es gibt nicht genug gemeinsame Historie fuer Benchmark und Sector-ETFs mit den gewaehlten Parametern. "
        "Mit etwa 50 Tagen funktionieren typischerweise eher kurze Fenster wie 5 / 15."
    )
    st.stop()

signal_history_by_symbol = rotation_data.groupby("symbol")["date"].nunique().to_dict()
effective_signal_history = (
    min(int(signal_history_by_symbol.get(symbol, 0)) for symbol in signal_history_by_symbol)
    if signal_history_by_symbol
    else 0
)

latest_snapshot = build_latest_sector_snapshot(rotation_data)
latest_date = latest_snapshot["date"].max()

raw_input_data = price_history[["date", "symbol", "close", "adjclose"]].copy()
raw_input_data["date"] = raw_input_data["date"].dt.strftime("%Y-%m-%d")
raw_input_data = raw_input_data.sort_values(["symbol", "date"]).reset_index(drop=True)

export_data = rotation_data[
    [
        "date", "symbol", "sector_name", "price", "benchmark_price",
        "rs_raw", "rs_smooth", "rs_smooth_long", "rs_norm",
        "rs_ratio", "rs_ratio_smooth", "rs_momentum",
        "historical_volatility", "volatility_signal", "quadrant",
    ]
].copy()
export_data["date"] = export_data["date"].dt.strftime("%Y-%m-%d")
export_data = export_data.sort_values(["symbol", "date"]).reset_index(drop=True)

snapshot_export = latest_snapshot[
    [
        "date",
        "symbol",
        "sector_name",
        "price",
        "benchmark_price",
        "rs_ratio",
        "rs_momentum",
        "quadrant",
        "historical_volatility",
        "volatility_signal",
    ]
].copy()
snapshot_export["date"] = snapshot_export["date"].dt.strftime("%Y-%m-%d")
snapshot_export["historical_volatility"] = (snapshot_export["historical_volatility"] * 100).round(4)
snapshot_export = snapshot_export.sort_values(["rs_ratio", "symbol"], ascending=[False, True]).reset_index(drop=True)

history_coverage_rows = []
for symbol in [parameters.benchmark_symbol, *SECTOR_ETFS.keys()]:
    symbol_history = price_history.loc[price_history["symbol"] == symbol].copy()
    symbol_dates = symbol_history["date"] if not symbol_history.empty else []
    history_coverage_rows.append(
        {
            "symbol": symbol,
            "role": "Benchmark" if symbol == parameters.benchmark_symbol else "Sektor",
            "sector_name": "Benchmark" if symbol == parameters.benchmark_symbol else SECTOR_ETFS[symbol],
            "rows_loaded": int(len(symbol_history)),
            "trading_days_loaded": int(history_lengths.get(symbol, 0)),
            "start_date": symbol_dates.min().strftime("%Y-%m-%d") if len(symbol_dates) else "",
            "end_date": symbol_dates.max().strftime("%Y-%m-%d") if len(symbol_dates) else "",
            "used_in_calculation": symbol in available_symbols,
        }
    )

history_coverage_data = (
    pd.DataFrame(history_coverage_rows)
    .sort_values(["role", "symbol"], ascending=[True, True])
    .reset_index(drop=True)
)

parameter_export = {
    "benchmark_symbol": parameters.benchmark_symbol,
    "price_column": parameters.price_column,
    "short_window": parameters.short_window,
    "long_window": parameters.long_window,
    "volatility_window": parameters.volatility_window,
    "volatility_threshold_low": parameters.volatility_threshold_low,
    "volatility_threshold_high": parameters.volatility_threshold_high,
    "lookback_days_requested": parameters.lookback_days,
    "tail_days": parameters.tail_days,
    "required_history_length": min_history_needed,
    "benchmark_history_available": benchmark_history,
    "common_history_available": common_available_history,
    "effective_signal_history": effective_signal_history,
    "latest_snapshot_date": latest_date.strftime("%Y-%m-%d"),
    "missing_symbols": missing_symbols,
}

sql_query = build_sector_rotation_query(
    symbols=[parameters.benchmark_symbol, *SECTOR_ETFS.keys()],
    lookback_days=parameters.lookback_days,
).strip()

parameter_export_data = pd.DataFrame(
    [{"parameter": key, "value": json.dumps(value, ensure_ascii=True) if isinstance(value, (list, dict)) else value}
     for key, value in parameter_export.items()]
)

sql_query_export_data = pd.DataFrame(
    [{"query_name": "sector_rotation_source_query", "sql": sql_query}]
)

excel_workbook = io.BytesIO()
with pd.ExcelWriter(excel_workbook, engine="openpyxl") as writer:
    raw_input_data.to_excel(writer, sheet_name="input_price_history", index=False)
    history_coverage_data.to_excel(writer, sheet_name="history_coverage", index=False)
    export_data.to_excel(writer, sheet_name="rotation_timeseries", index=False)
    snapshot_export.to_excel(writer, sheet_name="latest_snapshot", index=False)
    parameter_export_data.to_excel(writer, sheet_name="parameters", index=False)
    sql_query_export_data.to_excel(writer, sheet_name="source_query", index=False)

excel_workbook_bytes = excel_workbook.getvalue()

audit_package = io.BytesIO()
with zipfile.ZipFile(audit_package, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("parameters.json", json.dumps(parameter_export, indent=2, ensure_ascii=True))
    archive.writestr("source_query.sql", sql_query + "\n")
    archive.writestr("input_price_history.csv", raw_input_data.to_csv(index=False))
    archive.writestr("input_history_coverage.csv", history_coverage_data.to_csv(index=False))
    archive.writestr("rotation_timeseries.csv", export_data.to_csv(index=False))
    archive.writestr("latest_snapshot.csv", snapshot_export.to_csv(index=False))
    archive.writestr("sector_rotation_audit.xlsx", excel_workbook_bytes)

audit_package_bytes = audit_package.getvalue()
raw_input_csv = raw_input_data.to_csv(index=False).encode("utf-8")
history_coverage_csv = history_coverage_data.to_csv(index=False).encode("utf-8")
rotation_timeseries_csv = export_data.to_csv(index=False).encode("utf-8")
snapshot_csv = snapshot_export.to_csv(index=False).encode("utf-8")
parameter_json = json.dumps(parameter_export, indent=2, ensure_ascii=True).encode("utf-8")
sql_query_bytes = (sql_query + "\n").encode("utf-8")

metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
metric_col1.metric("Stand", latest_date.strftime("%Y-%m-%d"))
metric_col2.metric("Benchmark", parameters.benchmark_symbol)
metric_col3.metric("Sektoren mit Signal", int(latest_snapshot["symbol"].nunique()))
metric_col4.metric("Verwendeter Lookback", f"{benchmark_history} Tage", delta=f"angefordert {lookback_days}")

if lookback_days > benchmark_history:
    start_text = benchmark_start_date.strftime("%Y-%m-%d") if benchmark_start_date is not None else "unbekannt"
    end_text = benchmark_end_date.strftime("%Y-%m-%d") if benchmark_end_date is not None else "unbekannt"
    st.info(
        f"Lookback angefordert: {lookback_days} Tage. Im View fuer {parameters.benchmark_symbol} verfuegbar: "
        f"{benchmark_history} Handelstage. Verwendet wurde daher die tatsaechlich vorhandene Historie von "
        f"{start_text} bis {end_text}."
    )

st.caption(
    f"Historie im View: angefordert {lookback_days} Tage, Benchmark verfuegbar {benchmark_history} Tage, "
    f"gemeinsam verfuegbar {common_available_history} Tage, nach Berechnungs-Warmup effektiv nutzbar {effective_signal_history} Tage."
)

figure = build_rotation_figure(rotation_data, parameters)
st.plotly_chart(figure, use_container_width=True)

with st.expander("Audit-Trail: alle verwendeten Daten herunterladen", expanded=True):
    st.markdown(
        """
        Diese Sektion stellt die komplette Nachvollziehbarkeit der Berechnung bereit:

        - Rohkurse aus dem Backend-View, exakt wie sie geladen wurden
        - Historienabdeckung je Ticker inklusive Start- und Enddatum
        - komplette RS-Zeitreihen mit allen Zwischenstufen
        - aktueller Snapshot der zuletzt angezeigten Ergebnisse
        - verwendete Parameter und die SQL-Abfrage
        """
    )

    download_col1, download_col2, download_col3 = st.columns(3)
    download_col1.download_button(
        label="Audit-Paket (.zip)",
        data=audit_package_bytes,
        file_name="sector_rotation_audit_package.zip",
        mime="application/zip",
    )
    download_col2.download_button(
        label="Rohkurse als CSV",
        data=raw_input_csv,
        file_name="sector_rotation_input_price_history.csv",
        mime="text/csv",
    )
    download_col3.download_button(
        label="SQL + Parameter",
        data=sql_query_bytes,
        file_name="sector_rotation_source_query.sql",
        mime="text/plain",
    )

    extra_download_col1, extra_download_col2, extra_download_col3, extra_download_col4 = st.columns(4)
    extra_download_col1.download_button(
        label="Historienabdeckung CSV",
        data=history_coverage_csv,
        file_name="sector_rotation_history_coverage.csv",
        mime="text/csv",
    )
    extra_download_col2.download_button(
        label="Audit-Workbook (.xlsx)",
        data=excel_workbook_bytes,
        file_name="sector_rotation_audit.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    extra_download_col3.download_button(
        label="Parameter JSON",
        data=parameter_json,
        file_name="sector_rotation_parameters.json",
        mime="application/json",
    )
    extra_download_col4.download_button(
        label="Snapshot CSV",
        data=snapshot_csv,
        file_name="sector_rotation_latest_snapshot.csv",
        mime="text/csv",
    )

    with st.expander("Geladene Rohkurse", expanded=False):
        st.dataframe(raw_input_data, use_container_width=True, hide_index=True)

    with st.expander("Historienabdeckung je Ticker", expanded=False):
        st.dataframe(history_coverage_data, use_container_width=True, hide_index=True)

    with st.expander("Verwendete SQL-Abfrage", expanded=False):
        st.code(sql_query, language="sql")

with st.expander("RS-Zeitreihen exportieren (zur Validierung)", expanded=False):
    st.markdown(
        f"""
        **Berechnungsgrundlage – Schritt fuer Schritt**

        Alle Glaettungen nutzen einen **Weighted Moving Average (WMA)** mit linear aufsteigenden Gewichten.

        ---

        **WMA-Formel** (Fenster der Laenge n ueber die letzten n Werte $x_1, x_2, \\ldots, x_n$):

        $$
        WMA(n) = \\frac{{1 \\cdot x_1 + 2 \\cdot x_2 + \\ldots + n \\cdot x_n}}{{1 + 2 + \\ldots + n}} = \\frac{{\\sum_{{i=1}}^{{n}} i \\cdot x_i}}{{\\frac{{n(n+1)}}{{2}}}}
        $$

        Der juengste Wert ($x_n$) bekommt das hoechste Gewicht $n$, der aelteste ($x_1$) das Gewicht $1$.

        ---

        **Berechnungskette** (pro Sektor-ETF, Benchmark = SPY):

        | Schritt | Spalte | Formel | Erlaeuterung |
        |:---:|---|---|---|
        | 1 | `rs_raw` | price / benchmark_price | Relative Staerke des Sektors gegenueber SPY |
        | 2 | `rs_smooth` | WMA(rs_raw, **{short_window}**) | Kurzfristig geglaettete RS |
        | 3 | `rs_smooth_long` | WMA(rs_smooth, **{long_window}**) | Langfristig geglaettete RS (Referenzlinie) |
        | 4 | `rs_norm` | rs_smooth / rs_smooth_long | Normierung: liegt rs_smooth ueber oder unter seinem Trend? |
        | 5 | `rs_ratio` | WMA(rs_norm, **{short_window}**) × 100 | Nochmals geglaettet und auf 100 zentriert → **X-Achse im Chart** |
        | 6 | `rs_ratio_smooth` | WMA(rs_ratio, **{short_window}**) | Geglaettetes RS-Ratio als Momentum-Referenz |
        | 7 | `rs_momentum` | (rs_ratio / rs_ratio_smooth) × 100 | Dynamik des RS-Ratio → **Y-Achse im Chart** |

        ---

        **Rechenbeispiel WMA mit Fenster {short_window}:**

        Bei {short_window} Werten $[v_1, v_2, \\ldots, v_{{{short_window}}}]$ und Gewichten $[1, 2, \\ldots, {short_window}]$:

        $$
        WMA = \\frac{{1 \\cdot v_1 + 2 \\cdot v_2 + \\ldots + {short_window} \\cdot v_{{{short_window}}}}}  {{{int(short_window * (short_window + 1) / 2)}}}
        $$

        **Interpretation der Achsen:**
        - **rs_ratio > 100**: Sektor ist staerker als der Benchmark-Trend → rechte Haelfte.
        - **rs_ratio < 100**: Sektor ist schwaecher als der Benchmark-Trend → linke Haelfte.
        - **rs_momentum > 100**: RS-Ratio steigt (relative Staerke nimmt zu) → obere Haelfte.
        - **rs_momentum < 100**: RS-Ratio faellt (relative Staerke nimmt ab) → untere Haelfte.
        """
    )
    st.dataframe(export_data, use_container_width=True, hide_index=True)
    st.download_button(
        label="CSV herunterladen",
        data=rotation_timeseries_csv,
        file_name="rs_zeitreihen_export.csv",
        mime="text/csv",
    )

display_snapshot = latest_snapshot[
    [
        "symbol",
        "sector_name",
        "rs_ratio",
        "rs_momentum",
        "quadrant",
        "historical_volatility",
        "volatility_signal",
    ]
].rename(
    columns={
        "symbol": "Ticker",
        "sector_name": "Sektor",
        "rs_ratio": "JdK RS-Ratio",
        "rs_momentum": "JdK RS-Momentum",
        "quadrant": "Quadrant",
        "historical_volatility": "Historische Volatilitaet",
        "volatility_signal": "Vola-Signal",
    }
)

display_snapshot["JdK RS-Ratio"] = display_snapshot["JdK RS-Ratio"].round(2)
display_snapshot["JdK RS-Momentum"] = display_snapshot["JdK RS-Momentum"].round(2)
display_snapshot["Historische Volatilitaet"] = (display_snapshot["Historische Volatilitaet"] * 100).round(2)

st.dataframe(display_snapshot, use_container_width=True, hide_index=True)

st.markdown(
    """
    **Berechnungslogik**

    - X-Achse: JdK RS-Ratio auf Basis Sektor-ETF geteilt durch SPY, mit WMA-Glaettung und Normierung auf 100.
    - Y-Achse: JdK RS-Momentum als Verhaeltnis von RS-Ratio zu seinem kurzen WMA, ebenfalls auf 100 normiert.
    - Kreisfarbe: annualisierte historische Volatilitaet aus logarithmischen Tagesrenditen ueber ein rollierendes Fenster.
    """
)

with st.expander("Erklaerung der Stellschrauben", expanded=False):
    st.markdown(
        f"""
        **1. Kursbasis**

        - `adjclose`: um Dividenden und Splits bereinigter Schlusskurs. Fuer ETFs in der Regel die bessere Wahl.
        - `close`: roher Schlusskurs. Kann sinnvoll sein, wenn du bewusst ohne Adjustments arbeiten willst.

        **2. Kurzer WMA ({short_window})**

        - Das ist die schnelle Glaettung im Signal.
        - Kleinere Werte: schneller, aber unruhiger.
        - Groessere Werte: ruhiger, aber traeger.
        - Bei nur etwa 50 Tagen Historie sollte dieser Wert eher klein bleiben.

        **3. Langer WMA ({long_window})**

        - Dieser Wert definiert den langsameren Vergleichsmassstab fuer die Normierung des RS-Signals.
        - Wenn du ihn erhoehst, wird die Matrix stabiler, braucht aber mehr Historie.
        - Fachlich ist das die wichtigste Stellschraube fuer den Trade-off zwischen Robustheit und Fruehindikator.

        **4. HV-Fenster ({volatility_window})**

        - Bestimmt, ueber wie viele Tage die historische Volatilitaet berechnet wird.
        - Kurzes Fenster: die Farbe springt schneller.
        - Langes Fenster: die Farbe ist stabiler, reagiert aber spaeter auf Stressphasen.

        **5. HV-Schwellen ({volatility_threshold_low:.0%} / {volatility_threshold_high:.0%})**

        - Unter der unteren Schwelle: Gruen.
        - Zwischen beiden Schwellen: Orange.
        - Oberhalb der oberen Schwelle: Rot.
        - Das veraendert nicht die Position im Quadranten, sondern nur die Risikofarbe.

        **6. Lookback Tage ({lookback_days})**

        - Das ist nur die Laenge des geladenen Datenfensters.
        - Mehr Lookback heisst nicht automatisch bessere Signale, wenn die echte Historie im View ohnehin kurz ist.
        - Mit eurer aktuellen Datenlage ist dieser Parameter vor allem eine technische Obergrenze.
        - Beispiel: Wenn 400 Tage angefordert werden, im View aber nur 100 Handelstage vorhanden sind, zeigt die Seite explizit an, dass effektiv nur diese 100 Tage verwendet wurden.

        **7. Tail im Chart ({tail_days})**

        - Zeigt die letzten Bewegungspunkte pro Sektor als Spur.
        - Kleinerer Wert: saubereres Chartbild.
        - Groesserer Wert: mehr Bewegungshistorie, aber schneller unuebersichtlich.

        **8. Mindesthistorie**

        - Fuer die aktuelle Parametrisierung braucht die Seite mindestens `{min_history_needed}` Handelstage.
        - Dieser Wert ergibt sich aus langer WMA plus mehrfacher kurzer Glaettung fuer RS-Ratio und RS-Momentum.
        - Wenn weniger Daten vorhanden sind, wird die Matrix absichtlich gestoppt statt scheinbar praezise, aber instabile Werte zu zeigen.
        - Zusaetzlich unterscheidet die Seite jetzt zwischen angefordertem Lookback, tatsaechlich verfuegbarer Historie im View und nach Warmup wirklich nutzbarer Historie.

        **Praktische Empfehlung fuer eure aktuelle Datenlage**

        - Bei rund 50 Tagen Historie sind kleine Fenster wie `5 / 15` sinnvoll.
        - Wenn spaeter mehr Historie verfuegbar ist, kann man sich schrittweise Richtung `10 / 30` bewegen.
        - Fuer den Start ist Stabilitaet wichtiger als maximale Naehe zur Langfrist-Spezifikation.
        """
    )