import logging
from flask import Flask, render_template
from src.logger_config import setup_logging
from config import VERSION

# enable logging
setup_logging(component="flask", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(__name__)
logger.info("Start SKULD Flask App")

app = Flask(__name__)
app.secret_key = "skuld-secret-key-change-in-production"

# Inject version into all templates
@app.context_processor
def inject_globals():
    return {"version": VERSION}

# Register blueprints
from flask_pages.analyst_prices import bp as analyst_prices_bp
from flask_pages.spreads import bp as spreads_bp
from flask_pages.married_puts import bp as married_puts_bp
from flask_pages.position_insurance import bp as position_insurance_bp
from flask_pages.multifactor import bp as multifactor_bp
from flask_pages.sector_rotation import bp as sector_rotation_bp
from flask_pages.expected_value import bp as expected_value_bp
from flask_pages.symbol_page import bp as symbol_page_bp
from flask_pages.data_logs import bp as data_logs_bp

app.register_blueprint(analyst_prices_bp)
app.register_blueprint(spreads_bp)
app.register_blueprint(married_puts_bp)
app.register_blueprint(position_insurance_bp)
app.register_blueprint(multifactor_bp)
app.register_blueprint(sector_rotation_bp)
app.register_blueprint(expected_value_bp)
app.register_blueprint(symbol_page_bp)
app.register_blueprint(data_logs_bp)


@app.route("/")
def index():
    return render_template("index.html", active_page="home")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
