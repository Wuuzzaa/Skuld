import streamlit as st

from src.sector_rotation import (
    RotationParameters,
    SECTOR_ETFS,
    build_latest_sector_snapshot,
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
        short_window = st.slider("Kurzer WMA", min_value=3, max_value=12, value=5)

    with col2:
        long_window = st.slider("Langer WMA", min_value=8, max_value=30, value=15)
        volatility_window = st.slider("HV-Fenster", min_value=10, max_value=30, value=20)

    with col3:
        volatility_threshold_low = st.number_input(
            "HV Schwelle Gruen/Orange",
            min_value=0.05,
            max_value=0.50,
            value=0.15,
            step=0.01,
            format="%.2f",
        )
        volatility_threshold_high = st.number_input(
            "HV Schwelle Orange/Rot",
            min_value=0.10,
            max_value=1.00,
            value=0.30,
            step=0.01,
            format="%.2f",
        )

    with col4:
        lookback_days = st.slider("Lookback Tage", min_value=50, max_value=240, value=120, step=10)
        tail_days = st.slider("Tail im Chart", min_value=3, max_value=12, value=6)

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

latest_snapshot = build_latest_sector_snapshot(rotation_data)
latest_date = latest_snapshot["date"].max()

metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
metric_col1.metric("Stand", latest_date.strftime("%Y-%m-%d"))
metric_col2.metric("Benchmark", parameters.benchmark_symbol)
metric_col3.metric("Sektoren mit Signal", int(latest_snapshot["symbol"].nunique()))
metric_col4.metric("Min. Historie", f"{min_history_needed} Tage")

figure = build_rotation_figure(rotation_data, parameters)
st.plotly_chart(figure, use_container_width=True)

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