from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go


SECTOR_ETFS = {
    "XLC": "Kommunikation",
    "XLY": "Nicht-Basiskonsumgueter",
    "XLP": "Basiskonsumgueter",
    "XLE": "Energie",
    "XLF": "Finanzen",
    "XLV": "Gesundheit",
    "XLI": "Industrie",
    "XLB": "Materialien",
    "XLRE": "Immobilien",
    "XLK": "Technologie",
    "XLU": "Versorger",
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


def required_history_length(parameters: RotationParameters) -> int:
    return parameters.long_window + (3 * parameters.short_window) - 2


def build_sector_rotation_query(symbols: list[str], lookback_days: int) -> str:
    quoted_symbols = ", ".join(f"'{symbol}'" for symbol in symbols)
    return f'''
        SELECT
            date,
            symbol,
            "close",
            adjclose
        FROM "StockPricesYahooHistory"
        WHERE symbol IN ({quoted_symbols})
          AND date >= CURRENT_DATE - INTERVAL '{int(lookback_days)} day'
        ORDER BY date ASC, symbol ASC
    '''


def load_sector_rotation_price_history(parameters: RotationParameters) -> pd.DataFrame:
    from src.database import select_into_dataframe

    symbols = [parameters.benchmark_symbol, *SECTOR_ETFS.keys()]
    query = build_sector_rotation_query(symbols=symbols, lookback_days=parameters.lookback_days)
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

    for symbol, sector_name in SECTOR_ETFS.items():
        if symbol not in pivot.columns:
            continue

        sector_prices = pivot[symbol]
        rs_raw = sector_prices / benchmark_prices
        rs_smooth = rolling_wma(rs_raw, parameters.short_window)
        rs_norm = rs_smooth / rolling_wma(rs_smooth, parameters.long_window)
        rs_ratio = rolling_wma(rs_norm, parameters.short_window) * 100
        rs_momentum = (rs_ratio / rolling_wma(rs_ratio, parameters.short_window)) * 100

        log_returns = np.log(sector_prices / sector_prices.shift(1))
        historical_volatility = log_returns.rolling(
            window=parameters.volatility_window,
            min_periods=parameters.volatility_window,
        ).std() * np.sqrt(252)

        symbol_frame = pd.DataFrame(
            {
                "date": pivot.index,
                "symbol": symbol,
                "sector_name": sector_name,
                "benchmark_symbol": parameters.benchmark_symbol,
                "price": sector_prices,
                "benchmark_price": benchmark_prices,
                "rs_raw": rs_raw,
                "rs_ratio": rs_ratio,
                "rs_momentum": rs_momentum,
                "historical_volatility": historical_volatility,
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
                "benchmark_symbol",
                "price",
                "benchmark_price",
                "rs_raw",
                "rs_ratio",
                "rs_momentum",
                "historical_volatility",
                "volatility_signal",
                "quadrant",
            ]
        )

    rotation = pd.concat(results, ignore_index=True)
    rotation = rotation.dropna(subset=["rs_ratio", "rs_momentum"]).reset_index(drop=True)
    return rotation


def build_latest_sector_snapshot(rotation_data: pd.DataFrame) -> pd.DataFrame:
    if rotation_data.empty:
        return rotation_data.copy()

    latest_snapshot = (
        rotation_data.sort_values(["symbol", "date"])
        .groupby("symbol", as_index=False)
        .tail(1)
        .sort_values("rs_ratio", ascending=False)
        .reset_index(drop=True)
    )
    latest_snapshot["volatility_pct"] = latest_snapshot["historical_volatility"] * 100
    return latest_snapshot


def build_rotation_figure(rotation_data: pd.DataFrame, parameters: RotationParameters) -> go.Figure:
    figure = go.Figure()

    axis_min = 94
    axis_max = 106

    figure.add_shape(
        type="rect",
        x0=100,
        y0=100,
        x1=axis_max,
        y1=axis_max,
        fillcolor="rgba(46, 139, 87, 0.10)",
        line_width=0,
    )
    figure.add_shape(
        type="rect",
        x0=100,
        y0=axis_min,
        x1=axis_max,
        y1=100,
        fillcolor="rgba(241, 196, 15, 0.10)",
        line_width=0,
    )
    figure.add_shape(
        type="rect",
        x0=axis_min,
        y0=axis_min,
        x1=100,
        y1=100,
        fillcolor="rgba(192, 57, 43, 0.10)",
        line_width=0,
    )
    figure.add_shape(
        type="rect",
        x0=axis_min,
        y0=100,
        x1=100,
        y1=axis_max,
        fillcolor="rgba(52, 152, 219, 0.10)",
        line_width=0,
    )

    figure.add_vline(x=100, line_width=1, line_dash="dash", line_color="#4a4a4a")
    figure.add_hline(y=100, line_width=1, line_dash="dash", line_color="#4a4a4a")

    quadrant_annotations = [
        (103.5, 105.4, "Leading"),
        (103.5, 94.6, "Weakening"),
        (96.5, 94.6, "Lagging"),
        (96.5, 105.4, "Improving"),
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
    latest_snapshot = build_latest_sector_snapshot(rotation_data)

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
            "range": [axis_min, axis_max],
            "zeroline": False,
        },
        yaxis={
            "title": "JdK RS-Momentum (Y-Achse)",
            "range": [axis_min, axis_max],
            "zeroline": False,
            "scaleanchor": "x",
            "scaleratio": 1,
        },
    )
    return figure