'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getSectorRotation } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatNumber } from '@/lib/utils';
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Label } from 'recharts';

export default function SectorRotationPage() {
  const [params, setParams] = useState({
    short_window: 5,
    long_window: 15,
    volatility_window: 20,
    lookback_days: 120,
    tail_days: 6,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['sector-rotation', params],
    queryFn: () => getSectorRotation(params),
  });

  const snapshot = data?.snapshot || [];

  const columns = [
    { key: 'symbol', label: 'Ticker' },
    { key: 'sector_name', label: 'Sector' },
    { key: 'rs_ratio', label: 'RS-Ratio', format: (v: number) => formatNumber(v) },
    { key: 'rs_momentum', label: 'RS-Momentum', format: (v: number) => formatNumber(v) },
    { key: 'quadrant', label: 'Quadrant' },
    { key: 'volatility_signal', label: 'Vol Signal' },
  ];

  const chartData = snapshot.map((s: any) => ({
    x: s.rs_ratio,
    y: s.rs_momentum,
    name: s.symbol,
    sector: s.sector_name,
    quadrant: s.quadrant,
  }));

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">S&P 500 Sector Rotation</h1>
      <p className="text-sm text-muted-foreground">Benchmark: SPY. Sectors via SPDR Sector ETFs.</p>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Parameters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">Short WMA</label>
              <Input type="number" value={params.short_window} onChange={(e) => setParams({ ...params, short_window: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Long WMA</label>
              <Input type="number" value={params.long_window} onChange={(e) => setParams({ ...params, long_window: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">HV Window</label>
              <Input type="number" value={params.volatility_window} onChange={(e) => setParams({ ...params, volatility_window: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Lookback Days</label>
              <Input type="number" value={params.lookback_days} onChange={(e) => setParams({ ...params, lookback_days: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Tail Days</label>
              <Input type="number" value={params.tail_days} onChange={(e) => setParams({ ...params, tail_days: +e.target.value })} />
            </div>
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <LoadingState message="Calculating sector rotation..." />
      ) : (
        <>
          {/* Scatter chart */}
          {chartData.length > 0 && (
            <Card>
              <CardContent className="pt-6">
                <ResponsiveContainer width="100%" height={500}>
                  <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(217 33% 17%)" />
                    <XAxis type="number" dataKey="x" name="RS-Ratio" domain={['auto', 'auto']}>
                      <Label value="RS-Ratio" position="bottom" style={{ fill: 'hsl(215 20% 55%)' }} />
                    </XAxis>
                    <YAxis type="number" dataKey="y" name="RS-Momentum" domain={['auto', 'auto']}>
                      <Label value="RS-Momentum" angle={-90} position="left" style={{ fill: 'hsl(215 20% 55%)' }} />
                    </YAxis>
                    <ReferenceLine x={100} stroke="hsl(215 20% 35%)" strokeDasharray="5 5" />
                    <ReferenceLine y={100} stroke="hsl(215 20% 35%)" strokeDasharray="5 5" />
                    <Tooltip
                      content={({ payload }) => {
                        if (!payload?.length) return null;
                        const d = payload[0].payload;
                        return (
                          <div className="bg-card border rounded p-2 text-xs">
                            <p className="font-semibold">{d.name} - {d.sector}</p>
                            <p>RS-Ratio: {d.x?.toFixed(2)}</p>
                            <p>RS-Momentum: {d.y?.toFixed(2)}</p>
                            <p>Quadrant: {d.quadrant}</p>
                          </div>
                        );
                      }}
                    />
                    <Scatter data={chartData} fill="hsl(217 91% 60%)" />
                  </ScatterChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          <DataTable data={snapshot} columns={columns} />
        </>
      )}
    </div>
  );
}
