'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getStockPrices, getSectors, getHedgeCandidates } from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { DataTable, Column } from '@/components/ui/data-table';
import { formatCurrency } from '@/lib/utils';
import { cn } from '@/lib/utils';
import type { Position } from '@/lib/deltaPortfolioStore';
import { buildHedgeSuggestions, hedgeScenarios, type HedgeSuggestion } from '@/lib/deltaPortfolio';

const KIND_STYLE: Record<HedgeSuggestion['kind'], { bg: string; border: string; label: string }> = {
  critical: { bg: '#FBEAEA', border: '#DC5757', label: '🔴 Kritisch' },
  hint: { bg: '#FCF3E1', border: '#D9962B', label: '🟡 Hinweis' },
  diversification: { bg: '#E8F1FD', border: '#2F80ED', label: '🔵 Diversifikation' },
};

type Props = {
  positions: Position[];
  totalDelta: number;
  prices: Record<string, number | null>;
};

export function HedgeSection({ positions, totalDelta, prices }: Props) {
  // ── Hedge-Rechner ───────────────────────────────────────────────────────────
  const [targetDelta, setTargetDelta] = useState(0);
  const [hedgeSym, setHedgeSym] = useState('');
  const deltaToHedge = totalDelta - targetDelta;

  const { data: hedgePrices = {} } = useQuery({
    queryKey: ['dpt-hedge-price', hedgeSym],
    queryFn: () => getStockPrices([hedgeSym.toUpperCase()]),
    enabled: hedgeSym.trim().length > 0,
  });
  const hedgePrice = hedgeSym ? hedgePrices[hedgeSym.toUpperCase()] ?? null : null;

  // ── Sektoren für Vorschläge ─────────────────────────────────────────────────
  const symbols = useMemo(() => Array.from(new Set(positions.map((p) => p.symbol))), [positions]);
  const { data: sectors = {} } = useQuery({
    queryKey: ['dpt-sectors', symbols],
    queryFn: () => getSectors(symbols),
    enabled: symbols.length > 0,
  });

  const suggestions = useMemo(
    () => buildHedgeSuggestions(positions, totalDelta, prices, sectors),
    [positions, totalDelta, prices, sectors],
  );

  return (
    <div className="space-y-6">
      {/* ── Hedge-Rechner ── */}
      <section className="space-y-3">
        <div>
          <h2 className="text-base font-semibold">🧮 Hedge-Rechner</h2>
          <p className="text-sm text-muted-foreground">Wie viel brauche ich um delta-neutral zu werden?</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div><label className="text-xs text-muted-foreground">Ziel-Delta</label>
            <Input type="number" value={targetDelta} step={10} onChange={(e) => setTargetDelta(Number(e.target.value))} className="w-32" /></div>
        </div>
        {Math.abs(deltaToHedge) < 0.1 ? (
          <p className="text-sm text-positive">✅ Portfolio ist bereits nahe am Ziel-Delta.</p>
        ) : (
          <>
            <p className="text-sm">
              Du musst <b>{deltaToHedge > 0 ? 'Short' : 'Long'} {Math.abs(deltaToHedge).toFixed(1)} Delta</b> aufbauen,
              um auf {targetDelta.toFixed(0)} zu kommen.
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <div><label className="text-xs text-muted-foreground">Symbol für Hedge</label>
                <Input value={hedgeSym} onChange={(e) => setHedgeSym(e.target.value)} placeholder="AAPL" className="w-40" /></div>
            </div>
            {hedgeSym && hedgePrice != null && (
              <div className="grid md:grid-cols-2 gap-3">
                <Card><CardContent className="p-4">
                  <div className="text-sm font-medium">📈 Aktien-Hedge</div>
                  <div className="text-sm mt-1">{deltaToHedge > 0 ? 'Short' : 'Long'} <b>{Math.abs(deltaToHedge).toFixed(0)} Stück {hedgeSym.toUpperCase()}</b></div>
                  <div className="text-xs text-muted-foreground">Kosten: ~{formatCurrency(Math.abs(deltaToHedge) * hedgePrice)}</div>
                </CardContent></Card>
                <Card><CardContent className="p-4">
                  {(() => {
                    const contracts = Math.max(1, Math.ceil(Math.abs(deltaToHedge) / 50));
                    const optType = deltaToHedge > 0 ? 'put' : 'call';
                    return (<>
                      <div className="text-sm font-medium">{optType === 'put' ? '🔴 Put' : '🟢 Call'}-Hedge (ATM ~Δ0.50)</div>
                      <div className="text-sm mt-1">Kauf <b>{contracts} ATM-{optType[0].toUpperCase()}{optType.slice(1)}-Kontrakte {hedgeSym.toUpperCase()}</b></div>
                      <div className="text-xs text-muted-foreground">Ergibt ca. {deltaToHedge > 0 ? 'Short' : 'Long'} {(contracts * 50).toFixed(0)} Delta</div>
                    </>);
                  })()}
                </CardContent></Card>
              </div>
            )}
          </>
        )}
      </section>

      {/* ── Hedge-Vorschläge ── */}
      <section className="space-y-3">
        <div>
          <h2 className="text-base font-semibold">💡 Hedge- & Diversifikations-Vorschläge</h2>
          <p className="text-sm text-muted-foreground">Automatische Analyse auf Klumpenrisiken und Lücken.</p>
        </div>
        {suggestions.length === 0 ? (
          <p className="text-sm text-positive">✅ Keine kritischen Klumpenrisiken erkannt. Portfolio ist gut diversifiziert.</p>
        ) : (
          <div className="space-y-2">
            {suggestions.map((s, i) => {
              const st = KIND_STYLE[s.kind];
              return (
                <div key={i} className="rounded-md px-4 py-3" style={{ background: st.bg, borderLeft: `4px solid ${st.border}` }}>
                  <div className="text-xs font-bold" style={{ color: st.border }}>{st.label}</div>
                  <div className="text-sm font-semibold text-foreground mt-0.5">{s.title}</div>
                  <div className="text-sm text-foreground/80 mt-1">{s.detail}</div>
                  <div className="text-sm mt-1"><b>Vorschlag:</b> {s.suggestion}</div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* ── Konkrete Hedge-Kandidaten (Tabs) ── */}
      <HedgeCandidatesTabs positions={positions} prices={prices} />
    </div>
  );
}

// ── Tabs: Einzelwert / SPY / VIX ─────────────────────────────────────────────

type TabKey = 'single' | 'spy' | 'vix';

function HedgeCandidatesTabs({ positions, prices }: { positions: Position[]; prices: Record<string, number | null> }) {
  const [tab, setTab] = useState<TabKey>('single');

  const stockSymbols = useMemo(
    () => Array.from(new Set(positions.filter((p) => p.type === 'stock').map((p) => p.symbol))),
    [positions],
  );
  const totalNotional = useMemo(
    () => positions.filter((p) => p.type === 'stock').reduce((a, p: any) => a + (prices[p.symbol] || 0) * p.qty, 0),
    [positions, prices],
  );

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-base font-semibold">🔍 Konkrete Hedge-Kandidaten (live aus DB)</h2>
        <p className="text-sm text-muted-foreground">Zeile anklicken → Kosten- und Schutz-Rechnung erscheint darunter.</p>
      </div>

      <div className="flex gap-1 border-b border-border">
        {([['single', '📌 Einzelwert-Hedge'], ['spy', '📊 SPY Index-Hedge'], ['vix', '⚡ VIX-Hedge']] as [TabKey, string][]).map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            className={cn('px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
              tab === k ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground')}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'single' && <SingleHedgeTab positions={positions} stockSymbols={stockSymbols} prices={prices} />}
      {tab === 'spy' && <SpyHedgeTab totalNotional={totalNotional} prices={prices} />}
      {tab === 'vix' && <VixHedgeTab prices={prices} />}
    </section>
  );
}

// ── gemeinsame Kandidaten-Tabelle + Szenario-Detail ──────────────────────────

function CandidateTable({
  symbol, stockPrice, qtyOrNotional, isIndex,
}: { symbol: string; stockPrice: number; qtyOrNotional: number; isIndex: boolean }) {
  const [selected, setSelected] = useState<number | null>(null);
  const { data = [], isLoading } = useQuery({
    queryKey: ['dpt-hedge-candidates', symbol, stockPrice],
    queryFn: () => getHedgeCandidates(symbol, stockPrice),
    enabled: !!symbol && stockPrice > 0,
  });

  const rows = useMemo(
    () => (Array.isArray(data) ? data : []).map((r: any) => ({
      ...r,
      puffer: ((stockPrice - r.strike_price) / stockPrice) * 100,
      kosten_kontrakt: Math.round((r.praemie ?? 0) * 100),
    })),
    [data, stockPrice],
  );

  const columns: Column[] = [
    { key: 'strike_price', label: 'Strike', align: 'right', format: (v) => formatCurrency(v) },
    { key: 'expiration_date', label: 'Verfall' },
    { key: 'days_to_expiration', label: 'DTE', align: 'right' },
    { key: 'puffer', label: 'Puffer %', align: 'right', format: (v) => `${Number(v).toFixed(1)}%` },
    { key: 'praemie', label: 'Prämie $', align: 'right', format: (v) => formatCurrency(v) },
    { key: 'kosten_kontrakt', label: 'Kosten/Kontrakt $', align: 'right', format: (v) => formatCurrency(v) },
    { key: 'delta', label: 'Delta', align: 'right', format: (v) => Number(v).toFixed(3) },
    { key: 'iv_pct', label: 'IV %', align: 'right', format: (v) => `${Number(v).toFixed(1)}%` },
    { key: 'iv_rank', label: 'IV Rank', align: 'right', format: (v) => (v == null ? '—' : Number(v).toFixed(0)) },
    { key: 'oi', label: 'OI', align: 'right' },
  ];

  if (isLoading) return <p className="text-sm text-muted-foreground">Lade Kandidaten…</p>;
  if (!rows.length) return <p className="text-sm text-muted-foreground">Keine liquiden OTM-Puts für {symbol} in der DB.</p>;

  const sel = selected != null ? rows[selected] : null;

  return (
    <div className="space-y-3">
      <DataTable data={rows} columns={columns} maxHeight="320px"
        onRowClick={(_, i) => setSelected(i)} selectedIndex={selected} />
      <p className="text-xs text-muted-foreground">🔴 IV Rank ≥ 60 = teuer · 🟡 40–60 = fair · sonst günstig als Hedge. Zeile anklicken → Szenario-Rechnung.</p>
      {sel && <ScenarioDetail row={sel} stockPrice={stockPrice} qtyOrNotional={qtyOrNotional} isIndex={isIndex} />}
    </div>
  );
}

function ScenarioDetail({
  row, stockPrice, qtyOrNotional, isIndex,
}: { row: any; stockPrice: number; qtyOrNotional: number; isIndex: boolean }) {
  const strike = Number(row.strike_price);
  const premium = Number(row.praemie);
  const puffer = Number(row.puffer);
  const contracts = isIndex
    ? Math.max(1, Math.round(qtyOrNotional / (stockPrice * 100)))
    : Math.max(1, Math.round(qtyOrNotional / 100));
  const kostenGesamt = premium * 100 * contracts;
  const schutzAb = stockPrice * (1 - puffer / 100);
  const maxGewinn = (strike - premium) * 100 * contracts;
  const breakeven = strike - premium;
  const ivRank = row.iv_rank != null ? Number(row.iv_rank) : null;
  const ivColor = (ivRank ?? 0) >= 60 ? '#DC5757' : (ivRank ?? 0) >= 40 ? '#D9962B' : '#2FA36B';
  const ivLabel = (ivRank ?? 0) >= 60 ? 'teuer — schlechter Zeitpunkt' : (ivRank ?? 0) >= 40 ? 'fair' : 'günstig — guter Zeitpunkt';

  const scenarios = hedgeScenarios(strike, premium, stockPrice, contracts, qtyOrNotional, isIndex);

  return (
    <div className="rounded-md px-4 py-4 space-y-3" style={{ background: '#E8F1FD', borderLeft: '4px solid #2F80ED' }}>
      <div>
        <div className="text-sm font-bold text-foreground">
          {row.symbol} Put {strike.toFixed(0)} · Verfall {row.expiration_date} · {row.days_to_expiration} DTE
        </div>
        <div className="text-xs text-muted-foreground mt-0.5">
          Prämie <b className="text-foreground">{formatCurrency(premium)}</b> · {contracts} Kontrakt{contracts > 1 ? 'e' : ''} ·{' '}
          <b>Gesamtkosten: {formatCurrency(kostenGesamt)}</b> · Puffer bis Strike: <b>{puffer.toFixed(1)}%</b> (Schutz ab {formatCurrency(schutzAb)}) ·{' '}
          IV Rank: <b style={{ color: ivColor }}>{ivRank != null ? `${ivRank.toFixed(0)}% — ${ivLabel}` : '—'}</b>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Metric label="Kosten (einmalig)" value={formatCurrency(kostenGesamt)} />
        <Metric label="Max. Gewinn des Puts" value={formatCurrency(maxGewinn)} />
        <Metric label="Put Breakeven" value={formatCurrency(breakeven)} />
      </div>
      <div>
        <div className="text-sm font-medium mb-1">Schutzwirkung in verschiedenen Szenarien:</div>
        <div className="overflow-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted text-muted-foreground">
              <tr>{['Szenario', 'Aktien-Verlust $', 'Put-Gewinn $', 'Netto $', 'Abgefedert %'].map((h) => (
                <th key={h} className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide">{h}</th>))}</tr>
            </thead>
            <tbody>
              {scenarios.map((s) => (
                <tr key={s.scenario} className="border-t border-border/60">
                  <td className="px-3 py-2">{s.scenario}</td>
                  <td className="px-3 py-2 text-negative">{fmtSigned(s.stockLoss)}</td>
                  <td className="px-3 py-2 text-positive">{fmtSigned(s.putGain)}</td>
                  <td className={cn('px-3 py-2', s.net >= 0 ? 'text-positive' : 'text-negative')}>{fmtSigned(s.net)}</td>
                  <td className="px-3 py-2">{s.cushionPct != null ? `${s.cushionPct.toFixed(0)}%` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function SingleHedgeTab({ positions, stockSymbols, prices }: { positions: Position[]; stockSymbols: string[]; prices: Record<string, number | null> }) {
  const allSyms = useMemo(() => Array.from(new Set(positions.map((p) => p.symbol))).sort(), [positions]);
  const [sym, setSym] = useState(allSyms[0] || '');
  const price = sym ? prices[sym] ?? null : null;
  const qty = positions.filter((p: any) => p.type === 'stock' && p.symbol === sym).reduce((a, p: any) => a + p.qty, 0);

  return (
    <div className="space-y-3">
      <div className="flex items-end gap-3">
        <div><label className="text-xs text-muted-foreground">Symbol auswählen</label>
          <select value={sym} onChange={(e) => setSym(e.target.value)}
            className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm">
            {allSyms.map((s) => <option key={s} value={s}>{s}</option>)}
          </select></div>
      </div>
      {!sym ? null : price == null ? (
        <p className="text-sm text-muted-foreground">Kein Kurs für {sym} in der DB.</p>
      ) : (
        <>
          <p className="text-sm"><b>{sym}</b> · Kurs {formatCurrency(price)} · {qty} Stück im Portfolio</p>
          <CandidateTable symbol={sym} stockPrice={price} qtyOrNotional={qty || 100} isIndex={false} />
        </>
      )}
    </div>
  );
}

function SpyHedgeTab({ totalNotional, prices }: { totalNotional: number; prices: Record<string, number | null> }) {
  const [hedgePct, setHedgePct] = useState(50);
  const { data: spyPrices = {} } = useQuery({
    queryKey: ['dpt-spy-price'],
    queryFn: () => getStockPrices(['SPY']),
  });
  const spyPrice = spyPrices['SPY'] ?? null;

  if (spyPrice == null || totalNotional <= 0) {
    return <p className="text-sm text-muted-foreground">Kein SPY-Kurs oder keine Aktienposition vorhanden.</p>;
  }
  const hedgeNotional = (totalNotional * hedgePct) / 100;

  return (
    <div className="space-y-3">
      <div>
        <label className="text-xs text-muted-foreground">Wieviel % des Portfolios absichern? — {hedgePct}%</label>
        <input type="range" min={10} max={100} step={5} value={hedgePct}
          onChange={(e) => setHedgePct(Number(e.target.value))} className="w-full accent-[color:hsl(var(--primary))]" />
      </div>
      <p className="text-sm">
        <b>SPY</b> · Kurs {formatCurrency(spyPrice)} · Aktien-Notional: <b>{formatCurrency(totalNotional)}</b> ·{' '}
        {hedgePct}%-Absicherung: <b>{formatCurrency(hedgeNotional)}</b>
      </p>
      <CandidateTable symbol="SPY" stockPrice={spyPrice} qtyOrNotional={hedgeNotional} isIndex />
    </div>
  );
}

function VixHedgeTab({ prices }: { prices: Record<string, number | null> }) {
  const { data: vixPrices = {} } = useQuery({
    queryKey: ['dpt-vix'],
    queryFn: () => getStockPrices(['^VIX']),
  });
  const vix = vixPrices['^VIX'] ?? null;

  return (
    <div className="space-y-3 text-sm">
      <h3 className="text-base font-semibold">⚡ VIX-Call als Crash-Hedge</h3>
      <p className="text-muted-foreground">
        Der VIX misst die erwartete Schwankungsbreite des S&P 500 und steigt stark, wenn der Markt fällt — oft überproportional
        (−10% → +50–80% VIX, −35% Covid → +300%). Long VIX Calls profitieren direkt von Crashes.
      </p>
      {vix != null ? (
        <Card><CardContent className="p-4 text-center">
          <div className="text-xs text-muted-foreground">Aktueller VIX</div>
          <div className="text-3xl font-extrabold" style={{ color: vix < 20 ? '#2FA36B' : vix < 30 ? '#D9962B' : '#DC5757' }}>{vix.toFixed(1)}</div>
          <div className="text-xs text-muted-foreground">{vix < 15 ? '🟢 Sehr niedrig — VIX-Calls günstig' : vix < 20 ? '🟢 Niedrig — guter Einstieg' : vix < 30 ? '🟡 Erhöht — Calls teurer' : '🔴 Hoch — Crash läuft, Calls sehr teuer'}</div>
        </CardContent></Card>
      ) : (
        <p className="text-muted-foreground">VIX-Daten nicht in DB (^VIX). Aktuellen Wert auf finance.yahoo.com/quote/%5EVIX prüfen.</p>
      )}
      <p className="text-xs text-muted-foreground">
        ⚠️ VIX-Calls sind kein 1:1-Ersatz für Put-Hedges — sie korrelieren mit Marktangst, nicht mit deinen Einzelwert-Verlusten. Am besten in Kombination. Position klein halten (1–3% des Portfolios).
      </p>
    </div>
  );
}

// kleine Helfer
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-secondary/50 px-3 py-2">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-lg font-bold">{value}</div>
    </div>
  );
}
function fmtSigned(v: number): string {
  const s = v >= 0 ? '+' : '-';
  return `${s}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}
