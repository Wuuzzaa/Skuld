"""
Filter-field whitelist for the dynamic universe UI.

Kap. 3.4: kuratierte Whitelist (ca. 30-50 Felder), gruppiert nach Kategorien.
The UI consumes FIELD_CATEGORIES to render tabs, and FILTER_FIELDS to build
individual widgets.

Each field maps: UI-label -> DB-column-name -> data-type + category.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FieldDef:
    key: str  # DB column name (matches OptionDataMerged / getOptionDataMergedHistory)
    label: str  # human-readable UI label
    category: str
    dtype: str  # "float", "int", "bool", "date", "str"
    unit: Optional[str] = None
    description: Optional[str] = None


FILTER_FIELDS: dict[str, FieldDef] = {
    # ─── Market ───────────────────────────────────────────────────────────
    "live_stock_price": FieldDef(
        "live_stock_price", "Stock Price", "Market", "float", "$",
        "EOD close price of the underlying",
    ),
    "day_volume": FieldDef(
        "day_volume", "Day Volume", "Market", "int", None,
        "Trading volume of the underlying",
    ),
    "day_close": FieldDef(
        "day_close", "Option Price", "Options", "float", "$",
        "EOD close price of the option contract",
    ),
    # ─── Technicals ───────────────────────────────────────────────────────
    "historical_volatility_30d": FieldDef(
        "historical_volatility_30d", "HV30", "Technicals", "float", "%",
        "30-day historical volatility of the underlying",
    ),
    "iv_rank": FieldDef(
        "iv_rank", "IV Rank", "Technicals", "float", "%",
        "IV rank over trailing 52 weeks",
    ),
    "iv_percentile": FieldDef(
        "iv_percentile", "IV Percentile", "Technicals", "float", "%",
        "IV percentile over trailing 52 weeks",
    ),
    "days_of_options_data_history": FieldDef(
        "days_of_options_data_history", "Options History Days", "Technicals",
        "int", "days",
    ),
    # ─── Fundamentals ─────────────────────────────────────────────────────
    "market_cap": FieldDef(
        "market_cap", "Market Cap", "Fundamentals", "float", "$",
        "Market capitalization (from StockAssetProfilesYahoo)",
    ),
    "sector": FieldDef(
        "sector", "Sector", "Fundamentals", "str", None,
        "GICS sector",
    ),
    "industry": FieldDef(
        "industry", "Industry", "Fundamentals", "str", None,
    ),
    "country": FieldDef(
        "country", "Country", "Fundamentals", "str", None,
    ),
    # ─── Options ──────────────────────────────────────────────────────────
    "open_interest": FieldDef(
        "open_interest", "Open Interest", "Options", "int", "contracts",
        "Aggregate OI across the option chain",
    ),
    "implied_volatility": FieldDef(
        "implied_volatility", "Implied Volatility", "Options", "float", "%",
    ),
    "greeks_delta": FieldDef(
        "greeks_delta", "Delta", "Options", "float", None,
    ),
    # ─── Dividends ────────────────────────────────────────────────────────
    "last_dividend": FieldDef(
        "last_dividend", "Last Dividend", "Dividends", "float", "$",
    ),
    "dividend_growth_years": FieldDef(
        "dividend_growth_years", "Dividend Growth Years", "Dividends",
        "int", "years",
    ),
    "no_dividend_payouts_last_year": FieldDef(
        "no_dividend_payouts_last_year", "Dividend Payouts (LY)", "Dividends",
        "int", None,
    ),
    "dividend_classification": FieldDef(
        "dividend_classification", "Dividend Classification", "Dividends",
        "str", None,
    ),
    # ─── Earnings ─────────────────────────────────────────────────────────
    "earnings_date": FieldDef(
        "earnings_date", "Next Earnings Date", "Earnings", "date", None,
    ),
    "days_to_earnings": FieldDef(
        "days_to_earnings", "Days to Earnings", "Earnings", "int", "days",
    ),
    # ─── Analyst ──────────────────────────────────────────────────────────
    "analyst_mean_target": FieldDef(
        "analyst_mean_target", "Analyst Mean Target", "Analyst", "float", "$",
    ),
    # ─── Momentum / Custom (computed) ─────────────────────────────────────
    "rsl": FieldDef(
        "rsl", "RSL (Levy)", "Momentum", "float", None,
        "Relative Strength Levy — close / SMA-27w",
    ),
}


def _group_by_category() -> dict[str, list[FieldDef]]:
    groups: dict[str, list[FieldDef]] = {}
    for f in FILTER_FIELDS.values():
        groups.setdefault(f.category, []).append(f)
    return groups


FIELD_CATEGORIES: dict[str, list[FieldDef]] = _group_by_category()


def field_definition(key: str) -> Optional[FieldDef]:
    return FILTER_FIELDS.get(key)
