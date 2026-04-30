'use client';

import { useState, useMemo } from 'react';
import { cn } from '@/lib/utils';
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react';

export interface Column {
  key: string;
  label: string;
  format?: (v: any, row?: any) => string | React.ReactNode;
  sortable?: boolean;
  align?: 'left' | 'center' | 'right';
  colorCode?: 'pnl' | 'percent' | 'iv';
  width?: string;
}

interface DataTableProps {
  data: Record<string, any>[];
  columns?: Column[];
  onRowClick?: (row: Record<string, any>, index: number) => void;
  selectedIndex?: number | null;
  className?: string;
  maxHeight?: string;
  defaultSort?: { key: string; direction: 'asc' | 'desc' };
  stickyHeader?: boolean;
  compact?: boolean;
  striped?: boolean;
}

type SortDirection = 'asc' | 'desc' | null;

function getColorClass(value: number | null | undefined, type: string): string {
  if (value == null) return '';
  if (type === 'pnl' || type === 'percent') {
    if (value > 0) return 'text-emerald-400 font-medium';
    if (value < 0) return 'text-red-400 font-medium';
    return 'text-muted-foreground';
  }
  if (type === 'iv') {
    if (value >= 0.6) return 'text-orange-400 font-medium';
    if (value >= 0.4) return 'text-yellow-400';
    return '';
  }
  return '';
}

export function DataTable({
  data,
  columns,
  onRowClick,
  selectedIndex,
  className,
  maxHeight = '600px',
  defaultSort,
  stickyHeader = true,
  compact = false,
  striped = false,
}: DataTableProps) {
  const [sortKey, setSortKey] = useState<string | null>(defaultSort?.key || null);
  const [sortDir, setSortDir] = useState<SortDirection>(defaultSort?.direction || null);

  const cols: Column[] = useMemo(
    () => columns || Object.keys(data[0] || {}).map((key) => ({ key, label: key, sortable: true })),
    [columns, data]
  );

  const sortedData = useMemo(() => {
    if (!sortKey || !sortDir) return data;
    return [...data].sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
      }
      const aStr = String(aVal).toLowerCase();
      const bStr = String(bVal).toLowerCase();
      return sortDir === 'asc' ? aStr.localeCompare(bStr) : bStr.localeCompare(aStr);
    });
  }, [data, sortKey, sortDir]);

  function handleSort(key: string) {
    if (sortKey === key) {
      if (sortDir === 'asc') setSortDir('desc');
      else if (sortDir === 'desc') { setSortKey(null); setSortDir(null); }
      else setSortDir('asc');
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  }

  if (!data.length) {
    return (
      <div className="text-muted-foreground text-center py-12 border border-dashed rounded-lg">
        <p className="text-base">No data available</p>
        <p className="text-xs mt-1">Try adjusting your filters</p>
      </div>
    );
  }

  const cellPadding = compact ? 'px-2.5 py-1.5' : 'px-3 py-2.5';

  return (
    <div className={cn('overflow-auto border border-border/50 rounded-lg bg-card/50', className)} style={{ maxHeight }}>
      <table className="w-full text-sm">
        <thead className={cn(
          stickyHeader && 'sticky top-0 z-10',
          'bg-muted/90 backdrop-blur-sm border-b border-border/50'
        )}>
          <tr>
            {cols.map((col) => (
              <th
                key={col.key}
                onClick={() => (col.sortable !== false) && handleSort(col.key)}
                className={cn(
                  cellPadding,
                  'text-xs font-semibold uppercase tracking-wider text-muted-foreground whitespace-nowrap select-none',
                  col.align === 'right' && 'text-right',
                  col.align === 'center' && 'text-center',
                  col.sortable !== false && 'cursor-pointer hover:text-foreground transition-colors group'
                )}
                style={col.width ? { width: col.width } : undefined}
              >
                <span className="inline-flex items-center gap-1">
                  {col.label}
                  {col.sortable !== false && (
                    <span className="inline-flex opacity-40 group-hover:opacity-100 transition-opacity">
                      {sortKey === col.key ? (
                        sortDir === 'asc' ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronsUpDown className="w-3.5 h-3.5" />
                      )}
                    </span>
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedData.map((row, i) => (
            <tr
              key={i}
              onClick={() => onRowClick?.(row, i)}
              className={cn(
                'border-t border-border/30 transition-all duration-150',
                onRowClick && 'cursor-pointer',
                selectedIndex === i
                  ? 'bg-primary/10 border-l-2 border-l-primary'
                  : 'hover:bg-accent/40',
                striped && i % 2 === 1 && 'bg-muted/20'
              )}
            >
              {cols.map((col) => {
                const raw = row[col.key];
                const colorClass = col.colorCode ? getColorClass(raw, col.colorCode) : '';
                const formatted = col.format ? col.format(raw, row) : String(raw ?? '');

                return (
                  <td
                    key={col.key}
                    className={cn(
                      cellPadding,
                      'whitespace-nowrap',
                      col.align === 'right' && 'text-right',
                      col.align === 'center' && 'text-center',
                      colorClass
                    )}
                  >
                    {formatted}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
