'use client';

import { useMemo } from 'react';
import {
  ComposedChart, Area, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine,
} from 'recharts';
import { payoffOption } from '@/lib/deltaPortfolio';

/**
 * Interaktiver Payoff-Chart für einen 2-Bein-Spread (Option Alpha-Stil).
 * P&L bei Verfall über einen Kursbereich; Hover zeigt den P&L kontinuierlich
 * an der Cursor-Position. Grün = Gewinnzone, Rot = Verlustzone.
 *
 * Payoff via payoffOption() aus deltaPortfolio.ts (reines Intrinsic-Modell).
 * Ein Spread = Short-Leg + Long-Leg, je 1 Kontrakt.
 */

type SpreadRow = {
  symbol?: string;
  option_type?: 'call' | 'put' | string;
  sell_strike?: number;
  buy_strike?: number;
  sell_last_option_price?: number;
  buy_last_option_price?: number;
  close?: number; // aktueller Aktienkurs (LIVE_STOCK_PRICE)
};

type Props = {
  spread: SpreadRow;
  /** 'credit' = Short auf sell_strike / Long auf buy_strike; 'debit' umgekehrt. */
  strategyType: 'credit' | 'debit';
};

export function SpreadPayoffChart({ spread, strategyType }: Props) {
  const contractType: 'call' | 'put' = spread.option_type === 'call' ? 'call' : 'put';

  const model = useMemo(() => {
    const sellK = Number(spread.sell_strike);
    const buyK = Number(spread.buy_strike);
    const sellPrem = Number(spread.sell_last_option_price ?? 0);
    const buyPrem = Number(spread.buy_last_option_price ?? 0);
    const spot = Number(spread.close);
    if (!Number.isFinite(sellK) || !Number.isFinite(buyK)) return null;

    // Credit: Short auf sell_strike (kassiert), Long auf buy_strike (bezahlt).
    // Debit: umgekehrt.
    const shortStrike = strategyType === 'credit' ? sellK : buyK;
    const longStrike = strategyType === 'credit' ? buyK : sellK;
    const shortPrem = strategyType === 'credit' ? sellPrem : buyPrem;
    const longPrem = strategyType === 'credit' ? buyPrem : sellPrem;

    // Kursbereich: beide Strikes einschließen + Puffer
    const kLo = Math.min(sellK, buyK);
    const kHi = Math.max(sellK, buyK);
    const width = kHi - kLo || kHi * 0.1;
    const lo = Math.max(0, kLo - width * 1.5);
    const hi = kHi + width * 1.5;

    const N = 140;
    const data: { price: number; pnl: number; pos: number | null; neg: number | null }[] = [];
    for (let i = 0; i < N; i++) {
      const price = lo + ((hi - lo) * i) / (N - 1);
      const pnl =
        payoffOption(1, 'Short', contractType, shortStrike, shortPrem, price) +
        payoffOption(1, 'Long', contractType, longStrike, longPrem, price);
      data.push({ price, pnl, pos: pnl >= 0 ? pnl : 0, neg: pnl < 0 ? pnl : 0 });
    }

    // Breakeven(s): Vorzeichenwechsel linear interpolieren
    const breakevens: number[] = [];
    for (let i = 1; i < data.length; i++) {
      const a = data[i - 1], b = data[i];
      if (a.pnl === 0) breakevens.push(a.price);
      else if (a.pnl < 0 !== b.pnl < 0) {
        const t = Math.abs(a.pnl) / (Math.abs(a.pnl) + Math.abs(b.pnl));
        breakevens.push(a.price + t * (b.price - a.price));
      }
    }

    return { data, spot: Number.isFinite(spot) ? spot : null, breakevens, lo, hi };
  }, [spread, strategyType, contractType]);

  if (!model) return null;

  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
        Payoff bei Verfall
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={model.data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis
            dataKey="price" type="number" domain={[model.lo, model.hi]}
            tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
            tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
          />
          <YAxis
            tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
            tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
          />
          <Tooltip
            formatter={(v: any) => [`$${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`, 'P&L']}
            labelFormatter={(v: any) => `Kurs bei Verfall: $${Number(v).toFixed(2)}`}
            contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8, fontSize: 12 }}
          />
          <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeDasharray="4 4" />
          {model.spot != null && (
            <ReferenceLine
              x={model.spot} stroke="#2F80ED" strokeDasharray="4 3"
              label={{ value: `$${model.spot.toFixed(2)}`, position: 'top', fill: '#2F80ED', fontSize: 11 }}
            />
          )}
          {model.breakevens.map((be, i) => (
            <ReferenceLine
              key={i} x={be} stroke="#D9962B" strokeDasharray="2 2"
              label={{ value: `BE ${be.toFixed(0)}`, position: 'bottom', fill: '#D9962B', fontSize: 10 }}
            />
          ))}
          <Area type="monotone" dataKey="pos" stroke="none" fill="#2FA36B" fillOpacity={0.15} isAnimationActive={false} />
          <Area type="monotone" dataKey="neg" stroke="none" fill="#DC5757" fillOpacity={0.15} isAnimationActive={false} />
          <Line type="monotone" dataKey="pnl" stroke="hsl(var(--primary))" strokeWidth={2.5} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
