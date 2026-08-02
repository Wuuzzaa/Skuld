import type { Position } from './deltaPortfolioStore';

/**
 * Reine Rechenlogik des Delta-Portfolios — Portierung aus delta_portfolio.py.
 * Keine Seiteneffekte, kein React. Preise/Delta/Sektoren kommen von außen rein.
 */

// ── Payoff (Risikograf) ──────────────────────────────────────────────────────

/** P&L einer Aktienposition bei Kurs `price`. */
export function payoffStock(qty: number, direction: 'Long' | 'Short', entry: number, price: number): number {
  const sign = direction === 'Long' ? 1 : -1;
  return sign * qty * (price - entry);
}

/** P&L einer Optionsposition bei Verfall (nur Intrinsic, kein IV-Einfluss). */
export function payoffOption(
  contracts: number,
  direction: 'Long' | 'Short',
  contractType: 'call' | 'put',
  strike: number,
  premium: number,
  price: number,
): number {
  const sign = direction === 'Long' ? 1 : -1;
  const intrinsic = contractType === 'call' ? Math.max(price - strike, 0) : Math.max(strike - price, 0);
  return sign * (intrinsic - premium) * contracts * 100;
}

/**
 * Schätzt den IV-Multiplikator bei einem Marktfall (VIX-Korrelationsmodus).
 * `dropPct` als positiver Anteil (0.20 = -20%). Kalibriert auf 2008/2020/2022.
 */
export function vixIvMultiplier(dropPct: number): number {
  if (dropPct <= 0) return 1.0;
  return 1.0 + 4.5 * dropPct ** 1.6;
}

// ── Delta-Aggregat ───────────────────────────────────────────────────────────

export type PositionDelta = {
  index: number;
  posDelta: number;
  hasDelta: boolean;
};

/**
 * Netto-Delta pro Position. `optionDelta(pos)` liefert den rohen greeks_delta
 * (oder null wenn unbekannt). Aktien = ±1 pro Stück, Optionen = ±contracts·100·delta.
 */
export function computePositionDelta(
  pos: Position,
  optionDelta: (p: Position) => number | null,
): PositionDelta {
  const sign = pos.direction === 'Long' ? 1 : -1;
  if (pos.type === 'stock') {
    return { index: -1, posDelta: sign * pos.qty * 1.0, hasDelta: true };
  }
  const raw = optionDelta(pos);
  if (raw == null) return { index: -1, posDelta: 0, hasDelta: false };
  return { index: -1, posDelta: sign * pos.contracts * 100 * raw, hasDelta: true };
}

// ── Netto-Delta-Banner (5 Stufen) ────────────────────────────────────────────

export type DeltaRegime = {
  label: string;
  /** OA-Soft-Ampel: Hintergrund, Rand/Akzentfarbe (Tailwind-inline-Werte). */
  bg: string;
  border: string;
};

export function deltaRegime(totalDelta: number): DeltaRegime {
  if (totalDelta > 50) return { label: '🟢 BULLISH', bg: '#E6F4EC', border: '#2FA36B' };
  if (totalDelta > 10) return { label: '🟡 LEICHT BULLISH', bg: '#FCF3E1', border: '#D9962B' };
  if (totalDelta >= -10) return { label: '🔵 ANNÄHERND NEUTRAL', bg: '#E8F1FD', border: '#2F80ED' };
  if (totalDelta >= -50) return { label: '🟡 LEICHT BEARISH', bg: '#FCF3E1', border: '#D9962B' };
  return { label: '🔴 BEARISH', bg: '#FBEAEA', border: '#DC5757' };
}

// ── Hedge-Vorschläge (6 Regeln) ──────────────────────────────────────────────

export type HedgeSuggestion = {
  kind: 'critical' | 'hint' | 'diversification';
  title: string;
  detail: string;
  suggestion: string;
};

const DIVERSIFICATION_SECTORS: Record<string, [string, string]> = {
  Energy: ['XLE', 'Energie — negative Ölpreis-Korrelation zum Tech-Sektor'],
  'Consumer Staples': ['XLP', 'Defensive Konsumgüter — Rezessions-Hedge'],
  Utilities: ['XLU', 'Versorger — steigen oft wenn Zinsen fallen'],
  Healthcare: ['XLV', 'Gesundheit — weitgehend konjunkturunabhängig'],
  'Financial Services': ['XLF', 'Finanzwerte — profitieren von steigenden Zinsen'],
};

/**
 * Erzeugt Hedge-/Diversifikations-Vorschläge. Portierung von
 * `_render_hedge_suggestions`. `prices`/`sectors` sind vorab geladene Maps.
 */
export function buildHedgeSuggestions(
  positions: Position[],
  totalDelta: number,
  prices: Record<string, number | null>,
  sectors: Record<string, string>,
): HedgeSuggestion[] {
  const out: HedgeSuggestion[] = [];
  const stockSyms = Array.from(new Set(positions.filter((p) => p.type === 'stock').map((p) => p.symbol)));

  // 1. Gesamt-Delta-Ausrichtung
  if (totalDelta > 200) {
    out.push({
      kind: 'critical',
      title: 'Sehr hohes Netto-Delta — starkes Klumpenrisiko Long',
      detail: `Dein Netto-Delta ist ${totalDelta >= 0 ? '+' : ''}${totalDelta.toFixed(0)}. Bei einem Markteinbruch von 10% verlierst du rechnerisch ~${(totalDelta * 0.1).toFixed(0)} × Kurswert.`,
      suggestion: 'Erwäge Index-Puts (SPX/SPY) als Tail-Hedge oder Short Calls auf deine größten Positionen um Delta zu reduzieren.',
    });
  } else if (totalDelta > 100) {
    out.push({
      kind: 'hint',
      title: 'Erhöhtes Netto-Delta',
      detail: `Netto-Delta ${totalDelta >= 0 ? '+' : ''}${totalDelta.toFixed(0)} — Portfolio ist klar bullish ausgerichtet.`,
      suggestion: 'Ein partieller Hedge mit 2–3 ATM-Puts auf SPY oder deine größte Einzelposition würde das Risiko deutlich reduzieren.',
    });
  } else if (totalDelta < -50) {
    out.push({
      kind: 'hint',
      title: 'Hohes negatives Delta — bearish ausgerichtet',
      detail: `Netto-Delta ${totalDelta.toFixed(0)} — Portfolio profitiert von fallenden Kursen.`,
      suggestion: 'Falls kein bewusster Hedge: Long Calls oder Bull Put Spreads um Delta zu neutralisieren.',
    });
  }

  // 2. Sektor-Klumpen (≥2 Aktien im selben Sektor)
  const sectorCounts: Record<string, string[]> = {};
  for (const sym of stockSyms) {
    const sec = sectors[sym] || 'Unbekannt';
    (sectorCounts[sec] ||= []).push(sym);
  }
  for (const [sec, syms] of Object.entries(sectorCounts)) {
    if (syms.length >= 2) {
      out.push({
        kind: 'hint',
        title: `Sektor-Klumpen: ${sec}`,
        detail: `${syms.join(', ')} sind alle im selben Sektor. Ein sektorspezifischer Schock trifft alle gleichzeitig.`,
        suggestion: `Diversifikation durch Positionen in anderen Sektoren — oder Short Calls auf ${syms[0]} als partiellen Hedge.`,
      });
    }
  }

  // 3. Fehlende Sektoren (≥3 der Diversifikations-Sektoren nicht abgedeckt)
  const covered = new Set(stockSyms.map((s) => sectors[s]).filter(Boolean));
  const missing = Object.entries(DIVERSIFICATION_SECTORS).filter(([sec]) => !covered.has(sec));
  if (missing.length >= 3) {
    const etfList = missing.slice(0, 3).map(([, [etf]]) => etf).join(', ');
    out.push({
      kind: 'diversification',
      title: 'Kaum Sektor-Diversifikation',
      detail: `Dein Portfolio enthält keine Positionen in: ${missing.map(([sec]) => sec).join(', ')}.`,
      suggestion: `Sektor-ETFs als einfache Beimischung: ${etfList} — oder Covered Calls auf bestehende Positionen finanzieren den Kauf.`,
    });
  }

  // 4. Einzelne Riesenpositionen (>40% des Aktien-Notionals)
  const stockPositions = positions.filter((p): p is Extract<Position, { type: 'stock' }> => p.type === 'stock');
  const notionals = stockPositions.map((p) => ({ sym: p.symbol, val: (prices[p.symbol] || 0) * p.qty }));
  const totalNotional = notionals.reduce((a, b) => a + b.val, 0);
  if (totalNotional > 0) {
    for (const { sym, val } of notionals) {
      const pct = (val / totalNotional) * 100;
      if (pct > 40) {
        out.push({
          kind: 'critical',
          title: `${sym} macht ${pct.toFixed(0)}% deines Aktien-Notionals aus`,
          detail: `$${val.toLocaleString('en-US', { maximumFractionDigits: 0 })} in ${sym} — Einzelwert-Klumpenrisiko. Ein -20% Move kostet ~$${(val * 0.2).toLocaleString('en-US', { maximumFractionDigits: 0 })}.`,
          suggestion: `Protective Put auf ${sym} (z.B. 10% OTM, 60–90 DTE) als direkter Hedge. Oder Covered Call verkaufen um den Hedge zu finanzieren.`,
        });
      }
    }
  }

  // 5. Kein Tail-Hedge (kein Long-Put, aber deutlich bullish)
  const hasLongPut = positions.some((p) => p.type === 'option' && p.contract_type === 'put' && p.direction === 'Long');
  if (!hasLongPut && totalDelta > 50) {
    out.push({
      kind: 'hint',
      title: 'Kein Long-Put-Hedge im Portfolio',
      detail: 'Du hast keine Long-Put-Position. Bei einem schnellen Absturz (-20%+) gibt es kein automatisches Gegengewicht.',
      suggestion: '1–2 SPY/SPX Puts weit OTM (5–10% unter aktuellem Kurs, 60–90 DTE) als Tail-Risk-Hedge — kosten wenig, wirken bei echten Crashes.',
    });
  }

  // 6. Nackte Short-Puts (ohne Long-Put-Gegenleg gleicher Symbol/Verfall)
  const keyOf = (p: Extract<Position, { type: 'option' }>) => `${p.symbol}|${p.expiry}`;
  const shortPuts = new Set(
    positions.filter((p): p is Extract<Position, { type: 'option' }> => p.type === 'option' && p.contract_type === 'put' && p.direction === 'Short').map(keyOf),
  );
  const longPutKeys = new Set(
    positions.filter((p): p is Extract<Position, { type: 'option' }> => p.type === 'option' && p.contract_type === 'put' && p.direction === 'Long').map(keyOf),
  );
  const naked = Array.from(shortPuts).filter((k) => !longPutKeys.has(k));
  if (naked.length) {
    const syms = Array.from(new Set(naked.map((k) => k.split('|')[0]))).slice(0, 3);
    out.push({
      kind: 'critical',
      title: `Nackte Short Puts ohne Long-Leg: ${syms.join(', ')}`,
      detail: 'Short Puts ohne schützendes Long-Leg haben theoretisch unbegrenztes Verlustrisiko bis 0.',
      suggestion: 'Bull Put Spread — kauf einen weiter OTM Put dazu um das maximale Verlustrisiko zu begrenzen.',
    });
  }

  return out;
}

// ── Szenario-Rechnung (Hedge-Detail) ─────────────────────────────────────────

export type ScenarioRow = {
  scenario: string;
  stockLoss: number;
  putGain: number;
  net: number;
  cushionPct: number | null;
};

/**
 * Schutzwirkung eines Puts in -10/-20/-40%-Szenarien. Portierung aus
 * `_render_hedge_detail`. `qtyOrNotional` = Stückzahl (Einzelwert) bzw.
 * abzusicherndes Notional in $ (Index).
 */
export function hedgeScenarios(
  strike: number,
  premium: number,
  stockPrice: number,
  contracts: number,
  qtyOrNotional: number,
  isIndex: boolean,
): ScenarioRow[] {
  const scen: [number, string][] = [
    [-10, 'normaler Rücksetzer'],
    [-20, 'Korrektur'],
    [-40, 'Crash'],
  ];
  return scen.map(([dropPct, label]) => {
    const priceThen = stockPrice * (1 + dropPct / 100);
    const intrinsic = Math.max(strike - priceThen, 0);
    const putGain = (intrinsic - premium) * 100 * contracts;
    const stockLoss = isIndex
      ? (dropPct / 100) * qtyOrNotional
      : ((priceThen - stockPrice) * qtyOrNotional) / stockPrice;
    const net = stockLoss + putGain;
    return {
      scenario: `${dropPct}% (${label})`,
      stockLoss,
      putGain,
      net,
      cushionPct: stockLoss !== 0 ? Math.abs((putGain / stockLoss) * 100) : null,
    };
  });
}
