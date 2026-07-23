from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup


def _fmt_ts(unix_ts: int | float | None) -> str:
    if not unix_ts:
        return "N/A"
    try:
        dt = datetime.fromtimestamp(float(unix_ts), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OSError):
        return "N/A"


def _compact_num(value) -> str:
    if value is None:
        return "N/A"
    try:
        val = float(value)
    except (TypeError, ValueError):
        return "N/A"

    abs_val = abs(val)
    if abs_val >= 1_000_000_000_000:
        return f"{val/1_000_000_000_000:.2f}T"
    if abs_val >= 1_000_000_000:
        return f"{val/1_000_000_000:.2f}B"
    if abs_val >= 1_000_000:
        return f"{val/1_000_000:.2f}M"
    return f"{val:.2f}"


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fetch_article_excerpt(
    url: str,
    *,
    timeout_seconds: int = 8,
    max_chars: int = 800,
) -> str:
    """Fetch and extract a compact article excerpt from a news URL."""
    if not url:
        return ""

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = requests.get(url, timeout=timeout_seconds, headers=headers)
        resp.raise_for_status()
    except requests.RequestException:
        return ""

    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        return ""

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return ""

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.extract()

    paragraphs: list[str] = []
    for p in soup.find_all("p"):
        text = " ".join(p.get_text(" ", strip=True).split())
        if len(text) < 60:
            continue
        paragraphs.append(text)
        if len(paragraphs) >= 8:
            break

    excerpt = " ".join(paragraphs).strip()
    if not excerpt:
        return ""

    return excerpt[:max_chars].strip()


def fetch_symbol_live_snapshot(
    symbol: str,
    *,
    max_headlines: int = 3,
    include_google_news: bool = False,
    timeout_seconds: int = 8,
) -> dict:
    """Fetch lightweight live market/news context for one symbol."""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return {"symbol": "", "price": None, "currency": None, "market_time": None, "headlines": []}

    price = None
    currency = None
    market_time = None
    quote_meta: dict = {}
    headlines: list[dict] = []
    google_headlines: list[dict] = []

    # Live quote (Yahoo Finance quote endpoint)
    try:
        quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
        quote_resp = requests.get(quote_url, timeout=timeout_seconds)
        quote_resp.raise_for_status()
        quote_data = quote_resp.json()
        quote_results = (quote_data.get("quoteResponse") or {}).get("result") or []
        if quote_results:
            first = quote_results[0]
            price = first.get("regularMarketPrice")
            currency = first.get("currency")
            market_time = _fmt_ts(first.get("regularMarketTime"))
            quote_meta = {
                "change_pct": _safe_float(first.get("regularMarketChangePercent")),
                "day_range_low": _safe_float(first.get("regularMarketDayLow")),
                "day_range_high": _safe_float(first.get("regularMarketDayHigh")),
                "volume": _safe_float(first.get("regularMarketVolume")),
                "market_cap": _safe_float(first.get("marketCap")),
                "pe_ratio": _safe_float(first.get("trailingPE")),
                "forward_pe": _safe_float(first.get("forwardPE")),
            }
    except requests.RequestException:
        pass

    # Latest headlines (Yahoo RSS)
    try:
        rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
        rss_resp = requests.get(rss_url, timeout=timeout_seconds)
        rss_resp.raise_for_status()
        root = ET.fromstring(rss_resp.text)
        items = root.findall(".//item")
        for item in items[:max_headlines]:
            title = (item.findtext("title") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            source = (item.findtext("source") or "").strip()
            if not title:
                continue
            headlines.append(
                {
                    "title": title,
                    "pub_date": pub_date,
                    "source": source,
                    "url": (item.findtext("link") or "").strip(),
                }
            )
    except (requests.RequestException, ET.ParseError):
        pass

    # Additional broad-web source: Google News RSS
    if include_google_news:
        try:
            q = quote_plus(f"{symbol} stock")
            rss_url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
            rss_resp = requests.get(rss_url, timeout=timeout_seconds)
            rss_resp.raise_for_status()
            root = ET.fromstring(rss_resp.text)
            items = root.findall(".//item")
            for item in items[:max_headlines]:
                title = (item.findtext("title") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()
                source_node = item.find("source")
                source = (source_node.text or "").strip() if source_node is not None else ""
                if not title:
                    continue
                google_headlines.append(
                    {
                        "title": title,
                        "pub_date": pub_date,
                        "source": source,
                        "url": (item.findtext("link") or "").strip(),
                    }
                )
        except (requests.RequestException, ET.ParseError):
            pass

    return {
        "symbol": symbol,
        "price": price,
        "currency": currency,
        "market_time": market_time,
        "quote_meta": quote_meta,
        "headlines": headlines,
        "google_headlines": google_headlines,
    }


def build_live_research_bundle(
    symbols: list[str],
    *,
    max_headlines: int = 3,
    timeout_seconds: int = 8,
    max_symbols: int = 30,
    deep_research: bool = False,
    include_article_content: bool = False,
    max_articles_per_symbol: int = 1,
    article_excerpt_chars: int = 800,
) -> tuple[str, list[dict], list[dict]]:
    """Create compact prompt context + structured per-symbol source rows."""
    cleaned_symbols: list[str] = []
    for sym in symbols:
        s = (sym or "").strip().upper()
        if s and s not in cleaned_symbols:
            cleaned_symbols.append(s)

    cleaned_symbols = cleaned_symbols[:max_symbols]
    if not cleaned_symbols:
        return "Keine Symbole fuer Live-Recherche vorhanden.", [], []

    lines: list[str] = []
    source_rows: list[dict] = []
    article_quality_rows: list[dict] = []
    snapshots: dict[str, dict] = {}

    # Network-bound step: fetch multiple symbols concurrently.
    with ThreadPoolExecutor(max_workers=min(8, max(2, len(cleaned_symbols)))) as pool:
        future_map = {
            pool.submit(
                fetch_symbol_live_snapshot,
                symbol,
                max_headlines=max_headlines,
                include_google_news=deep_research,
                timeout_seconds=timeout_seconds,
            ): symbol
            for symbol in cleaned_symbols
        }
        for future in as_completed(future_map):
            symbol = future_map[future]
            try:
                snapshots[symbol] = future.result()
            except Exception:
                snapshots[symbol] = {
                    "symbol": symbol,
                    "price": None,
                    "currency": None,
                    "market_time": None,
                    "quote_meta": {},
                    "headlines": [],
                    "google_headlines": [],
                }

    for symbol in cleaned_symbols:
        snap = snapshots.get(symbol, {})
        price = snap.get("price")
        currency = snap.get("currency") or ""
        market_time = snap.get("market_time") or "N/A"
        quote_meta = snap.get("quote_meta") or {}

        if price is None:
            lines.append(f"- {symbol}: Live Price nicht verfuegbar")
        else:
            lines.append(f"- {symbol}: Live Price {price} {currency} (as of {market_time})")

        if quote_meta:
            change_pct = quote_meta.get("change_pct")
            pe_ratio = quote_meta.get("pe_ratio")
            fwd_pe = quote_meta.get("forward_pe")
            market_cap = _compact_num(quote_meta.get("market_cap"))
            volume = _compact_num(quote_meta.get("volume"))
            low = quote_meta.get("day_range_low")
            high = quote_meta.get("day_range_high")
            lines.append(
                "  - Quote-Meta: "
                f"Change% {change_pct if change_pct is not None else 'N/A'} | "
                f"DayRange {low if low is not None else 'N/A'}-{high if high is not None else 'N/A'} | "
                f"Volume {volume} | MarketCap {market_cap} | "
                f"PE {pe_ratio if pe_ratio is not None else 'N/A'} | FwdPE {fwd_pe if fwd_pe is not None else 'N/A'}"
            )

        symbol_headlines = snap.get("headlines") or []
        article_candidates: list[tuple[str, dict]] = []
        if symbol_headlines:
            for h in symbol_headlines:
                title = h.get("title") or ""
                pub_date = h.get("pub_date") or ""
                source = h.get("source") or ""
                url = h.get("url") or ""
                meta = " | ".join([m for m in [pub_date, source] if m])
                if meta:
                    lines.append(f"  - News: {title} ({meta})")
                else:
                    lines.append(f"  - News: {title}")
                source_rows.append(
                    {
                        "Symbol": symbol,
                        "Typ": "Yahoo",
                        "Quelle": source or "Yahoo Finance RSS",
                        "Titel": title,
                        "Datum": pub_date,
                        "URL": url,
                        "Artikel Excerpt": "",
                    }
                )
                article_candidates.append(("Yahoo", h))
        else:
            lines.append("  - News: Keine aktuellen Headlines gefunden")

        if deep_research:
            google_items = snap.get("google_headlines") or []
            if google_items:
                for h in google_items:
                    title = h.get("title") or ""
                    pub_date = h.get("pub_date") or ""
                    source = h.get("source") or ""
                    url = h.get("url") or ""
                    meta = " | ".join([m for m in [pub_date, source] if m])
                    if meta:
                        lines.append(f"  - Web-News: {title} ({meta})")
                    else:
                        lines.append(f"  - Web-News: {title}")
                    source_rows.append(
                        {
                            "Symbol": symbol,
                            "Typ": "GoogleNews",
                            "Quelle": source or "Google News",
                            "Titel": title,
                            "Datum": pub_date,
                            "URL": url,
                            "Artikel Excerpt": "",
                        }
                    )
                    article_candidates.append(("GoogleNews", h))
            else:
                lines.append("  - Web-News: Keine zusaetzlichen Treffer")

        attempted_articles = 0
        read_articles = 0
        if include_article_content and article_candidates:
            fetched = 0
            for source_type, item in article_candidates:
                if fetched >= max(0, int(max_articles_per_symbol)):
                    break

                url = (item.get("url") or "").strip()
                if not url:
                    continue

                attempted_articles += 1

                excerpt = _fetch_article_excerpt(
                    url,
                    timeout_seconds=timeout_seconds,
                    max_chars=int(article_excerpt_chars),
                )
                if not excerpt:
                    continue

                lines.append(f"  - Artikel-Excerpt ({source_type}): {excerpt}")

                # Fill excerpt on first matching row (same symbol + url)
                for row in source_rows:
                    if row.get("Symbol") == symbol and row.get("URL") == url and not row.get("Artikel Excerpt"):
                        row["Artikel Excerpt"] = excerpt
                        break

                fetched += 1
                read_articles += 1

        success_rate = (read_articles / attempted_articles * 100.0) if attempted_articles else 0.0
        article_quality_rows.append(
            {
                "Symbol": symbol,
                "Artikel gelesen": read_articles,
                "Artikel versucht": attempted_articles,
                "Erfolgsquote %": round(success_rate, 1),
            }
        )

    return "\n".join(lines), source_rows, article_quality_rows


def build_live_research_context(
    symbols: list[str],
    *,
    max_headlines: int = 3,
    timeout_seconds: int = 8,
    max_symbols: int = 30,
    deep_research: bool = False,
) -> str:
    """Backward-compatible helper returning prompt context only."""
    context, _, _ = build_live_research_bundle(
        symbols,
        max_headlines=max_headlines,
        timeout_seconds=timeout_seconds,
        max_symbols=max_symbols,
        deep_research=deep_research,
    )
    return context
