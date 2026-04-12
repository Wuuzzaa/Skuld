import logging
import pandas as pd
from flask import Blueprint, render_template, request
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.flask_table_helper import dataframe_to_html

logger = logging.getLogger(__name__)
bp = Blueprint("married_puts", __name__, url_prefix="/married-puts")

DEFAULTS = {
    "max_results": 50,
    "min_roi": 3.0,
    "max_roi": 7.0,
    "strike_multiplier": 1.2,
    "min_dte": 30,
    "max_dte": 500,
    "chk_contender": True,
    "chk_challenger": True,
    "chk_champion": True,
    "show_all": False,
    "symbol_filter": "All",
}


@bp.route("/")
def index():
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

    def gbool(key):
        val = request.args.get(key)
        if val is None:
            return DEFAULTS[key]
        return val.lower() in ("true", "1", "on")

    params = {
        "max_results": gint("max_results"),
        "min_roi": gfloat("min_roi"),
        "max_roi": gfloat("max_roi"),
        "strike_multiplier": gfloat("strike_multiplier"),
        "min_dte": gint("min_dte"),
        "max_dte": gint("max_dte"),
        "chk_contender": gbool("chk_contender"),
        "chk_challenger": gbool("chk_challenger"),
        "chk_champion": gbool("chk_champion"),
        "show_all": gbool("show_all"),
        "symbol_filter": request.args.get("symbol_filter", "All"),
    }

    table_html = None
    result_count = 0
    error_msg = None
    symbols = ["All"]

    try:
        sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'married_put.sql'
        df = select_into_dataframe(sql_file_path=sql_file_path,
                                   params={"strike_multiplier": params["strike_multiplier"]})

        if df is not None and not df.empty:
            df = df[
                (df['roi_annualized_pct'] >= params["min_roi"]) &
                (df['roi_annualized_pct'] <= params["max_roi"])
            ]
            df = df[
                (df['days_to_expiration'] >= params["min_dte"]) &
                (df['days_to_expiration'] <= params["max_dte"])
            ]

            if not params["show_all"]:
                selected_statuses = []
                if params["chk_contender"]:
                    selected_statuses.append("Dividend Contender")
                if params["chk_challenger"]:
                    selected_statuses.append("Dividend Challenger")
                if params["chk_champion"]:
                    selected_statuses.append("Dividend Champion")
                if selected_statuses:
                    df = df[df['Classification'].isin(selected_statuses)]

            symbols = ["All"] + sorted(df['symbol'].unique().tolist())

            if params["symbol_filter"] != "All":
                df = df[df['symbol'] == params["symbol_filter"]]

            df = df.head(params["max_results"])
            result_count = len(df)
            table_html = dataframe_to_html(df, symbol_column='symbol')
        else:
            error_msg = "No data found."

    except Exception as e:
        logger.exception("Error loading married puts")
        error_msg = str(e)

    return render_template("pages/married_puts.html",
                           active_page="married_puts",
                           params=params,
                           table_html=table_html,
                           result_count=result_count,
                           error_msg=error_msg,
                           symbols=symbols)
