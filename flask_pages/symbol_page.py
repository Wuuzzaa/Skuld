import logging
from flask import Blueprint, render_template, request
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.flask_table_helper import dataframe_to_html

logger = logging.getLogger(__name__)
bp = Blueprint("symbol_page", __name__, url_prefix="/symbol")


@bp.route("/")
def index():
    # Load symbol list
    symbols_df = select_into_dataframe(query='SELECT DISTINCT symbol FROM "OptionDataMerged" ORDER BY symbol ASC')
    symbol_list = symbols_df["symbol"].tolist() if symbols_df is not None and not symbols_df.empty else []

    selected_symbol = request.args.get("symbol", "")

    fundamental_html = None
    iv_html = None
    technical_html = None

    if selected_symbol:
        params = {"symbol": selected_symbol}
        try:
            df = select_into_dataframe(sql_file_path=PATH_DATABASE_QUERY_FOLDER / 'symbolpage.sql', params=params)
            fundamental_html = dataframe_to_html(df, symbol_column='symbol')
        except Exception as e:
            logger.warning(f"Error loading fundamental data: {e}")

        try:
            df_iv = select_into_dataframe(sql_file_path=PATH_DATABASE_QUERY_FOLDER / 'iv_history_symbolpage.sql', params=params)
            iv_html = dataframe_to_html(df_iv, symbol_column='symbol')
        except Exception as e:
            logger.warning(f"Error loading IV history: {e}")

        try:
            df_ti = select_into_dataframe(sql_file_path=PATH_DATABASE_QUERY_FOLDER / 'technical_indicators_one_year_one_symbol.sql', params=params)
            technical_html = dataframe_to_html(df_ti, symbol_column='symbol')
        except Exception as e:
            logger.warning(f"Error loading technical indicators: {e}")

    return render_template("pages/symbol_page.html",
                           active_page="symbol_page",
                           symbol_list=symbol_list,
                           selected_symbol=selected_symbol,
                           fundamental_html=fundamental_html,
                           iv_html=iv_html,
                           technical_html=technical_html)
