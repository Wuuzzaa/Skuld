'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { backtestMarriedPut } from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { formatCurrency, formatPercent } from '@/lib/utils';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid,
} from 'recharts';

interface Props {
  trade: any;
  /** Entry date of the position (YYYY-MM-DD). Defaults to today if not provided. */
  entryDate?: string;
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: 'pos' | 'neg' }) {
  const cls = tone === 'pos' ? 'text-emerald-400' : tone === 'neg' ? 'text-red-400' : 'text-foreground';
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`font-semibold ${cls}`}>{value}</p>
    </div>
  );
}

export function MarriedPutBacktestPanel({ trade, entryDate }: Props) {
  const today = new Date().toISOString().slice(0, 10);
  const [entry, setEntry] = useState(entryDate || today);
  const [compareDate, setCompareDate] = useState(String(trade.expiration_date).slice(0, 10));

  const mutation = useMutation({
    mutationFn: () =>
      backtestMarriedPut({
        symbol: trade.symbol,
        live_stock_price: Number(trade.live_stock_price),
        premium_option_price: Number(trade.premium_option_price),
        number_of_stocks: Number(trade.number_of_stocks),
        option_osi: trade.option_osi ?? null,
        strike_price: Number(trade.strike_price),
        expiration_date: String(trade.expiration_date).slice(0, 10),
        entry_date: entry,
        compare_date: compareDate,
      }),
  });

  const r = mutation.data;
  const hasError = r && r.error;

  // Merge stock + option series by date for the chart
  const chartData = (() => {
    if (!r || !r.stock_series) return [];
    const map: Record<string, any> = {};
    for (const p of r.stock_series) map[p.date] = { date: p.date, close: p.close };
    for (const p of r.option_series || []) {
      map[p.date] = { ...(map[p.date] || { date: p.date }), premium: p.premium };
    }
    return Object.values(map).sort((a: any, b: any) => a.date.localeCompare(b.date));
  })();

  return (
    <Card className="border-primary/20">
      <CardContent className="p-4 space-y-3">
        <h3 className="text-sm font-semibold">📈 Simulated Exit Backtest — {trade.symbol}</h3>

        <div className="flex flex-wrap gap-3 items-end">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Entry date</label>
            <Input type="date" value={entry} onChange={(e) => setEntry(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Comparison (exit) date</label>
            <Input type="date" value={compareDate} onChange={(e) => setCompareDate(e.target.value)} className="w-40" />
          </div>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? 'Simulating…' : 'Run Backtest'}
          </Button>
        </div>

        {hasError && (
          <p className="text-sm text-amber-400">{r.message || 'No data available for the comparison date.'}</p>
        )}

        {r && !hasError && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <Metric label="Days Held" value={String(r.days_held)} />
              <Metric label="Exit Stock Price" value={formatCurrency(r.stock_exit_price)} />
              <Metric
                label={r.option_exit_kind === 'premium' ? 'Exit Put Premium' : 'Put Intrinsic Value'}
                value={formatCurrency(r.option_exit_unit)}
              />
              <Metric label="Dividends Received" value={formatCurrency(r.dividends_paid_total)} />
              <Metric label="Investment" value={formatCurrency(r.investment_start)} />
              <Metric label="End Value" value={formatCurrency(r.total_end_value)} />
              <Metric label="P&L" value={formatCurrency(r.profit)} tone={r.profit >= 0 ? 'pos' : 'neg'} />
              <Metric label="ROI" value={formatPercent(r.roi_pct / 100)} tone={r.roi_pct >= 0 ? 'pos' : 'neg'} />
              {r.roi_annualized_pct != null && (
                <Metric label="Annualized ROI" value={formatPercent(r.roi_annualized_pct / 100)} tone={r.roi_annualized_pct >= 0 ? 'pos' : 'neg'} />
              )}
              <Metric label="Stock Change" value={formatPercent(r.stock_change_pct / 100)} tone={r.stock_change_pct >= 0 ? 'pos' : 'neg'} />
            </div>

            {r.after_expiration && (
              <p className="text-xs text-muted-foreground">
                Comparison date is after expiration — option valued at intrinsic value.
              </p>
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
                    <ReferenceLine y={r.strike_price} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: 'Strike', fontSize: 9, fill: '#f59e0b' }} />
                    <ReferenceLine y={r.breakeven} stroke="#3b82f6" strokeDasharray="4 4" label={{ value: 'Breakeven', fontSize: 9, fill: '#3b82f6' }} />
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
