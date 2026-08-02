'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { backtestRslMomentum } from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { DataTable, Column } from '@/components/ui/data-table';
import { formatCurrency, formatPercent, formatNumber } from '@/lib/utils';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts';

function StatTile({ label, value, tone }: { label: string; value: string; tone?: 'pos' | 'neg' }) {
  const cls = tone === 'pos' ? 'text-positive' : tone === 'neg' ? 'text-negative' : 'text-foreground';
  return (
    <div className="flex flex-col gap-0.5 p-3 bg-card rounded-lg border border-border/40">
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">{label}</span>
      <span className={`text-lg font-bold ${cls}`}>{value}</span>
    </div>
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

const DEFAULTS = {
  start_date: '2023-01-01',
  end_date: new Date().toISOString().slice(0, 10),
  start_budget: 10000,
  flat_fee: 4.9,
  pct_fee: 0.001,
  top_n: 5,
  max_per_sector: 2,
  exit_percentile: 50,
  trading_frequency: 'monthly',
  fractional_shares: false,
  risk_free_rate: 0,
  tax_rate: 0.25,
};

export function RslBacktestPanel() {
  const [form, setForm] = useState(DEFAULTS);

  const mutation = useMutation({
    mutationFn: () => backtestRslMomentum(form),
  });

  const r = mutation.data;
  const summary = r?.summary || {};
  const equity: any[] = r?.equity_curve || [];
  const transactions: any[] = r?.transactions || [];

  const num = (key: keyof typeof DEFAULTS) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value === '' ? 0 : Number(e.target.value) });

  const txColumns: Column[] = [
    { key: 'date', label: 'Date', sortable: true },
    { key: 'action', label: 'Action', sortable: true },
    { key: 'symbol', label: 'Symbol', sortable: true },
    { key: 'sector', label: 'Sector', sortable: true },
    { key: 'shares', label: 'Shares', align: 'right', format: (v) => formatNumber(v, 2) },
    { key: 'price', label: 'Price', align: 'right', format: (v) => formatCurrency(v) },
    { key: 'value', label: 'Value', align: 'right', format: (v) => formatCurrency(v) },
    { key: 'fee', label: 'Fee', align: 'right', format: (v) => formatCurrency(v) },
    { key: 'tax', label: 'Tax', align: 'right', format: (v) => formatCurrency(v) },
    { key: 'profit_abs', label: 'P&L', align: 'right', format: (v) => (v == null ? '—' : formatCurrency(v)), colorCode: 'pnl' },
    { key: 'profit_pct', label: 'P&L %', align: 'right', format: (v) => (v == null ? '—' : formatPercent(v / 100)), colorCode: 'pnl' },
  ];

  return (
    <div className="space-y-4">
      {/* Parameters */}
      <Card>
        <CardContent className="p-4 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <Field label="Start date"><Input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
          <Field label="End date"><Input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
          <Field label="Start budget"><Input type="number" value={form.start_budget} onChange={num('start_budget')} /></Field>
          <Field label="Flat fee"><Input type="number" step="0.1" value={form.flat_fee} onChange={num('flat_fee')} /></Field>
          <Field label="% fee"><Input type="number" step="0.001" value={form.pct_fee} onChange={num('pct_fee')} /></Field>
          <Field label="Top N"><Input type="number" value={form.top_n} onChange={num('top_n')} /></Field>
          <Field label="Max / sector"><Input type="number" value={form.max_per_sector} onChange={num('max_per_sector')} /></Field>
          <Field label="Exit percentile"><Input type="number" value={form.exit_percentile} onChange={num('exit_percentile')} /></Field>
          <Field label="Risk-free rate"><Input type="number" step="0.01" value={form.risk_free_rate} onChange={num('risk_free_rate')} /></Field>
          <Field label="Tax rate"><Input type="number" step="0.01" value={form.tax_rate} onChange={num('tax_rate')} /></Field>
          <Field label="Frequency">
            <select
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
              value={form.trading_frequency}
              onChange={(e) => setForm({ ...form, trading_frequency: e.target.value })}
            >
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </Field>
          <label className="flex items-center gap-2 text-xs text-muted-foreground pb-2 self-end">
            <input type="checkbox" checked={form.fractional_shares} onChange={(e) => setForm({ ...form, fractional_shares: e.target.checked })} />
            Fractional shares
          </label>
          <div className="flex items-end">
            <Button className="w-full" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
              {mutation.isPending ? 'Running…' : 'Run Backtest'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {mutation.isError && <p className="text-sm text-negative">Backtest failed. Check date range / data availability.</p>}

      {r && Object.keys(summary).length > 0 && (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <StatTile label="End Capital" value={formatCurrency(summary.end_capital)} tone={summary.total_return_pct >= 0 ? 'pos' : 'neg'} />
            <StatTile label="Total Return" value={formatPercent(summary.total_return_pct / 100)} tone={summary.total_return_pct >= 0 ? 'pos' : 'neg'} />
            <StatTile label="CAGR" value={formatPercent(summary.cagr / 100)} tone={summary.cagr >= 0 ? 'pos' : 'neg'} />
            <StatTile label="Sharpe" value={formatNumber(summary.sharpe, 2)} />
            <StatTile label="Volatility" value={formatPercent(summary.volatility / 100)} />
            <StatTile label="Max Drawdown" value={formatPercent(summary.max_drawdown / 100)} tone="neg" />
            <StatTile label="Trades" value={String(summary.num_trades ?? 0)} />
            <StatTile label="Avg Hold (days)" value={formatNumber(summary.avg_holding_days, 0)} />
            <StatTile label="SPY End Capital" value={formatCurrency(summary.spy_end_capital)} />
            <StatTile label="SPY Return" value={formatPercent(summary.spy_return_pct / 100)} tone={summary.spy_return_pct >= 0 ? 'pos' : 'neg'} />
            <StatTile label="SPY CAGR" value={formatPercent(summary.spy_cagr / 100)} />
            <StatTile label="Days" value={String(summary.days ?? 0)} />
          </div>

          {/* Equity curve vs SPY */}
          {equity.length > 0 && (
            <Card>
              <CardContent className="p-4">
                <h3 className="text-sm font-semibold mb-2">Portfolio vs SPY</h3>
                <div className="h-72 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={equity} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                      <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
                      <YAxis tick={{ fontSize: 10 }} domain={['auto', 'auto']} />
                      <Tooltip
                        contentStyle={{ fontSize: 12, background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))' }}
                        formatter={(v: any) => (typeof v === 'number' ? v.toFixed(0) : v)}
                      />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Line type="monotone" dataKey="portfolio_value" stroke="#10b981" dot={false} strokeWidth={2} name="Portfolio" />
                      <Line type="monotone" dataKey="spy_value" stroke="#6b7280" dot={false} strokeWidth={1.5} name="SPY" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Transaction log */}
          {transactions.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold mb-2">Transaction Log ({transactions.length})</h3>
              <DataTable data={transactions} columns={txColumns} stickyHeader maxHeight="50vh" compact />
            </div>
          )}
        </>
      )}
    </div>
  );
}
