'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { buildDividendPortfolio } from '@/lib/api';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatPercent, formatNumber, exportToCSV } from '@/lib/utils';
import { Wallet, Download, TrendingUp, Calendar, PieChart } from 'lucide-react';

function StatCard({ label, value, sub, highlight }: { label: string; value: string; sub?: string; highlight?: boolean }) {
  return (
    <div className={`flex flex-col gap-0.5 p-3 rounded-lg border ${
      highlight ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-card border-border/40'
    }`}>
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">{label}</span>
      <span className={`text-lg font-bold ${highlight ? 'text-emerald-400' : 'text-foreground'}`}>{value}</span>
      {sub && <span className="text-[10px] text-muted-foreground">{sub}</span>}
    </div>
  );
}

function MonthlyChart({ breakdown }: { breakdown: any[] }) {
  if (!breakdown?.length) return null;
  const max = Math.max(...breakdown.map(m => m.dividend_eur));
  return (
    <div className="bg-card rounded-lg border border-border/40 p-4">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <Calendar className="h-4 w-4 text-cyan-400" />
        Monthly Dividend Income (EUR)
      </h3>
      <div className="flex items-end gap-1.5 h-32">
        {breakdown.map((m) => (
          <div key={m.month} className="flex-1 flex flex-col items-center gap-1">
            <span className="text-[9px] text-muted-foreground font-medium">
              {m.dividend_eur > 0 ? `€${m.dividend_eur.toFixed(0)}` : ''}
            </span>
            <div
              className="w-full rounded-t bg-emerald-500/60 transition-all min-h-[2px]"
              style={{ height: max > 0 ? `${(m.dividend_eur / max) * 100}%` : '2px' }}
            />
            <span className="text-[9px] text-muted-foreground">{m.month}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SectorBreakdown({ portfolio }: { portfolio: any[] }) {
  if (!portfolio?.length) return null;
  const sectors: Record<string, { count: number; investment: number }> = {};
  portfolio.forEach(p => {
    if (!sectors[p.sector]) sectors[p.sector] = { count: 0, investment: 0 };
    sectors[p.sector].count++;
    sectors[p.sector].investment += p.investment_usd;
  });
  const total = Object.values(sectors).reduce((s, v) => s + v.investment, 0);
  const sorted = Object.entries(sectors).sort((a, b) => b[1].investment - a[1].investment);

  return (
    <div className="bg-card rounded-lg border border-border/40 p-4">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <PieChart className="h-4 w-4 text-pink-400" />
        Sector Allocation
      </h3>
      <div className="space-y-1.5">
        {sorted.map(([sector, data]) => (
          <div key={sector} className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground w-28 truncate" title={sector}>{sector}</span>
            <div className="flex-1 h-3 bg-background rounded overflow-hidden">
              <div
                className="h-full bg-primary/40 rounded"
                style={{ width: `${(data.investment / total) * 100}%` }}
              />
            </div>
            <span className="text-[10px] text-muted-foreground w-12 text-right">
              {((data.investment / total) * 100).toFixed(0)}%
            </span>
            <span className="text-[10px] text-muted-foreground w-4 text-right">{data.count}x</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function DividendPortfolioPage() {
  const [params, setParams] = useState({
    target_monthly_eur: 100,
    eur_usd_rate: 1.08,
    max_positions: 20,
    max_per_sector: 2,
    min_score: 18,
    min_yield_pct: 2.5,
    min_price: 10,
    max_single_position_pct: 10,
  });
  const [submitted, setSubmitted] = useState(false);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['dividend-portfolio', params],
    queryFn: () => buildDividendPortfolio(params),
    enabled: submitted,
  });

  const portfolio = data?.portfolio || [];
  const summary = data?.summary || {};
  const breakdown = data?.monthly_breakdown || [];

  const columns: Column[] = useMemo(() => [
    { key: 'symbol', label: 'Symbol', sortable: true, width: '70px',
      format: (v: string) => <span className="font-mono font-bold text-primary">{v}</span> },
    { key: 'company_name', label: 'Company', sortable: true, width: '160px',
      format: (v: string) => <span className="truncate block max-w-[160px] text-xs" title={v}>{v}</span> },
    { key: 'sector', label: 'Sector', sortable: true, width: '100px',
      format: (v: string) => <span className="text-xs text-muted-foreground">{v}</span> },
    { key: 'payment_months', label: 'Pays', sortable: true, width: '120px',
      format: (v: string) => <span className="text-[10px] text-cyan-400 font-mono">{v}</span> },
    { key: 'score_total', label: 'Score', sortable: true, align: 'center', width: '55px',
      format: (v: number) => (
        <span className={`font-bold text-xs ${v >= 23 ? 'text-emerald-400' : v >= 18 ? 'text-yellow-400' : 'text-muted-foreground'}`}>
          {v}/33
        </span>
      )},
    { key: 'shares', label: 'Shares', sortable: true, align: 'right' },
    { key: 'price', label: 'Price', sortable: true, align: 'right', format: (v: number) => `$${v.toFixed(2)}` },
    { key: 'investment_usd', label: 'Invest $', sortable: true, align: 'right',
      format: (v: number) => formatCurrency(v) },
    { key: 'weight_pct', label: 'Weight', sortable: true, align: 'right',
      format: (v: number) => `${v.toFixed(1)}%` },
    { key: 'dividend_yield_pct', label: 'Yield %', sortable: true, align: 'right', colorCode: 'percent',
      format: (v: number) => `${v.toFixed(2)}%` },
    { key: 'annual_dividend_usd', label: 'Ann. Div $', sortable: true, align: 'right',
      format: (v: number) => `$${v.toFixed(2)}` },
    { key: 'quarterly_dividend_usd', label: 'Qtr Div $', sortable: true, align: 'right',
      format: (v: number) => `$${v.toFixed(2)}` },
    { key: 'dividend_growth_years', label: 'Yrs', sortable: true, align: 'right' },
    { key: 'dividend_classification', label: 'Class', sortable: true, width: '90px',
      format: (v: string) => {
        if (!v || v === 'None') return <span className="text-xs text-muted-foreground">-</span>;
        const c = v.includes('Champion') ? 'text-amber-400' : v.includes('Contender') ? 'text-blue-400' : 'text-cyan-400';
        return <span className={`text-xs ${c}`}>{v.replace('Dividend ', '')}</span>;
      }},
  ], []);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2">
          <Wallet className="h-5 w-5 text-emerald-400" />
          Dividend Portfolio Builder
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5">
          Optimiertes Portfolio fuer Ziel-Dividende mit monatlicher Staffelung
        </p>
      </div>

      {/* Input Controls */}
      <div className="bg-card rounded-lg border border-border/40 p-4">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          <div className="space-y-1 col-span-2">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">
              Ziel: EUR pro Monat
            </label>
            <input type="number" step="25" min="10" value={params.target_monthly_eur}
              onChange={e => setParams({...params, target_monthly_eur: +e.target.value})}
              className="w-full px-3 py-2 rounded-lg bg-background border border-primary/30 text-lg font-bold text-emerald-400 focus:border-primary focus:outline-none" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">EUR/USD</label>
            <input type="number" step="0.01" value={params.eur_usd_rate}
              onChange={e => setParams({...params, eur_usd_rate: +e.target.value})}
              className="w-full px-2 py-1.5 rounded bg-background border border-border/50 text-sm" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">Max Positionen</label>
            <input type="number" step="1" min="5" max="40" value={params.max_positions}
              onChange={e => setParams({...params, max_positions: +e.target.value})}
              className="w-full px-2 py-1.5 rounded bg-background border border-border/50 text-sm" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">Max/Sektor</label>
            <input type="number" step="1" min="1" max="5" value={params.max_per_sector}
              onChange={e => setParams({...params, max_per_sector: +e.target.value})}
              className="w-full px-2 py-1.5 rounded bg-background border border-border/50 text-sm" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">Min Score</label>
            <input type="number" step="1" min="1" max="33" value={params.min_score}
              onChange={e => setParams({...params, min_score: +e.target.value})}
              className="w-full px-2 py-1.5 rounded bg-background border border-border/50 text-sm" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">Min Yield %</label>
            <input type="number" step="0.5" value={params.min_yield_pct}
              onChange={e => setParams({...params, min_yield_pct: +e.target.value})}
              className="w-full px-2 py-1.5 rounded bg-background border border-border/50 text-sm" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-muted-foreground font-medium">Max Position %</label>
            <input type="number" step="1" min="3" max="50" value={params.max_single_position_pct}
              onChange={e => setParams({...params, max_single_position_pct: +e.target.value})}
              className="w-full px-2 py-1.5 rounded bg-background border border-border/50 text-sm" />
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={() => setSubmitted(true)}
            className="px-6 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm transition-colors flex items-center gap-2"
          >
            <TrendingUp className="h-4 w-4" />
            Portfolio berechnen
          </button>
          {portfolio.length > 0 && (
            <button
              onClick={() => exportToCSV(portfolio, 'dividend-portfolio')}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs bg-card border border-border/50 text-muted-foreground hover:text-foreground"
            >
              <Download className="h-3.5 w-3.5" />
              CSV Export
            </button>
          )}
          {summary.target_coverage_pct > 0 && (
            <span className={`text-xs font-medium ${
              summary.target_coverage_pct >= 95 ? 'text-emerald-400' : 'text-yellow-400'
            }`}>
              Ziel-Erreichung: {summary.target_coverage_pct}%
            </span>
          )}
        </div>
      </div>

      {/* Loading */}
      {isLoading && <LoadingState message="Building optimized portfolio..." />}

      {/* Results */}
      {!isLoading && portfolio.length > 0 && (
        <>
          {/* Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
            <StatCard
              label="Monatl. Dividende"
              value={`€${summary.achieved_monthly_eur?.toFixed(0)}`}
              sub={`Ziel: €${summary.target_monthly_eur}`}
              highlight
            />
            <StatCard
              label="Jahres-Dividende"
              value={`€${summary.achieved_annual_eur?.toFixed(0)}`}
              sub={`$${summary.total_annual_dividend_usd?.toFixed(0)} USD`}
            />
            <StatCard
              label="Gesamt-Investment"
              value={`€${formatNumber(summary.total_investment_eur)}`}
              sub={`$${formatNumber(summary.total_investment_usd)} USD`}
            />
            <StatCard
              label="Portfolio Yield"
              value={`${summary.portfolio_yield_pct}%`}
              sub="gewichteter Durchschnitt"
            />
            <StatCard label="Positionen" value={`${summary.num_positions}`} sub={`${summary.num_sectors} Sektoren`} />
            <StatCard label="Avg Score" value={`${summary.avg_score}/33`} />
            <StatCard label="Avg Div Years" value={`${summary.avg_dividend_years}`} sub="Jahre Wachstum" />
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <MonthlyChart breakdown={breakdown} />
            <SectorBreakdown portfolio={portfolio} />
          </div>

          {/* Portfolio Table */}
          <DataTable
            data={portfolio}
            columns={columns}
            defaultSort={{ key: 'score_total', direction: 'desc' }}
            maxHeight="calc(100vh - 580px)"
            compact
            stickyHeader
            striped
          />
        </>
      )}

      {/* Empty state */}
      {submitted && !isLoading && portfolio.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <Wallet className="h-10 w-10 mx-auto mb-2 opacity-30" />
          <p>Kein Portfolio gefunden. Versuche niedrigere Schwellwerte (Min Score, Min Yield).</p>
        </div>
      )}

      {isFetching && !isLoading && (
        <div className="fixed bottom-4 right-4 bg-card border border-border/50 rounded-lg px-3 py-2 text-xs text-muted-foreground shadow-lg">
          Recalculating...
        </div>
      )}
    </div>
  );
}
