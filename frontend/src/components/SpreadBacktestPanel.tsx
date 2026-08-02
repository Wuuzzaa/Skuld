'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { backtestSpread } from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { formatCurrency, formatPercent } from '@/lib/utils';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid,
} from 'recharts';

interface Props {
  spread: any;
  entryDate?: string;
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: 'pos' | 'neg' }) {
  const cls = tone === 'pos' ? 'text-positive' : tone === 'neg' ? 'text-negative' : 'text-foreground';
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`font-semibold ${cls}`}>{value}</p>
    </div>
  );
}

export function SpreadBacktestPanel({ spread, entryDate }: Props) {
  const today = new Date().toISOString().slice(0, 10);
  const [entry, setEntry] = useState(entryDate || today);
  const [compareDate, setCompareDate] = useState(String(spread.expiration_date).slice(0, 10));
  const [useOverride, setUseOverride] = useState(false);
  const [ov, setOv] = useState({
    entry_sell_price: Number(spread.sell_last_option_price) || 0,
    entry_buy_price: Number(spread.buy_last_option_price) || 0,
    exit_sell_price: 0,
    exit_buy_price: 0,
    start_transaction_cost: 0,
    exit_transaction_cost: 0,
  });

  const mutation = useMutation({
    mutationFn: () =>
      backtestSpread({
        symbol: spread.symbol,
        sell_option_osi: spread.sell_option_osi,
        buy_option_osi: spread.buy_option_osi,
        sell_strike: Number(spread.sell_strike),
        buy_strike: Number(spread.buy_strike),
        sell_last_option_price: Number(spread.sell_last_option_price),
        buy_last_option_price: Number(spread.buy_last_option_price),
        expiration_date: String(spread.expiration_date).slice(0, 10),
        entry_date: entry,
        compare_date: compareDate,
        override: useOverride ? ov : null,
      }),
  });

  const r = mutation.data;
  const hasError = r && r.error;

  const chartData = (() => {
    if (!r || !r.stock_series) return [];
    return r.stock_series.map((p: any) => ({ date: p.date, close: p.close }));
  })();

  const ovNum = (key: keyof typeof ov) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setOv({ ...ov, [key]: e.target.value === '' ? 0 : Number(e.target.value) });

  return (
    <Card className="border-primary/20">
      <CardContent className="p-4 space-y-3">
        <h3 className="text-sm font-semibold">📊 Spread Exit Backtest — {spread.symbol}</h3>

        <div className="flex flex-wrap gap-3 items-end">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Entry date</label>
            <Input type="date" value={entry} onChange={(e) => setEntry(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Comparison (exit) date</label>
            <Input type="date" value={compareDate} onChange={(e) => setCompareDate(e.target.value)} className="w-40" />
          </div>
          <label className="flex items-center gap-2 text-xs text-muted-foreground pb-2">
            <input type="checkbox" checked={useOverride} onChange={(e) => setUseOverride(e.target.checked)} />
            Manual fill prices
          </label>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? 'Simulating…' : 'Run Backtest'}
          </Button>
        </div>

        {useOverride && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2 p-3 rounded bg-muted/20">
            <Field label="Entry Short (sell)"><Input type="number" step="0.01" value={ov.entry_sell_price} onChange={ovNum('entry_sell_price')} /></Field>
            <Field label="Entry Long (buy)"><Input type="number" step="0.01" value={ov.entry_buy_price} onChange={ovNum('entry_buy_price')} /></Field>
            <Field label="Entry fees"><Input type="number" step="0.5" value={ov.start_transaction_cost} onChange={ovNum('start_transaction_cost')} /></Field>
            <Field label="Exit Short (buy back)"><Input type="number" step="0.01" value={ov.exit_sell_price} onChange={ovNum('exit_sell_price')} /></Field>
            <Field label="Exit Long (sell)"><Input type="number" step="0.01" value={ov.exit_buy_price} onChange={ovNum('exit_buy_price')} /></Field>
            <Field label="Exit fees"><Input type="number" step="0.5" value={ov.exit_transaction_cost} onChange={ovNum('exit_transaction_cost')} /></Field>
          </div>
        )}

        {hasError && <p className="text-sm text-amber-400">{r.message || 'No data for comparison date.'}</p>}

        {r && !hasError && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <Metric label="Days Held" value={String(r.days_held)} />
              <Metric label="Max Profit (Credit)" value={formatCurrency(r.initial_cash_flow)} />
              <Metric label="Profit" value={formatCurrency(r.profit)} tone={r.profit >= 0 ? 'pos' : 'neg'} />
              <Metric label="Capital at Risk (BPR)" value={formatCurrency(r.bpr_capital)} />
              {r.roi_pct != null && <Metric label="ROI (on Risk)" value={formatPercent(r.roi_pct / 100)} tone={r.roi_pct >= 0 ? 'pos' : 'neg'} />}
              {r.roi_annualized_pct != null && <Metric label="Annualized ROI" value={formatPercent(r.roi_annualized_pct / 100)} tone={r.roi_annualized_pct >= 0 ? 'pos' : 'neg'} />}
              <Metric label="Exit Short" value={formatCurrency(r.exit_sell_price)} />
              <Metric label="Exit Long" value={formatCurrency(r.exit_buy_price)} />
            </div>

            {r.after_expiration && (
              <p className="text-xs text-muted-foreground">Comparison date is on/after expiration — legs closed at zero remaining debit.</p>
            )}

            {chartData.length > 0 && (
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={30} />
                    <YAxis tick={{ fontSize: 10 }} domain={['auto', 'auto']} />
                    <Tooltip
                      contentStyle={{ fontSize: 12, background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))' }}
                      formatter={(v: any) => (typeof v === 'number' ? v.toFixed(2) : v)}
                    />
                    <ReferenceLine y={r.strike_sell} stroke="#ef4444" strokeDasharray="4 4" label={{ value: 'Short', fontSize: 9, fill: '#ef4444' }} />
                    <ReferenceLine y={r.strike_buy} stroke="#3b82f6" strokeDasharray="4 4" label={{ value: 'Long', fontSize: 9, fill: '#3b82f6' }} />
                    <Line type="monotone" dataKey="close" stroke="#10b981" dot={false} strokeWidth={2} name="Stock" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-muted-foreground">{label}</label>
      {children}
    </div>
  );
}
