'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { LoadingState } from '@/components/ui/spinner';
import { Filter, Download, TrendingUp, TrendingDown, Minus, Info, AlertTriangle } from 'lucide-react';
import { formatNumber } from '@/lib/utils';

// API functions
async function getCorrelationSymbols() {
  const { data } = await api.get('/correlation/symbols');
  return data as string[];
}

async function getCorrelationMatrix(params: { symbols: string; lookback_days: number; method: string }) {
  const { data } = await api.get('/correlation/', { params });
  return data as {
    matrix: { x: string; y: string; value: number }[];
    symbols: string[];
    stats: {
      avg_correlation: number;
      max_correlation: number;
      min_correlation: number;
      num_symbols: number;
      num_data_points: number;
      date_from: string;
      date_to: string;
    };
    top_correlated: { pair: string; correlation: number }[];
    least_correlated: { pair: string; correlation: number }[];
  };
}

// Color scale: red (-1) -> white (0) -> blue (+1)
function getCorrelationColor(value: number): string {
  if (value >= 0) {
    const intensity = Math.min(value, 1);
    const r = Math.round(255 - intensity * 200);
    const g = Math.round(255 - intensity * 180);
    const b = 255;
    return `rgb(${r}, ${g}, ${b})`;
  } else {
    const intensity = Math.min(Math.abs(value), 1);
    const r = 255;
    const g = Math.round(255 - intensity * 180);
    const b = Math.round(255 - intensity * 200);
    return `rgb(${r}, ${g}, ${b})`;
  }
}

function getTextColor(value: number): string {
  return Math.abs(value) > 0.6 ? 'white' : 'inherit';
}

export default function CorrelationPage() {
  const [symbolInput, setSymbolInput] = useState('AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, JPM, GLD, TLT');
  const [lookbackDays, setLookbackDays] = useState(252);
  const [method, setMethod] = useState<'pearson' | 'spearman' | 'kendall'>('pearson');
  const [showFilters, setShowFilters] = useState(false);
  const [showExplain, setShowExplain] = useState(false);

  const symbols = useMemo(() => symbolInput.trim(), [symbolInput]);

  const { data: availableSymbols } = useQuery({
    queryKey: ['correlation-symbols'],
    queryFn: getCorrelationSymbols,
    staleTime: 60 * 60 * 1000, // 1 hour
  });

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['correlation-matrix', symbols, lookbackDays, method],
    queryFn: () => getCorrelationMatrix({ symbols, lookback_days: lookbackDays, method }),
    enabled: symbols.split(',').filter(s => s.trim()).length >= 2,
  });

  const matrixGrid = useMemo(() => {
    if (!data?.matrix || !data?.symbols) return null;
    const syms = data.symbols;
    const grid: number[][] = Array.from({ length: syms.length }, () => Array(syms.length).fill(0));
    for (const entry of data.matrix) {
      const i = syms.indexOf(entry.x);
      const j = syms.indexOf(entry.y);
      if (i >= 0 && j >= 0) grid[i][j] = entry.value;
    }
    return grid;
  }, [data]);

  const exportCSV = () => {
    if (!data?.symbols || !matrixGrid) return;
    const syms = data.symbols;
    let csv = ',' + syms.join(',') + '\n';
    for (let i = 0; i < syms.length; i++) {
      csv += syms[i] + ',' + matrixGrid[i].map(v => v.toFixed(4)).join(',') + '\n';
    }
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `correlation_matrix_${method}_${lookbackDays}d.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const presetGroups = [
    { label: 'FAANG+', symbols: 'AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA' },
    { label: 'Sectors', symbols: 'XLK, XLF, XLE, XLV, XLI, XLP, XLU, XLRE, XLB, XLC, XLY' },
    { label: 'Asset Classes', symbols: 'SPY, QQQ, IWM, GLD, TLT, HYG, UUP, USO, VNQ' },
    { label: 'Mega Caps', symbols: 'AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, BRK-B, JPM, V' },
    { label: 'S&P 500 Top 30', symbols: 'AAPL, MSFT, NVDA, AMZN, GOOGL, META, BRK-B, AVGO, JPM, LLY, TSLA, V, UNH, XOM, MA, COST, HD, PG, JNJ, NFLX, ABBV, BAC, CRM, CVX, MRK, KO, WMT, PEP, AMD, TMO' },
    { label: 'All Available', symbols: '', isSpecial: true },
  ];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Correlation Matrix</h1>
          {isFetching && <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />}
          {data?.stats && (
            <span className="text-xs text-muted-foreground bg-secondary/60 px-2 py-0.5 rounded-full">
              {data.stats.num_symbols} symbols · {data.stats.num_data_points} days
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={exportCSV}
            disabled={!data?.matrix?.length}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-secondary/60 text-muted-foreground border border-border/50 hover:text-foreground transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Download className="w-3 h-3" /> CSV
          </button>
          <button
            onClick={() => setShowExplain(!showExplain)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer ${
              showExplain ? 'bg-violet-500/20 text-violet-400 border border-violet-500/30' : 'bg-secondary/60 text-muted-foreground border border-border/50 hover:text-foreground'
            }`}
          >
            <Info className="w-3 h-3" /> Explain
          </button>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer ${
              showFilters ? 'bg-primary/20 text-primary border border-primary/30' : 'bg-secondary/60 text-muted-foreground border border-border/50 hover:text-foreground'
            }`}
          >
            <Filter className="w-3 h-3" /> Parameters
          </button>
        </div>
      </div>

      {/* Symbol Input */}
      <Card className="border-border/40">
        <CardContent className="pt-4 space-y-3">
          <div>
            <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Symbols (comma-separated)</label>
            <Input
              value={symbolInput}
              onChange={(e) => setSymbolInput(e.target.value)}
              placeholder="AAPL, MSFT, GOOGL, ..."
              className="h-9 mt-1 font-mono text-sm"
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {presetGroups.map((group) => (
              <button
                key={group.label}
                onClick={() => {
                  if ((group as any).isSpecial && availableSymbols) {
                    setSymbolInput(availableSymbols.join(', '));
                  } else {
                    setSymbolInput(group.symbols);
                  }
                }}
                className="px-2.5 py-1 rounded-full text-[11px] font-medium bg-secondary/60 text-muted-foreground hover:text-foreground hover:bg-secondary transition-all cursor-pointer border border-border/30"
              >
                {group.label}{(group as any).isSpecial && availableSymbols ? ` (${availableSymbols.length})` : ''}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Explain Panel */}
      {showExplain && (
        <Card className="border-violet-500/20 bg-violet-500/5">
          <CardContent className="pt-4 space-y-4">
            <h3 className="text-sm font-semibold flex items-center gap-1.5">
              <Info className="w-4 h-4 text-violet-400" /> How the Correlation Matrix Works
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs text-muted-foreground">
              <div className="space-y-2">
                <h4 className="font-medium text-foreground">Calculation Basis</h4>
                <ul className="space-y-1.5 list-none">
                  <li className="flex gap-2">
                    <span className="text-violet-400 font-bold">1.</span>
                    <span>Historical <span className="font-medium text-foreground">daily closing prices</span> are fetched from our Yahoo Finance database</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="text-violet-400 font-bold">2.</span>
                    <span><span className="font-medium text-foreground">Daily returns</span> are calculated as percentage change: (Close[t] - Close[t-1]) / Close[t-1]</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="text-violet-400 font-bold">3.</span>
                    <span>The <span className="font-medium text-foreground">correlation coefficient</span> measures how returns move together (-1 to +1)</span>
                  </li>
                </ul>
              </div>

              <div className="space-y-2">
                <h4 className="font-medium text-foreground">Methods Explained</h4>
                <ul className="space-y-1.5 list-none">
                  <li className="flex gap-2">
                    <span className="w-16 font-mono font-medium text-blue-400 flex-shrink-0">Pearson</span>
                    <span>Linear relationship between returns. Most common. Sensitive to outliers.</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="w-16 font-mono font-medium text-emerald-400 flex-shrink-0">Spearman</span>
                    <span>Rank-based. Captures monotonic (not just linear) relationships. More robust to outliers.</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="w-16 font-mono font-medium text-amber-400 flex-shrink-0">Kendall</span>
                    <span>Concordance of pairs. Best for small samples or non-normal data. Most conservative.</span>
                  </li>
                </ul>
              </div>
            </div>

            <div className="space-y-2 text-xs text-muted-foreground">
              <h4 className="font-medium text-foreground">Interpretation</h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                <div className="flex items-center gap-2 bg-background/50 rounded-md px-3 py-2">
                  <div className="w-4 h-4 rounded-sm" style={{ backgroundColor: getCorrelationColor(0.85) }} />
                  <span><span className="font-medium text-foreground">+0.7 to +1.0</span> — Move together (high risk if both in portfolio)</span>
                </div>
                <div className="flex items-center gap-2 bg-background/50 rounded-md px-3 py-2">
                  <div className="w-4 h-4 rounded-sm" style={{ backgroundColor: getCorrelationColor(0.0) }} />
                  <span><span className="font-medium text-foreground">-0.3 to +0.3</span> — Uncorrelated (good diversification)</span>
                </div>
                <div className="flex items-center gap-2 bg-background/50 rounded-md px-3 py-2">
                  <div className="w-4 h-4 rounded-sm" style={{ backgroundColor: getCorrelationColor(-0.7) }} />
                  <span><span className="font-medium text-foreground">-0.7 to -1.0</span> — Move opposite (natural hedge)</span>
                </div>
              </div>
            </div>

            <div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/20 rounded-md px-3 py-2 text-xs">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="text-muted-foreground">
                <span className="font-medium text-foreground">Note:</span> Correlation is not constant — it changes over time and tends to increase during market crashes.
                Symbols with &lt;80% data coverage in the selected period are automatically excluded.
                Only trading days are counted (weekends/holidays excluded).
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Data Basis Info (always visible when data loaded) */}
      {data?.stats && !isLoading && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground bg-secondary/30 rounded-lg px-3 py-2">
          <span>Basis: <span className="font-medium text-foreground">Daily Close-to-Close Returns</span></span>
          <span className="text-border">|</span>
          <span>Period: <span className="font-mono text-foreground">{data.stats.date_from?.slice(0, 10)}</span> to <span className="font-mono text-foreground">{data.stats.date_to?.slice(0, 10)}</span></span>
          <span className="text-border">|</span>
          <span>Data Points: <span className="font-mono text-foreground">{data.stats.num_data_points}</span> trading days</span>
          <span className="text-border">|</span>
          <span>Method: <span className="font-medium text-foreground">{method.charAt(0).toUpperCase() + method.slice(1)}</span></span>
          <span className="text-border">|</span>
          <span>Source: <span className="text-foreground">Yahoo Finance (adj. close)</span></span>
        </div>
      )}

      {/* Parameters */}
      {showFilters && (
        <Card className="border-blue-500/20">
          <CardContent className="pt-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Lookback (Days)</label>
                <select
                  value={lookbackDays}
                  onChange={(e) => setLookbackDays(+e.target.value)}
                  className="w-full h-8 mt-1 rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value={63}>3 Months (63d)</option>
                  <option value={126}>6 Months (126d)</option>
                  <option value={252}>1 Year (252d)</option>
                  <option value={504}>2 Years (504d)</option>
                  <option value={756}>3 Years (756d)</option>
                </select>
              </div>
              <div>
                <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Method</label>
                <select
                  value={method}
                  onChange={(e) => setMethod(e.target.value as any)}
                  className="w-full h-8 mt-1 rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="pearson">Pearson</option>
                  <option value="spearman">Spearman</option>
                  <option value="kendall">Kendall</option>
                </select>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {isLoading ? (
        <LoadingState message="Calculating correlations..." />
      ) : data?.symbols && matrixGrid ? (
        <>
          {/* Stats Cards */}
          <div className="grid grid-cols-3 gap-3">
            <Card className="border-border/40">
              <CardContent className="pt-3 pb-3">
                <p className="text-[11px] text-muted-foreground uppercase tracking-wider">Avg Correlation</p>
                <p className="text-xl font-bold font-mono mt-0.5">{data.stats.avg_correlation.toFixed(3)}</p>
              </CardContent>
            </Card>
            <Card className="border-border/40">
              <CardContent className="pt-3 pb-3">
                <p className="text-[11px] text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                  <TrendingUp className="w-3 h-3 text-blue-400" /> Highest
                </p>
                <p className="text-xl font-bold font-mono mt-0.5 text-blue-400">{data.stats.max_correlation.toFixed(3)}</p>
              </CardContent>
            </Card>
            <Card className="border-border/40">
              <CardContent className="pt-3 pb-3">
                <p className="text-[11px] text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                  <TrendingDown className="w-3 h-3 text-red-400" /> Lowest
                </p>
                <p className="text-xl font-bold font-mono mt-0.5 text-red-400">{data.stats.min_correlation.toFixed(3)}</p>
              </CardContent>
            </Card>
          </div>

          {/* Heatmap */}
          <Card className="border-border/40">
            <CardContent className="pt-4 overflow-x-auto">
              <div className="min-w-fit">
                <table className="border-collapse">
                  <thead>
                    <tr>
                      <th className="p-1 text-[10px] text-muted-foreground w-16"></th>
                      {data.symbols.map((sym) => (
                        <th key={sym} className="p-1 text-[10px] font-medium text-muted-foreground text-center" style={{ minWidth: '52px', writingMode: data.symbols.length > 12 ? 'vertical-rl' : undefined }}>
                          {sym}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.symbols.map((sym, i) => (
                      <tr key={sym}>
                        <td className="p-1 text-[10px] font-medium text-muted-foreground text-right pr-2">{sym}</td>
                        {data.symbols.map((_, j) => {
                          const val = matrixGrid[i][j];
                          return (
                            <td
                              key={j}
                              className="p-0 text-center border border-background/20"
                              style={{
                                backgroundColor: getCorrelationColor(val),
                                color: getTextColor(val),
                                minWidth: '52px',
                                height: '36px',
                              }}
                              title={`${data.symbols[i]} / ${data.symbols[j]}: ${val.toFixed(4)}`}
                            >
                              <span className="text-[11px] font-mono font-medium">
                                {i === j ? '1.00' : val.toFixed(2)}
                              </span>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Color Legend */}
              <div className="flex items-center justify-center gap-2 mt-4 text-[10px] text-muted-foreground">
                <span>-1.0</span>
                <div className="flex h-3 w-48 rounded-sm overflow-hidden">
                  {Array.from({ length: 20 }, (_, i) => {
                    const val = -1 + (i / 19) * 2;
                    return <div key={i} className="flex-1" style={{ backgroundColor: getCorrelationColor(val) }} />;
                  })}
                </div>
                <span>+1.0</span>
              </div>
            </CardContent>
          </Card>

          {/* Top / Bottom Pairs */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Most Correlated */}
            <Card className="border-border/40">
              <CardContent className="pt-3">
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-1.5">
                  <TrendingUp className="w-3.5 h-3.5 text-blue-400" /> Most Correlated
                </h3>
                <div className="space-y-1">
                  {data.top_correlated.map((pair, idx) => (
                    <div key={idx} className="flex items-center justify-between text-xs py-1 border-b border-border/20 last:border-0">
                      <span className="font-mono text-muted-foreground">{pair.pair}</span>
                      <span className="font-mono font-medium" style={{ color: getCorrelationColor(pair.correlation) }}>
                        {pair.correlation.toFixed(4)}
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Least Correlated */}
            <Card className="border-border/40">
              <CardContent className="pt-3">
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-1.5">
                  <Minus className="w-3.5 h-3.5 text-emerald-400" /> Least Correlated (Best Diversifiers)
                </h3>
                <div className="space-y-1">
                  {data.least_correlated.map((pair, idx) => (
                    <div key={idx} className="flex items-center justify-between text-xs py-1 border-b border-border/20 last:border-0">
                      <span className="font-mono text-muted-foreground">{pair.pair}</span>
                      <span className="font-mono font-medium" style={{ color: getCorrelationColor(pair.correlation) }}>
                        {pair.correlation.toFixed(4)}
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      ) : (
        <Card className="border-border/40">
          <CardContent className="pt-8 pb-8 text-center text-muted-foreground">
            <p className="text-sm">Enter at least 2 symbols to calculate the correlation matrix.</p>
            <p className="text-xs mt-1">Available: {availableSymbols?.length || '...'} symbols with historical data</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
