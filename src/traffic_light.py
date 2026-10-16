from __future__ import annotations

import streamlit as st
import pandas as pd
from src.spread_checklist import ChecklistThresholds

_EMOJI = {"g": "🟢", "y": "🟡", "r": "🔴", "n": "⚪"}
_LABEL = {"g": "grün", "y": "gelb", "r": "rot", "n": "n/v"}

_CRITERIA = [
    ("chk_iv_rank",  "IV Rank",        "iv_rank",          "%",     "Optionen sind gerade teuer, mehr Prämie für dasselbe Risiko."),
    ("chk_delta",    "Short Delta",     "sell_delta",       "",      "Um 0,16 liegt der Short Strike etwa eine Standardabweichung unter dem Kurs."),
    ("chk_dte",      "Laufzeit",        "days_to_expiration", "d",   "Schneller Zeitverfall, aber weniger Puffer."),
    ("chk_credit",   "Credit / Breite", "max_profit%",      "%",     "Anteil der Breite als Prämie; bei 16 Delta sind 33 % nur bei hoher IV realistisch."),
    ("chk_earnings", "Earnings",        "earnings_date",    "",      "Kurssprung-Risiko in der Laufzeit."),
]


def checklist_badge(row: pd.Series) -> str:
    """Returns a compact emoji badge string, e.g. '🟢🟢🟡🟢🔴 3/5'."""
    emojis = "".join(_EMOJI.get(row.get(col, "n"), "⚪") for col, *_ in _CRITERIA)
    score = int(row.get("chk_score", 0))
    return f"{emojis} {score}/5"


def render_checklist_detail(row: pd.Series, t: ChecklistThresholds | None = None) -> None:
    """Renders one row per checklist criterion with status, value and explanation."""
    if t is None:
        t = ChecklistThresholds()

    st.markdown("**Einstiegs-Checkliste**")

    _rules = {
        "chk_iv_rank":  f"≥ {t.min_iv_rank:.0f} % = grün, ≥ {t.min_iv_rank - 10:.0f} % = gelb",
        "chk_delta":    f"{t.delta_min:.2f} – {t.delta_max:.2f} = grün, ≤ 0,30 = gelb",
        "chk_dte":      f"{t.dte_min} – {t.dte_max} d = grün, ≤ 45 d = gelb",
        "chk_credit":   f"≥ {t.min_credit_pct:.0f} % = grün, ≥ 20 % = gelb",
        "chk_earnings": "keine Earnings vor Verfall = grün",
    }

    for col, name, val_col, unit, why in _CRITERIA:
        status = row.get(col, "n")
        emoji = _EMOJI[status]
        label = _LABEL[status]

        raw = row.get(val_col)
        if pd.isna(raw) if not isinstance(raw, str) else raw == "":
            val_str = "n/v"
        elif unit:
            try:
                val_str = f"{float(raw):.1f} {unit}"
            except (TypeError, ValueError):
                val_str = str(raw)
        else:
            val_str = str(raw)

        rule = _rules[col]
        st.markdown(
            f"{emoji} **{name}** — {label} | Wert: {val_str} | Regel: {rule}  \n"
            f"_{why}_"
        )
