import { cn } from '@/lib/utils';

interface DataTableProps {
  data: Record<string, any>[];
  columns?: { key: string; label: string; format?: (v: any) => string }[];
  onRowClick?: (row: Record<string, any>, index: number) => void;
  selectedIndex?: number | null;
  className?: string;
  maxHeight?: string;
}

export function DataTable({ data, columns, onRowClick, selectedIndex, className, maxHeight = '600px' }: DataTableProps) {
  if (!data.length) {
    return <p className="text-muted-foreground text-center py-8">No data available.</p>;
  }

  const cols: { key: string; label: string; format?: (v: any) => string }[] =
    columns || Object.keys(data[0]).map((key) => ({ key, label: key }));

  return (
    <div className={cn('overflow-auto border rounded-md', className)} style={{ maxHeight }}>
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-muted/80 backdrop-blur z-10">
          <tr>
            {cols.map((col) => (
              <th key={col.key} className="px-3 py-2 text-left font-medium text-muted-foreground whitespace-nowrap">
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr
              key={i}
              onClick={() => onRowClick?.(row, i)}
              className={cn(
                'border-t hover:bg-accent/50 cursor-pointer transition-colors',
                selectedIndex === i && 'bg-accent'
              )}
            >
              {cols.map((col) => (
                <td key={col.key} className="px-3 py-2 whitespace-nowrap">
                  {col.format ? col.format(row[col.key]) : String(row[col.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
