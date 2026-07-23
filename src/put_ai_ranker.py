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
    # Sektor-Übersicht für Quervergleich
    sectors = puts_df.get("sector", pd.Series(dtype=str)).dropna().unique().tolist() if "sector" in puts_df.columns else []
    sector_summary = ", ".join(sorted(set(sectors))) if sectors else "k.A."

    lines = [
        "## Strategie-Kontext",
        "Wir suchen Aktien für Cash-Secured-Put-Prämienverkauf (~30 DTE, am Geld).",
        "Ziel: Prämien kassieren und Zuteilung vermeiden. Dafür brauchen wir fundamental",
        "solide Unternehmen deren Kurs stabil bleibt — die Put-Kennzahlen sind sekundär.",
        "",
        "## Deine Aufgabe: ZWEISTUFIGE BEWERTUNG",
        "",
        "**Stufe 1 — Unternehmensqualität (Hauptkriterium, 60% Gewicht):**",
        "Bewerte jedes Unternehmen als eigenständige Investition. Kernfragen:",
        "- Ist das Unternehmen profitabel und wächst es? (FCF positiv, Revenue/EPS-Wachstum)",
        "- Ist die Bilanz solide? (Debt/Equity <2, Gross Margin >30%)",
        "- Ist die Bewertung fair? (KGV nicht extrem überhöht für den Sektor)",
        "- Ist der Kurs technisch stabil? (RSI nicht überkauft, über SMA200)",
        "- Gibt es Kursrisiken? (Beta hoch, Earnings in <14 Tagen, Short-Float >15%)",
        "",
        "**Stufe 2 — Put-Attraktivität (Sekundärkriterium, 40% Gewicht):**",
        "Nur wenn das Unternehmen fundamental überzeugt — lohnt sich der Put?",
        "- IV-Rank hoch = gute Prämie zum Zeitpunkt des Verkaufs",
        "- Annualisierte Rendite attraktiv?",
        "- Puffer zwischen Strike und Kurs ausreichend?",
        "",
        "**Wichtig:** Ein Put mit hoher Prämie bei einem schwachen Unternehmen ist KEIN guter Kandidat.",
        "Ein Put mit moderater Prämie bei einem qualitativ hochwertigen Unternehmen ist BESSER.",
        "",
        f"Vertretene Sektoren: {sector_summary}",
        "Beachte Sektor-Unterschiede: Tech-Wachstum rechtfertigt höhere KGVs, defensive Sektoren",
        "punkten durch Stabilität und Cashflow.",
        "",
        "## Output-Format",
        "",
        "**Teil 1 — Ranking-Tabelle** (alle Kandidaten, sortiert nach Gesamtbewertung):",
        "| Platz | Symbol | Sektor | Fundamental-Note | Put-Note | IV-Rank | Ann.% | Fazit (1 Satz) |",
        "Fundamental-Note: A/B/C/D. Put-Note: A/B/C/D. Fazit: wichtigste Stärke ODER Risiko.",
        "",
        "**Teil 2 — Top-3 Empfehlungen** (je 4-5 Sätze):",
        "Für jeden Top-3-Kandidaten:",
        "1. Warum ist das Unternehmen fundamental stark? (konkrete Zahlen: FCF, KGV, Wachstum)",
        "2. Warum ist der Put attraktiv? (IV-Rank, Rendite, Puffer)",
        "3. Was ist das Hauptrisiko?",
        "",
        "**Teil 3 — Warnungen** (nur wenn relevant):",
        "Kandidaten mit erhöhtem Risiko: Earnings <14 Tage, Beta >1.5, negativer FCF, Debt/Eq >3.",
        "",
        "=== KANDIDATEN-DATEN ===",
    ]

    for _, r in puts_df.iterrows():
        sym  = r.get("symbol", "?")
        name = r.get("company_name", "")
        sec  = r.get("sector", "")

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

        # Unternehmensqualität (Hauptkriterium)
        fcf     = _fmt_large(r.get("free_cashflow") or r.get("FreeCashFlow"))
        ocf     = _fmt_large(r.get("operating_cashflow") or r.get("OperatingCashFlow"))
        debt_eq = _fmt(r.get("debt_to_equity"), decimals=2)
        gm      = _fmt(r.get("gross_margin_pct"), "%", decimals=1)
        roe     = _fmt(r.get("return_on_equity_pct"), "%", decimals=1)
        rev_g   = _fmt(r.get("revenue_growth_pct"), "%", decimals=1)
        eps_g   = _fmt(r.get("eps_growth_pct"), "%", decimals=1)
        pe      = _fmt(r.get("trailing_pe"), decimals=1)
        fwd_pe  = _fmt(r.get("forward_pe"), decimals=1)
        mcap    = _fmt_large(r.get("market_cap") or r.get("MarketCap"))

        lines.append(f"\n--- {sym} ({name}) | {sec} | MarketCap: {mcap} ---")
        lines.append(
            f"  [FUNDAMENTAL] FCF {fcf} | OCF {ocf} | Debt/Eq {debt_eq} | "
            f"Gross Margin {gm} | ROE {roe} | Rev-Wachstum {rev_g} | EPS-Wachstum {eps_g} | "
            f"P/E {pe} | Fwd P/E {fwd_pe}"
        )
        lines.append(
            f"  [KURSRISIKO]  Beta {beta} | Earnings in {dte_earnings} | "
            f"Short-Float {short_float} | RSI {rsi} | SMA200 {sma200} | 52W-Tief {w52low}"
        )
        lines.append(
            f"  [PUT]         Strike {strike} | Kurs {kurs} | DTE {dte} | "
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
            "Du bist ein erfahrener Optionshändler spezialisiert auf Cash-Secured-Put-Prämienverkauf. "
            "Du vergleichst Kandidaten miteinander und gibst strukturierte, tabellarische Antworten. "
            "Antworte auf Deutsch. Nutze Markdown-Tabellen für das Ranking. "
            "Nenne immer konkrete Zahlen aus den gegebenen Daten. "
            "Sei präzise — kein allgemeines Finanzwissen, nur Analyse der gegebenen Kandidaten."
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
