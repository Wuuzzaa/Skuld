'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getPositionInsurance } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatNumber } from '@/lib/utils';
import { Shield, Search, TrendingUp, TrendingDown } from 'lucide-react';

export default function PositionInsurancePage() {
  const [symbol, setSymbol] = useState('');
  const [costBasis, setCostBasis] = useState(100);
  const [searchSymbol, setSearchSymbol] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['position-insurance', searchSymbol, costBasis],
    queryFn: () => getPositionInsurance({ symbol: searchSymbol, cost_basis: costBasis }),
    enabled: !!searchSymbol,
  });

  const putColumns: Column[] = [
    {
      key: 'expiration_date',
      label: 'Expiration',
      sortable: true,
      format: (v: string) => v ? String(v).split('T')[0] : '',
    },
    { key: 'strike_price', label: 'Strike', format: formatCurrency, sortable: true, align: 'right' },
    { key: 'last_option_price', label: 'Price', format: formatCurrency, sortable: true, align: 'right' },
    { key: 'greeks_delta', label: 'Delta', format: (v: number) => formatNumber(v, 3), sortable: true, align: 'right' },
    { key: 'open_interest', label: 'OI', sortable: true, align: 'right' },
    { key: 'days_to_expiration', label: 'DTE', sortable: true, align: 'right' },
  ];

  const profit = data?.current_price ? data.current_price - costBasis : 0;
  const profitPct = costBasis > 0 ? (profit / costBasis * 100) : 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold">Position Insurance</h1>
      </div>
      <p className="text-sm text-muted-foreground">RadioActive Trading - Find protective puts and financing calls.</p>

      {/* Search */}
      <Card className="border-orange-500/20">
        <CardContent className="pt-4">
          <div className="flex gap-3 items-end">
            <div className="flex-1">
              <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Stock Symbol</label>
              <Input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                placeholder="AAPL"
                className="h-9 mt-1"
                onKeyDown={(e) => e.key === 'Enter' && setSearchSymbol(symbol)}
              />
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Cost Basis/Share</label>
              <Input type="number" step="0.5" value={costBasis} onChange={(e) => setCostBasis(+e.target.value)} className="h-9 mt-1" />
            </div>
            <Button onClick={() => setSearchSymbol(symbol)} className="h-9 gap-1.5">
              <Search className="w-3.5 h-3.5" /> Calculate
            </Button>
          </div>
        </CardContent>
      </Card>

      {isLoading && <LoadingState message={`Loading options for ${searchSymbol}...`} />}

      {/* Current Price Summary */}
      {data?.current_price && (
        <div className="grid grid-cols-3 gap-3">
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">{searchSymbol} Price</span>
            <span className="text-lg font-bold">{formatCurrency(data.current_price)}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Your P/L</span>
            <span className={`text-lg font-bold inline-flex items-center gap-1 ${profit >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {profit >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
              {formatCurrency(profit)}
            </span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">P/L %</span>
            <span className={`text-lg font-bold ${profitPct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {profitPct.toFixed(1)}%
            </span>
          </div>
        </div>
      )}

      {/* Put Options */}
      {data?.puts?.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-400" />
            Protective Puts ({data.puts.length})
          </h2>
          <DataTable data={data.puts} columns={putColumns} defaultSort={{ key: 'days_to_expiration', direction: 'asc' }} striped />
        </div>
      )}

      {/* Call Options */}
      {data?.calls?.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            Financing Calls ({data.calls.length})
          </h2>
          <DataTable data={data.calls} columns={putColumns} defaultSort={{ key: 'days_to_expiration', direction: 'asc' }} striped />
        </div>
      )}
    </div>
  );
}
