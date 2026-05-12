'use client';

import { useQuery } from '@tanstack/react-query';
import { getSymbolDetails } from '@/lib/api';
import { DataTable } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useParams } from 'next/navigation';

export default function SymbolDetailPage() {
  const { symbol } = useParams<{ symbol: string }>();

  const { data, isLoading } = useQuery({
    queryKey: ['symbol-detail', symbol],
    queryFn: () => getSymbolDetails(symbol),
    enabled: !!symbol,
  });

  if (isLoading) return <LoadingState message={`Loading ${symbol}...`} />;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">{symbol}</h1>

      {data?.fundamentals?.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Fundamentals</CardTitle></CardHeader>
          <CardContent><DataTable data={data.fundamentals} /></CardContent>
        </Card>
      )}

      {data?.iv_history?.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">IV History</CardTitle></CardHeader>
          <CardContent><DataTable data={data.iv_history} maxHeight="400px" /></CardContent>
        </Card>
      )}

      {data?.technicals?.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Technical Indicators</CardTitle></CardHeader>
          <CardContent><DataTable data={data.technicals} maxHeight="400px" /></CardContent>
        </Card>
      )}
    </div>
  );
}
