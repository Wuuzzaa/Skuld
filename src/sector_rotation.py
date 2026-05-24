from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go


SECTOR_ETFS = {
    "XLC": {"name": "Kommunikation", "full_name": "Communication Services Select Sector SPDR Fund", "isin": "US81369Y8030"},
    "XLY": {"name": "Nicht-Basiskonsumgueter", "full_name": "Consumer Discretionary Select Sector SPDR Fund", "isin": "US81369Y5069"},
    "XLP": {"name": "Basiskonsumgueter", "full_name": "Consumer Staples Select Sector SPDR Fund", "isin": "US81369Y7070"},
    "XLE": {"name": "Energie", "full_name": "Energy Select Sector SPDR Fund", "isin": "US81369Y2033"},
    "XLF": {"name": "Finanzen", "full_name": "Financial Select Sector SPDR Fund", "isin": "US81369Y4016"},
    "XLV": {"name": "Gesundheit", "full_name": "Health Care Select Sector SPDR Fund", "isin": "US81369Y2090"},
    "XLI": {"name": "Industrie", "full_name": "Industrial Select Sector SPDR Fund", "isin": "US81369Y3056"},
    "XLB": {"name": "Materialien", "full_name": "Materials Select Sector SPDR Fund", "isin": "US81369Y1001"},
    "XLRE": {"name": "Immobilien", "full_name": "Real Estate Select Sector SPDR Fund", "isin": "US81369Y8618"},
    "XLK": {"name": "Technologie", "full_name": "Technology Select Sector SPDR Fund", "isin": "US81369Y6059"},
    "XLU": {"name": "Versorger", "full_name": "Utilities Select Sector SPDR Fund", "isin": "US81369Y8865"},
}

VOLATILITY_COLORS = {
    "Gruen": "#2e8b57",
    "Orange": "#f39c12",
    "Rot": "#c0392b",
    "Unbekannt": "#7f8c8d",
}

QUADRANT_LABELS = {
    "Leading": "Leading",
    "Weakening": "Weakening",
    "Lagging": "Lagging",
    "Improving": "Improving",
}


@dataclass(frozen=True)
class RotationParameters:
    benchmark_symbol: str = "SPY"
    price_column: str = "adjclose"
    short_window: int = 5
    long_window: int = 15
    volatility_window: int = 20
    volatility_threshold_low: float = 0.15
    volatility_threshold_high: float = 0.30
    lookback_days: int = 120
    tail_days: int = 6
    # RRG Score weights (must sum to 1.0)
    rs_weight: float = 0.60
    momentum_weight: float = 0.40
    # Momentum Persistence Score (MPS) — consecutive months above/below 100
    mps_long_months: int = 8   # months required for "strong" persistence
    mps_short_months: int = 6  # months required for "moderate" persistence
    # Capital allocation
    allocated_capital: float = 0.0  # total capital to allocate (0 = disabled)
    # SMA200 lookback (needs more history)
    sma200_days: int = 200


def required_history_length(parameters: RotationParameters) -> int:
    return parameters.long_window + (3 * parameters.short_window) - 2


def build_sector_rotation_query(symbols: list[str], lookback_days: int) -> str:
    quoted_symbols = ", ".join(f"'{symbol}'" for symbol in symbols)
    return f'''
        SELECT
            snapshot_date AS date,
            symbol,
            "close",
            adjclose
        FROM "StockPricesYahooHistoryDaily"
        WHERE symbol IN ({quoted_symbols})
          AND snapshot_date >= CURRENT_DATE - INTERVAL '{int(lookback_days)} day'
        ORDER BY snapshot_date ASC, symbol ASC
    '''


def load_sector_rotation_price_history(parameters: RotationParameters) -> pd.DataFrame:
    from src.database import select_into_dataframe

    symbols = [parameters.benchmark_symbol, *SECTOR_ETFS.keys()]
    # Use max of lookback_days and sma200_days + generous buffer for trading days vs calendar days
    effective_lookback = max(parameters.lookback_days, int(parameters.sma200_days * 1.6) + 30)
    query = build_sector_rotation_query(symbols=symbols, lookback_days=effective_lookback)
    return select_into_dataframe(query=query)


def weighted_moving_average(values: np.ndarray) -> float:
    if np.isnan(values).any():
        return np.nan

    weights = np.arange(1, len(values) + 1, dtype=float)
    return float(np.dot(values, weights) / weights.sum())


def rolling_wma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).apply(weighted_moving_average, raw=True)


def classify_volatility_signal(
    volatility: float,
    threshold_low: float,
    threshold_high: float,
) -> str:
    if pd.isna(volatility):
        return "Unbekannt"
    if volatility < threshold_low:
        return "Gruen"
    if volatility < threshold_high:
        return "Orange"
    return "Rot"


def classify_quadrant(rs_ratio: float, rs_momentum: float) -> str:
    if pd.isna(rs_ratio) or pd.isna(rs_momentum):
        return "Unbekannt"
    if rs_ratio >= 100 and rs_momentum >= 100:
        return QUADRANT_LABELS["Leading"]
    if rs_ratio >= 100 and rs_momentum < 100:
        return QUADRANT_LABELS["Weakening"]
    if rs_ratio < 100 and rs_momentum < 100:
        return QUADRANT_LABELS["Lagging"]
    return QUADRANT_LABELS["Improving"]


def calculate_sector_rotation(
    price_history: pd.DataFrame,
    parameters: RotationParameters,
) -> pd.DataFrame:
    required_columns = {"date", "symbol", parameters.price_column}
    missing_columns = required_columns.difference(price_history.columns)
    if missing_columns:
        missing_str = ", ".join(sorted(missing_columns))
        raise ValueError(f"Price history is missing required columns: {missing_str}")

    data = price_history.copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data.sort_values(["date", "symbol"])

    pivot = (
        data.pivot_table(
            index="date",
            columns="symbol",
            values=parameters.price_column,
            aggfunc="last",
        )
        .sort_index()
    )

    if parameters.benchmark_symbol not in pivot.columns:
        raise ValueError(f"Benchmark symbol {parameters.benchmark_symbol} is not available in the selected dataset")

    benchmark_prices = pivot[parameters.benchmark_symbol]
    results: list[pd.DataFrame] = []

    for symbol, sector_info in SECTOR_ETFS.items():
        if symbol not in pivot.columns:
            continue

        sector_name = sector_info["name"]
        sector_prices = pivot[symbol]
        rs_raw = sector_prices / benchmark_prices
        rs_smooth = rolling_wma(rs_raw, parameters.short_window)
        rs_smooth_long = rolling_wma(rs_smooth, parameters.long_window)
        rs_norm = rs_smooth / rs_smooth_long
        rs_ratio = rolling_wma(rs_norm, parameters.short_window) * 100
        rs_ratio_smooth = rolling_wma(rs_ratio, parameters.short_window)
        rs_momentum = (rs_ratio / rs_ratio_smooth) * 100

        log_returns = np.log(sector_prices / sector_prices.shift(1))
        historical_volatility = log_returns.rolling(
            window=parameters.volatility_window,
            min_periods=parameters.volatility_window,
        ).std() * np.sqrt(252)

        # SMA200 signal
        sma200 = sector_prices.rolling(window=parameters.sma200_days, min_periods=parameters.sma200_days).mean()
        sma200_signal = sector_prices > sma200  # True = above SMA200

        symbol_frame = pd.DataFrame(
            {
                "date": pivot.index,
                "symbol": symbol,
                "sector_name": sector_name,
                "etf_name": sector_info["full_name"],
                "isin": sector_info["isin"],
                "benchmark_symbol": parameters.benchmark_symbol,
                "price": sector_prices,
                "benchmark_price": benchmark_prices,
                "rs_raw": rs_raw,
                "rs_smooth": rs_smooth,
                "rs_smooth_long": rs_smooth_long,
                "rs_norm": rs_norm,
                "rs_ratio": rs_ratio,
                "rs_ratio_smooth": rs_ratio_smooth,
                "rs_momentum": rs_momentum,
                "historical_volatility": historical_volatility,
                "sma200": sma200,
                "above_sma200": sma200_signal,
            }
        )
        symbol_frame["volatility_signal"] = symbol_frame["historical_volatility"].apply(
            classify_volatility_signal,
            args=(parameters.volatility_threshold_low, parameters.volatility_threshold_high),
        )
        symbol_frame["quadrant"] = symbol_frame.apply(
            lambda row: classify_quadrant(row["rs_ratio"], row["rs_momentum"]),
            axis=1,
        )
        results.append(symbol_frame)

    if not results:
        return pd.DataFrame(
            columns=[
                "date",
                "symbol",
                "sector_name",
                "etf_name",
                "isin",
                "benchmark_symbol",
                "price",
                "benchmark_price",
                "rs_raw",
                "rs_smooth",
                "rs_smooth_long",
                "rs_norm",
                "rs_ratio",
                "rs_ratio_smooth",
                "rs_momentum",
                "historical_volatility",
                "sma200",
                "above_sma200",
                "volatility_signal",
                "quadrant",
                "rrg_score",
                "mps_score",
                "mps_signal",
                "sma200_signal",
            ]
        )

    rotation = pd.concat(results, ignore_index=True)
    rotation = rotation.dropna(subset=["rs_ratio", "rs_momentum"]).reset_index(drop=True)

    # Calculate weighted RRG Score (normalized: RS-Ratio and Momentum centered at 100)
    rotation["rrg_score"] = (
        parameters.rs_weight * rotation["rs_ratio"]
        + parameters.momentum_weight * rotation["rs_momentum"]
    )

    # Calculate Momentum Persistence Score (MPS)
    # MPS counts consecutive months where RS-Ratio stays in same direction (above or below 100)
    rotation = _calculate_mps(rotation, parameters)

    return rotation


def _calculate_mps(rotation: pd.DataFrame, parameters: RotationParameters) -> pd.DataFrame:
    """Calculate Momentum Persistence Score per symbol.

    MPS = number of consecutive months the RS-Ratio has been above (positive) or below (negative) 100.
    Signal: 'strong' if |MPS| >= mps_long_months, 'moderate' if >= mps_short_months, else 'weak'.
    """
    trading_days_per_month = 21
    rotation["mps_score"] = 0.0
    rotation["mps_signal"] = "weak"

    for symbol in rotation["symbol"].unique():
        mask = rotation["symbol"] == symbol
        symbol_data = rotation.loc[mask].sort_values("date")

        if symbol_data.empty:
            continue

        # Sample monthly (every ~21 trading days) to count consecutive months
        rs_ratio_values = symbol_data["rs_ratio"].values
        dates = symbol_data["date"].values

        # Count consecutive days above/below 100 at the end of the series, convert to months
        if len(rs_ratio_values) == 0:
            continue

        latest_above = rs_ratio_values[-1] >= 100
        consecutive_days = 0
        for i in range(len(rs_ratio_values) - 1, -1, -1):
            if (rs_ratio_values[i] >= 100) == latest_above:
                consecutive_days += 1
            else:
                break

        consecutive_months = consecutive_days / trading_days_per_month
        mps_value = consecutive_months if latest_above else -consecutive_months

        # Determine signal
        abs_months = abs(mps_value)
        if abs_months >= parameters.mps_long_months:
            signal = "strong"
        elif abs_months >= parameters.mps_short_months:
            signal = "moderate"
        else:
            signal = "weak"

        # Assign to latest row only (snapshot use)
        latest_idx = symbol_data.index[-1]
        rotation.loc[latest_idx, "mps_score"] = round(mps_value, 1)
        rotation.loc[latest_idx, "mps_signal"] = signal

    return rotation


def build_latest_sector_snapshot(rotation_data: pd.DataFrame, parameters: RotationParameters | None = None) -> pd.DataFrame:
    if rotation_data.empty:
        return rotation_data.copy()

    latest_snapshot = (
        rotation_data.sort_values(["symbol", "date"])
        .groupby("symbol", as_index=False)
        .tail(1)
        .sort_values("rrg_score", ascending=False)
        .reset_index(drop=True)
    )
    latest_snapshot["volatility_pct"] = latest_snapshot["historical_volatility"] * 100

    # SMA200 signal as traffic light: "Gruen" (above), "Rot" (below)
    latest_snapshot["sma200_signal"] = latest_snapshot["above_sma200"].apply(
        lambda x: "Gruen" if x else "Rot"
    )

    # Capital allocation (equal weight among "Leading" quadrant ETFs, or all if none leading)
    if parameters and parameters.allocated_capital > 0:
        leading_mask = latest_snapshot["quadrant"] == "Leading"
        eligible = latest_snapshot[leading_mask] if leading_mask.any() else latest_snapshot
        per_etf = parameters.allocated_capital / len(eligible)
        latest_snapshot["investment_amount"] = 0.0
        latest_snapshot.loc[eligible.index, "investment_amount"] = per_etf
    else:
        latest_snapshot["investment_amount"] = 0.0

    return latest_snapshot


def build_rotation_figure(rotation_data: pd.DataFrame, parameters: RotationParameters) -> go.Figure:
    figure = go.Figure()

    x_axis_min = 94
    x_axis_max = 106

    if not rotation_data.empty:
        tail = (
            rotation_data.sort_values(["symbol", "date"])
            .groupby("symbol", as_index=False)
            .tail(parameters.tail_days)
        )
        y_data_min = tail["rs_momentum"].min()
        y_data_max = tail["rs_momentum"].max()
        y_data_range = y_data_max - y_data_min
        y_padding = max(y_data_range * 0.25, 0.5)
        y_axis_min = min(y_data_min - y_padding, 94)
        y_axis_max = max(y_data_max + y_padding, 106)
    else:
        y_axis_min = 94
        y_axis_max = 106

    figure.add_shape(
        type="rect",
        x0=100,
        y0=100,
        x1=x_axis_max,
        y1=y_axis_max,
        fillcolor="rgba(46, 139, 87, 0.10)",
        line_width=0,
    )
    figure.add_shape(
        type="rect",
        x0=100,
        y0=y_axis_min,
        x1=x_axis_max,
        y1=100,
        fillcolor="rgba(241, 196, 15, 0.10)",
        line_width=0,
    )
    figure.add_shape(
        type="rect",
        x0=x_axis_min,
        y0=y_axis_min,
        x1=100,
        y1=100,
        fillcolor="rgba(192, 57, 43, 0.10)",
        line_width=0,
    )
    figure.add_shape(
        type="rect",
        x0=x_axis_min,
        y0=100,
        x1=100,
        y1=y_axis_max,
        fillcolor="rgba(52, 152, 219, 0.10)",
        line_width=0,
    )

    figure.add_vline(x=100, line_width=1, line_dash="dash", line_color="#4a4a4a")
    figure.add_hline(y=100, line_width=1, line_dash="dash", line_color="#4a4a4a")

    quadrant_annotations = [
        (103.5, y_axis_max - 0.6, "Leading"),
        (103.5, y_axis_min + 0.6, "Weakening"),
        (96.5, y_axis_min + 0.6, "Lagging"),
        (96.5, y_axis_max - 0.6, "Improving"),
    ]
    for x_position, y_position, label in quadrant_annotations:
        figure.add_annotation(
            x=x_position,
            y=y_position,
            text=label,
            showarrow=False,
            font={"size": 13, "color": "#34495e"},
        )

    if rotation_data.empty:
        figure.update_layout(
            title="S&P 500 Sector Rotation",
            xaxis_title="JdK RS-Ratio",
            yaxis_title="JdK RS-Momentum",
            template="plotly_white",
        )
        return figure

    tail = (
        rotation_data.sort_values(["symbol", "date"])
        .groupby("symbol", as_index=False)
        .tail(parameters.tail_days)
    )
    latest_snapshot = build_latest_sector_snapshot(rotation_data, None)

    for symbol in latest_snapshot["symbol"]:
        path = tail[tail["symbol"] == symbol]
        latest_row = latest_snapshot[latest_snapshot["symbol"] == symbol].iloc[0]
        line_color = VOLATILITY_COLORS.get(latest_row["volatility_signal"], VOLATILITY_COLORS["Unbekannt"])
        hover_template = (
            "<b>%{text}</b><br>"
            "Sektor: %{customdata[0]}<br>"
            "RS-Ratio: %{x:.2f}<br>"
            "RS-Momentum: %{y:.2f}<br>"
            f"HV {parameters.volatility_window}d: %{{customdata[1]:.2f}}%<br>"
            "Quadrant: %{customdata[2]}<extra></extra>"
        )

        figure.add_trace(
            go.Scatter(
                x=path["rs_ratio"],
                y=path["rs_momentum"],
                mode="lines+markers",
                line={"color": line_color, "width": 2},
                marker={"size": 5, "color": line_color, "opacity": 0.45},
                name=symbol,
                showlegend=False,
                hoverinfo="skip",
            )
        )

        figure.add_trace(
            go.Scatter(
                x=[latest_row["rs_ratio"]],
                y=[latest_row["rs_momentum"]],
                mode="markers+text",
                text=[symbol],
                textposition="top center",
                marker={
                    "size": 20,
                    "color": line_color,
                    "line": {"color": "#ffffff", "width": 1.5},
                },
                name=symbol,
                customdata=[[
                    latest_row["sector_name"],
                    latest_row["volatility_pct"],
                    latest_row["quadrant"],
                ]],
                hovertemplate=hover_template,
                showlegend=False,
            )
        )

    figure.update_layout(
        title=f"S&P 500 Sector Rotation vs. {parameters.benchmark_symbol}",
        template="plotly_white",
        height=760,
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
        xaxis={
            "title": "JdK RS-Ratio (X-Achse)",
            "range": [x_axis_min, x_axis_max],
            "zeroline": False,
        },
        yaxis={
            "title": "JdK RS-Momentum (Y-Achse)",
            "range": [y_axis_min, y_axis_max],
            "zeroline": False,
        },
    )
    return figure