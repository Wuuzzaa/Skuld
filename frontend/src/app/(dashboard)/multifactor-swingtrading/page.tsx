'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getMultifactorSwingtrading } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatPercent, formatNumber } from '@/lib/utils';
import { X, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function MultifactorSwingtradingPage() {
  const [params, setParams] = useState({
    top_percentile_value_score: 20,
    top_n: 50,
    drop_missing_values: false,
    drop_weak_value_factors: false,
  });
  const [selectedRow, setSelectedRow] = useState<any>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const { data: stocks, isLoading, isFetching } = useQuery({
    queryKey: ['multifactor-swingtrading', params],
    queryFn: () => getMultifactorSwingtrading(params),
  });

  const stats = useMemo(() => {
    if (!stocks?.length) return null;
    const avgScore = stocks.reduce((s: number, r: any) => s + (r.value_score || 0), 0) / stocks.length;
    const best = stocks.reduce((b: any, r: any) => (!b || r.value_score > b.value_score) ? r : b, null);
    return { count: stocks.length, avgScore, best };
  }, [stocks]);

  const columns: Column[] = [
    {
      key: 'symbol',
      label: 'Symbol',
      sortable: true,
      format: (v: string) => <span className="font-semibold text-foreground">{v}</span>,
    },
    {
      key: 'value_score',
      label: 'Score',
      sortable: true,
      align: 'right',
      format: (v: number) => (
        <span className={`font-bold ${v >= 400 ? 'text-emerald-400' : v >= 300 ? 'text-yellow-400' : 'text-foreground'}`}>
          {formatNumber(v, 1)}
        </span>
      ),
    },
    { key: 'price', label: 'Price', format: formatCurrency, sortable: true, align: 'right' },
    { key: 'price_to_book', label: 'P/B', format: (v: number) => formatNumber(v, 2), sortable: true, align: 'right' },
    { key: 'price_to_earnings', label: 'P/E', format: (v: number) => formatNumber(v, 1), sortable: true, align: 'right' },
    { key: 'price_to_sales', label: 'P/S', format: (v: number) => formatNumber(v, 2), sortable: true, align: 'right' },
    {
      key: 'ebitda_to_enterprise_value',
      label: 'EBITDA/EV',
      format: (v: number) => formatPercent(v * 100),
      sortable: true,
      align: 'right',
      colorCode: 'percent',
    },
    { key: 'price_to_cashflow', label: 'P/CF', format: (v: number) => formatNumber(v, 2), sortable: true, align: 'right' },
    {
      key: 'shareholder_yield',
      label: 'Sh. Yield',
      format: (v: number) => formatPercent(v * 100),
      sortable: true,
      align: 'right',
      colorCode: 'percent',
    },
    {
      key: '1_year_price_appreciation',
      label: '1Y Perf',
      format: (v: number) => formatPercent(v * 100),
      sortable: true,
      align: 'right',
      colorCode: 'percent',
    },
    { key: 'Sector', label: 'Sector', sortable: true },
  ];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Multifactor Swingtrading</h1>
          {isFetching && <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />}
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Top Percentile</label>
          <Input
            type="number"
            min={5}
            max={100}
            step={5}
            value={params.top_percentile_value_score}
            onChange={(e) => setParams({ ...params, top_percentile_value_score: +e.target.value })}
            className="w-20 h-8"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Top N</label>
          <Input
            type="number"
            min={1}
            max={500}
            step={5}
            value={params.top_n}
            onChange={(e) => setParams({ ...params, top_n: +e.target.value })}
            className="w-20 h-8"
          />
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={params.drop_missing_values}
            onChange={(e) => setParams({ ...params, drop_missing_values: e.target.checked })}
            className="rounded border-border"
          />
          <span className="text-xs text-muted-foreground">Drop Missing</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={params.drop_weak_value_factors}
            onChange={(e) => setParams({ ...params, drop_weak_value_factors: e.target.checked })}
            className="rounded border-border"
          />
          <span className="text-xs text-muted-foreground">Drop Weak Factors</span>
        </label>
      </div>

      {/* Stats */}
      {stats && !isLoading && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Results</span>
            <span className="text-lg font-bold">{stats.count}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Avg Score</span>
            <span className="text-lg font-bold text-amber-400">{formatNumber(stats.avgScore, 1)}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Best Stock</span>
            <span className="text-lg font-bold">{stats.best?.symbol || 'N/A'}</span>
            <span className="text-[10px] text-muted-foreground">{stats.best ? `Score: ${formatNumber(stats.best.value_score, 1)}` : ''}</span>
          </div>
        </div>
      )}

      {/* Table */}
      {isLoading ? (
        <LoadingState message="Calculating multifactor scores..." />
      ) : (
        <DataTable
          data={stocks || []}
          columns={columns}
          selectedIndex={selectedIndex}
          onRowClick={(row, i) => { setSelectedRow(row); setSelectedIndex(i); }}
          defaultSort={{ key: 'value_score', direction: 'desc' }}
          striped
        />
      )}

      {/* Detail Panel */}
      {selectedRow && (
        <Card className="border-amber-500/20 bg-card/80">
          <CardContent className="pt-4 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-400 text-sm font-bold">
                  {selectedRow.symbol}
                </span>
                <span className="text-sm text-muted-foreground">{selectedRow.Company}</span>
              </div>
              <Button variant="ghost" size="sm" onClick={() => { setSelectedRow(null); setSelectedIndex(null); }}>
                <X className="w-4 h-4" />
              </Button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Value Score</p>
                <p className="text-base font-bold text-amber-400">{formatNumber(selectedRow.value_score, 1)}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Price</p>
                <p className="text-base font-bold">{formatCurrency(selectedRow.price)}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">P/B</p>
                <p className="text-base font-bold">{formatNumber(selectedRow.price_to_book, 2)}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">P/E</p>
                <p className="text-base font-bold">{formatNumber(selectedRow.price_to_earnings, 1)}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Debt/Equity</p>
                <p className="text-base font-bold">{formatNumber(selectedRow['debt_to_equity %'], 1)}%</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">1Y Perf</p>
                <p className={`text-base font-bold ${(selectedRow['1_year_price_appreciation'] || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {formatPercent((selectedRow['1_year_price_appreciation'] || 0) * 100)}
                </p>
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
