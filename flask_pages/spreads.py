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
    "spread_width": 5.0,
    "option_type": "put",
    "min_day_volume": 20,
    "min_open_interest": 100,
    "min_sell_iv": 0.3,
    "max_sell_iv": 0.9,
    "min_max_profit": 80.0,
    "min_iv_rank": 0,
    "min_iv_percentile": 0,
    "expiration_date": "",
}

def _get_params():
    """Liest Filter-Parameter aus dem GET-Request mit Fallback auf Standardwerte."""
    params = DEFAULTS.copy()
    
    # Prüfen, ob überhaupt Parameter im Request sind (Formular wurde abgeschickt)
    is_form_submitted = len(request.args) > 0
    
    # Checkboxen/Booleans
    for key in ["show_monthly", "show_weekly", "show_daily", "show_only_positive_ev", "show_no_earnings"]:
        val = request.args.get(key)
        if val is not None:
            params[key] = val.lower() in ("true", "1", "on", "yes")
        elif is_form_submitted:
            # Falls das Formular abgeschickt wurde, aber das Feld fehlt, ist die Checkbox "aus"
            params[key] = False
            
    # Floats
    for key in ["delta_target", "spread_width", "min_sell_iv", "max_sell_iv", "min_max_profit"]:
        try:
            val = request.args.get(key)
            if val:
                params[key] = float(val)
        except (ValueError, TypeError):
            pass
            
    # Integers
    for key in ["min_day_volume", "min_open_interest", "min_iv_rank", "min_iv_percentile"]:
        try:
            val = request.args.get(key)
            if val:
                params[key] = int(val)
        except (ValueError, TypeError):
            pass
            
    # Strings
    if request.args.get("option_type"):
        params["option_type"] = request.args.get("option_type")
    if request.args.get("expiration_date"):
        params["expiration_date"] = request.args.get("expiration_date")
        
    return params

@bp.route("/")
def index():
    params = _get_params()
    
    # 1. Alle verfügbaren Ablaufdaten laden
    try:
        sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'expiration_dte_asc.sql'
        dates_df = select_into_dataframe(sql_file_path=sql_file_path)
    except Exception as e:
        logger.error(f"Fehler beim Laden der Ablaufdaten: {e}")
        return render_template("pages/spreads.html", error_msg=f"Datenbankfehler: {e}", params=params, defaults=DEFAULTS)

    if dates_df.empty:
        return render_template("pages/spreads.html", error_msg="Keine Ablaufdaten in der Datenbank gefunden.", params=params, defaults=DEFAULTS)

    # 2. Ablaufdaten basierend auf Typ (Monthly, Weekly, Daily) filtern
    def is_date_allowed(row):
        t = get_expiration_type(row['expiration_date'])
        if t == "Monthly" and params["show_monthly"]: return True
        if t == "Weekly" and params["show_weekly"]: return True
        if t == "Daily" and params["show_daily"]: return True
        return False

    filtered_dates = dates_df[dates_df.apply(is_date_allowed, axis=1)].copy()
    
    # 3. Dropdown-Labels und Werte vorbereiten
    dte_labels = []
    filtered_dates_values = []
    for _, row in filtered_dates.iterrows():
        date_str = str(row['expiration_date'])
        dte = int(row['days_to_expiration'])
        day_name = pd.to_datetime(date_str).strftime('%A')
        ext_type = get_expiration_type(date_str)
        
        label = f"{dte} DTE - {day_name} {date_str} - {ext_type}"
        dte_labels.append(label)
        filtered_dates_values.append(date_str)

    # 4. Aktuell ausgewähltes Datum bestimmen
    expiration_date = params["expiration_date"]
    
    # Wenn Expiry-Filter geändert wurden (erkannt daran, dass expiration_date leer ist oder nicht in Liste),
    # wählen wir das erste verfügbare Datum.
    if expiration_date not in filtered_dates_values:
        if filtered_dates_values:
            expiration_date = filtered_dates_values[0]
        else:
            expiration_date = ""

    selected_label = ""
    if expiration_date:
        try:
            idx = filtered_dates_values.index(expiration_date)
            selected_label = dte_labels[idx]
        except ValueError:
            pass

    # 5. Spreads berechnen/laden
    table_html = None
    result_count = 0
    error_msg = None

    if not expiration_date:
        if not dte_labels:
            error_msg = "Keine Ablaufdaten entsprechen den gewählten Filtern (Monthly/Weekly/Daily)."
    else:
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
            
            if df.empty:
                result_count = 0
                table_html = None
            else:
                spreads_df = get_page_spreads(df)
                
                # Python-seitige Filter anwenden
                # Max Profit
                spreads_df = spreads_df[spreads_df['max_profit'] >= params["min_max_profit"]]
                
                # No Earnings
                if params["show_no_earnings"]:
                    today = pd.Timestamp.now().normalize()
                    exp_ts = pd.Timestamp(expiration_date).normalize()
                    
                    # Filter: Behalte nur die, bei denen earnings_date NICHT zwischen heute und expiration liegt
                    # Oder earnings_date NaT ist (keine Earnings bekannt)
                    # Wir verwenden eine explizite Kopie um SettingWithCopy-Warnungen zu vermeiden
                    mask = (
                        (spreads_df['earnings_date'] >= today) & 
                        (spreads_df['earnings_date'] <= exp_ts)
                    )
                    before_count = len(spreads_df)
                    spreads_df = spreads_df[~mask].copy()
                    logger.info(f"No Earnings Filter: {before_count} -> {len(spreads_df)} (today: {today}, exp: {exp_ts})")
                
                # Positive EV
                if params["show_only_positive_ev"]:
                    before_count = len(spreads_df)
                    spreads_df = spreads_df[spreads_df['expected_value'] >= 0].copy()
                    logger.info(f"+EV Filter: {before_count} -> {len(spreads_df)}")
                
                # IV Range
                spreads_df = spreads_df[(spreads_df['sell_iv'] >= params["min_sell_iv"]) & 
                                      (spreads_df['sell_iv'] <= params["max_sell_iv"])]
                
                # Ergebnisse formatieren
                result_count = len(spreads_df)
                
                # Datum für Anzeige formatieren
                display_df = spreads_df.copy()
                if not display_df.empty:
                    display_df['earnings_date'] = pd.to_datetime(display_df['earnings_date']).dt.strftime('%d.%m.%Y')
                
                # Subheader definition
                subheaders = [
                    {'name': 'Underlying', 'colspan': 15},
                    {'name': 'Short Leg', 'colspan': 7},
                    {'name': 'Long Leg', 'colspan': 3},
                    {'name': 'Analysis', 'colspan': 6}
                ]
                
                # Spaltennamen kürzen (Kontext durch Subheader gegeben)
                column_rename = {
                    'symbol': 'Sym',
                    'earnings_date': 'Date',
                    'earnings_warning': '⚠️',
                    'close': 'Close',
                    'analyst_mean_target': 'Target',
                    'company_industry': 'Industry',
                    'company_sector': 'Sector',
                    'historical_volatility_30d': 'HV30',
                    'iv_rank': 'IVR',
                    'iv_percentile': 'IV%',
                    'days_to_earnings': 'DTE',
                    'sell_strike': 'Strike',
                    'sell_last_option_price': 'Price',
                    'sell_delta': 'Delta',
                    'sell_iv': 'IV',
                    '%_otm': 'OTM%',
                    'sell_expected_move': 'ExpM',
                    'sell_day_volume': 'Vol',
                    'buy_strike': 'Strike',
                    'buy_last_option_price': 'Price',
                    'buy_delta': 'Delta',
                    'max_profit': 'Profit',
                    'bpr': 'BPR',
                    'profit_to_bpr': 'P/BPR',
                    'expected_value': 'EV',
                    'APDI': 'APDI',
                    'APDI_EV': 'APDI EV'
                }
                
                table_html = dataframe_to_html(
                    display_df, 
                    symbol_column='symbol', 
                    page='spreads',
                    subheaders=subheaders,
                    column_rename=column_rename
                )

        except Exception as e:
            logger.exception("Fehler bei der Spread-Berechnung")
            error_msg = f"Fehler bei der Berechnung: {e}"

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
