'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getEarningsPutCandidates, getEarningsPutOptions } from '@/lib/api';
import { DataTable, Column } from '@/components/ui/data-table';
import { LoadingState } from '@/components/ui/spinner';
import { formatCurrency, formatPercent } from '@/lib/utils';
import { TrendingUp, Shield, ShieldCheck, ChevronDown, ChevronUp } from 'lucide-react';

function Explainer({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-border/40 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-accent/30 transition-colors"
      >
        <span>{title}</span>
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>
      {open && <div className="px-3 pb-3 pt-1 text-xs text-muted-foreground space-y-1.5 bg-muted/10">{children}</div>}
    </div>
  );
}

function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex flex-col gap-0.5 p-3 bg-card rounded-lg border border-border/40">
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">{label}</span>
      <span className="text-lg font-bold text-foreground">{value}</span>
      {sub && <span className="text-[11px] text-muted-foreground">{sub}</span>}
    </div>
  );
}

export default function EarningsPutScreenerPage() {
  const [daysAhead, setDaysAhead] = useState(7);
  const [minIvRank, setMinIvRank] = useState(0);
  const [maxIvRank, setMaxIvRank] = useState(100);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<any>(null);
  const [minOi, setMinOi] = useState(50);
  const [minPremiumPct, setMinPremiumPct] = useState(1.0);
  const [safeOnly, setSafeOnly] = useState(false);
  const [selectedPut, setSelectedPut] = useState<any>(null);

  const { data: candidates, isLoading: loadingCandidates, isFetching: fetchingCandidates } = useQuery({
    queryKey: ['earnings-put-candidates', daysAhead],
    queryFn: () => getEarningsPutCandidates({ days_ahead: daysAhead }),
  });

  const { data: putsRaw, isLoading: loadingPuts, isFetching: fetchingPuts } = useQuery({
    queryKey: ['earnings-put-options', selectedSymbol, minOi],
    queryFn: () => getEarningsPutOptions({ symbol: selectedSymbol!, min_oi: minOi }),
    enabled: !!selectedSymbol,
  });

  // Apply IV Rank filter on client
  const filteredCandidates = useMemo(() => {
    if (!candidates?.length) return [];
    return candidates.filter((c: any) => {
      const iv = c.iv_rank;
      if (iv == null) return true;
      return iv >= minIvRank && iv <= maxIvRank;
    });
  }, [candidates, minIvRank, maxIvRank]);

  // Apply safe-only + premium filter on client
  const puts = useMemo(() => {
    if (!putsRaw?.length || !selectedCandidate) return [];
    const safeThreshold =
      selectedCandidate.live_stock_price != null && selectedCandidate.expected_move != null
        ? selectedCandidate.live_stock_price - selectedCandidate.expected_move
        : null;

    return putsRaw
      .map((p: any) => ({
        ...p,
        is_safe: safeThreshold != null ? p.strike_price < safeThreshold : false,
        close_at_90pct: p.premium_option_price != null ? Math.round(p.premium_option_price * 0.10 * 100) / 100 : null,
      }))
      .filter((p: any) => {
        if (safeOnly && !p.is_safe) return false;
        if (p.premium_pct != null && p.premium_pct < minPremiumPct) return false;
        return true;
      });
  }, [putsRaw, safeOnly, minPremiumPct, selectedCandidate]);

  const candidateColumns: Column[] = [
    { key: 'symbol', label: 'Symbol', sortable: true, format: (v: string) => <span className="font-semibold">{v}</span> },
    { key: 'company_name', label: 'Name', sortable: true, format: (v: string) => <span className="text-muted-foreground">{v}</span> },
    { key: 'earnings_date', label: 'Earnings', sortable: true, format: (v: string) => v ? String(v).split('T')[0] : '—' },
    { key: 'days_to_earnings', label: 'Tage', sortable: true, align: 'right' },
    { key: 'live_stock_price', label: 'Kurs', sortable: true, align: 'right', format: (v: number) => v != null ? formatCurrency(v) : '—' },
    {
      key: 'expected_move',
      label: 'Exp. Move',
      sortable: true,
      align: 'right',
      format: (_v: number, row: any) =>
        row.expected_move != null && row.expected_move_pct != null
          ? `±${formatCurrency(row.expected_move)} (${row.expected_move_pct.toFixed(1)}%)`
          : '—',
    },
    {
      key: 'iv_rank',
      label: 'IV Rank',
      sortable: true,
      align: 'right',
      format: (v: number) =>
        v == null ? '—' : (
          <span className={v >= 60 ? 'text-positive font-medium' : v >= 40 ? 'text-yellow-400' : 'text-muted-foreground'}>
            {v.toFixed(0)}%
          </span>
        ),
    },
    {
      key: 'market_cap',
      label: 'Mkt Cap',
      sortable: true,
      align: 'right',
      format: (v: number) =>
        v == null ? '—' : v >= 1e12 ? `$${(v / 1e12).toFixed(1)}T` : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${(v / 1e6).toFixed(0)}M`,
    },
  ];

  const putColumns: Column[] = [
    {
      key: 'is_safe',
      label: '',
      sortable: false,
      format: (v: boolean) =>
        v ? <ShieldCheck className="w-3.5 h-3.5 text-positive" /> : <Shield className="w-3.5 h-3.5 text-muted-foreground/40" />,
    },
    { key: 'expiration_date', label: 'Expiry', sortable: true, format: (v: string) => v ? String(v).split('T')[0] : '—' },
    { key: 'days_to_expiration', label: 'DTE', sortable: true, align: 'right' },
    { key: 'strike_price', label: 'Strike', sortable: true, align: 'right', format: (v: number) => v != null ? formatCurrency(v) : '—' },
    { key: 'premium_option_price', label: 'Premium', sortable: true, align: 'right', format: (v: number) => v != null ? `$${v.toFixed(2)}` : '—' },
    { key: 'premium_pct', label: 'Prämie %', sortable: true, align: 'right', format: (v: number) => v != null ? `${v.toFixed(2)}%` : '—' },
    { key: 'close_at_90pct', label: 'Ziel (90%)', sortable: false, align: 'right', format: (v: number) => v != null ? `$${v.toFixed(2)}` : '—' },
    { key: 'open_interest', label: 'OI', sortable: true, align: 'right', format: (v: number) => v != null ? v.toLocaleString() : '—' },
    { key: 'greeks_delta', label: 'Delta', sortable: true, align: 'right', format: (v: number) => v != null ? v.toFixed(3) : '—' },
    { key: 'implied_volatility', label: 'IV', sortable: true, align: 'right', format: (v: number) => v != null ? `${(v * 100).toFixed(1)}%` : '—' },
  ];

  function handleCandidateClick(row: any) {
    setSelectedCandidate(row === selectedCandidate ? null : row);
    setSelectedSymbol(row === selectedCandidate ? null : row.symbol);
    setSelectedPut(null);
  }

  const safeThreshold =
    selectedCandidate?.live_stock_price != null && selectedCandidate?.expected_move != null
      ? selectedCandidate.live_stock_price - selectedCandidate.expected_move
      : null;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <TrendingUp className="w-6 h-6 text-orange-400" />
          <div>
            <h1 className="text-2xl font-bold">Earnings Put Screener</h1>
            <p className="text-xs text-muted-foreground mt-0.5">IV-Crush Strategie — Put unter Expected Move verkaufen, nächsten Morgen bei 90% Gewinn zurückkaufen</p>
          </div>
          {(fetchingCandidates || fetchingPuts) && <div className="w-2 h-2 rounded-full bg-orange-400 animate-pulse" />}
        </div>
      </div>

      {/* Strategie-Erklärung */}
      <Explainer title="Wie funktioniert die Strategie? (aufklappen)">
        <p className="font-medium text-foreground">Idee: IV-Crush nach Earnings</p>
        <p>Vor Earnings sind Optionen teuer — der Markt zahlt einen Aufpreis für die Unsicherheit. Sobald die Zahlen draußen sind, kollabiert diese Unsicherheitsprämie sofort (IV-Crush). Du profitierst davon, <span className="text-foreground font-medium">ohne die Richtung zu kennen</span>.</p>
        <ol className="list-decimal list-inside space-y-1 pt-1">
          <li>Put verkaufen mit Strike <span className="text-foreground font-medium">unterhalb des Expected Move</span> (Safe Zone)</li>
          <li>Nächsten Morgen nach Earnings: Buy-to-Close bei <span className="text-foreground font-medium">10% des Prämienpreises</span> (= 90% Gewinn einstreichen)</li>
          <li>Falls Zielorder nicht gefüllt: 60 min nach Marktöffnung zum Marktpreis schließen</li>
          <li>Bei Zuweisung: Covered Call auf die 100 Aktien verkaufen zur Kostenbasis-Rückgewinnung</li>
        </ol>
        <p className="pt-1 text-muted-foreground/70">Worst case: Aktie fällt unter deinen Strike → du kaufst 100 Aktien zu Strike-Preis, abzüglich der kassierten Prämie.</p>
      </Explainer>

      {/* Kandidaten-Filter */}
      <div className="flex flex-wrap items-center gap-4 p-3 bg-card rounded-lg border border-border/40">
        <div className="flex flex-col gap-1">
          <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Earnings binnen</label>
          <div className="flex gap-1">
            {[3, 5, 7, 10, 14].map((d) => (
              <button
                key={d}
                onClick={() => setDaysAhead(d)}
                className={`px-2.5 py-1 text-xs rounded transition-colors ${
                  daysAhead === d
                    ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
                    : 'bg-secondary/60 text-muted-foreground border border-border/50 hover:text-foreground'
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>
        <span className="text-border/60 text-sm self-end pb-0.5">|</span>
        <div className="flex items-end gap-2">
          <div className="flex flex-col gap-1">
            <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">IV Rank Min %</label>
            <input
              type="number"
              value={minIvRank}
              min={0}
              max={100}
              step={5}
              onChange={(e) => setMinIvRank(parseInt(e.target.value) || 0)}
              className="w-20 h-7 px-2 text-xs rounded-md border border-input bg-background"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">IV Rank Max %</label>
            <input
              type="number"
              value={maxIvRank}
              min={0}
              max={100}
              step={5}
              onChange={(e) => setMaxIvRank(parseInt(e.target.value) || 100)}
              className="w-20 h-7 px-2 text-xs rounded-md border border-input bg-background"
            />
          </div>
        </div>
        <span className="text-border/60 text-sm self-end pb-0.5">|</span>
        <div className="text-xs text-muted-foreground self-end pb-0.5">
          <span className="font-medium text-foreground">{filteredCandidates.length}</span>
          {candidates?.length !== filteredCandidates.length && (
            <span> von {candidates?.length ?? 0}</span>
          )} Kandidaten
        </div>
      </div>

      {/* Kandidatentabelle */}
      {loadingCandidates ? (
        <LoadingState message="Lade Earnings-Kandidaten..." />
      ) : (
        <DataTable
          data={filteredCandidates}
          columns={candidateColumns}
          defaultSort={{ key: 'days_to_earnings', direction: 'asc' }}
          onRowClick={handleCandidateClick}
          striped
        />
      )}

      {/* Put-Sektion für gewähltes Symbol */}
      {selectedCandidate && (
        <div className="space-y-3 pt-2">
          <div className="h-px bg-border/40" />

          {/* Kontext-Banner */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatTile label="Kurs" value={selectedCandidate.live_stock_price != null ? formatCurrency(selectedCandidate.live_stock_price) : '—'} />
            <StatTile
              label="Expected Move"
              value={selectedCandidate.expected_move != null ? `±${formatCurrency(selectedCandidate.expected_move)}` : '—'}
              sub={selectedCandidate.expected_move_pct != null ? `${selectedCandidate.expected_move_pct.toFixed(1)}% des Kurses` : undefined}
            />
            <StatTile
              label="Safe-Strike-Schwelle"
              value={safeThreshold != null ? `< ${formatCurrency(safeThreshold)}` : '—'}
              sub="Strike muss darunter liegen"
            />
            <StatTile
              label="Earnings"
              value={selectedCandidate.earnings_date ? String(selectedCandidate.earnings_date).split('T')[0] : '—'}
              sub={`${selectedCandidate.days_to_earnings} Tage`}
            />
          </div>

          <Explainer title="Was bedeutet Expected Move und Safe-Strike-Schwelle?">
            <p>Der <span className="text-foreground font-medium">Expected Move</span> wird aus dem ATM-Straddle berechnet (Call + Put am nächsten Verfallstag nach Earnings). Er zeigt, wie weit der Markt eine Bewegung für <span className="text-foreground font-medium">68% wahrscheinlich</span> hält.</p>
            <p>Beispiel: Kurs $100, Expected Move ±$8 → der Markt erwartet mit 68% Wahrscheinlichkeit, dass die Aktie zwischen $92 und $108 bleibt.</p>
            <p>Die <span className="text-foreground font-medium">Safe-Strike-Schwelle</span> ist Kurs minus Expected Move — also die untere Grenze dieser Zone. Puts mit Strike darunter (Safe Zone) werden nur dann ausgeübt, wenn die Aktie <span className="text-foreground font-medium">mehr fällt als erwartet</span>.</p>
            <p className="text-muted-foreground/70">IV Rank zeigt, wie teuer die Optionen historisch gesehen gerade sind. Über 60% = teuer = guter Zeitpunkt zum Verkaufen.</p>
          </Explainer>

          {/* Put-Filter */}
          <div className="flex flex-wrap items-center gap-4 p-3 bg-card rounded-lg border border-border/40">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-foreground">Puts — {selectedCandidate.symbol}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Min OI</label>
              <input
                type="number"
                value={minOi}
                min={0}
                step={25}
                onChange={(e) => setMinOi(parseInt(e.target.value) || 0)}
                className="w-20 h-7 px-2 text-xs rounded-md border border-input bg-background"
              />
            </div>
            <div className="flex items-center gap-1.5">
              <label className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Min Prämie %</label>
              <input
                type="number"
                value={minPremiumPct}
                min={0}
                max={10}
                step={0.1}
                onChange={(e) => setMinPremiumPct(parseFloat(e.target.value) || 0)}
                className="w-20 h-7 px-2 text-xs rounded-md border border-input bg-background"
              />
            </div>
            <label className="flex items-center gap-1.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={safeOnly}
                onChange={(e) => setSafeOnly(e.target.checked)}
                className="rounded border-border"
              />
              <ShieldCheck className="w-3.5 h-3.5 text-positive" />
              <span className="text-xs font-medium text-positive">Nur Safe Zone</span>
            </label>
          </div>

          {/* Put-Tabelle */}
          {loadingPuts ? (
            <LoadingState message={`Lade Puts für ${selectedCandidate.symbol}...`} />
          ) : puts.length === 0 ? (
            <p className="text-sm text-muted-foreground p-3">
              Keine Puts gefunden mit den aktuellen Filtern. Min OI oder Min Prämie % senken{safeOnly ? ', oder Safe-Zone-Filter deaktivieren' : ''}.
            </p>
          ) : (
            <DataTable
              data={puts}
              columns={putColumns}
              defaultSort={{ key: 'strike_price', direction: 'desc' }}
              onRowClick={(row) => setSelectedPut(row === selectedPut ? null : row)}
              striped
            />
          )}

          {/* Put-Detail Panel */}
          {selectedPut && (() => {
            const p = selectedPut;
            const premium = p.premium_option_price;
            const strike = p.strike_price;
            const price = selectedCandidate.live_stock_price;
            const breakeven = premium != null && strike != null ? strike - premium : null;
            const maxGain = premium != null ? Math.round(premium * 100 * 100) / 100 : null;
            const close90 = premium != null ? Math.round(premium * 0.10 * 100) / 100 : null;
            const profit90 = premium != null && close90 != null ? Math.round((premium - close90) * 100) / 100 : null;
            const distance = price != null && strike != null ? price - strike : null;
            const distancePct = distance != null && price ? distance / price * 100 : null;
            const assignProb = p.greeks_delta != null ? Math.abs(p.greeks_delta) * 100 : null;

            return (
              <div className="p-4 rounded-lg border border-border/60 bg-card space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-base">
                    {selectedCandidate.symbol} — ${strike?.toFixed(1)} Put ({p.days_to_expiration} DTE)
                  </h3>
                  <button onClick={() => setSelectedPut(null)} className="text-xs text-muted-foreground hover:text-foreground">Schließen</button>
                </div>

                {p.is_safe ? (
                  <div className="flex items-center gap-2 px-3 py-2 rounded-md bg-emerald-950/40 border border-emerald-500/20 text-positive text-xs">
                    <ShieldCheck className="w-4 h-4 flex-shrink-0" />
                    Safe Zone — Strike liegt unterhalb des Expected Move. Der Kurs müsste weiter fallen als der Markt erwartet.
                  </div>
                ) : (
                  <div className="flex items-center gap-2 px-3 py-2 rounded-md bg-red-950/30 border border-red-500/20 text-negative text-xs">
                    <Shield className="w-4 h-4 flex-shrink-0" />
                    Strike liegt innerhalb des Expected Move — realistisches Zuweisungsrisiko nach Earnings.
                  </div>
                )}

                {/* Kennzahlen */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div className="p-2 rounded bg-muted/30">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Prämie (pro Aktie)</p>
                    <p className="font-bold">{premium != null ? `$${premium.toFixed(2)}` : '—'}</p>
                  </div>
                  <div className="p-2 rounded bg-muted/30">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Prämie pro Kontrakt</p>
                    <p className="font-bold text-positive">{maxGain != null ? `$${maxGain.toFixed(2)}` : '—'}</p>
                  </div>
                  <div className="p-2 rounded bg-muted/30">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Breakeven</p>
                    <p className="font-bold">{breakeven != null ? `$${breakeven.toFixed(2)}` : '—'}</p>
                  </div>
                  <div className="p-2 rounded bg-muted/30">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Abstand zum Kurs</p>
                    <p className="font-bold">{distance != null ? `$${distance.toFixed(2)} (${distancePct?.toFixed(1)}%)` : '—'}</p>
                  </div>
                  <div className="p-2 rounded bg-muted/30">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Zielkurs (90% Gewinn)</p>
                    <p className="font-bold text-cyan-400">{close90 != null ? `$${close90.toFixed(2)}` : '—'}</p>
                  </div>
                  <div className="p-2 rounded bg-muted/30">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Gewinn bei 90%</p>
                    <p className="font-bold text-positive">{profit90 != null ? `$${(profit90 * 100).toFixed(2)} / Kontrakt` : '—'}</p>
                  </div>
                  <div className="p-2 rounded bg-muted/30">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Zuweisungswahrsch.</p>
                    <p className="font-bold">{assignProb != null ? `~${assignProb.toFixed(0)}%` : '—'}</p>
                  </div>
                  <div className="p-2 rounded bg-muted/30">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Prämie % vom Strike</p>
                    <p className="font-bold">{p.premium_pct != null ? `${p.premium_pct.toFixed(2)}%` : '—'}</p>
                  </div>
                </div>

                {/* Exit-Plan */}
                <div className="p-3 rounded-md bg-muted/20 border border-border/30 text-sm space-y-1">
                  <p className="font-semibold text-foreground text-xs uppercase tracking-wider text-muted-foreground mb-2">Exit-Plan</p>
                  <p>1. <span className="font-medium">Morgens nach Earnings:</span> Buy-to-Close bei {close90 != null ? `$${close90.toFixed(2)}` : '—'} (90% Gewinnziel)</p>
                  <p>2. <span className="font-medium">60 min nach Marktöffnung:</span> Falls nicht ausgeführt → zum Marktpreis schließen</p>
                  <p>3. <span className="font-medium">Bei Zuweisung:</span> 100 Aktien zu ${strike?.toFixed(2)} → Covered Call verkaufen zur Kostenbasis-Rückgewinnung</p>
                </div>

                <Explainer title="Was bedeuten diese Kennzahlen?">
                  <div className="space-y-1">
                    <p><span className="text-foreground font-medium">Prämie pro Aktie</span> — Betrag den du kassierst wenn du den Put verkaufst. 1 Kontrakt = 100 Aktien.</p>
                    <p><span className="text-foreground font-medium">Breakeven</span> — Strike minus Prämie. Erst darunter machst du Verlust. Bei Zuweisung kaufst du die Aktie effektiv zu diesem Preis.</p>
                    <p><span className="text-foreground font-medium">Ziel (90%)</span> — Zielpreis für deine Buy-to-Close Order am nächsten Morgen. Du hast die Prämie zu 10% des ursprünglichen Wertes zurückgekauft = 90% Gewinn einbehalten.</p>
                    <p><span className="text-foreground font-medium">Zuweisungswahrscheinlichkeit</span> — abgeleitet aus Delta. Delta −0.23 bedeutet ~23% Chance, dass der Put im Geld verfällt und du die Aktien kaufen musst.</p>
                    <p><span className="text-foreground font-medium">Delta</span> — negative Zahl bei Puts. Je näher an 0, desto weiter OTM (out of the money) und sicherer. −0.10 bis −0.25 ist typisch für diese Strategie.</p>
                    <p><span className="text-foreground font-medium">IV</span> — Implizite Volatilität dieses spezifischen Kontrakts. Hoch vor Earnings, kollabiert danach.</p>
                  </div>
                </Explainer>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}
