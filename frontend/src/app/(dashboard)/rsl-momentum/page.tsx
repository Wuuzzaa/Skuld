'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getRslMomentum } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatNumber, getClaudeAnalysisUrl } from '@/lib/utils';
import { X, ExternalLink, HelpCircle, ChevronDown, ChevronRight, Info, AlertTriangle, TrendingUp, Shield } from 'lucide-react';
import { Button } from '@/components/ui/button';

function RslZoneBadge({ zone }: { zone: string }) {
  const config: Record<string, { label: string; cls: string }> = {
    overheated: { label: 'ÜBERHITZT', cls: 'bg-red-500/15 text-red-400 border-red-500/30' },
    very_strong: { label: 'SEHR STARK', cls: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
    strong: { label: 'STARK', cls: 'bg-blue-500/15 text-blue-400 border-blue-500/30' },
    normal: { label: 'NORMAL', cls: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' },
    weak: { label: 'SCHWACH', cls: 'bg-red-500/15 text-red-400 border-red-500/30' },
  };
  const c = config[zone] || config.normal;
  return <span className={`px-1.5 py-0.5 rounded text-[9px] font-semibold border ${c.cls}`}>{c.label}</span>;
}

function MarketRegimeBanner({ regime }: { regime: any }) {
  if (!regime || regime.regime === 'unknown') return null;

  const config: Record<string, { bg: string; border: string; icon: any; text: string }> = {
    bull: {
      bg: 'bg-emerald-500/5',
      border: 'border-emerald-500/30',
      icon: <TrendingUp className="w-4 h-4 text-emerald-400" />,
      text: 'text-emerald-400',
    },
    caution: {
      bg: 'bg-amber-500/5',
      border: 'border-amber-500/30',
      icon: <AlertTriangle className="w-4 h-4 text-amber-400" />,
      text: 'text-amber-400',
    },
    bear: {
      bg: 'bg-red-500/5',
      border: 'border-red-500/30',
      icon: <Shield className="w-4 h-4 text-red-400" />,
      text: 'text-red-400',
    },
  };

  const c = config[regime.regime] || config.caution;

  return (
    <div className={`flex items-center gap-3 p-3 rounded-lg border ${c.bg} ${c.border}`}>
      {c.icon}
      <div className="flex-1">
        <p className={`text-sm font-semibold ${c.text}`}>{regime.description}</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          SPY: {regime.spy_price ? `$${regime.spy_price}` : 'N/A'}
          {regime.sma200 && ` | SMA200: $${regime.sma200}`}
          {regime.sma50 && ` | SMA50: $${regime.sma50}`}
        </p>
      </div>
      <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${c.text} ${c.bg} border ${c.border}`}>
        {regime.regime}
      </span>
    </div>
  );
}

export default function RslMomentumPage() {
  const [params, setParams] = useState({
    top_n: 5,
    max_per_sector: 2,
    exit_percentile: 50,
    max_volatility: null as number | null,
    min_days_to_earnings: null as number | null,
    market_filter: true,
  });
  const [selectedRow, setSelectedRow] = useState<any>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [showGuide, setShowGuide] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [showExplain, setShowExplain] = useState(false);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['rsl-momentum', params],
    queryFn: () => getRslMomentum(params),
  });

  const ranking = data?.ranking || [];
  const topPicks = data?.top_picks || [];
  const summary = data?.summary || null;
  const marketRegime = data?.market_regime || null;
  const filtersApplied = data?.filters_applied || null;

  const columns: Column[] = [
    {
      key: 'rank',
      label: '#',
      sortable: true,
      align: 'right',
      format: (v: number) => <span className="text-muted-foreground font-mono text-xs">{v}</span>,
    },
    {
      key: 'symbol',
      label: 'Symbol',
      sortable: true,
      format: (v: string, row: any) => (
        <span className={`font-semibold ${row.is_top_pick ? 'text-emerald-400' : row.filtered_out ? 'text-muted-foreground/50' : 'text-foreground'}`}>
          {v} {row.is_top_pick && '\u2605'}
        </span>
      ),
    },
    { key: 'company_name', label: 'Company', sortable: true },
    { key: 'sector', label: 'Sector', sortable: true },
    {
      key: 'rsl',
      label: 'RSL',
      sortable: true,
      align: 'right',
      format: (v: number) => (
        <span className={`font-bold ${v >= 2.0 ? 'text-red-400' : v >= 1.3 ? 'text-emerald-400' : v >= 1.0 ? 'text-foreground' : 'text-red-400'}`}>
          {formatNumber(v, 4)}
        </span>
      ),
    },
    {
      key: 'rsl_zone',
      label: 'Zone',
      sortable: true,
      align: 'center',
      format: (v: string) => <RslZoneBadge zone={v} />,
    },
    { key: 'price', label: 'Price', format: formatCurrency, sortable: true, align: 'right' },
    {
      key: 'hv30',
      label: 'HV30',
      sortable: true,
      align: 'right',
      format: (v: number | null, row: any) => {
        if (v == null) return <span className="text-muted-foreground text-xs">—</span>;
        const isHigh = v > 60;
        return <span className={`text-xs font-mono ${isHigh ? 'text-amber-400' : 'text-muted-foreground'}`}>{formatNumber(v, 1)}%</span>;
      },
    },
    {
      key: 'dte',
      label: 'DTE',
      sortable: true,
      align: 'right',
      format: (v: number | null) => {
        if (v == null) return <span className="text-muted-foreground text-xs">—</span>;
        const isClose = v < 14;
        return <span className={`text-xs font-mono ${isClose ? 'text-red-400 font-bold' : 'text-muted-foreground'}`}>{v}d</span>;
      },
    },
    {
      key: 'percentile',
      label: 'Pctl',
      sortable: true,
      align: 'right',
      format: (v: number) => (
        <span className={v >= 75 ? 'text-emerald-400' : v >= 50 ? 'text-foreground' : 'text-red-400'}>
          {formatNumber(v, 1)}%
        </span>
      ),
    },
    {
      key: 'above_threshold',
      label: 'Signal',
      sortable: true,
      align: 'center',
      format: (v: boolean) => (
        v
          ? <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-400">HOLD</span>
          : <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-500/10 text-red-400">EXIT</span>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">RSL Momentum Rotation</h1>
          {isFetching && <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowGuide(!showGuide)}
          className={showGuide ? 'text-primary' : 'text-muted-foreground'}
        >
          <HelpCircle className="w-4 h-4 mr-1" />
          Strategy Guide
        </Button>
      </div>

      {/* Market Regime Banner */}
      {!isLoading && marketRegime && params.market_filter && (
        <MarketRegimeBanner regime={marketRegime} />
      )}

      {/* Controls */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Top N</label>
          <Input
            type="number" min={1} max={50} step={1}
            value={params.top_n}
            onChange={(e) => setParams({ ...params, top_n: +e.target.value })}
            className="w-20 h-8"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Max / Sector</label>
          <Input
            type="number" min={1} max={10} step={1}
            value={params.max_per_sector}
            onChange={(e) => setParams({ ...params, max_per_sector: +e.target.value })}
            className="w-20 h-8"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Exit below Top %</label>
          <Input
            type="number" min={1} max={90} step={1}
            value={params.exit_percentile}
            onChange={(e) => setParams({ ...params, exit_percentile: +e.target.value })}
            className="w-20 h-8"
          />
        </div>
        <div className="h-6 w-px bg-border/50" />
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Max Vola %</label>
          <Input
            type="number" min={10} max={200} step={5}
            value={params.max_volatility ?? ''}
            placeholder="off"
            onChange={(e) => setParams({ ...params, max_volatility: e.target.value ? +e.target.value : null })}
            className="w-20 h-8"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Min DTE</label>
          <Input
            type="number" min={1} max={60} step={1}
            value={params.min_days_to_earnings ?? ''}
            placeholder="off"
            onChange={(e) => setParams({ ...params, min_days_to_earnings: e.target.value ? +e.target.value : null })}
            className="w-20 h-8"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground">Marktfilter</label>
          <button
            onClick={() => setParams({ ...params, market_filter: !params.market_filter })}
            className={`px-2 py-1 rounded text-[10px] font-semibold border transition-colors ${
              params.market_filter
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-muted/30 text-muted-foreground border-border/30'
            }`}
          >
            {params.market_filter ? 'AN' : 'AUS'}
          </button>
        </div>
      </div>

      {/* Filter Status */}
      {filtersApplied && (filtersApplied.volatility_filtered > 0 || filtersApplied.earnings_filtered > 0) && (
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>Filter aktiv:</span>
          {filtersApplied.volatility_filtered > 0 && (
            <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
              {filtersApplied.volatility_filtered} Vola-gefiltert
            </span>
          )}
          {filtersApplied.earnings_filtered > 0 && (
            <span className="px-2 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">
              {filtersApplied.earnings_filtered} Earnings-gefiltert
            </span>
          )}
        </div>
      )}

      {/* Top Picks Card */}
      {topPicks.length > 0 && !isLoading && (
        <Card className="border-emerald-500/20 bg-card/80">
          <CardContent className="pt-4">
            <h3 className="text-sm font-semibold text-emerald-400 mb-3">
              Top {params.top_n} Picks (max {params.max_per_sector} per sector)
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
              {topPicks.map((stock: any) => (
                <div key={stock.symbol} className="p-3 rounded-lg bg-muted/30 border border-emerald-500/20">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-emerald-400">{stock.symbol}</span>
                    <div className="flex items-center gap-1.5">
                      <RslZoneBadge zone={stock.rsl_zone} />
                      <span className="text-xs text-muted-foreground">#{stock.rank}</span>
                    </div>
                  </div>
                  <p className="text-[10px] text-muted-foreground truncate mt-1">{stock.company_name}</p>
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-xs font-mono">RSL {formatNumber(stock.rsl, 3)}</span>
                    <span className="text-xs">{formatCurrency(stock.price)}</span>
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-[10px] text-muted-foreground">{stock.sector}</span>
                    {stock.hv30 != null && (
                      <span className={`text-[10px] ${stock.hv30 > 60 ? 'text-amber-400' : 'text-muted-foreground'}`}>
                        HV {formatNumber(stock.hv30, 0)}%
                      </span>
                    )}
                  </div>
                  {stock.rsl_zone === 'overheated' && (
                    <div className="mt-2 flex items-center gap-1 text-[10px] text-red-400">
                      <AlertTriangle className="w-3 h-3" />
                      Mean-Reversion-Risiko
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Summary Stats */}
      {summary && !isLoading && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">S&P 500 Ranked</span>
            <span className="text-lg font-bold">{summary.total_stocks}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Above Threshold</span>
            <span className="text-lg font-bold text-emerald-400">{summary.above_threshold}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Avg RSL (Top Picks)</span>
            <span className="text-lg font-bold text-amber-400">{summary.avg_rsl_top_picks ? formatNumber(summary.avg_rsl_top_picks, 4) : 'N/A'}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">RSL Range</span>
            <span className="text-lg font-bold">{formatNumber(summary.min_rsl, 3)} – {formatNumber(summary.max_rsl, 3)}</span>
          </div>
          <div className="flex flex-col gap-1 p-3 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Überhitzt (RSL{'>'}2)</span>
            <span className={`text-lg font-bold ${summary.overheated_count > 0 ? 'text-red-400' : 'text-muted-foreground'}`}>
              {summary.overheated_count || 0}
            </span>
          </div>
        </div>
      )}

      {/* Strategy Guide / FAQ */}
      {showGuide && (
        <Card className="border-primary/20 bg-card/80">
          <CardContent className="pt-4 space-y-3">
            <h3 className="text-sm font-semibold text-primary mb-2">Strategy Guide</h3>
            {[
              {
                q: 'Was ist der RSL-Wert?',
                a: 'RSL (Relative Strength Line) = Aktueller Kurs / 200-Tage-Durchschnitt (SMA200). Ein RSL von 1.5 bedeutet, die Aktie notiert 50% über ihrem 200-Tage-Durchschnitt. RSL > 1.0 = Aufwärtstrend, RSL < 1.0 = Abwärtstrend. Je höher der RSL, desto stärker das Momentum.',
              },
              {
                q: 'Wie funktioniert die Rotation?',
                a: 'Du hältst immer die Top-N Aktien mit dem höchsten RSL (aktuell Top 5). Wöchentlich prüfst du das Ranking. Fällt eine Position unter den Exit-Threshold (aktuell Top 50%), wird sie verkauft und durch den nächsten qualifizierenden Nachrücker ersetzt.',
              },
              {
                q: 'Was ist der Marktfilter?',
                a: 'Der Marktfilter prüft ob der S&P 500 (SPY) über seinem 200-Tage-Durchschnitt handelt. In einem Bärenmarkt (SPY < SMA200) verliert die Momentum-Strategie deutlich. Der Filter empfiehlt dann KEINE Neukäufe — bestehende Positionen werden nur per Exit-Signal verkauft.',
              },
              {
                q: 'Was bedeuten die RSL-Zonen?',
                a: 'NORMAL (RSL 1.0–1.3): Gesunder Aufwärtstrend. STARK (RSL 1.3–1.8): Überdurchschnittliches Momentum. SEHR STARK (RSL 1.8–2.0): Extremes Momentum, erhöhte Aufmerksamkeit. ÜBERHITZT (RSL > 2.0): Kurs 100%+ über SMA200, hohes Mean-Reversion-Risiko — Position evtl. reduzieren oder engeren Stop setzen.',
              },
              {
                q: 'Wann kaufen und verkaufen?',
                a: 'HOLD = Position bleibt im Portfolio, sie ist noch im oberen Bereich des Rankings. EXIT = Position ist unter die Schwelle gefallen und muss verkauft werden. Neue Aktien werden nur gekauft, wenn ein Platz frei wird und der Marktfilter "grün" ist.',
              },
              {
                q: 'Was ist der Volatilitäts-Filter?',
                a: 'Aktien mit extrem hoher historischer Volatilität (HV30 > Schwelle) werden aus der Top-Picks-Auswahl ausgeschlossen. Grund: Extrem volatile Aktien erzeugen mehr Whipsaws und False Signals. Die Aktien bleiben im Ranking sichtbar, werden aber nicht als Top Pick empfohlen.',
              },
              {
                q: 'Earnings-Proximity-Filter?',
                a: 'Aktien mit Earnings in weniger als X Tagen (Standard: 7) werden markiert und optional aus den Top Picks ausgeschlossen. Grund: Earnings-Gaps können eine Momentum-Position in einem Tag zerstören. Nach den Earnings kann man wieder einsteigen.',
              },
            ].map((item, i) => (
              <div key={i} className="border border-border/30 rounded-lg overflow-hidden">
                <button
                  className="w-full flex items-center justify-between p-3 text-left hover:bg-muted/30 transition-colors"
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                >
                  <span className="text-sm font-medium">{item.q}</span>
                  {openFaq === i
                    ? <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />
                    : <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
                  }
                </button>
                {openFaq === i && (
                  <div className="px-3 pb-3 text-sm text-muted-foreground leading-relaxed">
                    {item.a}
                  </div>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Full Ranking Table */}
      {isLoading ? (
        <LoadingState message="Calculating RSL rankings..." />
      ) : (
        <DataTable
          data={ranking}
          columns={columns}
          selectedIndex={selectedIndex}
          onRowClick={(row, i) => { setSelectedRow(row); setSelectedIndex(i); }}
          defaultSort={{ key: 'rank', direction: 'asc' }}
          striped
        />
      )}

      {/* Detail Panel */}
      {selectedRow && (
        <Card className="border-amber-500/20 bg-card/80">
          <CardContent className="pt-4 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`px-2 py-0.5 rounded text-sm font-bold ${
                  selectedRow.is_top_pick ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'
                }`}>
                  {selectedRow.symbol}
                </span>
                <span className="text-sm text-muted-foreground">{selectedRow.company_name}</span>
                {selectedRow.is_top_pick && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 font-medium">TOP PICK</span>
                )}
                <RslZoneBadge zone={selectedRow.rsl_zone} />
                {selectedRow.rsl_zone === 'overheated' && (
                  <span className="flex items-center gap-1 text-[10px] text-red-400">
                    <AlertTriangle className="w-3 h-3" /> Mean-Reversion
                  </span>
                )}
              </div>
              <Button variant="ghost" size="sm" onClick={() => { setSelectedRow(null); setSelectedIndex(null); setShowExplain(false); }}>
                <X className="w-4 h-4" />
              </Button>
            </div>

            {/* Overheated Warning */}
            {selectedRow.rsl_zone === 'overheated' && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-red-500/5 border border-red-500/20">
                <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-red-400">Mean-Reversion-Risiko</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    RSL {'>'}2.0 bedeutet Kurs {formatNumber((selectedRow.rsl - 1) * 100, 0)}% über SMA200. Historisch fallen solche Extremwerte
                    oft 20-40% zurück. Erwäge: kleinere Position, engerer Stop-Loss, oder Teilverkauf.
                  </p>
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Rank</p>
                <p className="text-base font-bold">#{selectedRow.rank}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">RSL</p>
                <p className={`text-base font-bold ${selectedRow.rsl >= 2.0 ? 'text-red-400' : selectedRow.rsl >= 1.0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {formatNumber(selectedRow.rsl, 4)}
                </p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Price</p>
                <p className="text-base font-bold">{formatCurrency(selectedRow.price)}</p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">HV30</p>
                <p className={`text-base font-bold ${selectedRow.hv30 > 60 ? 'text-amber-400' : 'text-foreground'}`}>
                  {selectedRow.hv30 != null ? `${formatNumber(selectedRow.hv30, 1)}%` : '—'}
                </p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Beta</p>
                <p className="text-base font-bold">
                  {selectedRow.beta != null ? formatNumber(selectedRow.beta, 2) : '—'}
                </p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Earnings</p>
                <p className={`text-base font-bold ${selectedRow.dte != null && selectedRow.dte < 14 ? 'text-red-400' : 'text-foreground'}`}>
                  {selectedRow.dte != null ? `${selectedRow.dte}d` : '—'}
                </p>
                {selectedRow.dte != null && selectedRow.dte < 14 && (
                  <p className="text-[10px] text-red-400 mt-0.5">Earnings bald!</p>
                )}
              </div>
            </div>

            {/* Sector & Interpretation */}
            <div className="flex items-center justify-between px-1">
              <div className="flex items-center gap-4">
                <span className="text-xs text-muted-foreground">
                  Sektor: <span className="text-foreground font-medium">{selectedRow.sector}</span>
                </span>
                {selectedRow.industry && (
                  <span className="text-xs text-muted-foreground">
                    Industrie: <span className="text-foreground font-medium">{selectedRow.industry}</span>
                  </span>
                )}
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowExplain(!showExplain)}
                className={showExplain ? 'text-primary' : 'text-muted-foreground'}
              >
                <Info className="w-3.5 h-3.5 mr-1" />
                <span className="text-xs">Explain</span>
              </Button>
            </div>

            {/* Explain Section */}
            {showExplain && (
              <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 space-y-3 text-sm">
                <h4 className="font-semibold text-primary text-xs uppercase tracking-wider">Berechnung & Datengrundlage</h4>
                <div className="space-y-2 text-muted-foreground leading-relaxed">
                  <div>
                    <span className="text-foreground font-medium">RSL = {formatNumber(selectedRow.rsl, 4)}</span>
                    <p className="text-xs mt-0.5">
                      Berechnet als: Aktueller Kurs ({formatCurrency(selectedRow.price)}) / SMA200.{' '}
                      Implizierter SMA200: ca. {formatCurrency(selectedRow.price / selectedRow.rsl)}.{' '}
                      {selectedRow.rsl >= 1.0
                        ? `Die Aktie notiert ${formatNumber((selectedRow.rsl - 1) * 100, 1)}% über ihrem SMA200.`
                        : `Die Aktie notiert ${formatNumber((1 - selectedRow.rsl) * 100, 1)}% unter ihrem SMA200.`
                      }
                    </p>
                  </div>
                  <div>
                    <span className="text-foreground font-medium">Zone: {selectedRow.rsl_zone?.toUpperCase()}</span>
                    <p className="text-xs mt-0.5">
                      {selectedRow.rsl_zone === 'overheated' && 'RSL > 2.0: Extremes Momentum, aber hohes Rückschlagrisiko. Historisch Korrektur-anfällig.'}
                      {selectedRow.rsl_zone === 'very_strong' && 'RSL 1.8–2.0: Sehr starkes Momentum. Trend intakt, aber Aufmerksamkeit empfohlen.'}
                      {selectedRow.rsl_zone === 'strong' && 'RSL 1.3–1.8: Überdurchschnittliches Momentum. Idealer Bereich für Momentum-Trading.'}
                      {selectedRow.rsl_zone === 'normal' && 'RSL 1.0–1.3: Gesunder Aufwärtstrend. Stabiles Momentum ohne Übertreibung.'}
                      {selectedRow.rsl_zone === 'weak' && 'RSL < 1.0: Abwärtstrend. Kurs unter SMA200. Nicht für Momentum-Strategie geeignet.'}
                    </p>
                  </div>
                  <div>
                    <span className="text-foreground font-medium">Rank #{selectedRow.rank} / Percentile {formatNumber(selectedRow.percentile, 1)}%</span>
                    <p className="text-xs mt-0.5">
                      {formatNumber(selectedRow.percentile, 0)}% aller S&P 500 Aktien haben einen niedrigeren RSL.
                      Signal: {selectedRow.above_threshold ? 'HOLD' : 'EXIT'} (Schwelle: Percentile {'>='} {100 - params.exit_percentile}%).
                    </p>
                  </div>
                  <div className="pt-2 border-t border-border/30">
                    <p className="text-[10px] text-muted-foreground">
                      <span className="font-medium">Datenquelle:</span> Live-Kurse aus OptionDataMerged, SMA200 aus TechnicalIndicatorsMasterData.
                      Ranking wird alle 5 Minuten neu berechnet. Universum: S&P 500 ({summary?.total_stocks || '~500'} Aktien).
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              {[
                { name: 'TradingView', url: `https://www.tradingview.com/chart/?symbol=${selectedRow.symbol}` },
                { name: 'Finviz', url: `https://finviz.com/quote.ashx?t=${selectedRow.symbol}` },
                { name: 'Yahoo Finance', url: `https://finance.yahoo.com/quote/${selectedRow.symbol}` },
                { name: 'Claude AI', url: getClaudeAnalysisUrl(selectedRow.symbol, selectedRow.company_name) },
              ].map((link) => (
                <a key={link.name} href={link.url} target="_blank" rel="noopener"
                  className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-secondary/80 hover:bg-primary/20 hover:text-primary transition-all border border-border/30">
                  <ExternalLink className="w-3 h-3" /> {link.name}
                </a>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
