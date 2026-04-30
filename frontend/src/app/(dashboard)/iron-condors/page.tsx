'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getExpirations, getIronCondors } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatPercent, formatNumber } from '@/lib/utils';

export default function IronCondorsPage() {
  const [params, setParams] = useState({
    delta_put: 0.15,
    delta_call: 0.15,
    width_put: 5,
    width_call: 5,
    min_open_interest: 100,
    min_day_volume: 20,
    min_iv_rank: 0,
  });
  const [expPut, setExpPut] = useState('');
  const [expCall, setExpCall] = useState('');
  const [selectedRow, setSelectedRow] = useState<any>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const { data: expirations } = useQuery({
    queryKey: ['expirations'],
    queryFn: getExpirations,
  });

  if (expirations?.length && !expPut) {
    const idx = Math.min(1, expirations.length - 1);
    setExpPut(expirations[idx].expiration_date);
    setExpCall(expirations[idx].expiration_date);
  }

  const { data: condors, isLoading } = useQuery({
    queryKey: ['iron-condors', expPut, expCall, params],
    queryFn: () =>
      getIronCondors({
        expiration_date_put: expPut,
        expiration_date_call: expCall,
        ...params,
      }),
    enabled: !!expPut && !!expCall,
  });

  const columns = [
    { key: 'symbol', label: 'Symbol' },
    { key: 'close', label: 'Price', format: formatCurrency },
    { key: 'max_profit', label: 'Max Profit', format: formatCurrency },
    { key: 'bpr', label: 'BPR', format: formatCurrency },
    { key: 'expected_value', label: 'EV', format: formatCurrency },
    { key: 'APDI', label: 'APDI%', format: (v: number) => formatPercent(v) },
    { key: 'iv_rank', label: 'IV Rank', format: (v: number) => formatNumber(v, 1) },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Iron Condors</h1>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">Put Expiration</label>
              <select
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
                value={expPut}
                onChange={(e) => setExpPut(e.target.value)}
              >
                {(expirations || []).map((exp: any) => (
                  <option key={exp.expiration_date} value={exp.expiration_date}>
                    {exp.days_to_expiration} DTE - {exp.expiration_date}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Call Expiration</label>
              <select
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
                value={expCall}
                onChange={(e) => setExpCall(e.target.value)}
              >
                {(expirations || []).map((exp: any) => (
                  <option key={exp.expiration_date} value={exp.expiration_date}>
                    {exp.days_to_expiration} DTE - {exp.expiration_date}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Put Delta</label>
              <Input type="number" step="0.01" value={params.delta_put} onChange={(e) => setParams({ ...params, delta_put: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Call Delta</label>
              <Input type="number" step="0.01" value={params.delta_call} onChange={(e) => setParams({ ...params, delta_call: +e.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
            <div>
              <label className="text-xs text-muted-foreground">Put Width</label>
              <Input type="number" value={params.width_put} onChange={(e) => setParams({ ...params, width_put: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Call Width</label>
              <Input type="number" value={params.width_call} onChange={(e) => setParams({ ...params, width_call: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Min OI</label>
              <Input type="number" value={params.min_open_interest} onChange={(e) => setParams({ ...params, min_open_interest: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Min IV Rank</label>
              <Input type="number" value={params.min_iv_rank} onChange={(e) => setParams({ ...params, min_iv_rank: +e.target.value })} />
            </div>
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <LoadingState message="Calculating Iron Condors..." />
      ) : (
        <>
          <p className="text-sm text-muted-foreground">{condors?.length || 0} Results</p>
          <DataTable
            data={condors || []}
            columns={columns}
            selectedIndex={selectedIndex}
            onRowClick={(row, i) => { setSelectedRow(row); setSelectedIndex(i); }}
          />
        </>
      )}

      {selectedRow && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{selectedRow.symbol} Iron Condor</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div><p className="text-xs text-muted-foreground">Max Profit</p><p className="text-lg font-semibold">{formatCurrency(selectedRow.max_profit)}</p></div>
              <div><p className="text-xs text-muted-foreground">BPR</p><p className="text-lg font-semibold">{formatCurrency(selectedRow.bpr)}</p></div>
              <div><p className="text-xs text-muted-foreground">Expected Value</p><p className="text-lg font-semibold">{formatCurrency(selectedRow.expected_value)}</p></div>
              <div><p className="text-xs text-muted-foreground">IV Rank</p><p className="text-lg font-semibold">{formatNumber(selectedRow.iv_rank, 1)}</p></div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
