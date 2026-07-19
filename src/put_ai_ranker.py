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
        "Du bist ein erfahrener Options-Trader spezialisiert auf Cash-Secured Puts (Prämienverkauf).",
        "Ziel: Aktien identifizieren bei denen das Risiko einer ungewollten Zuteilung (Assignment) minimal ist.",
        "Eine Zuteilung ist unerwünscht, wenn die Aktie stark unter den Strike fällt und man die Aktie",
        "zu überhöhtem Preis halten muss. Bewerte daher primär die STABILITÄT und KURSRISIKEN.",
        "",
        "Bewertungskriterien (Priorität: Stabilitätsrisiko zuerst):",
        "1. Kursrisiko / Zuteilungsrisiko:",
        "   - Beta: >1.5 = hohes Kursrisiko, <0.8 = defensiv",
        "   - Days to Earnings: <14 Tage = gefährlich (Earnings-Gap-Risiko)",
        "   - Short % Float: >15% = erhöhtes Squeeze/Crash-Risiko",
        "   - RSI: >75 überkauft (Korrekturrisiko), <30 überverkauft (Bounce möglich)",
        "   - Abstand zum SMA200: Kurs weit darüber = Rückschlagsrisiko",
        "2. Unternehmensqualität (Überlebt die Aktie einen Abschwung?):",
        "   - FCF positiv = Unternehmen zahlt aus eigener Kraft",
        "   - Debt/Equity: >2.0 = Verschuldungsrisiko",
        "   - Gross Margin: >40% = Pricing-Power",
        "   - Return on Equity: >15% = effizientes Kapital",
        "3. Bewertung (faire Aktie fällt weniger):",
        "   - Forward PE vs. Trailing PE: Wachstum sichtbar?",
        "   - Revenue Growth und EPS Growth positiv?",
        "4. Options-Attraktivität (Prämie lohnt sich?):",
        "   - IV-Rank hoch = hohe Prämie",
        "   - Ann. Rendite und Puffer",
        "",
        "Antworte auf Deutsch. Format:",
        "**Platz X: SYMBOL $STRIKE (DTE d)** — 2-3 prägnante Sätze. Nenne konkrete Zahlen.",
        "Erkläre explizit warum das Zuteilungsrisiko gering/hoch ist.",
        "Am Ende: 2 Sätze Gesamteinschätzung welche 1-2 Kandidaten am sichersten sind.",
        "",
        "=== KANDIDATEN ===",
    ]

    for _, r in puts_df.iterrows():
        sym  = r.get("symbol", "?")
        name = r.get("company_name", "")
        sec  = r.get("sector", "")
        ind  = r.get("industry", "")

        # Options-Kennzahlen
        strike  = _fmt(r.get("strike_price"), "$", decimals=2)
        kurs    = _fmt(r.get("live_stock_price"), "$", decimals=2)
        dte     = _fmt(r.get("days_to_expiration"), "d", decimals=0)
        puffer  = _fmt(r.get("puffer_pct"), "%", decimals=1)
        ann     = _fmt(r.get("ann_pct") or r.get("annualized_pct"), "%", decimals=1)
        praemie = _fmt(r.get("premium_option_price"), "$", decimals=2)
        iv_rank = _fmt(r.get("iv_rank"), decimals=0)
        delta   = _fmt(r.get("greeks_delta") or r.get("put_delta"), decimals=3)

        # Kursrisiko
        beta         = _fmt(r.get("KeyStats_beta") or r.get("beta"), decimals=2)
        dte_earnings = _fmt(r.get("days_to_earnings"), "d", decimals=0)
        short_float  = _fmt(r.get("short_percent_float"), "%", decimals=1)
        rsi          = _fmt(r.get("rsi_14"), decimals=1)
        sma200       = _fmt(r.get("sma_200"), "$", decimals=2)
        w52low       = _fmt(r.get("week_52_low"), "$", decimals=2)

        # Unternehmensqualität
        fcf     = _fmt_large(r.get("free_cashflow") or r.get("FreeCashFlow"))
        ocf     = _fmt_large(r.get("operating_cashflow") or r.get("OperatingCashFlow"))
        debt_eq = _fmt(r.get("debt_to_equity"), decimals=2)
        gm      = _fmt(r.get("gross_margin_pct"), "%", decimals=1)
        roe     = _fmt(r.get("return_on_equity_pct"), "%", decimals=1)

        # Bewertung
        pe      = _fmt(r.get("trailing_pe"), decimals=1)
        fwd_pe  = _fmt(r.get("forward_pe"), decimals=1)
        rev_g   = _fmt(r.get("revenue_growth_pct"), "%", decimals=1)
        eps_g   = _fmt(r.get("eps_growth_pct"), "%", decimals=1)
        mcap    = _fmt_large(r.get("market_cap") or r.get("MarketCap"))

        lines.append(f"\n{sym} ({name}) | {sec} / {ind} | MarketCap: {mcap}")
        lines.append(
            f"  Kursrisiko: Beta {beta} | Earnings in {dte_earnings} | "
            f"Short-Float {short_float} | RSI {rsi} | SMA200 {sma200} | 52W-Tief {w52low}"
        )
        lines.append(
            f"  Qualität:   FCF {fcf} | OCF {ocf} | Debt/Eq {debt_eq} | "
            f"Gross Margin {gm} | ROE {roe}"
        )
        lines.append(
            f"  Bewertung:  P/E {pe} | Fwd P/E {fwd_pe} | Rev-Wachstum {rev_g} | EPS-Wachstum {eps_g}"
        )
        lines.append(
            f"  Put:        Strike {strike} | Kurs {kurs} | DTE {dte} | "
            f"Puffer {puffer} | Ann. {ann} | Prämie {praemie} | IV-Rank {iv_rank} | Delta {delta}"
        )

    return "\n".join(lines)


def rank_puts(
    puts_df: pd.DataFrame,
    max_candidates: int = 25,
    max_tokens: int = 4000,
) -> tuple[str, dict[str, Any]]:
    """Baut Prompt aus DB-Daten und fragt DeepSeek nach einer Rangliste.

    Alle Daten kommen aus der eigenen DB (put_screener.sql + StockData).
    Kein externer Scraping-Call.
    """
    df = puts_df.head(max_candidates).copy()
    symbols = df["symbol"].unique().tolist()

    prompt = _build_prompt(df)

    client = LLMClient()
    response = client.chat_completion(
        "deepseek",
        system_prompt=(
            "Du bist ein erfahrener Optionshändler spezialisiert auf Cash-Secured Puts. "
            "Dein Hauptziel ist es, Aktien zu identifizieren bei denen das Zuteilungsrisiko minimal ist. "
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
