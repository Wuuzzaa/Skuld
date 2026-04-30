'use client';

import { useQuery } from '@tanstack/react-query';
import { getAnalystPrices } from '@/lib/api';
import { DataTable } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatPercent } from '@/lib/utils';

export default function AnalystPricesPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['analyst-prices'],
    queryFn: getAnalystPrices,
  });

  const columns = [
    { key: 'symbol', label: 'Symbol' },
    { key: 'price', label: 'Price', format: formatCurrency },
    { key: 'mean_analyst_target', label: 'Analyst Target', format: formatCurrency },
    { key: 'difference_dollar', label: 'Diff ($)', format: formatCurrency },
    { key: 'difference_percent', label: 'Diff (%)', format: (v: number) => formatPercent(v) },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Analyst Prices</h1>
      {isLoading ? (
        <LoadingState />
      ) : (
        <>
          <p className="text-sm text-muted-foreground">{data?.length || 0} Results</p>
          <DataTable data={data || []} columns={columns} />
        </>
      )}
    </div>
  );
}
