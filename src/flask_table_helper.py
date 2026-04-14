import urllib.parse
import pandas as pd
from markupsafe import Markup


def _add_links(df: pd.DataFrame, symbol_column: str = 'symbol', page: str = None) -> pd.DataFrame:
    """Add TradingView, Chart and Claude AI links as HTML anchor tags."""
    df = df.copy()

    def tv_link(sym):
        url = f"https://www.tradingview.com/symbols/{sym}/"
        return Markup(f'<a href="{url}" target="_blank" class="icon-link" title="TradingView">📊</a>')

    def chart_link(sym):
        url = f"https://www.tradingview.com/chart/?symbol={sym}"
        return Markup(f'<a href="{url}" target="_blank" class="icon-link" title="Chart">📈</a>')

    def claude_link(row):
        if page == 'spreads':
            prompt = f"""
Erstelle eine kompakte Aktienanalyse für {row[symbol_column]}:
Unternehmen: Geschäftsmodell und Branche (1-2 Sätzen):
Aktuelle News: Wichtigste Entwicklungen der letzten 4 Wochen
Anstehende Events: Earnings, Produktlaunches oder relevante Termine (in 3-7 Sätzen).
Einschätzung (maximal 8 Sätze):
Kauf/Halten/Verkaufen mit Begründung
Aktuelles Kursziel (Analystenkonsens)
Eigenes Kursziel durch Fundamentaldaten, News, Technische Analyse State of the Art.
Wichtigste Chance und größtes Risiko.
Beurteile folgende Strategie mit Optionen für {row[symbol_column]}:
Verkaufe einen {row.get('option_type','')} Strike {row.get('sell_strike','')} für eine Prämie von {row.get('sell_last_option_price','')} bei einem Delta von {row.get('sell_delta','')}.
Kaufe einen {row.get('option_type','')} mit Strike {row.get('buy_strike','')} für eine Prämie von {row.get('buy_last_option_price','')}.
Expirationdate ist jeweils {row.get('expiration_date','')}.
Format: Prägnant, faktenbasiert, keine Füllwörter, max. eine Seite.
Rolle: Aktien und Finanzexperte.
"""
        else:
            sym = row[symbol_column]
            prompt = f"""
Erstelle eine kompakte Aktienanalyse für {sym}:
Unternehmen: Geschäftsmodell und Branche in 1-2 Sätzen
Aktuelle News: Wichtigste Entwicklungen der letzten 4 Wochen
Anstehende Events: Earnings, Produktlaunches oder relevante Termine
Einschätzung:
Kauf/Halten/Verkaufen mit Begründung
Aktuelles Kursziel (Analystenkonsens)
Eigenes Kursziel durch Fundamentaldaten, News, Technische Analyse State of the Art
Wichtigste Chance und größtes Risiko
Format: Prägnant, faktenbasiert, keine Füllwörter, max. eine Seite.
"""
        encoded = urllib.parse.quote(prompt.strip())
        url = f"https://claude.ai/new?q={encoded}"
        return Markup(f'<a href="{url}" target="_blank" class="icon-link" title="Claude AI">🤖</a>')

    def optionstrat_link(row):
        url = row.get('optionstrat_url')
        if not url:
            return ""
        return Markup(f'<a href="{url}" target="_blank" class="icon-link" title="OptionStrat">🔗</a>')

    if symbol_column in df.columns:
        df['📊'] = df[symbol_column].apply(tv_link)
        df['📈'] = df[symbol_column].apply(chart_link)
        df['🔗'] = df.apply(optionstrat_link, axis=1)
        df['🤖'] = df.apply(claude_link, axis=1)

    return df


def _format_cell(val):
    """Format a single cell value for HTML display."""
    if isinstance(val, float):
        if val < 0:
            return Markup(f'<span class="text-negative">{val:.2f}</span>')
        return f"{val:.2f}"
    if isinstance(val, Markup):
        return val
    return val


def dataframe_to_html(
        df: pd.DataFrame,
        symbol_column: str = 'symbol',
        page: str = None,
        drop_columns: list = None,
        subheaders: list = None,
        column_rename: dict = None
) -> Markup:
    """
    Convert a DataFrame to an HTML table string with TradingView/Claude links,
    alternating row colors (via CSS), and negative number highlighting.
    Returns a Markup string safe for Jinja2 rendering.
    """
    if df is None or df.empty:
        return Markup('<p class="text-muted">No data available.</p>')

    df = _add_links(df, symbol_column=symbol_column, page=page)

    if page == 'spreads':
        for col in ['option_type', 'expiration_date', 'optionstrat_url']:
            if col in df.columns:
                df = df.drop(columns=[col])
        
        # Reorder columns for better grouping if it's the spreads page
        # This ensures links are next to the symbol
        cols = df.columns.tolist()
        link_cols = ['📊', '📈', '🤖', '🔗']
        for lc in link_cols:
            if lc in cols:
                cols.remove(lc)
        
        if symbol_column in cols:
            idx = cols.index(symbol_column) + 1
            for lc in reversed(link_cols):
                if lc in df.columns:
                    cols.insert(idx, lc)
        df = df[cols]

    if column_rename:
        df = df.rename(columns=column_rename)

    if drop_columns:
        df = df.drop(columns=[c for c in drop_columns if c in df.columns])

    # Build HTML table
    headers = df.columns.tolist()
    
    # Subheader row
    subheader_html = ""
    if subheaders:
        cells = []
        for sh in subheaders:
            name = sh.get('name', '')
            colspan = sh.get('colspan', 1)
            cells.append(f'<th colspan="{colspan}" class="text-center subheader-cell">{name}</th>')
        subheader_html = f'<tr class="subheader-row">{"".join(cells)}</tr>'

    header_html = "".join(f"<th>{h}</th>" for h in headers)

    rows_html = []
    for _, row in df.iterrows():
        cells = "".join(
            f"<td>{_format_cell(row.iloc[i])}</td>" for i in range(len(headers))
        )
        rows_html.append(f"<tr>{cells}</tr>")

    table = f"""
<div class="table-responsive">
  <table class="table table-sm skuld-table w-100">
    <thead>
      {subheader_html}
      <tr>{header_html}</tr>
    </thead>
    <tbody>{"".join(rows_html)}</tbody>
  </table>
</div>
"""
    return Markup(table)
