'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getUniverse } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatNumber, getClaudeAnalysisUrl } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { ExternalLink } from 'lucide-react';

type IndexFilter = 'all' | 'sp500' | 'non-sp500';

export default function UniversePage() {
  const [search, setSearch] = useState('');
  const [indexFilter, setIndexFilter] = useState<IndexFilter>('all');
  const [sectorFilter, setSectorFilter] = useState('');
  const [exchangeFilter, setExchangeFilter] = useState('');
  const [selectedRow, setSelectedRow] = useState<any>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const { data, isLoading, isFetching, isError, error } = useQuery({
    queryKey: ['universe'],
    queryFn: getUniverse,
    staleTime: 5 * 60 * 1000,
  });

  const symbols = data?.symbols || [];
  const meta = data?.meta || {};

  const filtered = useMemo(() => {
    let result = symbols;

    if (search) {
      const q = search.toLowerCase();
      result = result.filter((s: any) =>
        s.symbol?.toLowerCase().includes(q) ||
        s.company_name?.toLowerCase().includes(q)
      );
    }

    if (indexFilter === 'sp500') {
      result = result.filter((s: any) => s.is_sp500);
    } else if (indexFilter === 'non-sp500') {
      result = result.filter((s: any) => !s.is_sp500);
    }

    if (sectorFilter) {
      result = result.filter((s: any) => s.sector === sectorFilter);
    }

    if (exchangeFilter) {
      result = result.filter((s: any) => s.exchange === exchangeFilter);
    }

    return result;
  }, [symbols, search, indexFilter, sectorFilter, exchangeFilter]);

  const columns: Column[] = [
    {
      key: 'symbol',
      label: 'Symbol',
      sortable: true,
      format: (v: string, row: any) => (
        <span className={`font-semibold font-mono ${row.is_sp500 ? 'text-teal-400' : 'text-foreground'}`}>
          {v}
        </span>
      ),
    },
    { key: 'company_name', label: 'Company', sortable: true },
    {
      key: 'sector',
      label: 'Sector',
      sortable: true,
      format: (v: string) => <span className="text-xs">{v || '—'}</span>,
    },
    {
      key: 'exchange',
      label: 'Exchange',
      sortable: true,
      align: 'center',
      format: (v: string) => (
        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
          v === 'NASDAQ' ? 'bg-blue-500/10 text-blue-400' :
          v === 'NYSE' ? 'bg-amber-500/10 text-amber-400' :
          v === 'AMEX' ? 'bg-purple-500/10 text-purple-400' :
          'bg-muted text-muted-foreground'
        }`}>
          {v || '—'}
        </span>
      ),
    },
    {
      key: 'price',
      label: 'Price',
      sortable: true,
      align: 'right',
      format: (v: number) => v ? formatCurrency(v) : '—',
    },
    {
      key: 'rsl',
      label: 'RSL',
      sortable: true,
      align: 'right',
      format: (v: number) => v ? (
        <span className={`font-mono ${v >= 1.2 ? 'text-emerald-400' : v >= 1.0 ? 'text-foreground' : 'text-red-400'}`}>
          {formatNumber(v, 3)}
        </span>
      ) : <span className="text-muted-foreground">—</span>,
    },
    {
      key: 'iv_rank',
      label: 'IV Rank',
      sortable: true,
      align: 'right',
      format: (v: number) => v != null ? (
        <span className={v >= 50 ? 'text-amber-400' : 'text-foreground'}>
          {formatNumber(v, 1)}
        </span>
      ) : <span className="text-muted-foreground">—</span>,
    },
    {
      key: 'beta',
      label: 'Beta',
      sortable: true,
      align: 'right',
      format: (v: number) => v != null ? formatNumber(v, 2) : '—',
    },
    {
      key: 'is_sp500',
      label: 'S&P',
      sortable: true,
      align: 'center',
      format: (v: boolean) => v
        ? <span className="text-teal-400 font-bold text-xs">500</span>
        : <span className="text-muted-foreground text-xs">—</span>,
    },
  ];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Universe</h1>
          {isFetching && <div className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />}
        </div>
        {!isLoading && (
          <span className="text-sm text-muted-foreground">
            {filtered.length} von {meta.total || symbols.length} Symbolen
          </span>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <Input
          placeholder="Symbol oder Name suchen..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64 h-8"
        />

        {/* Index Filter */}
        <div className="flex items-center gap-1 bg-muted/30 rounded-lg p-0.5">
          {([
            { key: 'all', label: 'Alle' },
            { key: 'sp500', label: 'S&P 500' },
            { key: 'non-sp500', label: 'Andere' },
          ] as const).map((opt) => (
            <button
              key={opt.key}
              onClick={() => setIndexFilter(opt.key)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                indexFilter === opt.key
                  ? 'bg-primary/20 text-primary shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Sector Filter */}
        <select
          value={sectorFilter}
          onChange={(e) => setSectorFilter(e.target.value)}
          className="h-8 px-2 text-xs bg-background border border-border rounded-md text-foreground"
        >
          <option value="">Alle Sektoren</option>
          {(meta.sectors || []).map((s: string) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        {/* Exchange Filter */}
        <select
          value={exchangeFilter}
          onChange={(e) => setExchangeFilter(e.target.value)}
          className="h-8 px-2 text-xs bg-background border border-border rounded-md text-foreground"
        >
          <option value="">Alle Exchanges</option>
          {(meta.exchanges || []).map((e: string) => (
            <option key={e} value={e}>{e}</option>
          ))}
        </select>

        {/* Reset */}
        {(search || indexFilter !== 'all' || sectorFilter || exchangeFilter) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => { setSearch(''); setIndexFilter('all'); setSectorFilter(''); setExchangeFilter(''); }}
            className="text-xs text-muted-foreground"
          >
            Reset
          </Button>
        )}
      </div>

      {/* Stats */}
      {!isLoading && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Gesamt</span>
            <span className="text-lg font-bold">{meta.total || 0}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">S&P 500</span>
            <span className="text-lg font-bold text-teal-400">{meta.sp500_count || 0}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Gefiltert</span>
            <span className="text-lg font-bold text-primary">{filtered.length}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Sektoren</span>
            <span className="text-lg font-bold">{meta.sectors?.length || 0}</span>
          </div>
        </div>
      )}

      {/* Table */}
      {isLoading ? (
        <LoadingState message="Lade Universe..." />
      ) : isError ? (
        <Card className="border-red-500/30 bg-red-500/5">
          <CardContent className="pt-4">
            <p className="text-sm text-red-400">Fehler beim Laden: {(error as any)?.message || 'API nicht erreichbar'}</p>
            <p className="text-xs text-muted-foreground mt-1">Prüfe ob die API läuft: /api/health/db</p>
          </CardContent>
        </Card>
      ) : (
        <DataTable
          data={filtered}
          columns={columns}
          selectedIndex={selectedIndex}
          onRowClick={(row, i) => { setSelectedRow(row); setSelectedIndex(i); }}
          defaultSort={{ key: 'symbol', direction: 'asc' }}
          striped
        />
      )}

      {/* Detail Panel */}
      {selectedRow && (
        <Card className="border-teal-500/20 bg-card/80">
          <CardContent className="pt-4 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-sm font-bold bg-teal-500/20 text-teal-400">
                  {selectedRow.symbol}
                </span>
                <span className="text-sm text-muted-foreground">{selectedRow.company_name}</span>
                {selectedRow.is_sp500 && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-teal-500/10 text-teal-400 font-medium">S&P 500</span>
                )}
              </div>
              <Button variant="ghost" size="sm" onClick={() => { setSelectedRow(null); setSelectedIndex(null); }}>
                <span className="text-xs">Schliessen</span>
              </Button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Sektor</p>
                <p className="text-sm font-medium">{selectedRow.sector || '—'}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Industrie</p>
                <p className="text-sm font-medium">{selectedRow.industry || '—'}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Exchange</p>
                <p className="text-sm font-medium">{selectedRow.exchange || '—'}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Price</p>
                <p className="text-sm font-bold">{selectedRow.price ? formatCurrency(selectedRow.price) : '—'}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">IV Rank</p>
                <p className="text-sm font-bold">{selectedRow.iv_rank != null ? formatNumber(selectedRow.iv_rank, 1) : '—'}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Dividende</p>
                <p className="text-sm font-medium">{selectedRow.dividend_classification || '—'}</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link
                href={`/symbols/${selectedRow.symbol}`}
                className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-primary/10 hover:bg-primary/20 text-primary transition-all border border-primary/20 font-medium"
              >
                Symbol-Details
              </Link>
              {[
                { name: 'TradingView', url: `https://www.tradingview.com/chart/?symbol=${selectedRow.symbol}` },
                { name: 'Finviz', url: `https://finviz.com/quote.ashx?t=${selectedRow.symbol}` },
                { name: 'Yahoo Finance', url: `https://finance.yahoo.com/quote/${selectedRow.symbol}` },
                { name: 'Claude AI', url: getClaudeAnalysisUrl(selectedRow.symbol, selectedRow.company_name) },
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
