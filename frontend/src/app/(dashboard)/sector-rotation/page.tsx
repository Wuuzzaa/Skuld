'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getSectorRotation } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatNumber } from '@/lib/utils';
import { Filter } from 'lucide-react';

// Spec colors
const QUADRANT_BG = {
  Leading: 'rgba(21, 101, 192, 0.08)',    // blue
  Weakening: 'rgba(245, 127, 23, 0.08)',   // orange
  Lagging: 'rgba(191, 54, 12, 0.08)',      // red
  Improving: 'rgba(46, 125, 50, 0.08)',    // green
};

const VOLATILITY_COLORS: Record<string, string> = {
  Gruen: '#2e8b57',
  Orange: '#f39c12',
  Rot: '#c0392b',
  Unbekannt: '#7f8c8d',
};

const QUADRANT_COLORS: Record<string, string> = {
  Leading: '#1565C0',
  Weakening: '#F57F17',
  Lagging: '#BF360C',
  Improving: '#2E7D32',
};

const MPS_COLORS: Record<string, string> = {
  strong: '#2e8b57',
  moderate: '#f39c12',
  weak: '#c0392b',
};

interface RotationPoint {
  date: string;
  symbol: string;
  sector_name: string;
  etf_name?: string;
  isin?: string;
  rs_ratio: number;
  rs_momentum: number;
  historical_volatility: number;
  volatility_signal: string;
  quadrant: string;
  volatility_pct?: number;
  rrg_score?: number;
  mps_score?: number;
  mps_signal?: string;
  sma200_signal?: string;
  above_sma200?: boolean;
  investment_amount?: number;
}

export default function SectorRotationPage() {
  const [params, setParams] = useState({
    short_window: 5,
    long_window: 15,
    volatility_window: 20,
    lookback_days: 120,
    tail_days: 6,
    rs_weight: 0.60,
    momentum_weight: 0.40,
    mps_long_months: 8,
    mps_short_months: 6,
    allocated_capital: 0,
  });
  const [showFilters, setShowFilters] = useState(false);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['sector-rotation', params],
    queryFn: () => getSectorRotation(params),
  });

  const snapshot: RotationPoint[] = data?.snapshot || [];
  const timeseries: RotationPoint[] = data?.timeseries || [];

  // Group timeseries by symbol, take last N (tail_days) entries
  const trailsBySymbol = useMemo(() => {
    const grouped: Record<string, RotationPoint[]> = {};
    for (const point of timeseries) {
      if (!grouped[point.symbol]) grouped[point.symbol] = [];
      grouped[point.symbol].push(point);
    }
    // Sort by date and take tail
    for (const sym of Object.keys(grouped)) {
      grouped[sym].sort((a, b) => a.date.localeCompare(b.date));
      grouped[sym] = grouped[sym].slice(-params.tail_days);
    }
    return grouped;
  }, [timeseries, params.tail_days]);

  // Compute chart bounds
  const chartBounds = useMemo(() => {
    if (snapshot.length === 0) return { xMin: 94, xMax: 106, yMin: 94, yMax: 106 };
    const allPoints = Object.values(trailsBySymbol).flat();
    const xVals = allPoints.map(p => p.rs_ratio);
    const yVals = allPoints.map(p => p.rs_momentum);
    const xMin = Math.min(94, Math.min(...xVals) - 0.5);
    const xMax = Math.max(106, Math.max(...xVals) + 0.5);
    const yMin = Math.min(94, Math.min(...yVals) - 0.5);
    const yMax = Math.max(106, Math.max(...yVals) + 0.5);
    return { xMin, xMax, yMin, yMax };
  }, [snapshot, trailsBySymbol]);

  // SVG coordinate helpers
  const SVG_W = 800;
  const SVG_H = 600;
  const MARGIN = { top: 30, right: 30, bottom: 40, left: 50 };
  const plotW = SVG_W - MARGIN.left - MARGIN.right;
  const plotH = SVG_H - MARGIN.top - MARGIN.bottom;

  const scaleX = (val: number) => MARGIN.left + ((val - chartBounds.xMin) / (chartBounds.xMax - chartBounds.xMin)) * plotW;
  const scaleY = (val: number) => MARGIN.top + plotH - ((val - chartBounds.yMin) / (chartBounds.yMax - chartBounds.yMin)) * plotH;

  // Axis ticks
  const xTicks = useMemo(() => {
    const ticks = [];
    const step = (chartBounds.xMax - chartBounds.xMin) > 8 ? 2 : 1;
    for (let v = Math.ceil(chartBounds.xMin); v <= Math.floor(chartBounds.xMax); v += step) ticks.push(v);
    return ticks;
  }, [chartBounds]);
  const yTicks = useMemo(() => {
    const ticks = [];
    const step = (chartBounds.yMax - chartBounds.yMin) > 8 ? 2 : 1;
    for (let v = Math.ceil(chartBounds.yMin); v <= Math.floor(chartBounds.yMax); v += step) ticks.push(v);
    return ticks;
  }, [chartBounds]);

  const columns: Column[] = [
    {
      key: 'symbol',
      label: 'Ticker',
      sortable: true,
      format: (v: string) => <span className="font-semibold text-foreground">{v}</span>,
    },
    { key: 'sector_name', label: 'Sektor', sortable: true },
    { key: 'etf_name', label: 'ETF Name', sortable: true,
      format: (v: string) => <span className="text-xs text-muted-foreground truncate max-w-[180px] inline-block" title={v}>{v}</span>,
    },
    { key: 'rs_ratio', label: 'Rel. Stärke', format: (v: number) => formatNumber(v), sortable: true, align: 'right' },
    { key: 'rs_momentum', label: 'Momentum', format: (v: number) => formatNumber(v), sortable: true, align: 'right' },
    {
      key: 'rrg_score',
      label: 'RRG Score',
      sortable: true,
      align: 'right',
      format: (v: number) => v != null ? <span className="font-semibold">{v.toFixed(2)}</span> : '—',
    },
    {
      key: 'mps_signal',
      label: 'Persistenz',
      sortable: true,
      format: (v: string, row: any) => {
        const color = MPS_COLORS[v] || '#999';
        const label = v === 'strong' ? 'Stark' : v === 'moderate' ? 'Moderat' : 'Schwach';
        const months = row?.mps_score != null ? ` (${Math.abs(row.mps_score).toFixed(0)}M)` : '';
        return (
          <span className="inline-flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
            <span className="text-xs" style={{ color }}>{label}{months}</span>
          </span>
        );
      },
    },
    {
      key: 'sma200_signal',
      label: '200T',
      sortable: true,
      format: (v: string) => {
        const isAbove = v === 'Gruen';
        return (
          <span className="inline-flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: isAbove ? '#2e8b57' : '#c0392b' }} />
            <span className="text-xs" style={{ color: isAbove ? '#2e8b57' : '#c0392b' }}>
              {isAbove ? 'Über' : 'Unter'}
            </span>
          </span>
        );
      },
    },
    {
      key: 'quadrant',
      label: 'Quadrant',
      sortable: true,
      format: (v: string) => (
        <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-medium`}
          style={{ background: `${QUADRANT_COLORS[v] || '#666'}22`, color: QUADRANT_COLORS[v] || '#999' }}>
          {v}
        </span>
      ),
    },
    {
      key: 'volatility_signal',
      label: 'HV Signal',
      sortable: true,
      format: (v: string) => (
        <span className="text-xs font-medium" style={{ color: VOLATILITY_COLORS[v] || '#999' }}>
          {v === 'Gruen' ? 'Low' : v === 'Orange' ? 'Medium' : v === 'Rot' ? 'High' : v}
        </span>
      ),
    },
    {
      key: 'volatility_pct',
      label: 'HV %',
      sortable: true,
      align: 'right',
      format: (v: number) => v != null ? `${v.toFixed(1)}%` : '—',
    },
    {
      key: 'investment_amount',
      label: 'Invest. (€)',
      sortable: true,
      align: 'right',
      format: (v: number) => v > 0 ? `€${v.toLocaleString('de-DE', { maximumFractionDigits: 0 })}` : '—',
    },
  ];

  const [hoveredSymbol, setHoveredSymbol] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Sektorrotation (RRG)</h1>
          {isFetching && <div className="w-2 h-2 rounded-full bg-pink-400 animate-pulse" />}
          <span className="text-xs text-muted-foreground bg-secondary/60 px-2 py-0.5 rounded-full">Benchmark: SPY</span>
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer ${
            showFilters ? 'bg-primary/20 text-primary border border-primary/30' : 'bg-secondary/60 text-muted-foreground border border-border/50 hover:text-foreground'
          }`}
        >
          <Filter className="w-3 h-3" /> Parameter
        </button>
      </div>

      {/* Parameters */}
      {showFilters && (
        <Card className="border-pink-500/20">
          <CardContent className="pt-4 space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Short WMA (P1)</label>
                <Input type="number" value={params.short_window} onChange={(e) => setParams({ ...params, short_window: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Long WMA (P2)</label>
                <Input type="number" value={params.long_window} onChange={(e) => setParams({ ...params, long_window: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">HV Window</label>
                <Input type="number" value={params.volatility_window} onChange={(e) => setParams({ ...params, volatility_window: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Lookback (days)</label>
                <Input type="number" value={params.lookback_days} onChange={(e) => setParams({ ...params, lookback_days: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Tail Days</label>
                <Input type="number" value={params.tail_days} onChange={(e) => setParams({ ...params, tail_days: +e.target.value })} className="h-8 mt-1" />
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">RS Gewicht (%)</label>
                <Input type="number" step="0.05" min="0" max="1" value={params.rs_weight} onChange={(e) => setParams({ ...params, rs_weight: +e.target.value, momentum_weight: +(1 - +e.target.value).toFixed(2) })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Mom. Gewicht (%)</label>
                <Input type="number" step="0.05" min="0" max="1" value={params.momentum_weight} onChange={(e) => setParams({ ...params, momentum_weight: +e.target.value, rs_weight: +(1 - +e.target.value).toFixed(2) })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">MPS Lang (Mon.)</label>
                <Input type="number" value={params.mps_long_months} onChange={(e) => setParams({ ...params, mps_long_months: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">MPS Kurz (Mon.)</label>
                <Input type="number" value={params.mps_short_months} onChange={(e) => setParams({ ...params, mps_short_months: +e.target.value })} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Kapital (€)</label>
                <Input type="number" value={params.allocated_capital} onChange={(e) => setParams({ ...params, allocated_capital: +e.target.value })} className="h-8 mt-1" placeholder="0 = aus" />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {isLoading ? (
        <LoadingState message="Berechne Sektorrotation..." />
      ) : (
        <>
          {/* Quadrant Legend */}
          <div className="flex flex-wrap gap-4">
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="font-medium text-foreground/70">Quadranten:</span>
              {Object.entries(QUADRANT_COLORS).map(([q, c]) => (
                <span key={q} className="inline-flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm" style={{ background: c }} />
                  {q}
                </span>
              ))}
            </div>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="font-medium text-foreground/70">Volatilität:</span>
              <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: VOLATILITY_COLORS.Gruen }} />Low</span>
              <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: VOLATILITY_COLORS.Orange }} />Medium</span>
              <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: VOLATILITY_COLORS.Rot }} />High</span>
            </div>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="font-medium text-foreground/70">Persistenz:</span>
              <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: MPS_COLORS.strong }} />Stark ({params.mps_long_months}M+)</span>
              <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: MPS_COLORS.moderate }} />Moderat ({params.mps_short_months}M+)</span>
              <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: MPS_COLORS.weak }} />Schwach</span>
            </div>
          </div>

          {/* RRG Chart - Custom SVG */}
          {snapshot.length > 0 && (
            <Card className="border-border/40">
              <CardContent className="pt-4">
                <svg
                  viewBox={`0 0 ${SVG_W} ${SVG_H}`}
                  className="w-full"
                  style={{ maxHeight: '650px' }}
                >
                  {/* Quadrant backgrounds */}
                  {/* Leading: top-right (x>100, y>100) */}
                  <rect
                    x={scaleX(100)} y={scaleY(chartBounds.yMax)}
                    width={scaleX(chartBounds.xMax) - scaleX(100)}
                    height={scaleY(100) - scaleY(chartBounds.yMax)}
                    fill={QUADRANT_BG.Leading}
                  />
                  {/* Weakening: bottom-right (x>100, y<100) */}
                  <rect
                    x={scaleX(100)} y={scaleY(100)}
                    width={scaleX(chartBounds.xMax) - scaleX(100)}
                    height={scaleY(chartBounds.yMin) - scaleY(100)}
                    fill={QUADRANT_BG.Weakening}
                  />
                  {/* Lagging: bottom-left (x<100, y<100) */}
                  <rect
                    x={scaleX(chartBounds.xMin)} y={scaleY(100)}
                    width={scaleX(100) - scaleX(chartBounds.xMin)}
                    height={scaleY(chartBounds.yMin) - scaleY(100)}
                    fill={QUADRANT_BG.Lagging}
                  />
                  {/* Improving: top-left (x<100, y>100) */}
                  <rect
                    x={scaleX(chartBounds.xMin)} y={scaleY(chartBounds.yMax)}
                    width={scaleX(100) - scaleX(chartBounds.xMin)}
                    height={scaleY(100) - scaleY(chartBounds.yMax)}
                    fill={QUADRANT_BG.Improving}
                  />

                  {/* Grid lines */}
                  {xTicks.map(v => (
                    <line key={`gx-${v}`} x1={scaleX(v)} y1={MARGIN.top} x2={scaleX(v)} y2={MARGIN.top + plotH}
                      stroke="hsl(217 33% 17%)" strokeWidth={v === 100 ? 1.5 : 0.5} strokeDasharray={v === 100 ? "6 3" : "2 4"} />
                  ))}
                  {yTicks.map(v => (
                    <line key={`gy-${v}`} x1={MARGIN.left} y1={scaleY(v)} x2={MARGIN.left + plotW} y2={scaleY(v)}
                      stroke="hsl(217 33% 17%)" strokeWidth={v === 100 ? 1.5 : 0.5} strokeDasharray={v === 100 ? "6 3" : "2 4"} />
                  ))}

                  {/* Quadrant labels */}
                  <text x={scaleX(chartBounds.xMax) - 10} y={scaleY(chartBounds.yMax) + 18} textAnchor="end" fill="#1565C0" fontSize="12" fontWeight="600" opacity={0.7}>Leading</text>
                  <text x={scaleX(chartBounds.xMax) - 10} y={scaleY(chartBounds.yMin) - 8} textAnchor="end" fill="#F57F17" fontSize="12" fontWeight="600" opacity={0.7}>Weakening</text>
                  <text x={scaleX(chartBounds.xMin) + 10} y={scaleY(chartBounds.yMin) - 8} textAnchor="start" fill="#BF360C" fontSize="12" fontWeight="600" opacity={0.7}>Lagging</text>
                  <text x={scaleX(chartBounds.xMin) + 10} y={scaleY(chartBounds.yMax) + 18} textAnchor="start" fill="#2E7D32" fontSize="12" fontWeight="600" opacity={0.7}>Improving</text>

                  {/* Axis labels */}
                  {xTicks.map(v => (
                    <text key={`xl-${v}`} x={scaleX(v)} y={SVG_H - 8} textAnchor="middle" fill="hsl(215 20% 55%)" fontSize="10">{v}</text>
                  ))}
                  {yTicks.map(v => (
                    <text key={`yl-${v}`} x={MARGIN.left - 8} y={scaleY(v) + 3} textAnchor="end" fill="hsl(215 20% 55%)" fontSize="10">{v}</text>
                  ))}
                  <text x={SVG_W / 2} y={SVG_H - 0} textAnchor="middle" fill="hsl(215 20% 55%)" fontSize="11">JdK RS-Ratio</text>
                  <text x={12} y={SVG_H / 2} textAnchor="middle" fill="hsl(215 20% 55%)" fontSize="11" transform={`rotate(-90 12 ${SVG_H / 2})`}>JdK RS-Momentum</text>

                  {/* Trail lines + dots */}
                  {snapshot.map((s) => {
                    const trail = trailsBySymbol[s.symbol] || [];
                    const volColor = VOLATILITY_COLORS[s.volatility_signal] || VOLATILITY_COLORS.Unbekannt;
                    const isHovered = hoveredSymbol === s.symbol;
                    const opacity = hoveredSymbol ? (isHovered ? 1 : 0.25) : 1;

                    // Build polyline path
                    const pathPoints = trail.map(p => `${scaleX(p.rs_ratio)},${scaleY(p.rs_momentum)}`).join(' ');

                    return (
                      <g key={s.symbol} opacity={opacity}
                        onMouseEnter={() => setHoveredSymbol(s.symbol)}
                        onMouseLeave={() => setHoveredSymbol(null)}
                        style={{ cursor: 'pointer' }}
                      >
                        {/* Trail line */}
                        {trail.length > 1 && (
                          <polyline
                            points={pathPoints}
                            fill="none"
                            stroke={volColor}
                            strokeWidth={isHovered ? 2.5 : 1.5}
                            strokeLinejoin="round"
                            opacity={0.6}
                          />
                        )}
                        {/* Trail dots (small) */}
                        {trail.slice(0, -1).map((p, i) => (
                          <circle
                            key={i}
                            cx={scaleX(p.rs_ratio)}
                            cy={scaleY(p.rs_momentum)}
                            r={isHovered ? 3 : 2}
                            fill={volColor}
                            opacity={0.4}
                          />
                        ))}
                        {/* Latest dot (large) */}
                        <circle
                          cx={scaleX(s.rs_ratio)}
                          cy={scaleY(s.rs_momentum)}
                          r={isHovered ? 12 : 9}
                          fill={volColor}
                          stroke="#fff"
                          strokeWidth={1.5}
                          opacity={0.85}
                        />
                        {/* Symbol label */}
                        <text
                          x={scaleX(s.rs_ratio)}
                          y={scaleY(s.rs_momentum) - (isHovered ? 16 : 13)}
                          textAnchor="middle"
                          fill="hsl(215 20% 85%)"
                          fontSize={isHovered ? 12 : 10}
                          fontWeight={isHovered ? 700 : 500}
                        >
                          {s.symbol}
                        </text>
                        {/* Tooltip on hover */}
                        {isHovered && (
                          <title>{`${s.symbol} (${s.sector_name})\nRRG Score: ${s.rrg_score?.toFixed(2)}\nRS-Ratio: ${s.rs_ratio?.toFixed(2)}\nRS-Momentum: ${s.rs_momentum?.toFixed(2)}\nHV: ${(s.volatility_pct ?? s.historical_volatility * 100)?.toFixed(1)}%\nQuadrant: ${s.quadrant}\n200T: ${s.sma200_signal === 'Gruen' ? 'Über SMA200' : 'Unter SMA200'}\nPersistenz: ${s.mps_signal} (${Math.abs(s.mps_score || 0).toFixed(0)}M)`}</title>
                        )}
                      </g>
                    );
                  })}
                </svg>
              </CardContent>
            </Card>
          )}

          {/* Table - sorted by RRG Score */}
          <DataTable
            data={snapshot}
            columns={columns}
            defaultSort={{ key: 'rrg_score', direction: 'desc' }}
            striped
          />
        </>
      )}
    </div>
  );
}
