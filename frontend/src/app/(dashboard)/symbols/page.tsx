'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listSymbols } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { LoadingState } from '@/components/ui/spinner';
import Link from 'next/link';

export default function SymbolsPage() {
  const [search, setSearch] = useState('');

  const { data: symbols, isLoading } = useQuery({
    queryKey: ['symbols'],
    queryFn: listSymbols,
  });

  const filtered = (symbols || []).filter((s: string) =>
    s.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Symbols</h1>

      <Input
        placeholder="Search symbols... (e.g., AAPL, MSFT)"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {isLoading ? (
        <LoadingState />
      ) : (
        <div className="grid grid-cols-4 md:grid-cols-8 lg:grid-cols-12 gap-2">
          {filtered.slice(0, 200).map((symbol: string) => (
            <Link
              key={symbol}
              href={`/symbols/${symbol}`}
              className="text-center py-2 px-1 rounded-md border hover:bg-accent hover:text-accent-foreground transition-colors text-sm font-mono"
            >
              {symbol}
            </Link>
          ))}
        </div>
      )}
      {filtered.length > 200 && (
        <p className="text-sm text-muted-foreground">Showing 200 of {filtered.length} symbols. Use search to narrow.</p>
      )}
    </div>
  );
}
