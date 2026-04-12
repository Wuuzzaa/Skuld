import logging
from flask import Blueprint, render_template, request
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.flask_table_helper import dataframe_to_html
from src.multifactor_swingtrading_strategy import calculate_multifactor_swingtrading_strategy

logger = logging.getLogger(__name__)
bp = Blueprint("multifactor", __name__, url_prefix="/multifactor")

DEFAULTS = {
    "top_percentile_value_score": 20.0,
    "top_n": 50,
    "drop_missing_values": False,
    "drop_weak_value_factors": False,
}


@bp.route("/")
def index():
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

    def gbool(key):
        val = request.args.get(key)
        if val is None:
            return DEFAULTS[key]
        return val.lower() in ("true", "1", "on")

    params = {
        "top_percentile_value_score": gfloat("top_percentile_value_score"),
        "top_n": gint("top_n"),
        "drop_missing_values": gbool("drop_missing_values"),
        "drop_weak_value_factors": gbool("drop_weak_value_factors"),
    }

    table_html = None
    result_count = 0
    error_msg = None

    try:
        sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'multifactor_swingtrading.sql'
        df = select_into_dataframe(sql_file_path=sql_file_path)
        df = calculate_multifactor_swingtrading_strategy(
            df,
            top_percentile_value_score=params["top_percentile_value_score"],
            top_n=params["top_n"],
            drop_missing_values=params["drop_missing_values"],
            drop_weak_value_factors=params["drop_weak_value_factors"],
        )
        result_count = len(df)
        table_html = dataframe_to_html(df, symbol_column='symbol')
    except Exception as e:
        logger.exception("Error calculating multifactor strategy")
        error_msg = str(e)

    return render_template("pages/multifactor.html",
                           active_page="multifactor",
                           params=params,
                           table_html=table_html,
                           result_count=result_count,
                           error_msg=error_msg)
