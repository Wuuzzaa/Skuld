import logging
import pandas as pd
from flask import Blueprint, render_template, request
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.flask_table_helper import dataframe_to_html
from src.married_put_finder import (
    MONTH_MAP,
    calculate_collar_metrics,
    calculate_put_only_metrics,
    filter_strikes_by_moneyness,
    get_month_options,
    get_month_options_with_dte,
)

logger = logging.getLogger(__name__)
bp = Blueprint("position_insurance", __name__, url_prefix="/position-insurance")


@bp.route("/", methods=["GET", "POST"])
def index():
    symbol = ""
    cost_basis = 0.0
    puts_html = None
    calls_html = None
    current_price = 0.0
    error_msg = None
    put_month_options = []
    call_month_options = []
    selected_put_month = ""
    selected_call_month = ""
    moneyness = "all"

    try:
        put_month_options = get_month_options_with_dte()
        call_month_options = get_month_options()
    except Exception as e:
        logger.warning(f"Could not load month options: {e}")

    if request.method == "POST":
        symbol = request.form.get("symbol", "").upper().strip()
        try:
            cost_basis = float(request.form.get("cost_basis", 0.0))
        except (ValueError, TypeError):
            cost_basis = 0.0
        selected_put_month = request.form.get("put_month", "")
        selected_call_month = request.form.get("call_month", "")
        moneyness = request.form.get("moneyness", "all")

        if symbol:
            try:
                sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'position_insurance_puts.sql'
                puts_df = select_into_dataframe(sql_file_path=sql_file_path,
                                                params={"symbol": symbol, "put_month": selected_put_month})
                if puts_df is not None and not puts_df.empty:
                    if 'live_stock_price' in puts_df.columns:
                        current_price = float(puts_df['live_stock_price'].iloc[0])
                    puts_df = filter_strikes_by_moneyness(puts_df, moneyness, current_price)
                    puts_df = calculate_put_only_metrics(puts_df, cost_basis)
                    puts_html = dataframe_to_html(puts_df, symbol_column='symbol')

                sql_file_path_calls = PATH_DATABASE_QUERY_FOLDER / 'position_insurance_calls.sql'
                calls_df = select_into_dataframe(sql_file_path=sql_file_path_calls,
                                                 params={"symbol": symbol, "call_month": selected_call_month})
                if calls_df is not None and not calls_df.empty:
                    calls_df = calculate_collar_metrics(calls_df, cost_basis, current_price)
                    calls_html = dataframe_to_html(calls_df, symbol_column='symbol')

            except Exception as e:
                logger.exception("Error loading position insurance data")
                error_msg = str(e)

    return render_template("pages/position_insurance.html",
                           active_page="position_insurance",
                           symbol=symbol,
                           cost_basis=cost_basis,
                           current_price=current_price,
                           puts_html=puts_html,
                           calls_html=calls_html,
                           error_msg=error_msg,
                           put_month_options=put_month_options,
                           call_month_options=call_month_options,
                           selected_put_month=selected_put_month,
                           selected_call_month=selected_call_month,
                           moneyness=moneyness,
                           MONTH_MAP=MONTH_MAP)
