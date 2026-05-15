'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getAnalystPrices } from '@/lib/api';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatPercent, getClaudeAnalysisUrl } from '@/lib/utils';
import { TrendingUp, TrendingDown, ExternalLink } from 'lucide-react';

export default function AnalystPricesPage() {
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['analyst-prices'],
    queryFn: getAnalystPrices,
  });

  const columns: Column[] = [
    {
      key: 'symbol',
      label: 'Symbol',
      sortable: true,
      format: (v: string) => <span className="font-semibold text-foreground">{v}</span>,
    },
    { key: 'price', label: 'Current Price', format: formatCurrency, sortable: true, align: 'right' },
    { key: 'mean_analyst_target', label: 'Analyst Target', format: formatCurrency, sortable: true, align: 'right' },
    {
      key: 'difference_dollar',
      label: 'Diff ($)',
      sortable: true,
      align: 'right',
      colorCode: 'pnl',
      format: (v: number) => formatCurrency(v),
    },
    {
      key: 'difference_percent',
      label: 'Upside %',
      sortable: true,
      align: 'right',
      colorCode: 'percent',
      format: (v: number, row: any) => (
        <span className="inline-flex items-center gap-1">
          {v > 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
          {formatPercent(v)}
        </span>
      ),
    },
    {
      key: 'symbol',
      label: 'AI',
      sortable: false,
      format: (v: string) => (
        <a href={getClaudeAnalysisUrl(v)} target="_blank" rel="noopener"
          className="inline-flex items-center gap-0.5 text-muted-foreground hover:text-primary transition-colors"
          title="Claude AI Analysis">
          <ExternalLink className="w-3 h-3" /> AI
        </a>
      ),
    },
  ];

  // Stats
  const stats = useMemo(() => {
    if (!data?.length) return null;
    const upside = data.filter((r: any) => r.difference_percent > 0);
    const downside = data.filter((r: any) => r.difference_percent < 0);
    const avgUpside = upside.length ? upside.reduce((s: number, r: any) => s + r.difference_percent, 0) / upside.length : 0;
    return { total: data.length, upside: upside.length, downside: downside.length, avgUpside };
  }, [data]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold">Analyst Prices</h1>
        {isFetching && <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />}
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Total</span>
            <span className="text-lg font-bold">{stats.total}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Undervalued</span>
            <span className="text-lg font-bold text-emerald-400">{stats.upside}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Overvalued</span>
            <span className="text-lg font-bold text-red-400">{stats.downside}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Avg Upside</span>
            <span className="text-lg font-bold text-emerald-400">{formatPercent(stats.avgUpside)}</span>
          </div>
        </div>
      )}

      {isLoading ? (
        <LoadingState />
      ) : (
        <DataTable
          data={data || []}
          columns={columns}
          defaultSort={{ key: 'difference_percent', direction: 'desc' }}
          striped
        />
      )}
    </div>
  );
}
