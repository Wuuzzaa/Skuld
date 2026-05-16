'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getExpirations, getCoveredCalls } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatPercent, formatNumber, exportToCSV, getClaudeAnalysisUrl } from '@/lib/utils';
import { TrendingUp, ExternalLink, Download, Shield, Filter } from 'lucide-react';

function StatCard({ label, value, trend }: { label: string; value: string; trend?: 'up' | 'down' | 'neutral' }) {
  return (
    <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">{label}</span>
      <span className={`text-lg font-bold ${
        trend === 'up' ? 'text-emerald-400' : trend === 'down' ? 'text-red-400' : 'text-foreground'
      }`}>
        {value}
      </span>
    </div>
  );
}

export default function CoveredCallsPage() {
  const [params, setParams] = useState({
    delta_target: 0.6,
    max_per_symbol: 3,
    min_open_interest: 100,
    min_annualized: 0,
    min_downside: 0,
    min_volume: 10,
    earnings_filter: false,
    above_ma20: false,
    above_ma50: false,
    // PowerOptions Pro
    macd_positive: true,
    rsi_below_70: true,
    min_eps_growth: 5,
    max_pe_ratio: 50,
    max_recommendation: 2.6,
    min_avg_volume: 500000,
    min_market_cap: 2500,
    exclude_biotech: true,
    exclude_leveraged: true,
    max_iv_hv_ratio: 0,
    // Monthly Picks
    min_itm_pct: 10,
    min_stock_price: 9,
    max_stock_price: 100,
    min_premium: 0.85,
  });
  const [selectedExpiration, setSelectedExpiration] = useState('');
  const [selectedRow, setSelectedRow] = useState<any>(null);
  const [expTypeFilter, setExpTypeFilter] = useState<'all' | 'Monthly' | 'Weekly' | 'Daily'>('all');
  const [showProFilters, setShowProFilters] = useState(false);
  const [showExplain, setShowExplain] = useState(false);

  const { data: expirations, isLoading: loadingExp } = useQuery({
    queryKey: ['expirations'],
    queryFn: getExpirations,
  });

  const { data: coveredCalls, isLoading: loadingData, isFetching } = useQuery({
    queryKey: ['covered-calls', selectedExpiration, params],
    queryFn: () => getCoveredCalls({ ...params, expiration_date: selectedExpiration }),
    enabled: !!selectedExpiration,
  });

  // Filter expirations by type
  const filteredExpirations = useMemo(() => {
    if (!expirations?.length) return [];
    if (expTypeFilter === 'all') return expirations;
    return expirations.filter((e: any) => e.expiration_type === expTypeFilter);
  }, [expirations, expTypeFilter]);

  // Auto-select expiration closest to 45 DTE
  if (filteredExpirations.length && !selectedExpiration) {
    const target = filteredExpirations.find((e: any) => e.days_to_expiration >= 42) || filteredExpirations[filteredExpirations.length - 1];
    setSelectedExpiration(target.expiration_date.split('T')[0]);
  }

  // Stats
  const stats = useMemo(() => {
    if (!coveredCalls?.length) return null;
    const avgAnnual = coveredCalls.reduce((s: number, r: any) => s + (r.annualized_return || 0), 0) / coveredCalls.length;
    const avgProtection = coveredCalls.reduce((s: number, r: any) => s + (r.downside_protection || 0), 0) / coveredCalls.length;
    const best = coveredCalls.reduce((best: any, r: any) => (r.annualized_return || 0) > (best?.annualized_return || 0) ? r : best, coveredCalls[0]);
    return { total: coveredCalls.length, avgAnnual, avgProtection, bestSymbol: best?.symbol, bestReturn: best?.annualized_return };
  }, [coveredCalls]);

  const columns: Column[] = [
    { key: 'symbol', label: 'Symbol', sortable: true, format: (v: string) => <span className="font-semibold text-foreground">{v}</span> },
    { key: 'company_name', label: 'Company', sortable: true },
    { key: 'stock_price', label: 'Stock', sortable: true, align: 'right', format: (v: number) => formatCurrency(v) },
    { key: 'strike_price', label: 'Strike', sortable: true, align: 'right', format: (v: number) => formatCurrency(v) },
    { key: 'premium', label: 'Premium', sortable: true, align: 'right', format: (v: number) => formatCurrency(v) },
    { key: 'net_debit', label: 'Net Debit', sortable: true, align: 'right', format: (v: number) => formatCurrency(v) },
    { key: 'annualized_return', label: 'Annual %', sortable: true, align: 'right', colorCode: 'percent', format: (v: number) => formatPercent(v) },
    { key: 'assigned_return', label: 'Assigned %', sortable: true, align: 'right', colorCode: 'percent', format: (v: number) => formatPercent(v) },
    { key: 'downside_protection', label: 'Protection %', sortable: true, align: 'right', format: (v: number) => formatPercent(v) },
    { key: 'moneyness', label: 'ITM %', sortable: true, align: 'right', format: (v: number) => formatPercent(v) },
    { key: 'DTE', label: 'DTE', sortable: true, align: 'right' },
    { key: 'delta', label: 'Delta', sortable: true, align: 'right', format: (v: number) => v ? v.toFixed(2) : '-' },
    { key: 'iv', label: 'IV', sortable: true, align: 'right', format: (v: number) => v ? `${(v * 100).toFixed(0)}%` : '-' },
    { key: 'rsi_14', label: 'RSI', sortable: true, align: 'right', format: (v: number) => v ? v.toFixed(0) : '-' },
    { key: 'open_interest', label: 'OI', sortable: true, align: 'right', format: (v: number) => v ? v.toLocaleString() : '-' },
    { key: 'volume', label: 'Vol', sortable: true, align: 'right', format: (v: number) => v ? v.toLocaleString() : '-' },
    { key: 'avg_volume', label: 'Avg Vol', sortable: true, align: 'right', format: (v: number) => v ? v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : `${(v/1e3).toFixed(0)}K` : '-' },
    { key: 'market_cap', label: 'Mkt Cap', sortable: true, align: 'right', format: (v: number) => v ? v >= 1e9 ? `$${(v/1e9).toFixed(1)}B` : `$${(v/1e6).toFixed(0)}M` : '-' },
    {
      key: '_ai',
      label: 'AI',
      sortable: false,
      format: (_v: any, row: any) => (
        <a href={getClaudeAnalysisUrl(row.symbol, row.company_name, row.company_sector)} target="_blank" rel="noopener"
          className="inline-flex items-center gap-0.5 text-muted-foreground hover:text-primary transition-colors"
          title="Claude AI Analysis">
          <ExternalLink className="w-3 h-3" /> AI
        </a>
      ),
    },
  ];

  const selectedExpData = filteredExpirations?.find((e: any) => e.expiration_date?.split('T')[0] === selectedExpiration);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Shield className="w-6 h-6 text-primary" />
          <h1 className="text-2xl font-bold">Covered Calls</h1>
          {isFetching && <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowProFilters(!showProFilters)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md transition-colors ${
              showProFilters ? 'bg-primary/20 text-primary border border-primary/30' : 'bg-secondary hover:bg-secondary/80'
            }`}
          >
            <Filter className="w-3 h-3" /> Pro Filters
          </button>
          {coveredCalls?.length > 0 && (
            <button
              onClick={() => exportToCSV(coveredCalls, `covered-calls-${selectedExpiration}.csv`)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md bg-secondary hover:bg-secondary/80 transition-colors"
            >
              <Download className="w-3 h-3" /> Export
            </button>
          )}
        </div>
      </div>

      <p className="text-sm text-muted-foreground">PowerOptions-Style ITM Covered Call Screener</p>

      {/* Controls */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {/* Expiration Type Filter */}
        <div className="flex flex-col gap-1.5">
          <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Expiration Type</label>
          <div className="flex gap-1">
            {(['all', 'Monthly', 'Weekly', 'Daily'] as const).map((type) => (
              <button key={type} onClick={() => { setExpTypeFilter(type); setSelectedExpiration(''); }}
                className={`px-2 py-1 text-xs rounded ${expTypeFilter === type ? 'bg-primary/20 text-primary border border-primary/30' : 'bg-secondary/60 text-muted-foreground border border-border/50'}`}>
                {type === 'all' ? 'All' : type}
              </button>
            ))}
          </div>
        </div>

        {/* Expiration Selector */}
        <div className="flex flex-col gap-1.5">
          <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Expiration</label>
          <select
            value={selectedExpiration}
            onChange={(e) => setSelectedExpiration(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          >
            {filteredExpirations?.map((e: any) => (
              <option key={e.expiration_date} value={e.expiration_date.split('T')[0]}>
                {e.days_to_expiration} DTE - {e.day_of_week} {e.expiration_date.split('T')[0]} - {e.expiration_type}
              </option>
            ))}
          </select>
        </div>

        {/* Delta Target */}
        <div className="flex flex-col gap-1.5">
          <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Delta Target</label>
          <Input type="number" step="0.05" min="0.3" max="0.9"
            value={params.delta_target}
            onChange={(e) => setParams({ ...params, delta_target: parseFloat(e.target.value) || 0.6 })}
            className="h-9"
          />
        </div>

        {/* Max per Symbol */}
        <div className="flex flex-col gap-1.5">
          <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Max per Symbol</label>
          <Input type="number" step="1" min="1" max="10"
            value={params.max_per_symbol}
            onChange={(e) => setParams({ ...params, max_per_symbol: parseInt(e.target.value) || 3 })}
            className="h-9"
          />
        </div>
      </div>

      {/* Basic Filters Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <div className="flex flex-col gap-1.5">
          <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Min OI</label>
          <Input type="number" value={params.min_open_interest}
            onChange={(e) => setParams({ ...params, min_open_interest: parseInt(e.target.value) || 0 })}
            className="h-8 text-xs" />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Min Annual %</label>
          <Input type="number" step="1" value={params.min_annualized}
            onChange={(e) => setParams({ ...params, min_annualized: parseFloat(e.target.value) || 0 })}
            className="h-8 text-xs" />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Min Protection %</label>
          <Input type="number" step="0.5" value={params.min_downside}
            onChange={(e) => setParams({ ...params, min_downside: parseFloat(e.target.value) || 0 })}
            className="h-8 text-xs" />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Min Volume</label>
          <Input type="number" value={params.min_volume}
            onChange={(e) => setParams({ ...params, min_volume: parseInt(e.target.value) || 0 })}
            className="h-8 text-xs" />
        </div>
        <div className="flex items-end gap-2">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input type="checkbox" checked={params.earnings_filter}
              onChange={(e) => setParams({ ...params, earnings_filter: e.target.checked })}
              className="rounded border-border" />
            <span className="text-xs text-muted-foreground">No Earnings</span>
          </label>
        </div>
        <div className="flex items-end gap-2">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input type="checkbox" checked={params.above_ma20}
              onChange={(e) => setParams({ ...params, above_ma20: e.target.checked })}
              className="rounded border-border" />
            <span className="text-xs text-muted-foreground">&gt; SMA20</span>
          </label>
        </div>
        <div className="flex items-end gap-2">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input type="checkbox" checked={params.above_ma50}
              onChange={(e) => setParams({ ...params, above_ma50: e.target.checked })}
              className="rounded border-border" />
            <span className="text-xs text-muted-foreground">&gt; SMA50</span>
          </label>
        </div>
      </div>

      {/* PowerOptions Pro Filters (collapsible) */}
      {showProFilters && (
        <div className="p-4 bg-card/50 rounded-lg border border-border/40 space-y-3">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Filter className="w-4 h-4 text-primary" /> PowerOptions Pro Filters
          </h3>
          {/* Monthly Picks Filters */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Min % ITM</label>
              <Input type="number" step="1" min="0" max="50" value={params.min_itm_pct}
                onChange={(e) => setParams({ ...params, min_itm_pct: parseFloat(e.target.value) || 0 })}
                className="h-8 text-xs" />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Min Stock Price ($)</label>
              <Input type="number" step="1" min="0" value={params.min_stock_price}
                onChange={(e) => setParams({ ...params, min_stock_price: parseFloat(e.target.value) || 0 })}
                className="h-8 text-xs" />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Max Stock Price ($)</label>
              <Input type="number" step="10" min="0" value={params.max_stock_price}
                onChange={(e) => setParams({ ...params, max_stock_price: parseFloat(e.target.value) || 0 })}
                className="h-8 text-xs" />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Min Premium ($)</label>
              <Input type="number" step="0.05" min="0" value={params.min_premium}
                onChange={(e) => setParams({ ...params, min_premium: parseFloat(e.target.value) || 0 })}
                className="h-8 text-xs" />
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {/* Toggles */}
            <div className="space-y-2">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={params.macd_positive}
                  onChange={(e) => setParams({ ...params, macd_positive: e.target.checked })}
                  className="rounded border-border" />
                <span className="text-xs text-muted-foreground">MACD Positive</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={params.rsi_below_70}
                  onChange={(e) => setParams({ ...params, rsi_below_70: e.target.checked })}
                  className="rounded border-border" />
                <span className="text-xs text-muted-foreground">RSI &lt; 70</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={params.exclude_biotech}
                  onChange={(e) => setParams({ ...params, exclude_biotech: e.target.checked })}
                  className="rounded border-border" />
                <span className="text-xs text-muted-foreground">No Biotech</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={params.exclude_leveraged}
                  onChange={(e) => setParams({ ...params, exclude_leveraged: e.target.checked })}
                  className="rounded border-border" />
                <span className="text-xs text-muted-foreground">No Leveraged ETF</span>
              </label>
            </div>
            {/* EPS Growth */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Min EPS Growth %</label>
              <Input type="number" step="1" value={params.min_eps_growth}
                onChange={(e) => setParams({ ...params, min_eps_growth: parseFloat(e.target.value) || 0 })}
                className="h-8 text-xs" />
            </div>
            {/* P/E Ratio */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Max P/E Ratio</label>
              <Input type="number" step="5" value={params.max_pe_ratio}
                onChange={(e) => setParams({ ...params, max_pe_ratio: parseFloat(e.target.value) || 0 })}
                className="h-8 text-xs" />
            </div>
            {/* Analyst Rec */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Max Analyst Rec (1-5)</label>
              <Input type="number" step="0.1" min="0" max="5" value={params.max_recommendation}
                onChange={(e) => setParams({ ...params, max_recommendation: parseFloat(e.target.value) || 0 })}
                className="h-8 text-xs" />
            </div>
            {/* Avg Volume + Market Cap */}
            <div className="space-y-2">
              <div className="flex flex-col gap-1">
                <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Min Avg Vol</label>
                <Input type="number" step="100000" value={params.min_avg_volume}
                  onChange={(e) => setParams({ ...params, min_avg_volume: parseInt(e.target.value) || 0 })}
                  className="h-8 text-xs" />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Min Mkt Cap ($M)</label>
                <Input type="number" step="500" value={params.min_market_cap}
                  onChange={(e) => setParams({ ...params, min_market_cap: parseFloat(e.target.value) || 0 })}
                  className="h-8 text-xs" />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <StatCard label="Results" value={String(stats.total)} />
          <StatCard label="Avg Annual %" value={formatPercent(stats.avgAnnual)} trend="up" />
          <StatCard label="Avg Protection %" value={formatPercent(stats.avgProtection)} trend="up" />
          <StatCard label="Best Symbol" value={stats.bestSymbol || '-'} />
          <StatCard label="Best Annual %" value={formatPercent(stats.bestReturn)} trend="up" />
        </div>
      )}

      {/* Table */}
      {loadingData || loadingExp ? (
        <LoadingState />
      ) : (
        <DataTable
          data={coveredCalls || []}
          columns={columns}
          defaultSort={{ key: 'annualized_return', direction: 'desc' }}
          onRowClick={(row) => setSelectedRow(row === selectedRow ? null : row)}
          striped
        />
      )}

      {/* Detail Panel */}
      {selectedRow && (
        <div className="p-4 bg-card rounded-lg border border-border/60 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-lg">{selectedRow.symbol} - {selectedRow.company_name}</h3>
            <button onClick={() => setSelectedRow(null)} className="text-muted-foreground hover:text-foreground text-sm">Close</button>
          </div>

          {/* === TRADE ACTION SUMMARY === */}
          <div className="p-4 rounded-lg border border-emerald-500/30" style={{ background: 'linear-gradient(135deg, #1a3a2a 0%, #0d1f17 100%)' }}>
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Trade Action</p>
            <p className="text-xl font-bold text-emerald-400">
              BUY 100x {selectedRow.symbol} @ {formatCurrency(selectedRow.stock_price)}
              <span className="mx-2 text-muted-foreground">|</span>
              SELL 1x {selectedRow.symbol} {formatCurrency(selectedRow.strike_price)} Call @ {formatCurrency(selectedRow.premium)}
            </p>
            <p className="text-sm text-gray-300 mt-1">
              Expiration: {selectedRow.expiration_date?.split('T')[0] || selectedExpiration} ({selectedRow.DTE} DTE)
              <span className="mx-2">|</span>
              Max Profit: {formatCurrency(selectedRow.max_profit)}
              <span className="mx-2">|</span>
              Protection: {formatPercent(selectedRow.downside_protection)}
            </p>
          </div>

          {/* Core Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div><span className="text-muted-foreground">Stock:</span> <span className="font-medium">{formatCurrency(selectedRow.stock_price)}</span></div>
            <div><span className="text-muted-foreground">Strike:</span> <span className="font-medium">{formatCurrency(selectedRow.strike_price)}</span></div>
            <div><span className="text-muted-foreground">Premium:</span> <span className="font-medium">{formatCurrency(selectedRow.premium)}</span></div>
            <div><span className="text-muted-foreground">Net Debit:</span> <span className="font-medium">{formatCurrency(selectedRow.net_debit)}</span></div>
            <div><span className="text-muted-foreground">Annualized:</span> <span className="font-medium text-emerald-400">{formatPercent(selectedRow.annualized_return)}</span></div>
            <div><span className="text-muted-foreground">Assigned:</span> <span className="font-medium text-emerald-400">{formatPercent(selectedRow.assigned_return)}</span></div>
            <div><span className="text-muted-foreground">Protection:</span> <span className="font-medium">{formatPercent(selectedRow.downside_protection)}</span></div>
            <div><span className="text-muted-foreground">Delta:</span> <span className="font-medium">{formatNumber(selectedRow.delta)}</span></div>
          </div>

          {/* Per Contract */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm border-t border-border/40 pt-3">
            <div><span className="text-muted-foreground">Investment (100 shares):</span> <span className="font-medium">{formatCurrency(selectedRow.investment)}</span></div>
            <div><span className="text-muted-foreground">Premium Income:</span> <span className="font-medium">{formatCurrency(selectedRow.premium_income)}</span></div>
            <div><span className="text-muted-foreground">Net Cost:</span> <span className="font-medium">{formatCurrency(selectedRow.net_cost)}</span></div>
            <div><span className="text-muted-foreground">Max Profit:</span> <span className="font-medium text-emerald-400">{formatCurrency(selectedRow.max_profit)}</span></div>
          </div>

          {/* PowerOptions Indicators */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm border-t border-border/40 pt-3">
            <div><span className="text-muted-foreground">MACD:</span> <span className="font-medium">{selectedRow.macd?.toFixed(3) ?? 'N/A'}</span></div>
            <div><span className="text-muted-foreground">MACD Signal:</span> <span className="font-medium">{selectedRow.macd_signal?.toFixed(3) ?? 'N/A'}</span></div>
            <div><span className="text-muted-foreground">RSI(14):</span> <span className="font-medium">{selectedRow.rsi_14?.toFixed(1) ?? 'N/A'}</span></div>
            <div><span className="text-muted-foreground">IV/HV:</span> <span className="font-medium">{selectedRow.iv_hv_ratio?.toFixed(2) ?? 'N/A'}</span></div>
            <div><span className="text-muted-foreground">EPS Growth:</span> <span className="font-medium">{selectedRow.eps_growth != null ? `${selectedRow.eps_growth.toFixed(1)}%` : 'N/A'}</span></div>
            <div><span className="text-muted-foreground">P/E:</span> <span className="font-medium">{selectedRow.pe_ratio?.toFixed(1) ?? 'N/A'}</span></div>
            <div><span className="text-muted-foreground">Analyst Rec:</span> <span className="font-medium">{selectedRow.analyst_recommendation?.toFixed(2) ?? 'N/A'}</span></div>
            <div><span className="text-muted-foreground">Avg Volume:</span> <span className="font-medium">{selectedRow.avg_volume ? `${(selectedRow.avg_volume / 1e6).toFixed(1)}M` : 'N/A'}</span></div>
            <div><span className="text-muted-foreground">Market Cap:</span> <span className="font-medium">{selectedRow.market_cap ? `$${(selectedRow.market_cap / 1e9).toFixed(1)}B` : 'N/A'}</span></div>
            <div><span className="text-muted-foreground">IV Rank:</span> <span className="font-medium">{selectedRow.iv_rank ?? 'N/A'}</span></div>
            <div><span className="text-muted-foreground">Earnings:</span> <span className="font-medium">{selectedRow.earnings_date_next || 'N/A'}</span></div>
            <div><span className="text-muted-foreground">Sector:</span> <span className="font-medium">{selectedRow.company_sector || 'N/A'}</span></div>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              onClick={() => setShowExplain(!showExplain)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md transition-colors ${
                showExplain ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' : 'bg-secondary hover:bg-secondary/80'
              }`}
            >
              Explain Calculation
            </button>
            <a href={getClaudeAnalysisUrl(selectedRow.symbol, selectedRow.company_name, selectedRow.company_sector)}
              target="_blank" rel="noopener"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition-colors">
              <ExternalLink className="w-3 h-3" /> Claude AI Analysis
            </a>
            <a href={`https://www.tradingview.com/chart/?symbol=${selectedRow.symbol}`}
              target="_blank" rel="noopener"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md bg-secondary hover:bg-secondary/80 transition-colors">
              <TrendingUp className="w-3 h-3" /> TradingView
            </a>
          </div>

          {/* Explain Calculation */}
          {showExplain && (() => {
            const s = selectedRow;
            const stock = s.stock_price;
            const strike = s.strike_price;
            const premium = s.premium;
            const netDebit = s.net_debit;
            const dte = s.DTE;
            const assignedReturn = s.assigned_return;
            const annualizedReturn = s.annualized_return;
            const downsideProtection = s.downside_protection;
            const moneyness = s.moneyness;
            return (
              <div className="p-4 bg-amber-500/5 rounded-lg border border-amber-500/20 text-sm font-mono space-y-3">
                <h4 className="font-bold text-amber-400 text-base font-sans">Berechnungsdetails: {s.symbol}</h4>

                <div>
                  <span className="text-muted-foreground">Net Debit</span> (effektiver Einstiegspreis pro Aktie):
                  <div className="ml-4 mt-1">
                    Stock - Premium = ${stock?.toFixed(2)} - ${premium?.toFixed(2)} = <span className="font-bold text-foreground">${netDebit?.toFixed(2)}</span>
                  </div>
                </div>

                <div>
                  <span className="text-muted-foreground">Assigned Return</span> (Rendite wenn Call ausgeuebt wird):
                  <div className="ml-4 mt-1">
                    (Strike + Premium - Stock) / Net Debit<br/>
                    (${strike?.toFixed(2)} + ${premium?.toFixed(2)} - ${stock?.toFixed(2)}) / ${netDebit?.toFixed(2)}<br/>
                    = ${(strike + premium - stock)?.toFixed(2)} / ${netDebit?.toFixed(2)} = <span className="font-bold text-emerald-400">{assignedReturn?.toFixed(1)}%</span>
                  </div>
                </div>

                <div>
                  <span className="text-muted-foreground">Annualized Return</span> (auf 365 Tage hochgerechnet):
                  <div className="ml-4 mt-1">
                    Assigned Return x (365 / DTE)<br/>
                    {assignedReturn?.toFixed(1)}% x (365 / {dte}) = {assignedReturn?.toFixed(1)}% x {(365 / dte)?.toFixed(2)} = <span className="font-bold text-emerald-400">{annualizedReturn?.toFixed(1)}%</span>
                  </div>
                </div>

                <div>
                  <span className="text-muted-foreground">Downside Protection</span> (Praemie als Puffer):
                  <div className="ml-4 mt-1">
                    Premium / Stock = ${premium?.toFixed(2)} / ${stock?.toFixed(2)} = <span className="font-bold text-foreground">{downsideProtection?.toFixed(1)}%</span>
                  </div>
                </div>

                <div>
                  <span className="text-muted-foreground">ITM Depth</span> (wie tief im Geld):
                  <div className="ml-4 mt-1">
                    (Stock - Strike) / Stock = (${stock?.toFixed(2)} - ${strike?.toFixed(2)}) / ${stock?.toFixed(2)} = <span className="font-bold text-foreground">{moneyness?.toFixed(1)}%</span>
                  </div>
                </div>

                <div className="border-t border-amber-500/20 pt-3">
                  <span className="text-muted-foreground font-sans font-semibold">Per Contract (100 Shares):</span>
                  <div className="ml-4 mt-1 space-y-0.5">
                    <div>Investment = 100 x ${stock?.toFixed(2)} = <span className="font-bold">${(stock * 100)?.toLocaleString(undefined, {maximumFractionDigits: 0})}</span></div>
                    <div>Premium Income = 100 x ${premium?.toFixed(2)} = <span className="font-bold">${(premium * 100)?.toLocaleString(undefined, {maximumFractionDigits: 0})}</span></div>
                    <div>Net Cost = 100 x ${netDebit?.toFixed(2)} = <span className="font-bold">${(netDebit * 100)?.toLocaleString(undefined, {maximumFractionDigits: 0})}</span></div>
                    <div>Max Profit = 100 x (Strike - Stock + Premium) = 100 x ${(strike - stock + premium)?.toFixed(2)} = <span className="font-bold text-emerald-400">${((strike - stock + premium) * 100)?.toLocaleString(undefined, {maximumFractionDigits: 0})}</span></div>
                  </div>
                </div>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}
