import logging
from flask import Blueprint, render_template
from src.database import select_into_dataframe
from src.flask_table_helper import dataframe_to_html

logger = logging.getLogger(__name__)
bp = Blueprint("data_logs", __name__, url_prefix="/data-logs")


@bp.route("/")
def index():
    table_html = None
    error_msg = None

    try:
        df = select_into_dataframe('SELECT * FROM "DataChangeLogs" ORDER BY timestamp DESC')
        table_html = dataframe_to_html(df, symbol_column='table_name')
    except Exception as e:
        logger.exception("Error loading DataChangeLogs")
        error_msg = str(e)

    return render_template("pages/data_logs.html",
                           active_page="data_logs",
                           table_html=table_html,
                           error_msg=error_msg)
