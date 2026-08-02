'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ComposedChart, Area, Line, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { getSymbolChart, getSymbolDetails } from '@/lib/api';
import { cn, formatCurrency, formatNumber } from '@/lib/utils';
import { X } from 'lucide-react';

const RANGES = ['1M', '3M', '6M', '1Y', '3Y'] as const;
type Range = (typeof RANGES)[number];
type Tab = 'expirations' | 'stats' | 'technicals';

type Props = { symbol: string; onClose: () => void };

export function SymbolChartPanel({ symbol, onClose }: Props) {
  const [range, setRange] = useState<Range>('6M');
  const [tab, setTab] = useState<Tab>('expirations');

  const { data: chart, isLoading } = useQuery({
    queryKey: ['symbol-chart', symbol, range],
    queryFn: () => getSymbolChart(symbol, range),
    enabled: !!symbol,
  });
  const { data: details } = useQuery({
    queryKey: ['symbol-detail', symbol],
    queryFn: () => getSymbolDetails(symbol),
    enabled: !!symbol,
  });

  // Historie + Expected-Range-Fächer (in die Zukunft projiziert) in einen Datensatz.
  const { series, spot } = useMemo(() => buildSeries(chart), [chart]);

  const fundamentals = details?.fundamentals?.[0];

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />
      {/* Slide-in Panel rechts */}
      <div className="fixed right-0 top-0 z-50 h-full w-full max-w-2xl overflow-y-auto bg-background border-l border-border shadow-2xl">
        {/* Kopf */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-card px-5 py-3">
          <div className="flex items-baseline gap-3">
            <span className="text-lg font-bold text-primary">{symbol}</span>
            {fundamentals?.COMPANY_NAME && (
              <span className="text-sm text-muted-foreground">{fundamentals.COMPANY_NAME}</span>
            )}
            {chart?.spot != null && <span className="text-sm font-semibold">{formatCurrency(chart.spot)}</span>}
          </div>
          <button onClick={onClose} className="p-1.5 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* Range-Umschalter + Legende */}
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex gap-1">
              {RANGES.map((r) => (
                <button key={r} onClick={() => setRange(r)}
                  className={cn('px-2.5 py-1 rounded text-xs font-medium transition-colors',
                    range === r ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground')}>
                  {r}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
              <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: '#2FA36B' }} /> Expected Range</span>
              <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: '#D9962B' }} /> Max Pain</span>
            </div>
          </div>

          {/* Chart */}
          {isLoading ? (
            <div className="h-72 flex items-center justify-center text-sm text-muted-foreground">Lade Chart…</div>
          ) : series.length === 0 ? (
            <div className="h-72 flex items-center justify-center text-sm text-muted-foreground">Keine Kursdaten für {symbol}.</div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={series} margin={{ top: 8, right: 8, bottom: 4, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="label" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} minTickGap={40} />
                <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                  tickFormatter={(v) => `$${Number(v).toFixed(0)}`} />
                <Tooltip
                  formatter={(v: any, name: any) => [v == null ? '—' : `$${Number(v).toFixed(2)}`, name]}
                  contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8, fontSize: 12 }} />
                {/* Historie */}
                <Line type="monotone" dataKey="close" name="Kurs" stroke="#2F80ED" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
                {/* Expected Range Fächer */}
                <Line type="monotone" dataKey="expHigh" name="Exp. High" stroke="#2FA36B" strokeWidth={1.5} strokeDasharray="4 3" dot={false} isAnimationActive={false} connectNulls />
                <Line type="monotone" dataKey="expLow" name="Exp. Low" stroke="#DC5757" strokeWidth={1.5} strokeDasharray="4 3" dot={false} isAnimationActive={false} connectNulls />
                {/* Max Pain Punkte */}
                <Scatter dataKey="maxPain" name="Max Pain" fill="#D9962B" isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          )}

          {/* Tabs */}
          <div className="flex gap-1 border-b border-border">
            {([['expirations', 'Expirations'], ['stats', 'Stats'], ['technicals', 'Technicals']] as [Tab, string][]).map(([k, label]) => (
              <button key={k} onClick={() => setTab(k)}
                className={cn('px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
                  tab === k ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground')}>
                {label}
              </button>
            ))}
          </div>

          {tab === 'expirations' && <ExpirationsTab expirations={chart?.expirations || []} />}
          {tab === 'stats' && <StatsTab f={fundamentals} />}
          {tab === 'technicals' && <TechnicalsTab rows={details?.technicals || []} />}
        </div>
      </div>
    </>
  );
}

// ── Chart-Datensatz bauen: Historie + Zukunfts-Fächer ────────────────────────
function buildSeries(chart: any) {
  if (!chart?.price_history?.length) return { series: [], spot: null };
  const spot = chart.spot ?? chart.price_history[chart.price_history.length - 1]?.close ?? null;

  const series: any[] = chart.price_history.map((p: any) => ({
    label: p.date.slice(5), // MM-DD
    close: p.close,
    expHigh: null, expLow: null, maxPain: null,
  }));

  // Ankerpunkt: letzter Kurs = Start des Fächers
  const exps = (chart.expirations || [])
    .filter((e: any) => e.expected_high != null && e.expected_low != null)
    .sort((a: any, b: any) => a.dte - b.dte);

  if (exps.length && spot != null) {
    // Startpunkt am letzten Historie-Datenpunkt verankern
    const last = series[series.length - 1];
    last.expHigh = spot; last.expLow = spot;
    for (const e of exps) {
      series.push({
        label: e.expiration_date.slice(5),
        close: null,
        expHigh: e.expected_high,
        expLow: e.expected_low,
        maxPain: e.max_pain ?? null,
      });
    }
  }
  return { series, spot };
}

// ── Tabs ─────────────────────────────────────────────────────────────────────
function ExpirationsTab({ expirations }: { expirations: any[] }) {
  if (!expirations.length) return <Empty>Keine Optionsdaten.</Empty>;
  return (
    <div className="overflow-auto rounded-md border border-border max-h-80">
      <table className="w-full text-sm">
        <thead className="bg-muted text-muted-foreground sticky top-0">
          <tr>{['Expiration', 'DTE', 'Expected Range', 'IV', 'Max Pain'].map((h) => (
            <th key={h} className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide">{h}</th>))}</tr>
        </thead>
        <tbody>
          {expirations.map((e) => (
            <tr key={e.expiration_date} className="border-t border-border/60">
              <td className="px-3 py-2">{e.expiration_date}</td>
              <td className="px-3 py-2">{e.dte}d</td>
              <td className="px-3 py-2">
                {e.expected_low != null ? `${formatCurrency(e.expected_low)} – ${formatCurrency(e.expected_high)}` : '—'}
                {e.expected_move != null && <span className="text-muted-foreground"> (±{formatCurrency(e.expected_move)})</span>}
              </td>
              <td className="px-3 py-2">{e.iv != null ? `${e.iv}%` : '—'}</td>
              <td className="px-3 py-2 font-medium" style={{ color: '#D9962B' }}>{e.max_pain != null ? formatCurrency(e.max_pain) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatsTab({ f }: { f: any }) {
  if (!f) return <Empty>Keine Fundamentaldaten.</Empty>;
  const items: [string, any][] = [
    ['IV Rank', f.IV_RANK], ['IV', f.IV != null ? `${f.IV}%` : null],
    ['Hist. Vol 30D', f.HISTORICAL_VOLATILITY_30D != null ? `${f.HISTORICAL_VOLATILITY_30D}%` : null],
    ['Beta', f.BETA], ['IV Low', f.IV_LOW != null ? `${f.IV_LOW}%` : null],
    ['IV High', f.IV_HIGH != null ? `${f.IV_HIGH}%` : null],
    ['IV Percentile', f.IV_PERCENTILE], ['Analyst Target', f.ANALYST_MEAN_TARGET != null ? formatCurrency(f.ANALYST_MEAN_TARGET) : null],
    ['Earnings', f.EARNINGS_DATE ? String(f.EARNINGS_DATE).slice(0, 10) : null],
    ['Sektor', f.COMPANY_SECTOR], ['Industrie', f.COMPANY_INDUSTRY],
    ['Dividende', f.DIVIDEND_CLASSIFICATION],
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
      {items.map(([label, val]) => (
        <div key={label} className="rounded-md border border-border bg-secondary/40 px-3 py-2">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
          <div className="text-sm font-bold mt-0.5">{val ?? '—'}</div>
        </div>
      ))}
    </div>
  );
}

function TechnicalsTab({ rows }: { rows: any[] }) {
  const latest = rows?.[rows.length - 1];
  if (!latest) return <Empty>Keine technischen Indikatoren.</Empty>;
  // Kompakte Auswahl gängiger Indikatoren, falls vorhanden
  const keys = ['RSI_14', 'MACD_12_26_9', 'ADX_10', 'STOCHk_14_3_3', 'ATR_14', 'RSL',
    'SMA_20', 'SMA_50', 'SMA_200', 'EMA_20', 'EMA_50', 'EMA_200'];
  const present = keys.filter((k) => latest[k] != null);
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
      {present.map((k) => (
        <div key={k} className="rounded-md border border-border bg-secondary/40 px-3 py-2">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{k.replace(/_/g, ' ')}</div>
          <div className="text-sm font-bold mt-0.5 font-mono">{formatNumber(Number(latest[k]), 2)}</div>
        </div>
      ))}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="py-8 text-center text-sm text-muted-foreground">{children}</div>;
}
