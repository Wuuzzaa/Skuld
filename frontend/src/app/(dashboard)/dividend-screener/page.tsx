'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getDividendScreener, getDividendScreenerSectors } from '@/lib/api';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatPercent, formatNumber, exportToCSV } from '@/lib/utils';
import { Download, Filter, TrendingUp, Award, Eye, Trash2 } from 'lucide-react';

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex flex-col gap-0.5 p-3 bg-card rounded-lg border border-border/40">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">{label}</span>
      <span className="text-lg font-bold text-foreground">{value}</span>
      {sub && <span className="text-[10px] text-muted-foreground">{sub}</span>}
    </div>
  );
}

function ScoreBadge({ score }: { score: number }) {
  let color = 'bg-red-500/20 text-red-400';
  let label = 'DISCARD';
  if (score >= 23) {
    color = 'bg-emerald-500/20 text-emerald-400';
    label = 'BUY';
  } else if (score >= 12) {
    color = 'bg-yellow-500/20 text-yellow-400';
    label = 'WATCH';
  }
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${color}`}>
      {score}/{33} {label}
    </span>
  );
}

function ClassificationBadge({ classification }: { classification: string }) {
  if (!classification || classification === 'None') return <span className="text-muted-foreground text-xs">-</span>;
  let color = 'text-muted-foreground';
  if (classification.includes('Champion')) color = 'text-amber-400';
  else if (classification.includes('Contender')) color = 'text-blue-400';
  else if (classification.includes('Challenger')) color = 'text-cyan-400';
  return <span className={`text-xs font-medium ${color}`}>{classification.replace('Dividend ', '')}</span>;
}

export default function DividendScreenerPage() {
  const [showFilters, setShowFilters] = useState(false);
  const [params, setParams] = useState({
    min_yield: 3.0,
    max_yield: 100.0,
    min_price: 10.0,
    max_price: 10000.0,
    min_market_cap_b: 2.0,
    min_avg_volume: 200000,
    max_debt_to_equity: 0,
    min_dividend_years: 5,
    only_champions: false,
    only_contenders_plus: false,
    below_sma200: false,
    above_52w_low: false,
    sector: '',
    exclude_reits: false,
    min_score: 12,
  });

  const { data: sectors } = useQuery({
    queryKey: ['dividend-screener-sectors'],
    queryFn: getDividendScreenerSectors,
  });

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['dividend-screener', params],
    queryFn: () => getDividendScreener(params),
  });

  const results = data?.results || [];
  const summary = data?.summary || {};

  const columns: Column[] = useMemo(() => [
    { key: 'score_total', label: 'Score', sortable: true, align: 'center', width: '80px',
      format: (v: number) => <ScoreBadge score={v} /> },
    { key: 'symbol', label: 'Symbol', sortable: true, width: '80px' },
    { key: 'company_name', label: 'Company', sortable: true, width: '180px',
      format: (v: string) => <span className="truncate block max-w-[180px]" title={v}>{v}</span> },
    { key: 'sector', label: 'Sector', sortable: true, width: '120px',
      format: (v: string) => <span className="text-xs text-muted-foreground">{v}</span> },
    { key: 'price', label: 'Price', sortable: true, align: 'right', format: (v: number) => formatCurrency(v) },
    { key: 'dividend_yield_pct', label: 'Yield %', sortable: true, align: 'right', colorCode: 'percent',
      format: (v: number) => v?.toFixed(2) + '%' },
    { key: 'dividend_growth_years', label: 'Div Years', sortable: true, align: 'right' },
    { key: 'dividend_classification', label: 'Class', sortable: true, align: 'center',
      format: (v: string) => <ClassificationBadge classification={v} /> },
    { key: 'payout_ratio_pct', label: 'Payout %', sortable: true, align: 'right',
      format: (v: number) => v != null ? v.toFixed(0) + '%' : '-' },
    { key: 'trailing_pe', label: 'P/E', sortable: true, align: 'right',
      format: (v: number) => v != null ? v.toFixed(1) : '-' },
    { key: 'profit_margin_pct', label: 'Margin %', sortable: true, align: 'right',
      format: (v: number) => v != null ? v.toFixed(1) + '%' : '-' },
    { key: 'debt_to_equity', label: 'D/E', sortable: true, align: 'right',
      format: (v: number) => v != null ? v.toFixed(0) : '-' },
    { key: 'roe_pct', label: 'ROE %', sortable: true, align: 'right',
      format: (v: number) => v != null ? v.toFixed(1) + '%' : '-' },
    { key: 'pct_from_sma200', label: '% SMA200', sortable: true, align: 'right', colorCode: 'pnl',
      format: (v: number) => v != null ? v.toFixed(1) + '%' : '-' },
    { key: 'rsi_14', label: 'RSI', sortable: true, align: 'right',
      format: (v: number) => v != null ? v.toFixed(0) : '-' },
    { key: 'score_fundamental', label: 'F', sortable: true, align: 'center', width: '40px',
      format: (v: number) => <span className="text-xs text-blue-400">{v}/15</span> },
    { key: 'score_dividend', label: 'D', sortable: true, align: 'center', width: '40px',
      format: (v: number) => <span className="text-xs text-amber-400">{v}/15</span> },
    { key: 'score_technical', label: 'T', sortable: true, align: 'center', width: '40px',
      format: (v: number) => <span className="text-xs text-cyan-400">{v}/3</span> },
  ], []);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Award className="h-5 w-5 text-amber-400" />
            Dividend Screener
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Zahltagstrategie 11-Punkte-Matrix (5 Fundamental + 5 Dividend + 1 Technik)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              showFilters ? 'bg-primary/20 text-primary' : 'bg-card border border-border/50 text-muted-foreground hover:text-foreground'
            }`}
          >
            <Filter className="h-3.5 w-3.5" />
            Filter
          </button>
          {results.length > 0 && (
            <button
              onClick={() => exportToCSV(results, 'dividend-screener')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-card border border-border/50 text-muted-foreground hover:text-foreground"
            >
              <Download className="h-3.5 w-3.5" />
              CSV
            </button>
          )}
        </div>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 p-4 bg-card rounded-lg border border-border/40">
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">Min Yield %</label>
            <input type="number" step="0.5" value={params.min_yield}
              onChange={e => setParams({...params, min_yield: +e.target.value})}
              className="w-full px-2 py-1.5 rounded bg-background border border-border/50 text-sm" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">Min Price $</label>
            <input type="number" step="1" value={params.min_price}
              onChange={e => setParams({...params, min_price: +e.target.value})}
              className="w-full px-2 py-1.5 rounded bg-background border border-border/50 text-sm" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">Min Market Cap (B$)</label>
            <input type="number" step="0.5" value={params.min_market_cap_b}
              onChange={e => setParams({...params, min_market_cap_b: +e.target.value})}
              className="w-full px-2 py-1.5 rounded bg-background border border-border/50 text-sm" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">Min Avg Volume</label>
            <input type="number" step="50000" value={params.min_avg_volume}
              onChange={e => setParams({...params, min_avg_volume: +e.target.value})}
              className="w-full px-2 py-1.5 rounded bg-background border border-border/50 text-sm" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">Min Div Years</label>
            <input type="number" step="1" value={params.min_dividend_years}
              onChange={e => setParams({...params, min_dividend_years: +e.target.value})}
              className="w-full px-2 py-1.5 rounded bg-background border border-border/50 text-sm" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">Min Score</label>
            <input type="number" step="1" min="0" max="33" value={params.min_score}
              onChange={e => setParams({...params, min_score: +e.target.value})}
              className="w-full px-2 py-1.5 rounded bg-background border border-border/50 text-sm" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">Max D/E Ratio</label>
            <input type="number" step="10" value={params.max_debt_to_equity}
              onChange={e => setParams({...params, max_debt_to_equity: +e.target.value})}
              className="w-full px-2 py-1.5 rounded bg-background border border-border/50 text-sm" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">Sector</label>
            <select value={params.sector}
              onChange={e => setParams({...params, sector: e.target.value})}
              className="w-full px-2 py-1.5 rounded bg-background border border-border/50 text-sm">
              <option value="">All Sectors</option>
              {(sectors || []).map((s: string) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          {/* Toggle filters */}
          <div className="col-span-2 md:col-span-4 lg:col-span-6 flex flex-wrap gap-3 pt-2 border-t border-border/30">
            {[
              { key: 'below_sma200', label: 'Below SMA200 (undervalued)' },
              { key: 'above_52w_low', label: 'Above 52w Low (no free-fall)' },
              { key: 'only_contenders_plus', label: 'Contenders+ (10+ yrs)' },
              { key: 'only_champions', label: 'Champions only (25+ yrs)' },
              { key: 'exclude_reits', label: 'Exclude REITs' },
            ].map(({ key, label }) => (
              <label key={key} className="flex items-center gap-1.5 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={(params as any)[key]}
                  onChange={e => setParams({...params, [key]: e.target.checked})}
                  className="rounded border-border/50"
                />
                <span className="text-muted-foreground">{label}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Summary Stats */}
      {summary.total_dividend_stocks > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
          <StatCard label="Universe" value={formatNumber(summary.total_dividend_stocks)} sub="dividend payers" />
          <StatCard label="Filtered" value={formatNumber(summary.filtered_count)} />
          <StatCard
            label="BUY Signal"
            value={String(summary.buy_count)}
            sub={`score >= 23`}
          />
          <StatCard
            label="WATCH"
            value={String(summary.watch_count)}
            sub="score 12-22"
          />
          <StatCard label="Avg Score" value={String(summary.avg_score) + '/33'} />
          <StatCard label="Avg Yield" value={summary.avg_yield?.toFixed(2) + '%'} />
        </div>
      )}

      {/* Results Table */}
      {isLoading ? (
        <LoadingState message="Scoring dividend stocks..." />
      ) : results.length > 0 ? (
        <DataTable
          data={results}
          columns={columns}
          defaultSort={{ key: 'score_total', direction: 'desc' }}
          maxHeight="calc(100vh - 320px)"
          compact
          stickyHeader
          striped
        />
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <Award className="h-10 w-10 mx-auto mb-2 opacity-30" />
          <p>No stocks match your criteria. Try relaxing filters.</p>
        </div>
      )}

      {isFetching && !isLoading && (
        <div className="fixed bottom-4 right-4 bg-card border border-border/50 rounded-lg px-3 py-2 text-xs text-muted-foreground shadow-lg">
          Updating...
        </div>
      )}
    </div>
  );
}
