import logging
import json
from flask import Blueprint, render_template, request
from src.sector_rotation import (
    RotationParameters,
    SECTOR_ETFS,
    build_latest_sector_snapshot,
    build_rotation_figure,
    calculate_sector_rotation,
    load_sector_rotation_price_history,
    required_history_length,
)
from src.flask_table_helper import dataframe_to_html

logger = logging.getLogger(__name__)
bp = Blueprint("sector_rotation", __name__, url_prefix="/sector-rotation")

DEFAULTS = {
    "price_column": "adjclose",
    "short_window": 5,
    "long_window": 15,
    "volatility_window": 20,
    "volatility_threshold_low": 0.15,
    "volatility_threshold_high": 0.30,
    "lookback_days": 120,
    "tail_days": 6,
}


@bp.route("/")
def index():
    def gstr(key):
        return request.args.get(key, DEFAULTS[key])

    def gint(key):
        try:
            return int(request.args.get(key, DEFAULTS[key]))
        except (ValueError, TypeError):
            return DEFAULTS[key]

    def gfloat(key):
        try:
            return float(request.args.get(key, DEFAULTS[key]))
        except (ValueError, TypeError):
            return DEFAULTS[key]

    params = {
        "price_column": gstr("price_column"),
        "short_window": gint("short_window"),
        "long_window": gint("long_window"),
        "volatility_window": gint("volatility_window"),
        "volatility_threshold_low": gfloat("volatility_threshold_low"),
        "volatility_threshold_high": gfloat("volatility_threshold_high"),
        "lookback_days": gint("lookback_days"),
        "tail_days": gint("tail_days"),
    }

    error_msg = None
    chart_json = None
    snapshot_html = None
    warnings = []

    if params["long_window"] <= params["short_window"]:
        error_msg = "Der lange WMA muss größer als der kurze WMA sein."
    else:
        try:
            parameters = RotationParameters(**params)
            price_history = load_sector_rotation_price_history(parameters)
            rotation_data = calculate_sector_rotation(price_history, parameters)

            available_symbols = set(price_history["symbol"].unique()) if not price_history.empty else set()
            missing_symbols = [s for s in SECTOR_ETFS if s not in available_symbols]
            if missing_symbols:
                warnings.append(f"Fehlende Symbole: {', '.join(missing_symbols)}")

            if not rotation_data.empty:
                fig = build_rotation_figure(rotation_data, parameters)
                chart_json = json.dumps(fig, cls=_PlotlyEncoder())

                snapshot_df = build_latest_sector_snapshot(rotation_data)
                if snapshot_df is not None and not snapshot_df.empty:
                    snapshot_html = dataframe_to_html(snapshot_df, symbol_column='symbol' if 'symbol' in snapshot_df.columns else snapshot_df.columns[0])
            else:
                warnings.append("Keine Rotationsdaten verfügbar.")

        except Exception as e:
            logger.exception("Error calculating sector rotation")
            error_msg = str(e)

    return render_template("pages/sector_rotation.html",
                           active_page="sector_rotation",
                           params=params,
                           chart_json=chart_json,
                           snapshot_html=snapshot_html,
                           error_msg=error_msg,
                           warnings=warnings)


class _PlotlyEncoder(json.JSONEncoder):
    """JSON encoder that handles Plotly figures."""
    def default(self, obj):
        try:
            import plotly.io as pio
            return json.loads(pio.to_json(obj))
        except Exception:
            return super().default(obj)
