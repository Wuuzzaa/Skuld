'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getMarriedPuts } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatPercent } from '@/lib/utils';
import { Shield, ExternalLink, Filter } from 'lucide-react';

export default function MarriedPutsPage() {
  const [params, setParams] = useState({
    strike_multiplier: 1.2,
    min_roi: 3.0,
    max_roi: 7.0,
    min_days: 30,
    max_days: 500,
    max_results: 50,
  });
  const [showFilters, setShowFilters] = useState(true);
  const [selectedRow, setSelectedRow] = useState<any>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['married-puts', params],
    queryFn: () => getMarriedPuts(params),
  });

  const columns: Column[] = [
    {
      key: 'symbol',
      label: 'Symbol',
      sortable: true,
      format: (v: string) => <span className="font-semibold text-foreground">{v}</span>,
    },
    { key: 'Company', label: 'Company', sortable: true },
    {
      key: 'expiration_date',
      label: 'Expiration',
      sortable: true,
      format: (v: string) => v ? String(v).split('T')[0] : '',
    },
    { key: 'days_to_expiration', label: 'DTE', sortable: true, align: 'right' },
    { key: 'strike_price', label: 'Strike', format: formatCurrency, sortable: true, align: 'right' },
    { key: 'live_stock_price', label: 'Stock Price', format: formatCurrency, sortable: true, align: 'right' },
    {
      key: 'roi_annualized_pct',
      label: 'ROI% (Ann.)',
      sortable: true,
      align: 'right',
      colorCode: 'percent',
      format: (v: number) => formatPercent(v),
    },
    { key: 'total_investment', label: 'Investment', format: formatCurrency, sortable: true, align: 'right' },
    {
      key: 'minimum_potential_profit',
      label: 'Min Profit',
      sortable: true,
      align: 'right',
      colorCode: 'pnl',
      format: (v: number) => formatCurrency(v),
    },
    {
      key: 'Classification',
      label: 'Div Status',
      sortable: true,
      format: (v: string) => (
        <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-medium ${
          v === 'Champion' ? 'bg-emerald-500/20 text-emerald-400' :
          v === 'Contender' ? 'bg-blue-500/20 text-blue-400' :
          v === 'Challenger' ? 'bg-yellow-500/20 text-yellow-400' :
          'bg-secondary text-muted-foreground'
        }`}>
          {v || 'N/A'}
        </span>
      ),
    },
  ];

  // Stats
  const stats = useMemo(() => {
    if (!data?.length) return null;
    const avgROI = data.reduce((s: number, r: any) => s + (r.roi_annualized_pct || 0), 0) / data.length;
    const avgInvest = data.reduce((s: number, r: any) => s + (r.total_investment || 0), 0) / data.length;
    return { avgROI, avgInvest, count: data.length };
  }, [data]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Married Puts</h1>
          {isFetching && <div className="w-2 h-2 rounded-full bg-purple-400 animate-pulse" />}
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer ${
            showFilters ? 'bg-primary/20 text-primary border border-primary/30' : 'bg-secondary/60 text-muted-foreground border border-border/50 hover:text-foreground'
          }`}
        >
          <Filter className="w-3 h-3" /> Filters
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-3">
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Results</span>
            <span className="text-lg font-bold">{stats.count}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Avg ROI%</span>
            <span className="text-lg font-bold text-emerald-400">{formatPercent(stats.avgROI)}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Avg Investment</span>
            <span className="text-lg font-bold">{formatCurrency(stats.avgInvest)}</span>
          </div>
        </div>
      )}

      {/* Filters */}
      {showFilters && (
        <Card className="border-purple-500/20">
          <CardContent className="pt-4">
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Strike Mult.</label>
                <Input type="number" step="0.05" value={params.strike_multiplier} onChange={(e) => setParams({ ...params, strike_multiplier: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Min ROI %</label>
                <Input type="number" value={params.min_roi} onChange={(e) => setParams({ ...params, min_roi: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Max ROI %</label>
                <Input type="number" value={params.max_roi} onChange={(e) => setParams({ ...params, max_roi: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Min Days</label>
                <Input type="number" value={params.min_days} onChange={(e) => setParams({ ...params, min_days: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Max Days</label>
                <Input type="number" value={params.max_days} onChange={(e) => setParams({ ...params, max_days: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Max Results</label>
                <Input type="number" value={params.max_results} onChange={(e) => setParams({ ...params, max_results: +e.target.value })} className="h-8 mt-1" />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {isLoading ? (
        <LoadingState message="Loading married puts..." />
      ) : (
        <DataTable
          data={data || []}
          columns={columns}
          selectedIndex={selectedIndex}
          onRowClick={(row, i) => { setSelectedRow(row); setSelectedIndex(i); }}
          defaultSort={{ key: 'roi_annualized_pct', direction: 'desc' }}
          striped
        />
      )}

      {/* Detail Panel */}
      {selectedRow && (
        <Card className="border-purple-500/20">
          <CardContent className="pt-4">
            <div className="flex items-center justify-between mb-3">
              <span className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-400 text-sm font-bold">
                {selectedRow.symbol}
              </span>
              <a
                href={`https://finance.yahoo.com/quote/${selectedRow.symbol}`}
                target="_blank"
                rel="noopener"
                className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-secondary/80 hover:bg-primary/20 hover:text-primary transition-all border border-border/30"
              >
                <ExternalLink className="w-3 h-3" /> Yahoo Finance
              </a>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Company</p>
                <p className="text-sm font-medium truncate">{selectedRow.Company}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">ROI (Annual)</p>
                <p className="text-base font-bold text-emerald-400">{formatPercent(selectedRow.roi_annualized_pct)}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Total Investment</p>
                <p className="text-base font-bold">{formatCurrency(selectedRow.total_investment)}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Min Profit</p>
                <p className="text-base font-bold text-emerald-400">{formatCurrency(selectedRow.minimum_potential_profit)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
