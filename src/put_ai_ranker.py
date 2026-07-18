"""Put-AI-Ranker: Finviz-Scraping + DeepSeek-Analyse für gefilterte Puts."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.llm_client import LLMClient, LLMProviderError

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_FINVIZ_KEYS = [
    "P/E", "Fwd P/E", "EPS (ttm)", "EPS next Y", "EPS next Q",
    "Sales", "Income", "Profit Margin", "ROE", "ROA", "Debt/Eq",
    "Beta", "52W High", "52W Low", "RSI (14)", "Rel Volume",
    "Avg Volume", "Market Cap", "Analyst Recom", "Target Price",
    "Perf Week", "Perf Month", "Perf Quarter", "Perf Half Y",
    "Inst Own", "Short Float", "Earnings",
]


def _scrape_finviz(symbol: str) -> dict[str, str]:
    try:
        r = requests.get(
            f"https://finviz.com/quote.ashx?t={symbol}",
            headers=_HEADERS, timeout=10,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        cells = soup.select("table.snapshot-table2 td")
        raw: dict[str, str] = {}
        for i in range(0, len(cells) - 1, 2):
            raw[cells[i].text.strip()] = cells[i + 1].text.strip()
        return {k: raw[k] for k in _FINVIZ_KEYS if k in raw}
    except Exception as exc:
        logger.warning("Finviz scrape failed for %s: %s", symbol, exc)
        return {}


def _scrape_parallel(symbols: list[str], max_workers: int = 6) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_scrape_finviz, sym): sym for sym in symbols}
        for fut in as_completed(futures):
            sym = futures[fut]
            result[sym] = fut.result()
    return result


def _build_prompt(puts_df: pd.DataFrame, fundamentals: dict[str, dict]) -> str:
    lines = ["Du bist ein erfahrener Options-Trader. Analysiere folgende Cash-Secured-Put-Kandidaten",
             "und erstelle eine Rangliste der besten Einstiege. Bewerte jeden Put nach:",
             "- Fundamentals (KGV, Wachstum, Profitabilität, Analystenmeinung)",
             "- Technische Lage (RSI, 52W-Performance, Relative Stärke)",
             "- Options-Kennzahlen (Puffer, Ann. Rendite, IV-Rank, DTE)",
             "- Risiko (Beta, Short Float, Debt/Equity, Earnings-Nähe)",
             "",
             "Antworte auf Deutsch. Format: Nummerierte Rangliste, pro Put:",
             "**Platz X: SYMBOL $STRIKE (DTE d)** — 2-3 Sätze Begründung.",
             "Am Ende: kurze Gesamteinschätzung des Marktumfelds (2 Sätze).",
             "",
             "=== PUTS ==="]

    for _, r in puts_df.iterrows():
        sym = r["symbol"]
        lines.append(
            f"\n{sym} | Strike ${float(r['strike_price']):.2f} | Kurs ${float(r['live_stock_price']):.2f} "
            f"| DTE {int(r['days_to_expiration'])} | Puffer {float(r.get('puffer_pct', 0)):.1f}% "
            f"| Ann. {float(r.get('ann_pct', 0)):.1f}% | Prämie ${float(r['premium_option_price']):.2f} "
            f"| IV-Rank {r.get('iv_rank', '--')} | Delta {r.get('greeks_delta', '--')}"
        )
        fund = fundamentals.get(sym, {})
        if fund:
            fund_str = " | ".join(f"{k}: {v}" for k, v in fund.items())
            lines.append(f"  Finviz: {fund_str}")

    return "\n".join(lines)


def rank_puts(
    puts_df: pd.DataFrame,
    max_candidates: int = 25,
    max_tokens: int = 4000,
) -> tuple[str, dict[str, Any]]:
    """Scrapt Finviz für alle Symbole und fragt DeepSeek nach einer Rangliste.

    Returns (markdown_text, meta) where meta hat keys: symbols, token_usage.
    """
    df = puts_df.head(max_candidates).copy()
    symbols = df["symbol"].unique().tolist()

    fundamentals = _scrape_parallel(symbols)

    prompt = _build_prompt(df, fundamentals)

    client = LLMClient()
    response = client.chat_completion(
        "deepseek",
        system_prompt=(
            "Du bist ein erfahrener Optionshändler und Finanzanalyst. "
            "Antworte präzise, strukturiert und auf Deutsch."
        ),
        user_prompt=prompt,
        temperature=0.3,
        max_tokens=max_tokens,
    )

    meta = {
        "symbols": symbols,
        "token_usage": response.usage,
        "model": response.model,
    }
    return response.text, meta
