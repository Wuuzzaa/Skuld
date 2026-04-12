import logging
from flask import Blueprint, render_template, request
from src.monte_carlo_simulation import UniversalOptionsMonteCarloSimulator

logger = logging.getLogger(__name__)
bp = Blueprint("expected_value", __name__, url_prefix="/expected-value")

OPTION_TYPES = ["Call Bought", "Call Sold", "Put Bought", "Put Sold"]

DEFAULT_OPTIONS = [
    {"strike": 150.0, "premium": 3.47, "type": "Put Sold"},
    {"strike": 145.0, "premium": 1.72, "type": "Put Sold"},
]


@bp.route("/", methods=["GET", "POST"])
def index():
    result = None
    error_msg = None
    options = DEFAULT_OPTIONS.copy()

    # Simulation parameters with defaults
    sim_params = {
        "num_simulations": 100000,
        "current_price": 170.94,
        "dte": 63,
        "volatility": 0.42,
        "risk_free_rate": 0.03,
        "random_seed": 42,
        "dividend_yield": 0.0,
        "transaction_cost_per_contract": 2.0,
        "iv_correction": "auto",
    }

    if request.method == "POST":
        # Read simulation params from form
        def gfloat(key, default):
            try:
                return float(request.form.get(key, default))
            except (ValueError, TypeError):
                return default

        def gint(key, default):
            try:
                return int(request.form.get(key, default))
            except (ValueError, TypeError):
                return default

        sim_params = {
            "num_simulations": gint("num_simulations", 100000),
            "current_price": gfloat("current_price", 170.94),
            "dte": gint("dte", 63),
            "volatility": gfloat("volatility", 0.42),
            "risk_free_rate": gfloat("risk_free_rate", 0.03),
            "random_seed": gint("random_seed", 42),
            "dividend_yield": gfloat("dividend_yield", 0.0),
            "transaction_cost_per_contract": gfloat("transaction_cost_per_contract", 2.0),
            "iv_correction": request.form.get("iv_correction", "auto"),
        }

        # Read dynamic options from form
        strikes = request.form.getlist("strike")
        premiums = request.form.getlist("premium")
        types = request.form.getlist("option_type")

        options = []
        for s, p, t in zip(strikes, premiums, types):
            try:
                options.append({"strike": float(s), "premium": float(p), "type": t})
            except (ValueError, TypeError):
                pass

        if not options:
            options = DEFAULT_OPTIONS.copy()

        if "simulate" in request.form:
            try:
                option_defs = []
                for opt in options:
                    is_call = opt["type"] in ["Call Bought", "Call Sold"]
                    is_long = opt["type"] in ["Call Bought", "Put Bought"]
                    option_defs.append({
                        "strike": opt["strike"],
                        "premium": opt["premium"],
                        "is_call": is_call,
                        "is_long": is_long,
                    })

                simulator = UniversalOptionsMonteCarloSimulator(
                    num_simulations=sim_params["num_simulations"],
                    random_seed=sim_params["random_seed"],
                    current_price=sim_params["current_price"],
                    dte=sim_params["dte"],
                    volatility=sim_params["volatility"],
                    risk_free_rate=sim_params["risk_free_rate"],
                    dividend_yield=sim_params["dividend_yield"],
                    iv_correction=sim_params["iv_correction"],
                )
                expected_value = simulator.calculate_expected_value(options=option_defs)
                result = {
                    "expected_value": expected_value,
                    "corrected_volatility": simulator.volatility,
                    "iv_correction_factor": simulator.iv_correction_factor,
                    "time_to_expiration": simulator.time_to_expiration,
                    **sim_params,
                }
            except Exception as e:
                logger.exception("Error running Monte Carlo simulation")
                error_msg = str(e)

    return render_template("pages/expected_value.html",
                           active_page="expected_value",
                           sim_params=sim_params,
                           options=options,
                           option_types=OPTION_TYPES,
                           result=result,
                           error_msg=error_msg)
