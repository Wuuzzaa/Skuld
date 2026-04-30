'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getExpirations, getSpreads } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatPercent, formatNumber } from '@/lib/utils';

export default function SpreadsPage() {
  const [params, setParams] = useState({
    option_type: 'put',
    delta_target: 0.2,
    spread_width: 5,
    strategy_type: 'credit',
    min_open_interest: 100,
    min_day_volume: 20,
    min_iv_rank: 0,
    min_iv_percentile: 0,
    min_sell_iv: 0.3,
    max_sell_iv: 0.9,
    min_max_profit: 80,
  });
  const [selectedExpiration, setSelectedExpiration] = useState('');
  const [selectedRow, setSelectedRow] = useState<any>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const { data: expirations, isLoading: loadingExp } = useQuery({
    queryKey: ['expirations'],
    queryFn: getExpirations,
  });

  const {
    data: spreads,
    isLoading: loadingSpreads,
    refetch,
  } = useQuery({
    queryKey: ['spreads', selectedExpiration, params],
    queryFn: () => getSpreads({ ...params, expiration_date: selectedExpiration }),
    enabled: !!selectedExpiration,
  });

  // Auto-select first expiration
  if (expirations?.length && !selectedExpiration) {
    const idx = Math.min(1, expirations.length - 1);
    setSelectedExpiration(expirations[idx].expiration_date);
  }

  // Apply client-side filters
  const filteredSpreads = (spreads || []).filter((row: any) => {
    if (row.max_profit < params.min_max_profit) return false;
    if (row.sell_iv < params.min_sell_iv) return false;
    if (row.sell_iv > params.max_sell_iv) return false;
    return true;
  });

  const columns = [
    { key: 'symbol', label: 'Symbol' },
    { key: 'close', label: 'Price', format: formatCurrency },
    { key: 'sell_strike', label: 'Sell Strike', format: formatCurrency },
    { key: 'buy_strike', label: 'Buy Strike', format: formatCurrency },
    { key: 'max_profit', label: 'Max Profit', format: formatCurrency },
    { key: 'bpr', label: 'BPR', format: formatCurrency },
    { key: 'expected_value', label: 'EV', format: (v: number) => formatCurrency(v) },
    { key: 'APDI', label: 'APDI%', format: (v: number) => formatPercent(v) },
    { key: 'sell_iv', label: 'Sell IV', format: (v: number) => formatPercent(v * 100) },
    { key: 'sell_delta', label: 'Delta', format: (v: number) => formatNumber(v, 3) },
    { key: 'iv_rank', label: 'IV Rank', format: (v: number) => formatNumber(v, 1) },
    { key: 'company_sector', label: 'Sector' },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Spreads</h1>

      {/* Filters */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Configuration & Filters</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Row 1 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">Expiration</label>
              <select
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
                value={selectedExpiration}
                onChange={(e) => setSelectedExpiration(e.target.value)}
              >
                {(expirations || []).map((exp: any) => (
                  <option key={exp.expiration_date} value={exp.expiration_date}>
                    {exp.days_to_expiration} DTE - {exp.expiration_date}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Delta Target</label>
              <Input
                type="number"
                step="0.01"
                value={params.delta_target}
                onChange={(e) => setParams({ ...params, delta_target: +e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Spread Width</label>
              <Input
                type="number"
                value={params.spread_width}
                onChange={(e) => setParams({ ...params, spread_width: +e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Strategy</label>
              <select
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
                value={params.strategy_type}
                onChange={(e) => setParams({ ...params, strategy_type: e.target.value })}
              >
                <option value="credit">Credit</option>
                <option value="debit">Debit</option>
              </select>
            </div>
          </div>

          {/* Row 2 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">Option Type</label>
              <select
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
                value={params.option_type}
                onChange={(e) => setParams({ ...params, option_type: e.target.value })}
              >
                <option value="put">Put</option>
                <option value="call">Call</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Min Day Volume</label>
              <Input
                type="number"
                value={params.min_day_volume}
                onChange={(e) => setParams({ ...params, min_day_volume: +e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Min Open Interest</label>
              <Input
                type="number"
                value={params.min_open_interest}
                onChange={(e) => setParams({ ...params, min_open_interest: +e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Min Max Profit ($)</label>
              <Input
                type="number"
                value={params.min_max_profit}
                onChange={(e) => setParams({ ...params, min_max_profit: +e.target.value })}
              />
            </div>
          </div>

          {/* Row 3 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">Min Sell IV</label>
              <Input
                type="number"
                step="0.05"
                value={params.min_sell_iv}
                onChange={(e) => setParams({ ...params, min_sell_iv: +e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Max Sell IV</label>
              <Input
                type="number"
                step="0.05"
                value={params.max_sell_iv}
                onChange={(e) => setParams({ ...params, max_sell_iv: +e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Min IV Rank</label>
              <Input
                type="number"
                value={params.min_iv_rank}
                onChange={(e) => setParams({ ...params, min_iv_rank: +e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Min IV Percentile</label>
              <Input
                type="number"
                value={params.min_iv_percentile}
                onChange={(e) => setParams({ ...params, min_iv_percentile: +e.target.value })}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {loadingSpreads || loadingExp ? (
        <LoadingState message="Calculating spreads..." />
      ) : (
        <>
          <p className="text-sm text-muted-foreground">{filteredSpreads.length} Results</p>
          <DataTable
            data={filteredSpreads}
            columns={columns}
            selectedIndex={selectedIndex}
            onRowClick={(row, i) => {
              setSelectedRow(row);
              setSelectedIndex(i);
            }}
          />
        </>
      )}

      {/* Detail Panel */}
      {selectedRow && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">
              {selectedRow.symbol} {selectedRow.option_type?.toUpperCase()} {params.strategy_type === 'credit' ? 'Credit' : 'Debit'} Spread
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Max Profit</p>
                <p className="text-lg font-semibold">{formatCurrency(selectedRow.max_profit)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">BPR</p>
                <p className="text-lg font-semibold">{formatCurrency(selectedRow.bpr)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Expected Value</p>
                <p className="text-lg font-semibold">{formatCurrency(selectedRow.expected_value)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">APDI</p>
                <p className="text-lg font-semibold">{formatPercent(selectedRow.APDI)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">IV Rank</p>
                <p className="text-lg font-semibold">{formatNumber(selectedRow.iv_rank, 1)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">IV Percentile</p>
                <p className="text-lg font-semibold">{formatNumber(selectedRow.iv_percentile, 1)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Sector</p>
                <p className="text-sm">{selectedRow.company_sector}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Industry</p>
                <p className="text-sm">{selectedRow.company_industry}</p>
              </div>
            </div>

            {/* Leg details */}
            <div className="mt-4 border rounded-md overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr>
                    <th className="px-3 py-2 text-left">Leg</th>
                    <th className="px-3 py-2 text-left">Strike</th>
                    <th className="px-3 py-2 text-left">Price</th>
                    <th className="px-3 py-2 text-left">Delta</th>
                    <th className="px-3 py-2 text-left">IV</th>
                    <th className="px-3 py-2 text-left">Theta</th>
                    <th className="px-3 py-2 text-left">OI</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t">
                    <td className="px-3 py-2 font-medium">
                      {params.strategy_type === 'credit' ? 'Short' : 'Long'} {selectedRow.option_type}
                    </td>
                    <td className="px-3 py-2">{formatCurrency(selectedRow.sell_strike)}</td>
                    <td className="px-3 py-2">{formatCurrency(selectedRow.sell_last_option_price)}</td>
                    <td className="px-3 py-2">{formatNumber(selectedRow.sell_delta, 3)}</td>
                    <td className="px-3 py-2">{formatPercent(selectedRow.sell_iv * 100)}</td>
                    <td className="px-3 py-2">{formatNumber(selectedRow.sell_theta, 4)}</td>
                    <td className="px-3 py-2">{selectedRow.sell_open_interest}</td>
                  </tr>
                  <tr className="border-t">
                    <td className="px-3 py-2 font-medium">
                      {params.strategy_type === 'credit' ? 'Long' : 'Short'} {selectedRow.option_type}
                    </td>
                    <td className="px-3 py-2">{formatCurrency(selectedRow.buy_strike)}</td>
                    <td className="px-3 py-2">{formatCurrency(selectedRow.buy_last_option_price)}</td>
                    <td className="px-3 py-2">{formatNumber(selectedRow.buy_delta, 3)}</td>
                    <td className="px-3 py-2">{formatPercent(selectedRow.buy_iv * 100)}</td>
                    <td className="px-3 py-2">{formatNumber(selectedRow.buy_theta, 4)}</td>
                    <td className="px-3 py-2">{selectedRow.buy_open_interest}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* External Links */}
            <div className="flex flex-wrap gap-2 mt-4">
              <a
                href={`https://www.tradingview.com/chart/?symbol=${selectedRow.symbol}`}
                target="_blank"
                rel="noopener"
                className="text-xs px-3 py-1.5 rounded-md bg-secondary hover:bg-secondary/80 transition-colors"
              >
                TradingView
              </a>
              <a
                href={`https://finviz.com/quote.ashx?t=${selectedRow.symbol}`}
                target="_blank"
                rel="noopener"
                className="text-xs px-3 py-1.5 rounded-md bg-secondary hover:bg-secondary/80 transition-colors"
              >
                Finviz
              </a>
              <a
                href={`https://seekingalpha.com/symbol/${selectedRow.symbol}`}
                target="_blank"
                rel="noopener"
                className="text-xs px-3 py-1.5 rounded-md bg-secondary hover:bg-secondary/80 transition-colors"
              >
                Seeking Alpha
              </a>
              <a
                href={`https://finance.yahoo.com/quote/${selectedRow.symbol}`}
                target="_blank"
                rel="noopener"
                className="text-xs px-3 py-1.5 rounded-md bg-secondary hover:bg-secondary/80 transition-colors"
              >
                Yahoo Finance
              </a>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
