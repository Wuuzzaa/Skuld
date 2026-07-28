'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCoveredCallScanner } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { Button } from '@/components/ui/button';
import { formatCurrency, formatNumber, formatPercent, exportToCSV, getClaudeAnalysisUrl } from '@/lib/utils';
import { X, ExternalLink, Download } from 'lucide-react';

const DEFAULT_PARAMS = {
  dte_min: 20,
  dte_max: 60,
  delta_target: 0.8,
  delta_target_max: 1.0,
  min_annualized: 0,
  max_annualized: 0,
  min_market_cap_b: 1,
  min_oi: 50,
  min_downside: 0,
  price_min: 10,
  price_max: 500,
  min_iv_rank: 0,
  min_premium: 0,
};

export default function CoveredCallScannerPage() {
  const [form, setForm] = useState(DEFAULT_PARAMS);
  const [params, setParams] = useState<typeof DEFAULT_PARAMS | null>(null);
  const [selectedRow, setSelectedRow] = useState<any>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['covered-call-scanner', params],
    queryFn: () => getCoveredCallScanner(params as Record<string, any>),
    enabled: params !== null,
  });

  const rows: any[] = Array.isArray(data) ? data : [];

  const num = (key: keyof typeof DEFAULT_PARAMS) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value === '' ? 0 : Number(e.target.value) });

  const columns: Column[] = [
    { key: 'symbol', label: 'Symbol', sortable: true },
    { key: 'company_sector', label: 'Sector', sortable: true },
    { key: 'stock_price', label: 'Price', sortable: true, align: 'right', format: (v) => formatCurrency(v) },
    { key: 'strike_price', label: 'Strike', sortable: true, align: 'right', format: (v) => formatCurrency(v) },
    { key: 'premium', label: 'Premium', sortable: true, align: 'right', format: (v) => formatCurrency(v) },
    { key: 'dte', label: 'DTE', sortable: true, align: 'right' },
    { key: 'delta', label: 'Delta', sortable: true, align: 'right', format: (v) => formatNumber(v, 3) },
    { key: 'net_debit', label: 'Net Debit', sortable: true, align: 'right', format: (v) => formatCurrency(v) },
    { key: 'assigned_return_pct', label: 'Assigned %', sortable: true, align: 'right', format: (v) => formatPercent(v / 100), colorCode: 'pnl' },
    { key: 'annualized_return_pct', label: 'Annual. %', sortable: true, align: 'right', format: (v) => formatPercent(v / 100), colorCode: 'pnl' },
    { key: 'downside_protection_pct', label: 'Downside %', sortable: true, align: 'right', format: (v) => formatPercent(v / 100) },
    { key: 'iv_rank', label: 'IV Rank', sortable: true, align: 'right', format: (v) => formatNumber(v, 1) },
    { key: 'open_interest', label: 'OI', sortable: true, align: 'right', format: (v) => formatNumber(v, 0) },
    { key: 'market_cap_b', label: 'Mkt Cap (B)', sortable: true, align: 'right', format: (v) => formatNumber(v, 1) },
  ];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            Covered Call Scanner
            {isFetching && <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />}
          </h1>
          <p className="text-sm text-muted-foreground">
            Optimal ITM covered calls, ranked by annualized return (PowerOptions MorningUpdate style).
          </p>
        </div>
        {rows.length > 0 && (
          <Button variant="outline" size="sm" onClick={() => exportToCSV(rows, 'covered_call_scanner.csv')}>
            <Download className="w-3.5 h-3.5 mr-1" /> CSV
          </Button>
        )}
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <Field label="DTE Min"><Input type="number" value={form.dte_min} onChange={num('dte_min')} /></Field>
          <Field label="DTE Max"><Input type="number" value={form.dte_max} onChange={num('dte_max')} /></Field>
          <Field label="Delta Target"><Input type="number" step="0.05" value={form.delta_target} onChange={num('delta_target')} /></Field>
          <Field label="Delta Max"><Input type="number" step="0.05" value={form.delta_target_max} onChange={num('delta_target_max')} /></Field>
          <Field label="Min Annual %"><Input type="number" value={form.min_annualized} onChange={num('min_annualized')} /></Field>
          <Field label="Max Annual %"><Input type="number" value={form.max_annualized} onChange={num('max_annualized')} /></Field>
          <Field label="Min Mkt Cap (B)"><Input type="number" step="0.5" value={form.min_market_cap_b} onChange={num('min_market_cap_b')} /></Field>
          <Field label="Min OI"><Input type="number" value={form.min_oi} onChange={num('min_oi')} /></Field>
          <Field label="Min Downside %"><Input type="number" value={form.min_downside} onChange={num('min_downside')} /></Field>
          <Field label="Price Min"><Input type="number" value={form.price_min} onChange={num('price_min')} /></Field>
          <Field label="Price Max"><Input type="number" value={form.price_max} onChange={num('price_max')} /></Field>
          <Field label="Min IV Rank"><Input type="number" value={form.min_iv_rank} onChange={num('min_iv_rank')} /></Field>
          <Field label="Min Premium"><Input type="number" step="0.1" value={form.min_premium} onChange={num('min_premium')} /></Field>
          <div className="flex items-end">
            <Button className="w-full" onClick={() => setParams({ ...form })}>Scan</Button>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {params === null ? (
        <p className="text-sm text-muted-foreground">Set filters and click Scan to find covered calls.</p>
      ) : isLoading ? (
        <LoadingState message="Scanning for covered calls..." />
      ) : (
        <DataTable
          data={rows}
          columns={columns}
          defaultSort={{ key: 'annualized_return_pct', direction: 'desc' }}
          onRowClick={(row, index) => { setSelectedRow(row); setSelectedIndex(index); }}
          selectedIndex={selectedIndex ?? undefined}
          stickyHeader
          maxHeight="60vh"
        />
      )}

      {/* Detail panel */}
      {selectedRow && (
        <Card>
          <CardContent className="p-4 space-y-2 relative">
            <button onClick={() => { setSelectedRow(null); setSelectedIndex(null); }} className="absolute top-3 right-3 text-muted-foreground hover:text-foreground">
              <X className="w-4 h-4" />
            </button>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              {selectedRow.symbol}
              <a href={getClaudeAnalysisUrl(selectedRow.symbol)} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline text-sm inline-flex items-center gap-1">
                Analysis <ExternalLink className="w-3 h-3" />
              </a>
            </h2>
            <p className="text-sm text-muted-foreground">{selectedRow.company_name} · {selectedRow.company_sector}</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <Metric label="Stock Price" value={formatCurrency(selectedRow.stock_price)} />
              <Metric label="Strike" value={formatCurrency(selectedRow.strike_price)} />
              <Metric label="Premium" value={formatCurrency(selectedRow.premium)} />
              <Metric label="Net Debit" value={formatCurrency(selectedRow.net_debit)} />
              <Metric label="Assigned Return" value={formatPercent(selectedRow.assigned_return_pct / 100)} />
              <Metric label="Annualized" value={formatPercent(selectedRow.annualized_return_pct / 100)} />
              <Metric label="Downside Protection" value={formatPercent(selectedRow.downside_protection_pct / 100)} />
              <Metric label="DTE" value={String(selectedRow.dte)} />
            </div>
            <div className="text-xs text-muted-foreground pt-2 border-t border-border/50 space-y-0.5">
              <p>Net Debit = Stock Price − Premium = {formatCurrency(selectedRow.stock_price)} − {formatCurrency(selectedRow.premium)} = {formatCurrency(selectedRow.net_debit)}</p>
              <p>Assigned Return = (Strike − Net Debit) / Net Debit</p>
              <p>Annualized = Assigned Return / DTE × 365</p>
              <p>Downside Protection = (Stock Price − Net Debit) / Stock Price</p>
            </div>
          </CardContent>
        </Card>
      )}
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

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-medium">{value}</p>
    </div>
  );
}
