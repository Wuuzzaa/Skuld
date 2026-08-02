import type { Position } from './deltaPortfolioStore';

/**
 * Parst ein IBKR/CapTrader Activity-Statement CSV im Browser.
 * Portierung von `_parse_ibkr_csv` (Streamlit delta_portfolio.py).
 *
 * Liest die Sektion "Mark-to-Market-Performance-Überblick":
 *  - Aktien:   Menge + Richtung aus "Aktuell Menge"
 *  - Optionen: Symbol-String "AAPL 18SEP26 150 P" → strike, expiry, contract_type
 * Positionen mit Aktuell-Menge 0 (heute geschlossen) werden übersprungen.
 */

const MONTHS: Record<string, string> = {
  JAN: '01', FEB: '02', MAR: '03', APR: '04', MAY: '05', JUN: '06',
  JUL: '07', AUG: '08', SEP: '09', OCT: '10', NOV: '11', DEC: '12',
};

/** "18SEP26" → "2026-09-18". Fällt auf Rohwert zurück, wenn unparsbar. */
function parseExpiry(raw: string): string {
  const m = raw.match(/^(\d{2})([A-Z]{3})(\d{2})$/);
  if (!m) return raw;
  const [, dd, mon, yy] = m;
  const mm = MONTHS[mon];
  if (!mm) return raw;
  return `20${yy}-${mm}-${dd}`;
}

/** Minimaler CSV-Zeilen-Splitter mit Anführungszeichen-Support. */
function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') { cur += '"'; i++; }
      else inQuotes = !inQuotes;
    } else if (ch === ',' && !inQuotes) {
      out.push(cur);
      cur = '';
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out;
}

export function parseIbkrCsv(content: string): Position[] {
  const positions: Position[] = [];
  let mtmHeader: string[] = [];

  const lines = content.split(/\r?\n/);
  for (const rawLine of lines) {
    if (!rawLine.trim()) continue;
    const row = splitCsvLine(rawLine).map((c) => c.trim());
    const section = row[0];

    if (section !== 'Mark-to-Market-Performance-Überblick') continue;

    const recordType = row[1] ?? '';
    if (recordType === 'Header') {
      mtmHeader = row.slice(2);
      continue;
    }
    if (recordType !== 'Data' || !mtmHeader.length) continue;

    const data: Record<string, string> = {};
    mtmHeader.forEach((h, i) => { data[h] = row[2 + i] ?? ''; });

    const assetClass = (data['Vermögenswertkategorie'] || '').trim();
    const symbolRaw = (data['Symbol'] || '').trim();
    const qtyNow = parseFloat(data['Aktuell Menge'] || '0');
    if (!Number.isFinite(qtyNow) || qtyNow === 0) continue;

    if (assetClass === 'Aktien') {
      positions.push({
        type: 'stock',
        symbol: symbolRaw.toUpperCase(),
        qty: Math.abs(Math.round(qtyNow)),
        direction: qtyNow > 0 ? 'Long' : 'Short',
      });
    } else if (assetClass === 'Aktien- und Indexoptionen') {
      const m = symbolRaw.match(/^([A-Z0-9]+)\s+(\d{2}[A-Z]{3}\d{2})\s+([\d.]+)\s+([CP])$/);
      if (!m) continue;
      const [, sym, expiryRaw, strikeStr, cp] = m;
      positions.push({
        type: 'option',
        symbol: sym.toUpperCase(),
        contract_type: cp === 'C' ? 'call' : 'put',
        strike: parseFloat(strikeStr),
        expiry: parseExpiry(expiryRaw),
        contracts: Math.abs(Math.round(qtyNow)),
        direction: qtyNow > 0 ? 'Long' : 'Short',
      });
    }
  }

  return positions;
}
