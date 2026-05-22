'use client';

import { useQuery } from '@tanstack/react-query';
import { getDataLogs } from '@/lib/api';
import { DataTable } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';

export default function DataLogsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['data-logs'],
    queryFn: getDataLogs,
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Data Change Logs</h1>
      {isLoading ? (
        <LoadingState />
      ) : data?.length ? (
        <DataTable data={data} />
      ) : (
        <p className="text-muted-foreground">No data change logs available.</p>
      )}
    </div>
  );
}
