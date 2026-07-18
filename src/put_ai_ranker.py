"""Put-AI-Ranker: DB-Fundamentals + DeepSeek-Analyse für gefilterte Puts."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from src.llm_client import LLMClient, LLMProviderError  # noqa: F401 (re-exported)

logger = logging.getLogger(__name__)


def _fmt(val, suffix="", factor=1, decimals=2):
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "--"
        return f"{float(val)*factor:.{decimals}f}{suffix}"
    except Exception:
        return "--"


def _fmt_large(val):
    try:
        v = float(val)
        if abs(v) >= 1e9:
            return f"${v/1e9:.1f}B"
        if abs(v) >= 1e6:
            return f"${v/1e6:.0f}M"
        return f"${v:.0f}"
    except Exception:
        return "--"


def _build_prompt(puts_df: pd.DataFrame) -> str:
    lines = [
        "Du bist ein erfahrener Options-Trader und Finanzanalyst.",
        "Analysiere folgende Cash-Secured-Put-Kandidaten auf Basis der bereitgestellten",
        "Fundamentaldaten und Options-Kennzahlen aus unserer Datenbank.",
        "",
        "Bewerte jeden Put nach diesen Kriterien:",
        "1. Unternehmensqualität: Profitabilität (FCF, Operating Cashflow), Wachstum (Revenue, EPS), Bewertung (KGV, Fwd-KGV)",
        "2. Technische Lage: RSI (Überkauft/Überverkauft), Abstand zum SMA200, 52W-Tief",
        "3. Options-Attraktivität: IV-Rank (hohe IV = bessere Prämien), Ann. Rendite, Puffer",
        "4. Risiko: Beta, Earnings-Nähe, Verschuldung (Debt/Eq)",
        "",
        "Antworte auf Deutsch. Format:",
        "**Platz X: SYMBOL $STRIKE (DTE d)** — 2-3 prägnante Sätze mit konkreten Zahlen.",
        "Am Ende 2 Sätze Gesamteinschätzung.",
        "",
        "=== KANDIDATEN ===",
    ]

    for _, r in puts_df.iterrows():
        sym  = r.get("symbol", "?")
        name = r.get("company_name", "")
        sec  = r.get("sector", "")
        ind  = r.get("industry", "")

        # Options
        strike  = _fmt(r.get("strike_price"), "$", decimals=2)
        kurs    = _fmt(r.get("live_stock_price"), "$", decimals=2)
        dte     = _fmt(r.get("days_to_expiration"), "d", decimals=0)
        puffer  = _fmt(r.get("puffer_pct"), "%", decimals=1)
        ann     = _fmt(r.get("ann_pct") or r.get("annualized_pct"), "%", decimals=1)
        praemie = _fmt(r.get("premium_option_price"), "$", decimals=2)
        iv_rank = _fmt(r.get("iv_rank"), decimals=0)
        delta   = _fmt(r.get("greeks_delta") or r.get("put_delta"), decimals=3)

        # Fundamentals
        pe      = _fmt(r.get("trailing_pe"), decimals=1)
        fwd_pe  = _fmt(r.get("forward_pe"), decimals=1)
        rev_g   = _fmt(r.get("revenue_growth_pct"), "%", decimals=1)
        eps_g   = _fmt(r.get("eps_growth_pct"), "%", decimals=1)
        fcf     = _fmt_large(r.get("free_cashflow"))
        ocf     = _fmt_large(r.get("operating_cashflow"))
        mcap    = _fmt_large(r.get("market_cap"))
        rsi     = _fmt(r.get("rsi_14"), decimals=1)
        sma200  = _fmt(r.get("sma_200"), "$", decimals=2)
        w52low  = _fmt(r.get("week_52_low"), "$", decimals=2)

        lines.append(
            f"\n{sym} ({name}) | {sec} / {ind} | MarketCap: {mcap}"
        )
        lines.append(
            f"  Put: Strike {strike} | Kurs {kurs} | DTE {dte} | "
            f"Puffer {puffer} | Ann. {ann} | Prämie {praemie} | IV-Rank {iv_rank} | Delta {delta}"
        )
        lines.append(
            f"  Fundamental: P/E {pe} | Fwd P/E {fwd_pe} | Rev-Wachstum {rev_g} | "
            f"EPS-Wachstum {eps_g} | FCF {fcf} | OCF {ocf}"
        )
        lines.append(
            f"  Technisch: RSI {rsi} | SMA200 {sma200} | 52W-Tief {w52low}"
        )

    return "\n".join(lines)


def rank_puts(
    puts_df: pd.DataFrame,
    max_candidates: int = 25,
    max_tokens: int = 4000,
) -> tuple[str, dict[str, Any]]:
    """Baut Prompt aus DB-Daten und fragt DeepSeek nach einer Rangliste.

    Kein externer API-Call — alle Fundamentaldaten kommen aus puts_df (DB).
    """
    df = puts_df.head(max_candidates).copy()
    symbols = df["symbol"].unique().tolist()

    prompt = _build_prompt(df)

    client = LLMClient()
    response = client.chat_completion(
        "deepseek",
        system_prompt=(
            "Du bist ein erfahrener Optionshändler und Finanzanalyst. "
            "Antworte präzise, strukturiert und auf Deutsch. "
            "Nutze die gegebenen Zahlen explizit in deiner Begründung."
        ),
        user_prompt=prompt,
        temperature=0.3,
        max_tokens=max_tokens,
    )

    return response.text, {
        "symbols": symbols,
        "token_usage": response.usage,
        "model": response.model,
    }
