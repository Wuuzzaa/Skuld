'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getSectorRotation } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatNumber } from '@/lib/utils';
import { Filter } from 'lucide-react';
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Label } from 'recharts';

export default function SectorRotationPage() {
  const [params, setParams] = useState({
    short_window: 5,
    long_window: 15,
    volatility_window: 20,
    lookback_days: 120,
    tail_days: 6,
  });
  const [showFilters, setShowFilters] = useState(false);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['sector-rotation', params],
    queryFn: () => getSectorRotation(params),
  });

  const snapshot = data?.snapshot || [];

  const columns: Column[] = [
    {
      key: 'symbol',
      label: 'Ticker',
      sortable: true,
      format: (v: string) => <span className="font-semibold text-foreground">{v}</span>,
    },
    { key: 'sector_name', label: 'Sector', sortable: true },
    { key: 'rs_ratio', label: 'RS-Ratio', format: (v: number) => formatNumber(v), sortable: true, align: 'right' },
    { key: 'rs_momentum', label: 'RS-Mom.', format: (v: number) => formatNumber(v), sortable: true, align: 'right' },
    {
      key: 'quadrant',
      label: 'Quadrant',
      sortable: true,
      format: (v: string) => (
        <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-medium ${
          v === 'Leading' ? 'bg-emerald-500/20 text-emerald-400' :
          v === 'Weakening' ? 'bg-yellow-500/20 text-yellow-400' :
          v === 'Lagging' ? 'bg-red-500/20 text-red-400' :
          v === 'Improving' ? 'bg-blue-500/20 text-blue-400' :
          'bg-secondary text-muted-foreground'
        }`}>
          {v}
        </span>
      ),
    },
    {
      key: 'volatility_signal',
      label: 'Vol Signal',
      sortable: true,
      format: (v: string) => (
        <span className={`text-xs ${
          v === 'Low' ? 'text-emerald-400' : v === 'High' ? 'text-red-400' : 'text-muted-foreground'
        }`}>
          {v}
        </span>
      ),
    },
  ];

  const chartData = snapshot.map((s: any) => ({
    x: s.rs_ratio,
    y: s.rs_momentum,
    name: s.symbol,
    sector: s.sector_name,
    quadrant: s.quadrant,
  }));

  const getPointColor = (quadrant: string) => {
    switch (quadrant) {
      case 'Leading': return 'hsl(160 60% 50%)';
      case 'Weakening': return 'hsl(45 90% 55%)';
      case 'Lagging': return 'hsl(0 65% 55%)';
      case 'Improving': return 'hsl(217 91% 60%)';
      default: return 'hsl(215 20% 55%)';
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Sector Rotation</h1>
          {isFetching && <div className="w-2 h-2 rounded-full bg-pink-400 animate-pulse" />}
          <span className="text-xs text-muted-foreground bg-secondary/60 px-2 py-0.5 rounded-full">Benchmark: SPY</span>
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer ${
            showFilters ? 'bg-primary/20 text-primary border border-primary/30' : 'bg-secondary/60 text-muted-foreground border border-border/50 hover:text-foreground'
          }`}
        >
          <Filter className="w-3 h-3" /> Parameters
        </button>
      </div>

      {/* Parameters */}
      {showFilters && (
        <Card className="border-pink-500/20">
          <CardContent className="pt-4">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Short WMA</label>
                <Input type="number" value={params.short_window} onChange={(e) => setParams({ ...params, short_window: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Long WMA</label>
                <Input type="number" value={params.long_window} onChange={(e) => setParams({ ...params, long_window: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">HV Window</label>
                <Input type="number" value={params.volatility_window} onChange={(e) => setParams({ ...params, volatility_window: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Lookback</label>
                <Input type="number" value={params.lookback_days} onChange={(e) => setParams({ ...params, lookback_days: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Tail Days</label>
                <Input type="number" value={params.tail_days} onChange={(e) => setParams({ ...params, tail_days: +e.target.value })} className="h-8 mt-1" />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {isLoading ? (
        <LoadingState message="Calculating sector rotation..." />
      ) : (
        <>
          {/* Quadrant Legend */}
          <div className="flex flex-wrap gap-3">
            {['Leading', 'Weakening', 'Lagging', 'Improving'].map((q) => (
              <span key={q} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className={`w-2.5 h-2.5 rounded-full`} style={{ background: getPointColor(q) }} />
                {q}
              </span>
            ))}
          </div>

          {/* Scatter Chart */}
          {chartData.length > 0 && (
            <Card className="border-border/40">
              <CardContent className="pt-4">
                <ResponsiveContainer width="100%" height={450}>
                  <ScatterChart margin={{ top: 10, right: 20, bottom: 30, left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(217 33% 14%)" />
                    <XAxis type="number" dataKey="x" name="RS-Ratio" domain={['auto', 'auto']} tick={{ fill: 'hsl(215 20% 55%)', fontSize: 11 }}>
                      <Label value="RS-Ratio →" position="bottom" offset={10} style={{ fill: 'hsl(215 20% 55%)', fontSize: 11 }} />
                    </XAxis>
                    <YAxis type="number" dataKey="y" name="RS-Momentum" domain={['auto', 'auto']} tick={{ fill: 'hsl(215 20% 55%)', fontSize: 11 }}>
                      <Label value="RS-Momentum →" angle={-90} position="left" offset={5} style={{ fill: 'hsl(215 20% 55%)', fontSize: 11 }} />
                    </YAxis>
                    <ReferenceLine x={100} stroke="hsl(215 20% 30%)" strokeDasharray="5 5" />
                    <ReferenceLine y={100} stroke="hsl(215 20% 30%)" strokeDasharray="5 5" />
                    <Tooltip
                      content={({ payload }) => {
                        if (!payload?.length) return null;
                        const d = payload[0].payload;
                        return (
                          <div className="bg-card border border-border/50 rounded-lg p-2.5 text-xs shadow-lg">
                            <p className="font-bold text-foreground">{d.name}</p>
                            <p className="text-muted-foreground">{d.sector}</p>
                            <div className="mt-1.5 space-y-0.5">
                              <p>RS-Ratio: <span className="font-mono">{d.x?.toFixed(2)}</span></p>
                              <p>RS-Momentum: <span className="font-mono">{d.y?.toFixed(2)}</span></p>
                              <p>Quadrant: <span className="font-medium" style={{ color: getPointColor(d.quadrant) }}>{d.quadrant}</span></p>
                            </div>
                          </div>
                        );
                      }}
                    />
                    <Scatter
                      data={chartData}
                      shape={(props: any) => {
                        const { cx, cy, payload } = props;
                        return (
                          <circle
                            cx={cx}
                            cy={cy}
                            r={6}
                            fill={getPointColor(payload.quadrant)}
                            fillOpacity={0.8}
                            stroke={getPointColor(payload.quadrant)}
                            strokeWidth={1}
                          />
                        );
                      }}
                    />
                  </ScatterChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Table */}
          <DataTable
            data={snapshot}
            columns={columns}
            defaultSort={{ key: 'rs_ratio', direction: 'desc' }}
            striped
          />
        </>
      )}
    </div>
  );
}
