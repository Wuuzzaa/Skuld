'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getPositionInsurance } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatNumber } from '@/lib/utils';

export default function PositionInsurancePage() {
  const [symbol, setSymbol] = useState('');
  const [costBasis, setCostBasis] = useState(100);
  const [searchSymbol, setSearchSymbol] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['position-insurance', searchSymbol, costBasis],
    queryFn: () => getPositionInsurance({ symbol: searchSymbol, cost_basis: costBasis }),
    enabled: !!searchSymbol,
  });

  const putColumns = [
    { key: 'expiration_date', label: 'Expiration' },
    { key: 'strike_price', label: 'Strike', format: formatCurrency },
    { key: 'last_option_price', label: 'Price', format: formatCurrency },
    { key: 'greeks_delta', label: 'Delta', format: (v: number) => formatNumber(v, 3) },
    { key: 'open_interest', label: 'OI' },
    { key: 'days_to_expiration', label: 'DTE' },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Position Insurance Tool</h1>
      <p className="text-sm text-muted-foreground">RadioActive Trading - Find suitable puts for protection and optional calls for financing.</p>

      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-3 items-end">
            <div className="flex-1">
              <label className="text-xs text-muted-foreground">Stock Symbol</label>
              <Input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="AAPL" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Cost Basis/Share</label>
              <Input type="number" step="0.5" value={costBasis} onChange={(e) => setCostBasis(+e.target.value)} />
            </div>
            <Button onClick={() => setSearchSymbol(symbol)}>CALCULATE</Button>
          </div>
        </CardContent>
      </Card>

      {isLoading && <LoadingState message={`Loading options for ${searchSymbol}...`} />}

      {data?.current_price && (
        <div className="p-3 rounded-md bg-green-900/20 border border-green-800">
          <span className="font-semibold">{searchSymbol}</span> - Current Price: <span className="font-semibold">{formatCurrency(data.current_price)}</span>
          {' | '}Your Profit: <span className="font-semibold">{formatCurrency(data.current_price - costBasis)} ({((data.current_price - costBasis) / costBasis * 100).toFixed(1)}%)</span>
        </div>
      )}

      {data?.puts?.length > 0 && (
        <>
          <h2 className="text-lg font-semibold">Put Options ({data.puts.length})</h2>
          <DataTable data={data.puts} columns={putColumns} />
        </>
      )}

      {data?.calls?.length > 0 && (
        <>
          <h2 className="text-lg font-semibold">Call Options ({data.calls.length})</h2>
          <DataTable data={data.calls} columns={putColumns} />
        </>
      )}
    </div>
  );
}
