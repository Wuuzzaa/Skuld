import logging
import pandas as pd
from flask import Blueprint, render_template, request
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.flask_table_helper import dataframe_to_html
from src.spreads_calculation import get_page_spreads
from src.utils.option_utils import get_expiration_type

logger = logging.getLogger(__name__)
bp = Blueprint("spreads", __name__, url_prefix="/spreads")

DEFAULTS = {
    "show_monthly": True,
    "show_weekly": False,
    "show_daily": False,
    "show_only_positive_ev": True,
    "show_no_earnings": True,
    "delta_target": 0.2,
    "spread_width": 5,
    "option_type": "put",
    "min_day_volume": 20,
    "min_open_interest": 100,
    "min_sell_iv": 0.3,
    "max_sell_iv": 0.9,
    "min_max_profit": 80.0,
    "min_iv_rank": 0,
    "min_iv_percentile": 0,
}


def _get_params():
    """Read filter params from GET request, falling back to defaults."""
    def gbool(key):
        return request.args.get(key, str(DEFAULTS[key])).lower() in ("true", "1", "on")
    def gfloat(key):
        try:
            return float(request.args.get(key, DEFAULTS[key]))
        except (ValueError, TypeError):
            return DEFAULTS[key]
    def gint(key):
        try:
            return int(request.args.get(key, DEFAULTS[key]))
        except (ValueError, TypeError):
            return DEFAULTS[key]
    def gstr(key):
        return request.args.get(key, DEFAULTS[key])

    return {
        "show_monthly": gbool("show_monthly"),
        "show_weekly": gbool("show_weekly"),
        "show_daily": gbool("show_daily"),
        "show_only_positive_ev": gbool("show_only_positive_ev"),
        "show_no_earnings": gbool("show_no_earnings"),
        "delta_target": gfloat("delta_target"),
        "spread_width": gint("spread_width"),
        "option_type": gstr("option_type"),
        "min_day_volume": gint("min_day_volume"),
        "min_open_interest": gint("min_open_interest"),
        "min_sell_iv": gfloat("min_sell_iv"),
        "max_sell_iv": gfloat("max_sell_iv"),
        "min_max_profit": gfloat("min_max_profit"),
        "min_iv_rank": gint("min_iv_rank"),
        "min_iv_percentile": gint("min_iv_percentile"),
        "expiration_date": request.args.get("expiration_date", ""),
    }


@bp.route("/")
def index():
    params = _get_params()

    # Load expiration dates
    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'expiration_dte_asc.sql'
    dates_df = select_into_dataframe(sql_file_path=sql_file_path)

    # Filter dates by expiration type checkboxes
    def keep_row(row):
        t = get_expiration_type(row['expiration_date'])
        return (
            (t == "Monthly" and params["show_monthly"]) or
            (t == "Weekly" and params["show_weekly"]) or
            (t == "Daily" and params["show_daily"])
        )

    filtered_dates = dates_df[dates_df.apply(keep_row, axis=1)].copy()

    # Build DTE label list
    dte_labels = [
        (
            f"{int(row['days_to_expiration'])} DTE - "
            f"{pd.to_datetime(row['expiration_date']).strftime('%A')}  "
            f"{row['expiration_date']} - "
            f"{get_expiration_type(row['expiration_date'])}"
        )
        for _, row in filtered_dates.iterrows()
    ]

    # Determine selected expiration date
    expiration_date = params["expiration_date"]
    selected_label = ""
    if expiration_date and expiration_date in filtered_dates['expiration_date'].astype(str).values:
        idx = filtered_dates[filtered_dates['expiration_date'].astype(str) == expiration_date].index[0]
        pos = filtered_dates.index.get_loc(idx)
        selected_label = dte_labels[pos]
    elif len(dte_labels) > 0:
        selected_label = dte_labels[0]
        expiration_date = str(filtered_dates.iloc[0]['expiration_date'])

    table_html = None
    result_count = 0
    error_msg = None

    if not dte_labels:
        error_msg = "No expiration dates match the selected filters."
    elif expiration_date:
        try:
            query_params = {
                "expiration_date": expiration_date,
                "option_type": params["option_type"],
                "delta_target": params["delta_target"],
                "min_open_interest": params["min_open_interest"],
                "spread_width": params["spread_width"],
                "min_day_volume": params["min_day_volume"],
                "min_iv_rank": params["min_iv_rank"],
                "min_iv_percentile": params["min_iv_percentile"],
            }
            sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'spreads_input.sql'
            df = select_into_dataframe(sql_file_path=sql_file_path, params=query_params)
            spreads_df = get_page_spreads(df)

            # Apply filters
            filtered_df = spreads_df.copy()
            filtered_df = filtered_df[filtered_df['max_profit'] >= params["min_max_profit"]]
            if params["show_only_positive_ev"]:
                filtered_df = filtered_df[filtered_df['expected_value'] >= 0]

            today = pd.Timestamp.now().normalize()
            exp_ts = pd.Timestamp(expiration_date)
            if params["show_no_earnings"]:
                filtered_df = filtered_df[
                    ~(
                        (filtered_df['earnings_date'] > today) &
                        (filtered_df['earnings_date'] < exp_ts)
                    )
                ]

            filtered_df['earnings_date'] = pd.to_datetime(filtered_df['earnings_date']).dt.strftime('%d.%m.%Y')
            filtered_df = filtered_df[filtered_df['sell_iv'] >= params["min_sell_iv"]]
            filtered_df = filtered_df[filtered_df['sell_iv'] <= params["max_sell_iv"]]
            filtered_df.reset_index(drop=True, inplace=True)

            result_count = len(filtered_df)
            table_html = dataframe_to_html(filtered_df, symbol_column='symbol', page='spreads')
        except Exception as e:
            logger.exception("Error calculating spreads")
            error_msg = f"Error calculating spreads: {e}"

    filtered_dates_values = filtered_dates['expiration_date'].astype(str).tolist()

    return render_template(
        "pages/spreads.html",
        active_page="spreads",
        params=params,
        dte_labels=dte_labels,
        filtered_dates_values=filtered_dates_values,
        selected_label=selected_label,
        expiration_date=expiration_date,
        table_html=table_html,
        result_count=result_count,
        error_msg=error_msg,
        defaults=DEFAULTS,
    )
