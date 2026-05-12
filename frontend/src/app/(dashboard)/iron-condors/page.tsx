'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getExpirations, getIronCondors } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatPercent, formatNumber } from '@/lib/utils';
import { Filter, X, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function IronCondorsPage() {
  const [params, setParams] = useState({
    delta_put: 0.15,
    delta_call: 0.15,
    width_put: 5,
    width_call: 5,
    min_open_interest: 100,
    min_day_volume: 20,
    min_iv_rank: 0,
  });
  const [expPut, setExpPut] = useState('');
  const [expCall, setExpCall] = useState('');
  const [selectedRow, setSelectedRow] = useState<any>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [expTypeFilter, setExpTypeFilter] = useState<'all' | 'Monthly' | 'Weekly' | 'Daily'>('all');

  const { data: expirations } = useQuery({
    queryKey: ['expirations'],
    queryFn: getExpirations,
  });

  // Filter expirations by type
  const filteredExpirations = useMemo(() => {
    if (!expirations?.length) return [];
    if (expTypeFilter === 'all') return expirations;
    return expirations.filter((e: any) => e.expiration_type === expTypeFilter);
  }, [expirations, expTypeFilter]);

  // Auto-select ~30 DTE
  if (filteredExpirations.length && !expPut) {
    const target = filteredExpirations.find((e: any) => e.days_to_expiration >= 28) || filteredExpirations[filteredExpirations.length - 1];
    setExpPut(target.expiration_date);
    setExpCall(target.expiration_date);
  }

  const { data: condors, isLoading, isFetching } = useQuery({
    queryKey: ['iron-condors', expPut, expCall, params],
    queryFn: () =>
      getIronCondors({
        expiration_date_put: expPut,
        expiration_date_call: expCall,
        ...params,
      }),
    enabled: !!expPut && !!expCall,
  });

  const columns: Column[] = [
    {
      key: 'symbol',
      label: 'Symbol',
      sortable: true,
      format: (v: string) => <span className="font-semibold text-foreground">{v}</span>,
    },
    { key: 'close', label: 'Price', format: formatCurrency, sortable: true, align: 'right' },
    {
      key: 'max_profit',
      label: 'Max Profit',
      format: formatCurrency,
      sortable: true,
      align: 'right',
      colorCode: 'pnl',
    },
    { key: 'bpr', label: 'BPR', format: formatCurrency, sortable: true, align: 'right' },
    {
      key: 'expected_value',
      label: 'EV',
      format: formatCurrency,
      sortable: true,
      align: 'right',
      colorCode: 'pnl',
    },
    {
      key: 'APDI',
      label: 'APDI%',
      format: (v: number) => formatPercent(v),
      sortable: true,
      align: 'right',
      colorCode: 'percent',
    },
    {
      key: 'iv_rank',
      label: 'IV Rank',
      format: (v: number) => formatNumber(v, 1),
      sortable: true,
      align: 'right',
    },
    { key: 'company_sector', label: 'Sector', sortable: true },
  ];

  // Stats
  const stats = useMemo(() => {
    if (!condors?.length) return null;
    const avgProfit = condors.reduce((s: number, r: any) => s + (r.max_profit || 0), 0) / condors.length;
    const avgEV = condors.reduce((s: number, r: any) => s + (r.expected_value || 0), 0) / condors.length;
    const best = condors.reduce((b: any, r: any) => (!b || r.APDI > b.APDI) ? r : b, null);
    return { avgProfit, avgEV, best, count: condors.length };
  }, [condors]);

  const selectedDTE = expirations?.find((e: any) => e.expiration_date === expPut)?.days_to_expiration;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Iron Condors</h1>
          {isFetching && <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />}
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

      {/* Quick Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Expiration type filter pills */}
        <div className="flex items-center gap-1">
          {(['all', 'Monthly', 'Weekly', 'Daily'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setExpTypeFilter(t)}
              className={`px-2 py-1 rounded text-[11px] font-medium transition-all ${
                expTypeFilter === t
                  ? 'bg-primary/20 text-primary'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {t === 'all' ? 'All' : t}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Put Exp</label>
          <select
            className="h-8 rounded-md border border-input bg-background px-2 text-sm min-w-[260px]"
            value={expPut}
            onChange={(e) => setExpPut(e.target.value)}
          >
            {filteredExpirations.map((exp: any) => (
              <option key={exp.expiration_date} value={exp.expiration_date}>
                {exp.days_to_expiration} DTE - {exp.day_of_week || ''} {exp.expiration_date.split('T')[0]} - {exp.expiration_type || ''}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Call Exp</label>
          <select
            className="h-8 rounded-md border border-input bg-background px-2 text-sm min-w-[260px]"
            value={expCall}
            onChange={(e) => setExpCall(e.target.value)}
          >
            {filteredExpirations.map((exp: any) => (
              <option key={exp.expiration_date} value={exp.expiration_date}>
                {exp.days_to_expiration} DTE - {exp.day_of_week || ''} {exp.expiration_date.split('T')[0]} - {exp.expiration_type || ''}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Put Delta</label>
          <Input type="number" step="0.01" value={params.delta_put} onChange={(e) => setParams({ ...params, delta_put: +e.target.value })} className="w-20 h-8" />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Call Delta</label>
          <Input type="number" step="0.01" value={params.delta_call} onChange={(e) => setParams({ ...params, delta_call: +e.target.value })} className="w-20 h-8" />
        </div>
        {selectedDTE && (
          <span className="inline-flex items-center px-3 py-1.5 rounded-full text-xs font-medium bg-blue-500/20 text-blue-400 border border-blue-500/30">
            {selectedDTE} DTE
          </span>
        )}
      </div>

      {/* Extended Filters */}
      {showFilters && (
        <Card className="border-blue-500/20">
          <CardContent className="pt-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Put Width</label>
                <Input type="number" value={params.width_put} onChange={(e) => setParams({ ...params, width_put: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Call Width</label>
                <Input type="number" value={params.width_call} onChange={(e) => setParams({ ...params, width_call: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Min OI</label>
                <Input type="number" value={params.min_open_interest} onChange={(e) => setParams({ ...params, min_open_interest: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Min IV Rank</label>
                <Input type="number" value={params.min_iv_rank} onChange={(e) => setParams({ ...params, min_iv_rank: +e.target.value })} className="h-8 mt-1" />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Stats */}
      {stats && !isLoading && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Results</span>
            <span className="text-lg font-bold">{stats.count}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Avg Profit</span>
            <span className="text-lg font-bold text-emerald-400">{formatCurrency(stats.avgProfit)}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Avg EV</span>
            <span className={`text-lg font-bold ${stats.avgEV >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatCurrency(stats.avgEV)}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Best Trade</span>
            <span className="text-lg font-bold">{stats.best?.symbol || 'N/A'}</span>
            <span className="text-[10px] text-muted-foreground">{stats.best ? `APDI: ${formatPercent(stats.best.APDI)}` : ''}</span>
          </div>
        </div>
      )}

      {/* Table */}
      {isLoading ? (
        <LoadingState message="Calculating Iron Condors..." />
      ) : (
        <DataTable
          data={condors || []}
          columns={columns}
          selectedIndex={selectedIndex}
          onRowClick={(row, i) => { setSelectedRow(row); setSelectedIndex(i); }}
          defaultSort={{ key: 'APDI', direction: 'desc' }}
          striped
        />
      )}

      {/* Detail Panel */}
      {selectedRow && (
        <Card className="border-blue-500/20 bg-card/80">
          <CardContent className="pt-4 space-y-4">
            <div className="flex items-center justify-between">
              <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 text-sm font-bold">
                {selectedRow.symbol} Iron Condor
              </span>
              <Button variant="ghost" size="sm" onClick={() => { setSelectedRow(null); setSelectedIndex(null); }}>
                <X className="w-4 h-4" />
              </Button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Max Profit</p>
                <p className="text-base font-bold text-emerald-400">{formatCurrency(selectedRow.max_profit)}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">BPR</p>
                <p className="text-base font-bold">{formatCurrency(selectedRow.bpr)}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Expected Value</p>
                <p className={`text-base font-bold ${selectedRow.expected_value >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatCurrency(selectedRow.expected_value)}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">IV Rank</p>
                <p className="text-base font-bold">{formatNumber(selectedRow.iv_rank, 1)}</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {[
                { name: 'TradingView', url: `https://www.tradingview.com/chart/?symbol=${selectedRow.symbol}` },
                { name: 'Finviz', url: `https://finviz.com/quote.ashx?t=${selectedRow.symbol}` },
                { name: 'Yahoo Finance', url: `https://finance.yahoo.com/quote/${selectedRow.symbol}` },
              ].map((link) => (
                <a key={link.name} href={link.url} target="_blank" rel="noopener"
                  className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-secondary/80 hover:bg-primary/20 hover:text-primary transition-all border border-border/30">
                  <ExternalLink className="w-3 h-3" /> {link.name}
                </a>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
