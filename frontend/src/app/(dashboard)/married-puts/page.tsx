'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getMarriedPuts } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatPercent } from '@/lib/utils';

export default function MarriedPutsPage() {
  const [params, setParams] = useState({
    strike_multiplier: 1.2,
    min_roi: 3.0,
    max_roi: 7.0,
    min_days: 30,
    max_days: 500,
    max_results: 50,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['married-puts', params],
    queryFn: () => getMarriedPuts(params),
  });

  const columns = [
    { key: 'symbol', label: 'Symbol' },
    { key: 'Company', label: 'Company' },
    { key: 'expiration_date', label: 'Expiration' },
    { key: 'days_to_expiration', label: 'DTE' },
    { key: 'strike_price', label: 'Strike', format: formatCurrency },
    { key: 'live_stock_price', label: 'Stock Price', format: formatCurrency },
    { key: 'roi_annualized_pct', label: 'ROI% (Annual)', format: (v: number) => formatPercent(v) },
    { key: 'total_investment', label: 'Investment', format: formatCurrency },
    { key: 'minimum_potential_profit', label: 'Min Profit', format: formatCurrency },
    { key: 'Classification', label: 'Div Status' },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Married Put Analysis</h1>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">Strike Multiplier</label>
              <Input type="number" step="0.05" value={params.strike_multiplier} onChange={(e) => setParams({ ...params, strike_multiplier: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Min ROI %</label>
              <Input type="number" value={params.min_roi} onChange={(e) => setParams({ ...params, min_roi: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Max ROI %</label>
              <Input type="number" value={params.max_roi} onChange={(e) => setParams({ ...params, max_roi: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Min Days</label>
              <Input type="number" value={params.min_days} onChange={(e) => setParams({ ...params, min_days: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Max Days</label>
              <Input type="number" value={params.max_days} onChange={(e) => setParams({ ...params, max_days: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Max Results</label>
              <Input type="number" value={params.max_results} onChange={(e) => setParams({ ...params, max_results: +e.target.value })} />
            </div>
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <LoadingState message="Loading married puts..." />
      ) : (
        <>
          <p className="text-sm text-muted-foreground">{data?.length || 0} Results</p>
          <DataTable data={data || []} columns={columns} />
        </>
      )}
    </div>
  );
}
