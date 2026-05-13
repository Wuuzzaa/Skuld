'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getRslMomentum } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatNumber } from '@/lib/utils';
import { X, ExternalLink, HelpCircle, ChevronDown, ChevronRight, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function RslMomentumPage() {
  const [params, setParams] = useState({
    top_n: 5,
    max_per_sector: 2,
    exit_percentile: 50,
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
        <span className={`font-semibold ${row.is_top_pick ? 'text-emerald-400' : 'text-foreground'}`}>
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
        <span className={`font-bold ${v >= 1.2 ? 'text-emerald-400' : v >= 1.0 ? 'text-foreground' : 'text-red-400'}`}>
          {formatNumber(v, 4)}
        </span>
      ),
    },
    { key: 'price', label: 'Price', format: formatCurrency, sortable: true, align: 'right' },
    {
      key: 'percentile',
      label: 'Percentile',
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
            type="number" min={10} max={90} step={5}
            value={params.exit_percentile}
            onChange={(e) => setParams({ ...params, exit_percentile: +e.target.value })}
            className="w-20 h-8"
          />
        </div>
      </div>

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
                    <span className="text-xs text-muted-foreground">#{stock.rank}</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground truncate mt-1">{stock.company_name}</p>
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-xs font-mono">RSL {formatNumber(stock.rsl, 3)}</span>
                    <span className="text-xs">{formatCurrency(stock.price)}</span>
                  </div>
                  <span className="text-[10px] text-muted-foreground">{stock.sector}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Summary Stats */}
      {summary && !isLoading && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
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
                q: 'Was bedeuten die Parameter?',
                a: 'Top N = Anzahl Positionen im Portfolio (Standard: 5). Max/Sector = maximale Aktien aus demselben Sektor, verhindert Klumpenrisiko (Standard: 2). Exit below Top % = Ab welcher Percentile-Schwelle verkauft wird (Standard: 50% = untere Hälfte).',
              },
              {
                q: 'Wann kaufen und verkaufen?',
                a: 'HOLD = Position bleibt im Portfolio, sie ist noch im oberen Bereich des Rankings. EXIT = Position ist unter die Schwelle gefallen und muss verkauft werden. Neue Aktien werden nur gekauft, wenn ein Platz frei wird (durch EXIT) und der Nachrücker die Sektor-Regeln erfüllt.',
              },
              {
                q: 'Wie oft rebalancen?',
                a: 'Einmal pro Woche reicht (z.B. Freitag Abend oder Montag Morgen). Tägliches Checken erzeugt nur unnötige Trades. Die Strategie ist mechanisch — Signale werden ohne Diskussion umgesetzt, kein "Market Timing".',
              },
              {
                q: 'Sektor-Diversifikation erklärt',
                a: 'Die Max/Sector-Regel verhindert, dass alle Top-Picks aus einem einzigen Sektor kommen (z.B. nur Halbleiter). Der Algorithmus geht das Ranking von oben nach unten durch und überspringt Aktien, wenn ihr Sektor bereits das Maximum erreicht hat. So entsteht automatisch ein diversifiziertes Portfolio.',
              },
              {
                q: 'Positionsgröße & Einstieg',
                a: 'Gleichgewichtet: Jede Position bekommt den gleichen Anteil (bei Top 5 = je 20%). Beim Ersteinstieg alle Top-Picks gleichzeitig kaufen. Bei einem Broker mit niedrigen Gebühren (z.B. IBKR) sind die wöchentlichen Rotationen kostengünstig.',
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
              </div>
              <Button variant="ghost" size="sm" onClick={() => { setSelectedRow(null); setSelectedIndex(null); setShowExplain(false); }}>
                <X className="w-4 h-4" />
              </Button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Rank</p>
                <p className="text-base font-bold">#{selectedRow.rank}</p>
                <p className="text-[10px] text-muted-foreground italic mt-1">
                  Position von {summary?.total_stocks || '~500'} S&P 500 Aktien
                </p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">RSL</p>
                <p className={`text-base font-bold ${selectedRow.rsl >= 1.0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {formatNumber(selectedRow.rsl, 4)}
                </p>
                <p className="text-[10px] text-muted-foreground italic mt-1">
                  Kurs / SMA200 —{' '}
                  {selectedRow.rsl >= 1.5
                    ? <span className="text-emerald-400 not-italic font-medium">Sehr starker Trend</span>
                    : selectedRow.rsl >= 1.2
                    ? <span className="text-emerald-400/80 not-italic font-medium">Starker Trend</span>
                    : selectedRow.rsl >= 1.0
                    ? <span className="text-foreground not-italic font-medium">Aufwärtstrend</span>
                    : selectedRow.rsl >= 0.9
                    ? <span className="text-amber-400 not-italic font-medium">Neutral/Schwach</span>
                    : <span className="text-red-400 not-italic font-medium">Abwärtstrend</span>
                  }
                </p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Price</p>
                <p className="text-base font-bold">{formatCurrency(selectedRow.price)}</p>
                <p className="text-[10px] text-muted-foreground italic mt-1">
                  Aktueller Kurs
                </p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Percentile</p>
                <p className="text-base font-bold">{formatNumber(selectedRow.percentile, 1)}%</p>
                <p className="text-[10px] text-muted-foreground italic mt-1">
                  {formatNumber(selectedRow.percentile, 0)}% aller Aktien sind schwächer
                </p>
              </div>
              <div className="p-2 rounded bg-muted/30">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Signal</p>
                <p className={`text-base font-bold ${selectedRow.above_threshold ? 'text-emerald-400' : 'text-red-400'}`}>
                  {selectedRow.above_threshold ? 'HOLD' : 'EXIT'}
                </p>
                <p className="text-[10px] text-muted-foreground italic mt-1">
                  {selectedRow.above_threshold
                    ? `Über Schwelle (Top ${params.exit_percentile}%)`
                    : `Unter Schwelle — verkaufen`
                  }
                </p>
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
                      Berechnet als: Aktueller Kurs ({formatCurrency(selectedRow.price)}) / 200-Tage-Durchschnitt (SMA200).{' '}
                      Der SMA200 liegt damit bei ca. {formatCurrency(selectedRow.price / selectedRow.rsl)}.{' '}
                      {selectedRow.rsl >= 1.0
                        ? `Die Aktie notiert ${formatNumber((selectedRow.rsl - 1) * 100, 1)}% über ihrem SMA200.`
                        : `Die Aktie notiert ${formatNumber((1 - selectedRow.rsl) * 100, 1)}% unter ihrem SMA200.`
                      }
                    </p>
                  </div>
                  <div>
                    <span className="text-foreground font-medium">Rank #{selectedRow.rank} von {summary?.total_stocks || '~500'}</span>
                    <p className="text-xs mt-0.5">
                      Alle S&P 500 Aktien werden nach RSL absteigend sortiert. Rang 1 = höchster RSL = stärkstes Momentum.
                      {selectedRow.rank <= 10 && ' Diese Aktie gehört zu den Top 10 — extrem starkes relatives Momentum.'}
                      {selectedRow.rank > 10 && selectedRow.rank <= 50 && ' Solide im oberen Zehntel des Rankings.'}
                    </p>
                  </div>
                  <div>
                    <span className="text-foreground font-medium">Percentile = {formatNumber(selectedRow.percentile, 1)}%</span>
                    <p className="text-xs mt-0.5">
                      Formel: (Gesamtanzahl - Rang + 1) / Gesamtanzahl × 100.{' '}
                      Bedeutet: {formatNumber(selectedRow.percentile, 0)}% aller S&P 500 Aktien haben einen niedrigeren RSL.
                    </p>
                  </div>
                  <div>
                    <span className="text-foreground font-medium">Signal: {selectedRow.above_threshold ? 'HOLD' : 'EXIT'}</span>
                    <p className="text-xs mt-0.5">
                      Exit-Schwelle ist auf Top {params.exit_percentile}% gesetzt (= Percentile muss {'>='} {100 - params.exit_percentile}% sein).{' '}
                      Aktuelles Percentile: {formatNumber(selectedRow.percentile, 1)}% — {' '}
                      {selectedRow.above_threshold
                        ? 'liegt über der Schwelle, Position bleibt im Portfolio.'
                        : 'liegt unter der Schwelle, Position sollte verkauft und durch Nachrücker ersetzt werden.'
                      }
                    </p>
                  </div>
                  {selectedRow.is_top_pick && (
                    <div>
                      <span className="text-emerald-400 font-medium">Top Pick</span>
                      <p className="text-xs mt-0.5">
                        Diese Aktie ist einer der Top {params.top_n} Picks unter Berücksichtigung der Sektor-Diversifikation
                        (max {params.max_per_sector} pro Sektor). Der Algorithmus geht das Ranking von oben nach unten durch
                        und wählt Aktien aus, deren Sektor das Limit noch nicht erreicht hat.
                      </p>
                    </div>
                  )}
                  <div className="pt-2 border-t border-border/30">
                    <p className="text-[10px] text-muted-foreground">
                      <span className="font-medium">Datenquelle:</span> Live-Kurse aus OptionDataMerged (Polygon.io), SMA200 aus TechnicalIndicatorsMasterData.
                      Ranking wird alle 5 Minuten neu berechnet. Universum: S&P 500 Konstituenten ({summary?.total_stocks || '~500'} Aktien mit verfügbarem RSL).
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
