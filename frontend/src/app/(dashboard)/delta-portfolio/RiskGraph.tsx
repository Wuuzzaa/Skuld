'use client';

import { useMemo, useState } from 'react';
import {
  ComposedChart, Area, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine,
} from 'recharts';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import type { Position } from '@/lib/deltaPortfolioStore';
import { payoffStock, payoffOption, vixIvMultiplier } from '@/lib/deltaPortfolio';
import { callValue, putValue } from '@/lib/blackScholes';

type Props = {
  positions: Position[];
  prices: Record<string, number | null>;
};

const RISK_FREE = 0.04;

export function RiskGraph({ positions, prices }: Props) {
  const [rangePct, setRangePct] = useState(40);
  const [vixMode, setVixMode] = useState(false);
  const [ivShift, setIvShift] = useState(0);
  const [entryOverrides, setEntryOverrides] = useState<Record<number, number>>({});

  // Basis-Kurs: erster Aktien-Kurs, sonst erstes Options-Underlying
  const basePrice = useMemo(() => {
    const stockPx = positions.filter((p) => p.type === 'stock').map((p) => prices[p.symbol]).find((x) => x != null);
    if (stockPx != null) return stockPx;
    const firstOpt = positions.find((p) => p.type === 'option');
    return firstOpt ? prices[firstOpt.symbol] ?? null : null;
  }, [positions, prices]);

  const { data, maxProfit, maxLoss, breakevens, atZero } = useMemo(() => {
    if (basePrice == null) return { data: [], maxProfit: 0, maxLoss: 0, breakevens: 0, atZero: 0 };
    const lo = basePrice * (1 - rangePct / 100);
    const hi = basePrice * (1 + rangePct / 100);
    const N = 120;
    const pts: { pct: number; price: number; pnl: number; pos: number | null; neg: number | null }[] = [];

    for (let i = 0; i < N; i++) {
      const price = lo + ((hi - lo) * i) / (N - 1);
      let pnl = 0;
      positions.forEach((pos, idx) => {
        const entry = entryOverrides[idx];
        if (pos.type === 'stock') {
          const entryPx = entry && entry > 0 ? entry : prices[pos.symbol] ?? basePrice;
          pnl += payoffStock(pos.qty, pos.direction, entryPx, price);
        } else {
          const premium = entry && entry > 0 ? entry : 0.5;
          if (vixMode) {
            const drop = Math.max((basePrice - price) / basePrice, 0);
            const adj = pos.direction === 'Long' && pos.contract_type === 'put' ? premium * vixIvMultiplier(drop) : premium;
            pnl += payoffOption(pos.contracts, pos.direction, pos.contract_type, pos.strike, adj, price);
          } else if (ivShift > 0 && pos.expiry) {
            const dteDays = Math.max(1, Math.round((new Date(pos.expiry).getTime() - Date.now()) / 86400000));
            const baseIv = (premium / basePrice) * Math.sqrt(365 / dteDays);
            const shiftedIv = baseIv * (1 + ivShift / 100);
            const val = pos.contract_type === 'call'
              ? callValue(price, pos.strike, shiftedIv, dteDays, RISK_FREE)
              : putValue(price, pos.strike, shiftedIv, dteDays, RISK_FREE);
            const sign = pos.direction === 'Long' ? 1 : -1;
            pnl += sign * (val - premium) * pos.contracts * 100;
          } else {
            pnl += payoffOption(pos.contracts, pos.direction, pos.contract_type, pos.strike, premium, price);
          }
        }
      });
      const pct = ((price - basePrice) / basePrice) * 100;
      pts.push({ pct, price, pnl, pos: pnl >= 0 ? pnl : 0, neg: pnl < 0 ? pnl : 0 });
    }

    const pnls = pts.map((p) => p.pnl);
    let signChanges = 0;
    for (let i = 1; i < pnls.length; i++) if (Math.sign(pnls[i]) !== Math.sign(pnls[i - 1])) signChanges++;

    return {
      data: pts,
      maxProfit: Math.max(...pnls),
      maxLoss: Math.min(...pnls),
      breakevens: signChanges,
      atZero: pts[Math.floor(pts.length / 2)]?.pnl ?? 0,
    };
  }, [positions, prices, basePrice, rangePct, vixMode, ivShift, entryOverrides]);

  if (basePrice == null) {
    return <p className="text-sm text-muted-foreground">Kein Kurs für die Positionen in der DB — Risikograf nicht verfügbar.</p>;
  }

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-base font-semibold">📉 Risikograf — Portfolio-Simulation</h2>
        <p className="text-sm text-muted-foreground">P&L des gesamten Portfolios bei verschiedenen Kursszenarien zum Verfall · Basis {`$${basePrice.toFixed(2)}`}</p>
      </div>

      {/* Steuerung */}
      <div className="grid md:grid-cols-3 gap-4">
        <div>
          <label className="text-xs text-muted-foreground">Kursbereich simulieren (±%) — {rangePct}%</label>
          <input type="range" min={10} max={80} step={5} value={rangePct}
            onChange={(e) => setRangePct(Number(e.target.value))} className="w-full accent-[color:hsl(var(--primary))]" />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={vixMode} onChange={(e) => setVixMode(e.target.checked)} />
          VIX-Korrelation (IV-Anstieg bei Drawdowns)
        </label>
        <div>
          <label className={cn('text-xs text-muted-foreground', vixMode && 'opacity-40')}>Manueller IV-Shift (%) — {ivShift}%</label>
          <input type="range" min={0} max={500} step={5} value={ivShift} disabled={vixMode}
            onChange={(e) => setIvShift(Number(e.target.value))} className="w-full accent-[color:hsl(var(--primary))] disabled:opacity-40" />
        </div>
      </div>

      {/* Einstandspreise */}
      <details className="rounded-md border border-border">
        <summary className="cursor-pointer px-4 py-2 text-sm font-medium">💰 Einstandspreise eingeben (für korrekten P&L)</summary>
        <div className="p-4 grid md:grid-cols-2 gap-2">
          {positions.map((pos, idx) => (
            <div key={idx}>
              <label className="text-xs text-muted-foreground">
                #{idx} {pos.symbol} {pos.type === 'stock' ? 'Stock — Einstiegskurs $' : `${pos.contract_type.toUpperCase()} ${pos.strike} — Prämie $`}
              </label>
              <Input type="number" step={pos.type === 'stock' ? 1 : 0.05}
                value={entryOverrides[idx] ?? ''}
                placeholder={pos.type === 'stock' ? String(prices[pos.symbol] ?? '') : '0.50'}
                onChange={(e) => setEntryOverrides({ ...entryOverrides, [idx]: Number(e.target.value) })} />
            </div>
          ))}
        </div>
      </details>

      {/* Chart */}
      <Card><CardContent className="p-3">
        <ResponsiveContainer width="100%" height={380}>
          <ComposedChart data={data} margin={{ top: 10, right: 10, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="pct" tickFormatter={(v) => `${v >= 0 ? '+' : ''}${Number(v).toFixed(0)}%`}
              tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
            <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
              tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
            <Tooltip
              formatter={(v: any) => [`$${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`, 'P&L']}
              labelFormatter={(v: any) => `Kursveränderung: ${v >= 0 ? '+' : ''}${Number(v).toFixed(1)}%`}
              contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8, fontSize: 12 }} />
            <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeDasharray="4 4" />
            <ReferenceLine x={0} stroke="hsl(var(--muted-foreground))" strokeDasharray="2 2" />
            <Area type="monotone" dataKey="pos" stroke="none" fill="#2FA36B" fillOpacity={0.15} isAnimationActive={false} />
            <Area type="monotone" dataKey="neg" stroke="none" fill="#DC5757" fillOpacity={0.15} isAnimationActive={false} />
            <Line type="monotone" dataKey="pnl" stroke="hsl(var(--primary))" strokeWidth={2.5} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </CardContent></Card>

      {/* Kennzahlen */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Metric label="Max Profit" value={fmtSigned(maxProfit)} tone="pos" />
        <Metric label="Max Verlust" value={fmtSigned(maxLoss)} tone="neg" />
        <Metric label="Breakevens" value={String(breakevens)} />
        <Metric label="P&L bei 0%" value={fmtSigned(atZero)} tone={atZero >= 0 ? 'pos' : 'neg'} />
      </div>

      {vixMode && (
        <p className="text-xs text-muted-foreground rounded-md bg-secondary/50 border border-border px-3 py-2">
          <b>VIX-Korrelationsmodus aktiv</b> — Long-Put-Prämien werden bei Drawdowns automatisch nach oben angepasst
          (kalibriert auf 2008/2020/2022). Macht Long-Hedges realistischer als reine Intrinsic-Berechnung.
        </p>
      )}
    </section>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: 'pos' | 'neg' }) {
  const cls = tone === 'pos' ? 'text-positive' : tone === 'neg' ? 'text-negative' : 'text-foreground';
  return (
    <Card><CardContent className="p-4">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn('text-2xl font-bold mt-0.5', cls)}>{value}</div>
    </CardContent></Card>
  );
}
function fmtSigned(v: number): string {
  return `${v >= 0 ? '+' : '-'}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}
