from __future__ import annotations

from datetime import date
import json
import re
from typing import Any

import pandas as pd


# Prices per 1M tokens (as provided by DeepSeek pricing page in user context)
DEEPSEEK_PRICING = {
    "deepseek-v4-flash": {
        "input_cache_hit": 0.0028,
        "input_cache_miss": 0.14,
        "output": 0.28,
    },
    "deepseek-v4-pro": {
        "input_cache_hit": 0.003625,
        "input_cache_miss": 0.435,
        "output": 0.87,
    },
}


def _format_float(value, digits: int = 2) -> str:
    if pd.isna(value):
        return "N/A"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "N/A"


def build_bulk_spreads_prompt(
    spreads_df: pd.DataFrame,
    *,
    selected_date: date,
    expiration_date,
    strategy_type: str,
    option_type: str,
    live_research_context: str | None = None,
) -> str:
    """Build one prompt that asks for ranked analysis across many spreads."""
    if spreads_df.empty:
        return "Keine Spreads vorhanden."

    lines: list[str] = []
    for idx, (_, row) in enumerate(spreads_df.iterrows(), start=1):
        lines.append(
            (
                f"{idx}. {row.get('symbol', 'N/A')} ({row.get('Company', 'N/A')}) | "
                f"Sell {option_type} {row.get('sell_strike', 'N/A')} @ {_format_float(row.get('sell_last_option_price'))} "
                f"(Delta {_format_float(row.get('sell_delta'))}, IV {_format_float(row.get('sell_iv'))}) | "
                f"Buy {option_type} {row.get('buy_strike', 'N/A')} @ {_format_float(row.get('buy_last_option_price'))} | "
                f"Width {_format_float(row.get('spread_width'))} | "
                f"MaxProfit ${_format_float(row.get('max_profit'))} | "
                f"BPR ${_format_float(row.get('bpr'))} | "
                f"EV ${_format_float(row.get('expected_value'))} | "
                f"APDI {_format_float(row.get('APDI'))}% | "
                f"IVRank {_format_float(row.get('iv_rank'))} | "
                f"IVPct {_format_float(row.get('iv_percentile'))} | "
                f"Earnings {row.get('earnings_date', 'N/A')}"
            )
        )

    spread_block = "\n".join(lines)

    live_context_block = ""
    if live_research_context and live_research_context.strip():
        live_context_block = f"""

LIVE MARKT-/NEWS-KONTEXT (frisch aus dem Internet geladen):
{live_research_context.strip()}
"""

    return f"""
Du bist ein Senior-Optionsanalyst.

Analysiere ALLE folgenden {len(spreads_df)} {strategy_type.upper()}-Spreads (Option-Typ: {option_type.upper()})
vom Scan-Datum {selected_date} mit Expiration {expiration_date}.

WICHTIG:
- Fuehre pro Aktie eine Web-/News-Recherche durch (letzte 4 Wochen), inklusive Earnings, Guidance,
  relevante Makro-/Sektor-News und idiosynkratische Risiken.
- Nutze Fundamentals + Technicals + Optionsdaten gemeinsam.
- Beurteile fuer jeden Spread die Umsetzungsqualitaet (Chance/Risiko, EV-Qualitaet, Earnings-Risiko,
  Liquiditaet, IV-Setup).

SPREAD-LISTE:
{spread_block}
{live_context_block}

Gib als Antwort NUR valides JSON aus. Kein Markdown, keine Erklaerung ausserhalb von JSON.

Schema:
{{
  "overall_summary": "kurze Gesamteinschaetzung in 2-4 Saetzen",
  "rankings": [
    {{
      "rank": 1,
      "symbol": "AAPL",
      "score": 87,
      "recommendation": "Ja",
      "analysis_summary": "maximal 1-2 Saetze, nur die Kerngruende"
    }}
  ]
}}

Regeln:
- rankings muss ALLE gelieferten Symbole enthalten, sortiert nach rank.
- score ist Integer von 0 bis 100.
- recommendation ist exakt "Ja" oder "Nein".
- analysis_summary ist kurz und praezise (keine langen Details).
""".strip()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    content = (text or "").strip()
    if not content:
        return None

    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", content, re.IGNORECASE)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None

    return None


def parse_spreads_ranking_table(response_text: str) -> tuple[pd.DataFrame, str]:
    """Parse DeepSeek JSON response into a compact ranking dataframe."""
    payload = _extract_json_object(response_text)
    if not payload:
        return pd.DataFrame(), ""

    overall_summary = str(payload.get("overall_summary") or "").strip()
    rankings = payload.get("rankings")
    if not isinstance(rankings, list):
        return pd.DataFrame(), overall_summary

    rows: list[dict[str, Any]] = []
    for item in rankings:
        if not isinstance(item, dict):
            continue

        rank_value = item.get("rank")
        score_value = item.get("score")
        try:
            rank_value = int(rank_value)
        except (TypeError, ValueError):
            rank_value = None

        try:
            score_value = int(score_value)
        except (TypeError, ValueError):
            score_value = None

        rows.append(
            {
                "Rank": rank_value,
                "Symbol": str(item.get("symbol") or "").upper(),
                "Score": score_value,
                "Empfehlung": str(item.get("recommendation") or "").strip(),
                "Analyse Kurz": str(item.get("analysis_summary") or "").strip(),
            }
        )

    if not rows:
        return pd.DataFrame(), overall_summary

    ranking_df = pd.DataFrame(rows)
    if "Rank" in ranking_df.columns:
        ranking_df = ranking_df.sort_values(by=["Rank"], na_position="last")
    ranking_df = ranking_df.reset_index(drop=True)

    return ranking_df, overall_summary


def estimate_deepseek_cost(
    usage: dict[str, Any] | None,
    model: str,
) -> dict[str, float | str]:
    """Estimate request cost from usage and model pricing.

    Returns costs for cache-hit and cache-miss input pricing as a range.
    """
    usage = usage or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)

    model_key = (model or "").strip().lower()
    if model_key not in DEEPSEEK_PRICING:
        return {
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": int(usage.get("total_tokens") or (prompt_tokens + completion_tokens)),
            "cost_cache_hit_usd": 0.0,
            "cost_cache_miss_usd": 0.0,
        }

    pricing = DEEPSEEK_PRICING[model_key]
    prompt_in_million = prompt_tokens / 1_000_000
    completion_in_million = completion_tokens / 1_000_000

    cost_cache_hit = (
        prompt_in_million * float(pricing["input_cache_hit"])
        + completion_in_million * float(pricing["output"])
    )
    cost_cache_miss = (
        prompt_in_million * float(pricing["input_cache_miss"])
        + completion_in_million * float(pricing["output"])
    )

    return {
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": int(usage.get("total_tokens") or (prompt_tokens + completion_tokens)),
        "cost_cache_hit_usd": cost_cache_hit,
        "cost_cache_miss_usd": cost_cache_miss,
    }
