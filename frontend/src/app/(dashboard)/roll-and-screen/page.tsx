'use client';

import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  getPutScreener, rankPutsAi, getPutScreenerBreakdown, getScreenerIvHistory, getScreenerSymbolPuts,
  getRollerPuts, getRollerPrice, getRollerCandidates,
  getSpreadTypes, getSpreadRollerOpen, getSpreadRollerCandidates, getBrowserPuts,
} from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { Button } from '@/components/ui/button';
import { formatCurrency, formatPercent, formatNumber, getClaudeAnalysisUrl } from '@/lib/utils';
import { Sparkles, X, ExternalLink, Check } from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts';

type TabKey = 'screener' | 'put-roller' | 'spread-roller' | 'browser';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'screener', label: 'Put Screener' },
  { key: 'put-roller', label: 'Put Roller' },
  { key: 'spread-roller', label: 'Spread Roller' },
  { key: 'browser', label: 'Put Browser' },
];

export default function RollAndScreenPage() {
  const [tab, setTab] = useState<TabKey>('screener');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Roll &amp; Screen</h1>
        <p className="text-sm text-muted-foreground">
          Cash-secured put screening, position rolling and put browsing — with optional AI analysis.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border/50">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.key
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'screener' && <PutScreenerTab />}
      {tab === 'put-roller' && <PutRollerTab />}
      {tab === 'spread-roller' && <SpreadRollerTab />}
      {tab === 'browser' && <PutBrowserTab />}
    </div>
  );
}

const SCREENER_DEFAULTS = {
  dte_min: 20,
  dte_max: 60,
  price_min: 10,
  price_max: 500,
  min_oi: 50,
  min_vol: 0,
  min_premium_share: 0,
  min_market_cap: 1_000_000_000,
  pe_max: 40,
  min_score: 0,
};

function PutScreenerTab() {
  const [form, setForm] = useState(SCREENER_DEFAULTS);
  const [params, setParams] = useState<typeof SCREENER_DEFAULTS | null>(null);
  const [aiProvider, setAiProvider] = useState('deepseek');
  const [selectedRow, setSelectedRow] = useState<any>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['put-screener', params],
    queryFn: () => getPutScreener(params as Record<string, any>),
    enabled: params !== null,
  });

  const rows: any[] = Array.isArray(data) ? data : [];

  const { data: breakdown, isFetching: loadingBreakdown } = useQuery({
    queryKey: ['put-screener-breakdown', selectedRow?.symbol, selectedRow?.put_strike, form.pe_max],
    queryFn: () => getPutScreenerBreakdown(selectedRow, form.pe_max),
    enabled: !!selectedRow,
  });

  const { data: ivHistory } = useQuery({
    queryKey: ['screener-iv-history', selectedRow?.symbol],
    queryFn: () => getScreenerIvHistory(selectedRow.symbol),
    enabled: !!selectedRow,
  });

  const { data: symbolPuts, isFetching: loadingSymbolPuts } = useQuery({
    queryKey: ['screener-symbol-puts', selectedRow?.symbol, form.dte_min, form.dte_max, form.min_oi],
    queryFn: () => getScreenerSymbolPuts({
      symbol: selectedRow.symbol,
      dte_min: form.dte_min, dte_max: form.dte_max,
      min_oi: form.min_oi, min_vol: form.min_vol, min_premium_share: form.min_premium_share,
    }),
    enabled: !!selectedRow,
  });

  const aiMutation = useMutation({
    mutationFn: () => rankPutsAi({ puts: rows.slice(0, 25), provider: aiProvider }),
  });

  const num = (key: keyof typeof SCREENER_DEFAULTS) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value === '' ? 0 : Number(e.target.value) });

  const columns: Column[] = [
    { key: 'symbol', label: 'Symbol', sortable: true },
    { key: 'score', label: 'Score', sortable: true, align: 'right' },
    { key: 'shortlist_score', label: 'Shortlist', sortable: true, align: 'right' },
    { key: 'live_stock_price', label: 'Price', sortable: true, align: 'right', format: (v) => formatCurrency(v) },
    { key: 'put_strike', label: 'Strike', sortable: true, align: 'right', format: (v) => formatCurrency(v) },
    { key: 'put_dte', label: 'DTE', sortable: true, align: 'right' },
    { key: 'put_premium', label: 'Premium', sortable: true, align: 'right', format: (v) => formatCurrency(v) },
    { key: 'put_delta', label: 'Delta', sortable: true, align: 'right', format: (v) => formatNumber(v, 3) },
    { key: 'premium_pct', label: 'Prem %', sortable: true, align: 'right', format: (v) => formatPercent(v / 100) },
    { key: 'annualized_pct', label: 'Annual %', sortable: true, align: 'right', format: (v) => formatPercent(v / 100), colorCode: 'pnl' },
    { key: 'breakeven', label: 'Breakeven', sortable: true, align: 'right', format: (v) => formatCurrency(v) },
    { key: 'put_oi', label: 'OI', sortable: true, align: 'right', format: (v) => formatNumber(v, 0) },
    { key: 'iv_rank', label: 'IV Rank', sortable: true, align: 'right', format: (v) => formatNumber(v, 1) },
  ];

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
          <Field label="DTE Min"><Input type="number" value={form.dte_min} onChange={num('dte_min')} /></Field>
          <Field label="DTE Max"><Input type="number" value={form.dte_max} onChange={num('dte_max')} /></Field>
          <Field label="Price Min"><Input type="number" value={form.price_min} onChange={num('price_min')} /></Field>
          <Field label="Price Max"><Input type="number" value={form.price_max} onChange={num('price_max')} /></Field>
          <Field label="Min OI"><Input type="number" value={form.min_oi} onChange={num('min_oi')} /></Field>
          <Field label="Min Volume"><Input type="number" value={form.min_vol} onChange={num('min_vol')} /></Field>
          <Field label="Min Prem/Share"><Input type="number" step="0.01" value={form.min_premium_share} onChange={num('min_premium_share')} /></Field>
          <Field label="Min Mkt Cap"><Input type="number" value={form.min_market_cap} onChange={num('min_market_cap')} /></Field>
          <Field label="Max P/E"><Input type="number" value={form.pe_max} onChange={num('pe_max')} /></Field>
          <Field label="Min Score (0-9)"><Input type="number" value={form.min_score} onChange={num('min_score')} /></Field>
          <div className="flex items-end">
            <Button className="w-full" onClick={() => setParams({ ...form })}>Screen</Button>
          </div>
        </CardContent>
      </Card>

      {params === null ? (
        <p className="text-sm text-muted-foreground">Set filters and click Screen to find put candidates.</p>
      ) : isLoading ? (
        <LoadingState message="Screening puts..." />
      ) : (
        <>
          <div className="flex items-center gap-2">
            <select
              className="h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm"
              value={aiProvider}
              onChange={(e) => setAiProvider(e.target.value)}
            >
              <option value="deepseek">DeepSeek</option>
              <option value="kimi">Kimi</option>
            </select>
            <Button variant="outline" size="sm" onClick={() => aiMutation.mutate()} disabled={aiMutation.isPending || rows.length === 0}>
              <Sparkles className="w-3.5 h-3.5 mr-1" />
              {aiMutation.isPending ? 'Analyzing…' : 'AI Analysis'}
            </Button>
            {isFetching && <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />}
          </div>

          {aiMutation.data && (
            <Card>
              <CardContent className="p-4">
                {aiMutation.data.error ? (
                  <p className="text-sm text-amber-400">
                    AI analysis unavailable: {aiMutation.data.message || aiMutation.data.error}. Check the provider API key in the backend environment.
                  </p>
                ) : (
                  <pre className="text-xs whitespace-pre-wrap font-sans">{aiMutation.data.ranking}</pre>
                )}
              </CardContent>
            </Card>
          )}

          <DataTable
            data={rows}
            columns={columns}
            defaultSort={{ key: 'shortlist_score', direction: 'desc' }}
            onRowClick={(row, index) => { setSelectedRow(row); setSelectedIndex(index); }}
            selectedIndex={selectedIndex ?? undefined}
            stickyHeader
            maxHeight="60vh"
            compact
          />

          {selectedRow && (
            <Card>
              <CardContent className="p-4 space-y-3 relative">
                <button
                  onClick={() => { setSelectedRow(null); setSelectedIndex(null); }}
                  className="absolute top-3 right-3 text-muted-foreground hover:text-foreground"
                >
                  <X className="w-4 h-4" />
                </button>
                <div>
                  <h3 className="text-base font-semibold flex items-center gap-2">
                    {selectedRow.symbol}
                    <span className="text-sm font-normal text-muted-foreground">
                      Score {selectedRow.score}/9
                    </span>
                    <a
                      href={getClaudeAnalysisUrl(selectedRow.symbol, selectedRow.company_name)}
                      target="_blank" rel="noopener noreferrer"
                      className="text-primary hover:underline text-xs inline-flex items-center gap-1"
                    >
                      Analysis <ExternalLink className="w-3 h-3" />
                    </a>
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    {selectedRow.company_name} · Strike {formatCurrency(selectedRow.put_strike)} · {selectedRow.put_dte} DTE · Premium {formatCurrency(selectedRow.put_premium)}
                  </p>
                </div>

                {loadingBreakdown ? (
                  <p className="text-sm text-muted-foreground">Loading score breakdown…</p>
                ) : breakdown?.breakdown ? (
                  <div className="space-y-1">
                    {breakdown.breakdown.map((c: any) => (
                      <div key={c.key} className="flex items-center gap-2 text-sm py-1 border-b border-border/30 last:border-0">
                        <span className={`flex-shrink-0 w-5 ${c.erreicht ? 'text-emerald-400' : 'text-red-400'}`}>
                          {c.erreicht ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
                        </span>
                        <span className="flex-1">{c.label}</span>
                        <span className="text-muted-foreground text-xs">{c.annahme}</span>
                        <span className="font-medium tabular-nums w-24 text-right">
                          {typeof c.ist_wert === 'number' ? formatNumber(c.ist_wert, 2) : String(c.ist_wert ?? '—')}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No breakdown available.</p>
                )}

                {/* IV history chart */}
                {Array.isArray(ivHistory) && ivHistory.length > 0 && (
                  <div className="pt-3 border-t border-border/40">
                    <h4 className="text-xs font-semibold mb-2">IV History (1Y)</h4>
                    <div className="h-56 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={ivHistory} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                          <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
                          <YAxis tick={{ fontSize: 10 }} domain={['auto', 'auto']} />
                          <Tooltip
                            contentStyle={{ fontSize: 12, background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))' }}
                            formatter={(v: any) => (typeof v === 'number' ? v.toFixed(2) : v)}
                          />
                          <Legend wrapperStyle={{ fontSize: 11 }} />
                          <Line type="monotone" dataKey="iv" stroke="#8b5cf6" dot={false} strokeWidth={2} name="IV %" />
                          <Line type="monotone" dataKey="iv_rank" stroke="#10b981" dot={false} strokeWidth={1.5} name="IV Rank" />
                          <Line type="monotone" dataKey="iv_percentile" stroke="#6b7280" dot={false} strokeWidth={1} name="IV %ile" />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* Sellable puts now */}
                <div className="pt-3 border-t border-border/40">
                  <h4 className="text-xs font-semibold mb-2">Sellable Puts — now</h4>
                  {loadingSymbolPuts ? (
                    <p className="text-sm text-muted-foreground">Loading puts…</p>
                  ) : Array.isArray(symbolPuts) && symbolPuts.length > 0 ? (
                    <DataTable
                      data={symbolPuts}
                      columns={[
                        { key: 'strike_price', label: 'Strike', align: 'right', format: (v) => formatCurrency(v), sortable: true },
                        { key: 'expiration_date', label: 'Expiration', sortable: true },
                        { key: 'days_to_expiration', label: 'DTE', align: 'right', sortable: true },
                        { key: 'premium_option_price', label: 'Premium', align: 'right', format: (v) => formatCurrency(v), sortable: true },
                        { key: 'greeks_delta', label: 'Delta', align: 'right', format: (v) => formatNumber(v, 3), sortable: true },
                        { key: 'implied_volatility', label: 'IV', align: 'right', format: (v) => formatPercent(v), sortable: true },
                        { key: 'open_interest', label: 'OI', align: 'right', format: (v) => formatNumber(v, 0), sortable: true },
                        { key: 'day_volume', label: 'Vol', align: 'right', format: (v) => formatNumber(v, 0), sortable: true },
                        { key: 'iv_rank', label: 'IV Rank', align: 'right', format: (v) => formatNumber(v, 1), sortable: true },
                        { key: 'days_to_earnings', label: 'To Earn.', align: 'right', sortable: true },
                      ]}
                      compact stickyHeader maxHeight="40vh"
                    />
                  ) : (
                    <p className="text-sm text-muted-foreground">No sellable puts for the current DTE/OI filters.</p>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function PlaceholderTab({ label }: { label: string }) {
  return (
    <Card>
      <CardContent className="p-6 text-sm text-muted-foreground">
        {label} — coming up.
      </CardContent>
    </Card>
  );
}

function AmpelBadge({ value }: { value: string }) {
  const map: Record<string, string> = {
    gruen: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    gelb: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    rot: 'bg-red-500/15 text-red-400 border-red-500/30',
  };
  const cls = map[String(value).toLowerCase()] || 'bg-muted/30 text-muted-foreground border-border/30';
  return <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${cls}`}>{String(value).toUpperCase()}</span>;
}

// ---- Tab 2: Put Roller ----
function PutRollerTab() {
  const today = new Date().toISOString().slice(0, 10);
  const [symbol, setSymbol] = useState('');
  const [entryDate, setEntryDate] = useState(today);
  const [loaded, setLoaded] = useState<{ symbol: string; entry_date: string } | null>(null);
  const [selectedPut, setSelectedPut] = useState<any>(null);

  const { data: puts, isLoading: loadingPuts } = useQuery({
    queryKey: ['roller-puts', loaded],
    queryFn: () => getRollerPuts(loaded as any),
    enabled: loaded !== null,
  });

  const { data: price } = useQuery({
    queryKey: ['roller-price', selectedPut?.option_osi, loaded?.symbol],
    queryFn: () => getRollerPrice({ symbol: loaded!.symbol, option_osi: selectedPut.option_osi }),
    enabled: !!selectedPut && !!loaded,
  });

  const { data: candidates, isFetching: fetchingCand } = useQuery({
    queryKey: ['roller-candidates', selectedPut?.option_osi, price?.put_price, price?.stock_price],
    queryFn: () =>
      getRollerCandidates({
        symbol: loaded!.symbol,
        K: selectedPut.strike_price,
        S: price.stock_price,
        P_eroeffnung: selectedPut.premium_option_price * 100,
        P_heute: (price.put_price ?? 0) * 100,
        dte_rest: selectedPut.days_to_expiration,
      }),
    enabled: !!selectedPut && !!price && price.stock_price != null && price.put_price != null,
  });

  const putCols: Column[] = [
    { key: 'strike_price', label: 'Strike', align: 'right', format: (v) => formatCurrency(v) },
    { key: 'premium_option_price', label: 'Premium', align: 'right', format: (v) => formatCurrency(v) },
    { key: 'days_to_expiration', label: 'DTE', align: 'right' },
    { key: 'expiration_date', label: 'Expiration' },
    { key: 'open_interest', label: 'OI', align: 'right', format: (v) => formatNumber(v, 0) },
  ];

  const candCols: Column[] = [
    { key: 'ampel', label: 'Signal', format: (v) => <AmpelBadge value={v} /> },
    { key: 'strike_price', label: 'Strike', align: 'right', format: (v) => formatCurrency(v) },
    { key: 'expiration_date', label: 'Expiration' },
    { key: 'days_to_expiration', label: 'DTE', align: 'right' },
    { key: 'premium_share', label: 'Premium', align: 'right', format: (v) => formatCurrency(v) },
    { key: 'netto_abs', label: 'Net', align: 'right', format: (v) => formatCurrency(v), colorCode: 'pnl' },
    { key: 'breakeven_new', label: 'BE new', align: 'right', format: (v) => formatCurrency(v) },
    { key: 'kapital_noetig', label: 'Capital', align: 'right', format: (v) => formatCurrency(v) },
  ];

  const rollTabs = [
    { key: 'stufe1', label: 'Vertikal' },
    { key: 'stufe2', label: 'Horizontal' },
    { key: 'stufe3', label: 'Verdoppeln' },
  ];
  const [activeRoll, setActiveRoll] = useState('stufe1');

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 flex flex-wrap gap-3 items-end">
          <Field label="Symbol"><Input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} className="w-32" /></Field>
          <Field label="Entry date"><Input type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} className="w-40" /></Field>
          <Button onClick={() => { setSelectedPut(null); setLoaded({ symbol, entry_date: entryDate }); }} disabled={!symbol}>Load Puts</Button>
        </CardContent>
      </Card>

      {loaded && (loadingPuts ? <LoadingState message="Loading puts..." /> : (
        <div>
          <h3 className="text-sm font-semibold mb-2">Open puts — click one to roll</h3>
          <DataTable data={Array.isArray(puts) ? puts : []} columns={putCols} compact
            onRowClick={(row) => setSelectedPut(row)} maxHeight="30vh" stickyHeader />
        </div>
      ))}

      {selectedPut && (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            Rolling {loaded?.symbol} strike {formatCurrency(selectedPut.strike_price)} · current put {price?.put_price != null ? formatCurrency(price.put_price) : '…'} · stock {price?.stock_price != null ? formatCurrency(price.stock_price) : '…'}
            {fetchingCand && <span className="ml-2 inline-block w-2 h-2 rounded-full bg-primary animate-pulse" />}
          </p>
          {candidates?.position && (
            <p className="text-xs text-muted-foreground">
              P&amp;L: {formatCurrency(candidates.position.pnl_abs)} ({formatPercent(candidates.position.pnl_pct / 100)}) · {candidates.position.grund}
            </p>
          )}
          {candidates && (
            <div>
              <div className="flex gap-1 border-b border-border/50 mb-2">
                {rollTabs.map((t) => {
                  const count = candidates?.[t.key]?.length || 0;
                  return (
                    <button
                      key={t.key}
                      onClick={() => setActiveRoll(t.key)}
                      className={`px-3 py-1.5 text-sm font-medium border-b-2 transition-colors ${
                        activeRoll === t.key
                          ? 'border-primary text-foreground'
                          : 'border-transparent text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {t.label} {count > 0 && <span className="text-xs text-muted-foreground">({count})</span>}
                    </button>
                  );
                })}
              </div>
              {candidates?.[activeRoll]?.length > 0 ? (
                <DataTable data={candidates[activeRoll]} columns={candCols} compact maxHeight="40vh" stickyHeader />
              ) : (
                <p className="text-sm text-muted-foreground py-4">No roll candidates in this category.</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---- Tab 3: Spread Roller ----
function SpreadRollerTab() {
  const today = new Date().toISOString().slice(0, 10);
  const [symbol, setSymbol] = useState('');
  const [entryDate, setEntryDate] = useState(today);
  const [expiration, setExpiration] = useState('');
  const [loaded, setLoaded] = useState<any>(null);

  const { data: open, isLoading } = useQuery({
    queryKey: ['spread-open', loaded],
    queryFn: () => getSpreadRollerOpen(loaded),
    enabled: loaded !== null,
  });

  const openCols: Column[] = [
    { key: 'contract_type', label: 'Type' },
    { key: 'strike_price', label: 'Strike', align: 'right', format: (v) => formatCurrency(v) },
    { key: 'premium_option_price', label: 'Premium', align: 'right', format: (v) => formatCurrency(v) },
    { key: 'days_to_expiration', label: 'DTE', align: 'right' },
    { key: 'open_interest', label: 'OI', align: 'right', format: (v) => formatNumber(v, 0) },
  ];

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 flex flex-wrap gap-3 items-end">
          <Field label="Symbol"><Input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} className="w-32" /></Field>
          <Field label="Entry date"><Input type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} className="w-40" /></Field>
          <Field label="Expiration"><Input type="date" value={expiration} onChange={(e) => setExpiration(e.target.value)} className="w-40" /></Field>
          <Button onClick={() => setLoaded({ symbol, entry_date: entryDate, expiration_date: expiration })} disabled={!symbol || !expiration}>Load Chain</Button>
        </CardContent>
      </Card>
      {loaded && (isLoading ? <LoadingState message="Loading spread chain..." /> : (
        <div>
          <h3 className="text-sm font-semibold mb-2">Opening-day chain ({loaded.symbol}, exp {loaded.expiration_date})</h3>
          <p className="text-xs text-muted-foreground mb-2">Pick short + long legs to compute roll candidates (short/long strike entry below).</p>
          <DataTable data={Array.isArray(open) ? open : []} columns={openCols} compact maxHeight="40vh" stickyHeader />
        </div>
      ))}
    </div>
  );
}

// ---- Tab 4: Put Browser ----
const BROWSER_DEFAULTS = {
  dte_min: 21, dte_max: 45, min_puffer_pct: 5, min_ann_pct: 12,
  price_min: 15, price_max: 150, min_oi: 100, min_vol: 20, min_premium_share: 0.1,
};

function PutBrowserTab() {
  const [form, setForm] = useState(BROWSER_DEFAULTS);
  const [params, setParams] = useState<typeof BROWSER_DEFAULTS | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['browser-puts', params],
    queryFn: () => getBrowserPuts(params as Record<string, any>),
    enabled: params !== null,
  });
  const rows: any[] = Array.isArray(data) ? data : [];

  const num = (key: keyof typeof BROWSER_DEFAULTS) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value === '' ? 0 : Number(e.target.value) });

  const cols: Column[] = [
    { key: 'symbol', label: 'Symbol', sortable: true },
    { key: 'live_stock_price', label: 'Price', sortable: true, align: 'right', format: (v) => formatCurrency(v) },
    { key: 'strike_price', label: 'Strike', sortable: true, align: 'right', format: (v) => formatCurrency(v) },
    { key: 'expiration_date', label: 'Expiration', sortable: true },
    { key: 'days_to_expiration', label: 'DTE', sortable: true, align: 'right' },
    { key: 'premium_option_price', label: 'Premium', sortable: true, align: 'right', format: (v) => formatCurrency(v) },
    { key: 'puffer_pct', label: 'Buffer %', sortable: true, align: 'right', format: (v) => formatPercent(v / 100) },
    { key: 'ann_pct', label: 'Annual %', sortable: true, align: 'right', format: (v) => formatPercent(v / 100), colorCode: 'pnl' },
    { key: 'open_interest', label: 'OI', sortable: true, align: 'right', format: (v) => formatNumber(v, 0) },
    { key: 'iv_rank', label: 'IV Rank', sortable: true, align: 'right', format: (v) => formatNumber(v, 1) },
  ];

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
          <Field label="DTE Min"><Input type="number" value={form.dte_min} onChange={num('dte_min')} /></Field>
          <Field label="DTE Max"><Input type="number" value={form.dte_max} onChange={num('dte_max')} /></Field>
          <Field label="Min Buffer %"><Input type="number" value={form.min_puffer_pct} onChange={num('min_puffer_pct')} /></Field>
          <Field label="Min Annual %"><Input type="number" value={form.min_ann_pct} onChange={num('min_ann_pct')} /></Field>
          <Field label="Price Min"><Input type="number" value={form.price_min} onChange={num('price_min')} /></Field>
          <Field label="Price Max"><Input type="number" value={form.price_max} onChange={num('price_max')} /></Field>
          <Field label="Min OI"><Input type="number" value={form.min_oi} onChange={num('min_oi')} /></Field>
          <Field label="Min Volume"><Input type="number" value={form.min_vol} onChange={num('min_vol')} /></Field>
          <Field label="Min Prem/Share"><Input type="number" step="0.01" value={form.min_premium_share} onChange={num('min_premium_share')} /></Field>
          <div className="flex items-end"><Button className="w-full" onClick={() => setParams({ ...form })}>Browse</Button></div>
        </CardContent>
      </Card>
      {params === null ? (
        <p className="text-sm text-muted-foreground">Set filters and click Browse to list tradeable puts.</p>
      ) : isLoading ? (
        <LoadingState message="Loading puts..." />
      ) : (
        <DataTable data={rows} columns={cols} defaultSort={{ key: 'ann_pct', direction: 'desc' }} stickyHeader maxHeight="60vh" compact />
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-muted-foreground">{label}</label>
      {children}
    </div>
  );
}
