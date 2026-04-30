'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getExpirations, getSpreads } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatPercent, formatNumber } from '@/lib/utils';
import {
  TrendingUp, TrendingDown, Filter, ExternalLink,
  ChevronDown, X, BarChart3, Activity
} from 'lucide-react';

// Badge component for filter pills
function Badge({ children, active, onClick, onRemove }: {
  children: React.ReactNode;
  active?: boolean;
  onClick?: () => void;
  onRemove?: () => void;
}) {
  return (
    <span
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer ${
        active
          ? 'bg-primary/20 text-primary border border-primary/30'
          : 'bg-secondary/60 text-muted-foreground border border-border/50 hover:bg-secondary hover:text-foreground'
      }`}
    >
      {children}
      {onRemove && (
        <X className="w-3 h-3 hover:text-destructive" onClick={(e) => { e.stopPropagation(); onRemove(); }} />
      )}
    </span>
  );
}

// Stat card for summary metrics
function StatCard({ label, value, sub, trend }: { label: string; value: string; sub?: string; trend?: 'up' | 'down' | 'neutral' }) {
  return (
    <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">{label}</span>
      <span className={`text-lg font-bold ${
        trend === 'up' ? 'text-emerald-400' : trend === 'down' ? 'text-red-400' : 'text-foreground'
      }`}>
        {value}
      </span>
      {sub && <span className="text-[10px] text-muted-foreground">{sub}</span>}
    </div>
  );
}

export default function SpreadsPage() {
  const [params, setParams] = useState({
    option_type: 'put',
    delta_target: 0.2,
    spread_width: 5,
    strategy_type: 'credit',
    min_open_interest: 100,
    min_day_volume: 20,
    min_iv_rank: 0,
    min_iv_percentile: 0,
    min_sell_iv: 0.1,
    max_sell_iv: 2.0,
    min_max_profit: 30,
  });
  const [selectedExpiration, setSelectedExpiration] = useState('');
  const [selectedRow, setSelectedRow] = useState<any>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [expTypeFilter, setExpTypeFilter] = useState<'all' | 'Monthly' | 'Weekly' | 'Daily'>('all');

  const { data: expirations, isLoading: loadingExp } = useQuery({
    queryKey: ['expirations'],
    queryFn: getExpirations,
  });

  const {
    data: spreads,
    isLoading: loadingSpreads,
    isFetching,
  } = useQuery({
    queryKey: ['spreads', selectedExpiration, params],
    queryFn: () => getSpreads({ ...params, expiration_date: selectedExpiration }),
    enabled: !!selectedExpiration,
  });

  // Filter expirations by type
  const filteredExpirations = useMemo(() => {
    if (!expirations?.length) return [];
    if (expTypeFilter === 'all') return expirations;
    return expirations.filter((e: any) => e.expiration_type === expTypeFilter);
  }, [expirations, expTypeFilter]);

  // Auto-select expiration closest to 30 DTE
  if (filteredExpirations.length && !selectedExpiration) {
    const target = filteredExpirations.find((e: any) => e.days_to_expiration >= 28) || filteredExpirations[filteredExpirations.length - 1];
    setSelectedExpiration(target.expiration_date);
  }

  // Apply client-side filters
  const filteredSpreads = useMemo(() => {
    return (spreads || []).filter((row: any) => {
      if (row.max_profit < params.min_max_profit) return false;
      if (row.sell_iv < params.min_sell_iv) return false;
      if (row.sell_iv > params.max_sell_iv) return false;
      return true;
    });
  }, [spreads, params.min_max_profit, params.min_sell_iv, params.max_sell_iv]);

  // Summary stats
  const stats = useMemo(() => {
    if (!filteredSpreads.length) return null;
    const avgProfit = filteredSpreads.reduce((s: number, r: any) => s + (r.max_profit || 0), 0) / filteredSpreads.length;
    const avgAPDI = filteredSpreads.reduce((s: number, r: any) => s + (r.APDI || 0), 0) / filteredSpreads.length;
    const avgEV = filteredSpreads.reduce((s: number, r: any) => s + (r.expected_value || 0), 0) / filteredSpreads.length;
    const bestTrade = filteredSpreads.reduce((best: any, r: any) => (!best || r.APDI > best.APDI) ? r : best, null);
    return { avgProfit, avgAPDI, avgEV, bestTrade };
  }, [filteredSpreads]);

  // Get DTE for selected expiration
  const selectedDTE = expirations?.find((e: any) => e.expiration_date === selectedExpiration)?.days_to_expiration;

  const columns: Column[] = [
    {
      key: 'symbol',
      label: 'Symbol',
      sortable: true,
      format: (v: string) => (
        <span className="font-semibold text-foreground">{v}</span>
      ),
    },
    { key: 'close', label: 'Price', format: formatCurrency, sortable: true, align: 'right' },
    { key: 'sell_strike', label: 'Sell', format: formatCurrency, sortable: true, align: 'right' },
    { key: 'buy_strike', label: 'Buy', format: formatCurrency, sortable: true, align: 'right' },
    {
      key: 'max_profit',
      label: 'Max Profit',
      sortable: true,
      align: 'right',
      colorCode: 'pnl',
      format: (v: number) => formatCurrency(v),
    },
    { key: 'bpr', label: 'BPR', format: formatCurrency, sortable: true, align: 'right' },
    {
      key: 'expected_value',
      label: 'EV',
      sortable: true,
      align: 'right',
      colorCode: 'pnl',
      format: (v: number) => formatCurrency(v),
    },
    {
      key: 'APDI',
      label: 'APDI%',
      sortable: true,
      align: 'right',
      colorCode: 'percent',
      format: (v: number) => formatPercent(v),
    },
    {
      key: 'sell_iv',
      label: 'IV',
      sortable: true,
      align: 'right',
      colorCode: 'iv',
      format: (v: number) => formatPercent(v * 100),
    },
    { key: 'sell_delta', label: 'Delta', format: (v: number) => formatNumber(v, 3), sortable: true, align: 'right' },
    {
      key: 'iv_rank',
      label: 'IVR',
      sortable: true,
      align: 'right',
      format: (v: number) => (
        <span className={`inline-flex items-center gap-1 ${v >= 30 ? 'text-emerald-400' : 'text-muted-foreground'}`}>
          {formatNumber(v, 0)}
          {v >= 50 && <Activity className="w-3 h-3" />}
        </span>
      ),
    },
    { key: 'company_sector', label: 'Sector', sortable: true },
  ];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Spreads</h1>
          {isFetching && <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />}
        </div>
        <div className="flex items-center gap-2">
          <Badge active={params.strategy_type === 'credit'} onClick={() => setParams({ ...params, strategy_type: 'credit' })}>
            <TrendingUp className="w-3 h-3" /> Credit
          </Badge>
          <Badge active={params.strategy_type === 'debit'} onClick={() => setParams({ ...params, strategy_type: 'debit' })}>
            <TrendingDown className="w-3 h-3" /> Debit
          </Badge>
          <Badge active={params.option_type === 'put'} onClick={() => setParams({ ...params, option_type: 'put' })}>
            Put
          </Badge>
          <Badge active={params.option_type === 'call'} onClick={() => setParams({ ...params, option_type: 'call' })}>
            Call
          </Badge>
          <div className="w-px h-5 bg-border/50 mx-1" />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowFilters(!showFilters)}
            className={showFilters ? 'text-primary' : 'text-muted-foreground'}
          >
            <Filter className="w-4 h-4 mr-1" /> Filters
          </Button>
        </div>
      </div>

      {/* Quick Controls Row */}
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
          <label className="text-xs text-muted-foreground">Exp</label>
          <select
            className="h-8 rounded-md border border-input bg-background px-2 text-sm min-w-[260px]"
            value={selectedExpiration}
            onChange={(e) => setSelectedExpiration(e.target.value)}
          >
            {filteredExpirations.map((exp: any) => (
              <option key={exp.expiration_date} value={exp.expiration_date}>
                {exp.days_to_expiration} DTE - {exp.day_of_week || ''} {exp.expiration_date.split('T')[0]} - {exp.expiration_type || ''}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Delta</label>
          <Input
            type="number"
            step="0.05"
            value={params.delta_target}
            onChange={(e) => setParams({ ...params, delta_target: +e.target.value })}
            className="w-20 h-8"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Width</label>
          <Input
            type="number"
            value={params.spread_width}
            onChange={(e) => setParams({ ...params, spread_width: +e.target.value })}
            className="w-20 h-8"
          />
        </div>
        {selectedDTE && (
          <Badge active>
            {selectedDTE} DTE
          </Badge>
        )}
        {filteredSpreads.length > 0 && (
          <span className="text-xs text-muted-foreground ml-auto">
            {filteredSpreads.length} of {(spreads || []).length} results
          </span>
        )}
      </div>

      {/* Extended Filters Panel */}
      {showFilters && (
        <Card className="border-primary/20">
          <CardContent className="pt-4">
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Min Volume</label>
                <Input
                  type="number"
                  value={params.min_day_volume}
                  onChange={(e) => setParams({ ...params, min_day_volume: +e.target.value })}
                  className="h-8 mt-1"
                />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Min OI</label>
                <Input
                  type="number"
                  value={params.min_open_interest}
                  onChange={(e) => setParams({ ...params, min_open_interest: +e.target.value })}
                  className="h-8 mt-1"
                />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Min Profit ($)</label>
                <Input
                  type="number"
                  value={params.min_max_profit}
                  onChange={(e) => setParams({ ...params, min_max_profit: +e.target.value })}
                  className="h-8 mt-1"
                />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Min IV</label>
                <Input
                  type="number"
                  step="0.05"
                  value={params.min_sell_iv}
                  onChange={(e) => setParams({ ...params, min_sell_iv: +e.target.value })}
                  className="h-8 mt-1"
                />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Max IV</label>
                <Input
                  type="number"
                  step="0.05"
                  value={params.max_sell_iv}
                  onChange={(e) => setParams({ ...params, max_sell_iv: +e.target.value })}
                  className="h-8 mt-1"
                />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Min IV Rank</label>
                <Input
                  type="number"
                  value={params.min_iv_rank}
                  onChange={(e) => setParams({ ...params, min_iv_rank: +e.target.value })}
                  className="h-8 mt-1"
                />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Summary Stats */}
      {stats && !loadingSpreads && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            label="Avg Profit"
            value={formatCurrency(stats.avgProfit)}
            trend="up"
          />
          <StatCard
            label="Avg APDI"
            value={formatPercent(stats.avgAPDI)}
            trend={stats.avgAPDI > 0.1 ? 'up' : 'neutral'}
          />
          <StatCard
            label="Avg EV"
            value={formatCurrency(stats.avgEV)}
            trend={stats.avgEV > 0 ? 'up' : 'down'}
          />
          <StatCard
            label="Best Trade"
            value={stats.bestTrade?.symbol || 'N/A'}
            sub={stats.bestTrade ? `APDI: ${formatPercent(stats.bestTrade.APDI)}` : undefined}
          />
        </div>
      )}

      {/* Results Table */}
      {loadingSpreads || loadingExp ? (
        <LoadingState message="Calculating spreads..." />
      ) : (
        <DataTable
          data={filteredSpreads}
          columns={columns}
          selectedIndex={selectedIndex}
          onRowClick={(row, i) => {
            setSelectedRow(row);
            setSelectedIndex(i);
          }}
          defaultSort={{ key: 'APDI', direction: 'desc' }}
          striped
        />
      )}

      {/* Detail Panel */}
      {selectedRow && (
        <Card className="border-primary/20 bg-card/80">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg flex items-center gap-2">
                <span className="px-2 py-0.5 rounded bg-primary/20 text-primary text-sm font-bold">
                  {selectedRow.symbol}
                </span>
                <span className="text-muted-foreground font-normal text-sm">
                  {selectedRow.option_type?.toUpperCase()} {params.strategy_type === 'credit' ? 'Credit' : 'Debit'} Spread
                </span>
              </CardTitle>
              <Button variant="ghost" size="sm" onClick={() => { setSelectedRow(null); setSelectedIndex(null); }}>
                <X className="w-4 h-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Key metrics */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
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
                <p className={`text-base font-bold ${selectedRow.expected_value >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {formatCurrency(selectedRow.expected_value)}
                </p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">APDI</p>
                <p className={`text-base font-bold ${selectedRow.APDI > 0 ? 'text-emerald-400' : 'text-muted-foreground'}`}>
                  {formatPercent(selectedRow.APDI)}
                </p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">IV Rank</p>
                <p className="text-base font-bold">{formatNumber(selectedRow.iv_rank, 1)}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">IV Percentile</p>
                <p className="text-base font-bold">{formatNumber(selectedRow.iv_percentile, 1)}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Sector</p>
                <p className="text-xs font-medium truncate">{selectedRow.company_sector}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Industry</p>
                <p className="text-xs font-medium truncate">{selectedRow.company_industry}</p>
              </div>
            </div>

            {/* Leg details table */}
            <div className="rounded-lg overflow-hidden border border-border/40">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Leg</th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">Strike</th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">Price</th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">Delta</th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">IV</th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">Theta</th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">OI</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-border/30">
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-red-400" />
                        <span className="font-medium">
                          {params.strategy_type === 'credit' ? 'Short' : 'Long'} {selectedRow.option_type}
                        </span>
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono">{formatCurrency(selectedRow.sell_strike)}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatCurrency(selectedRow.sell_last_option_price)}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatNumber(selectedRow.sell_delta, 3)}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatPercent(selectedRow.sell_iv * 100)}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatNumber(selectedRow.sell_theta, 4)}</td>
                    <td className="px-3 py-2 text-right font-mono">{selectedRow.sell_open_interest?.toLocaleString()}</td>
                  </tr>
                  <tr className="border-t border-border/30">
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-emerald-400" />
                        <span className="font-medium">
                          {params.strategy_type === 'credit' ? 'Long' : 'Short'} {selectedRow.option_type}
                        </span>
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono">{formatCurrency(selectedRow.buy_strike)}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatCurrency(selectedRow.buy_last_option_price)}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatNumber(selectedRow.buy_delta, 3)}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatPercent(selectedRow.buy_iv * 100)}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatNumber(selectedRow.buy_theta, 4)}</td>
                    <td className="px-3 py-2 text-right font-mono">{selectedRow.buy_open_interest?.toLocaleString()}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* External Links */}
            <div className="flex flex-wrap gap-2">
              {[
                { name: 'TradingView', url: `https://www.tradingview.com/chart/?symbol=${selectedRow.symbol}` },
                { name: 'Finviz', url: `https://finviz.com/quote.ashx?t=${selectedRow.symbol}` },
                { name: 'Seeking Alpha', url: `https://seekingalpha.com/symbol/${selectedRow.symbol}` },
                { name: 'Yahoo Finance', url: `https://finance.yahoo.com/quote/${selectedRow.symbol}` },
                ...(selectedRow.optionstrat_url ? [{ name: 'OptionStrat', url: selectedRow.optionstrat_url }] : []),
              ].map((link) => (
                <a
                  key={link.name}
                  href={link.url}
                  target="_blank"
                  rel="noopener"
                  className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-secondary/80 hover:bg-primary/20 hover:text-primary transition-all border border-border/30"
                >
                  <ExternalLink className="w-3 h-3" />
                  {link.name}
                </a>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
