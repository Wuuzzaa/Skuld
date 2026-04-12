import logging
from flask import Blueprint, render_template
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.flask_table_helper import dataframe_to_html

logger = logging.getLogger(__name__)
bp = Blueprint("analyst_prices", __name__, url_prefix="/analyst-prices")


@bp.route("/")
def index():
    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'analyst_prices.sql'
    df = select_into_dataframe(sql_file_path=sql_file_path)
    df = df.rename(columns={
        "close": "Price",
        "analyst_mean_target": "Mean Analyst Target",
        "target-close$": "Difference ($) analyst target and price",
        "target-close%": "Difference (%) analyst target and price"
    })
    table_html = dataframe_to_html(df, symbol_column='symbol')
    return render_template("pages/analyst_prices.html",
                           active_page="analyst_prices",
                           table_html=table_html,
                           result_count=len(df))
