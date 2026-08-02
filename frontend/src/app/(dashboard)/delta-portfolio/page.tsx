'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getOptionDelta, getStockPrices } from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { DataTable, Column } from '@/components/ui/data-table';
import { formatCurrency } from '@/lib/utils';
import {
  useDeltaPortfolioStore,
  type Position,
  type OptionPosition,
} from '@/lib/deltaPortfolioStore';
import { parseIbkrCsv } from '@/lib/ibkrCsv';
import { deltaRegime } from '@/lib/deltaPortfolio';
import { HedgeSection } from './HedgeSection';
import { RiskGraph } from './RiskGraph';
import { Upload, Plus, Trash2, X } from 'lucide-react';

// Schlüssel für Options-Delta-Cache: eindeutig pro Kontrakt
const optKey = (p: OptionPosition) => `${p.symbol}|${p.contract_type}|${p.strike}|${p.expiry}`;

export default function DeltaPortfolioPage() {
  const { positions, setPositions, addPosition, removePosition, clear } = useDeltaPortfolioStore();

  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [importErr, setImportErr] = useState<string | null>(null);

  // Manuelle Eingabe-Formulare
  const [stockForm, setStockForm] = useState({ symbol: '', qty: 100, direction: 'Long' as 'Long' | 'Short' });
  const [optForm, setOptForm] = useState({
    symbol: '', contract_type: 'call' as 'call' | 'put', strike: 150,
    expiry: '', contracts: 1, direction: 'Long' as 'Long' | 'Short',
  });

  // ── Marktdaten laden (Preise batch + Delta pro Option) ──────────────────────
  const symbols = useMemo(
    () => Array.from(new Set(positions.map((p) => p.symbol))),
    [positions],
  );
  const options = useMemo(
    () => positions.filter((p): p is OptionPosition => p.type === 'option'),
    [positions],
  );

  const { data: prices = {} } = useQuery({
    queryKey: ['dpt-prices', symbols],
    queryFn: () => getStockPrices(symbols),
    enabled: symbols.length > 0,
  });

  const { data: optionDeltas = {} } = useQuery({
    queryKey: ['dpt-deltas', options.map(optKey)],
    queryFn: async () => {
      const entries = await Promise.all(
        options.map(async (o) => {
          const { delta } = await getOptionDelta({
            symbol: o.symbol, strike: o.strike, expiry: o.expiry, contract_type: o.contract_type,
          });
          return [optKey(o), delta] as const;
        }),
      );
      return Object.fromEntries(entries) as Record<string, number | null>;
    },
    enabled: options.length > 0,
  });

  // ── Delta-Berechnung pro Position ───────────────────────────────────────────
  const rows = useMemo(() => {
    return positions.map((pos, i) => {
      const sign = pos.direction === 'Long' ? 1 : -1;
      const price = prices[pos.symbol] ?? null;
      if (pos.type === 'stock') {
        const posDelta = sign * pos.qty * 1.0;
        return {
          idx: i,
          Symbol: pos.symbol,
          Typ: `${pos.direction === 'Long' ? '📈' : '📉'} ${pos.direction} Stock`,
          Details: `${pos.qty} Stück`,
          deltaUnit: sign * 1.0,
          posDelta,
          price,
          notional: price != null ? price * pos.qty : null,
          status: '✅',
        };
      }
      const raw = optionDeltas[optKey(pos)] ?? null;
      const posDelta = raw != null ? sign * pos.contracts * 100 * raw : 0;
      return {
        idx: i,
        Symbol: pos.symbol,
        Typ: `${pos.contract_type === 'call' ? '🟢' : '🔴'} ${pos.direction} ${pos.contract_type[0].toUpperCase()}${pos.contract_type.slice(1)}`,
        Details: `Strike ${pos.strike.toFixed(0)} | ${pos.expiry} | ${pos.contracts} Kontrakte`,
        deltaUnit: raw != null ? sign * raw : null,
        posDelta,
        price,
        notional: price != null ? price * 100 * pos.contracts : null,
        status: raw != null ? '✅' : '⚠️ kein Delta',
      };
    });
  }, [positions, prices, optionDeltas]);

  const totalDelta = useMemo(() => rows.reduce((a, r) => a + r.posDelta, 0), [rows]);
  const bullish = rows.filter((r) => r.posDelta > 0).reduce((a, r) => a + r.posDelta, 0);
  const bearish = rows.filter((r) => r.posDelta < 0).reduce((a, r) => a + r.posDelta, 0);
  const regime = deltaRegime(totalDelta);

  // ── Handler ─────────────────────────────────────────────────────────────────
  function handleCsv(e: React.ChangeEvent<HTMLInputElement>) {
    setImportMsg(null); setImportErr(null);
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const imported = parseIbkrCsv(String(reader.result));
        if (!imported.length) {
          setImportErr('Keine offenen Positionen gefunden. Ist das die richtige Datei?');
          return;
        }
        setPositions(imported);
        const nStocks = imported.filter((p) => p.type === 'stock').length;
        const nOpts = imported.filter((p) => p.type === 'option').length;
        setImportMsg(`✅ ${imported.length} Positionen importiert — ${nStocks} Aktien, ${nOpts} Optionen`);
      } catch (err: any) {
        setImportErr(`Fehler beim Parsen: ${err?.message || err}`);
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  }

  function addStock() {
    if (!stockForm.symbol.trim()) return;
    addPosition({ type: 'stock', symbol: stockForm.symbol.toUpperCase().trim(), qty: stockForm.qty, direction: stockForm.direction });
    setStockForm({ ...stockForm, symbol: '' });
  }
  function addOption() {
    if (!optForm.symbol.trim() || !optForm.expiry.trim()) return;
    addPosition({
      type: 'option', symbol: optForm.symbol.toUpperCase().trim(), contract_type: optForm.contract_type,
      strike: optForm.strike, expiry: optForm.expiry.trim(), contracts: optForm.contracts, direction: optForm.direction,
    });
    setOptForm({ ...optForm, symbol: '', expiry: '' });
  }

  const columns: Column[] = [
    { key: 'Symbol', label: 'Symbol', sortable: true },
    { key: 'Typ', label: 'Typ' },
    { key: 'Details', label: 'Details' },
    { key: 'deltaUnit', label: 'Delta/Einheit', align: 'right', format: (v) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${Number(v).toFixed(3)}`) },
    { key: 'posDelta', label: 'Pos.-Delta', align: 'right', colorCode: 'pnl', format: (v) => `${v >= 0 ? '+' : ''}${Number(v).toFixed(1)}` },
    { key: 'price', label: 'Kurs', align: 'right', format: (v) => (v == null ? '—' : formatCurrency(v)) },
    { key: 'notional', label: 'Notional', align: 'right', format: (v) => (v == null ? '—' : formatCurrency(v)) },
    { key: 'status', label: 'Status', align: 'center' },
  ];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold">📐 Delta Portfolio Tracker</h1>
        <p className="text-sm text-muted-foreground">
          Netto-Delta aller Positionen live aus der DB — bei jedem Aufruf neu berechnet. Positionen bleiben nur im Browser.
        </p>
      </div>

      {/* CSV-Import */}
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Upload className="h-4 w-4" /> Portfolio aus CapTrader/IBKR CSV importieren
          </div>
          <p className="text-xs text-muted-foreground">
            Activity Statement hochladen. Jeder Import ersetzt das aktuelle Portfolio — nichts wird gespeichert.
          </p>
          <input type="file" accept=".csv" onChange={handleCsv}
            className="block text-sm file:mr-3 file:rounded-md file:border file:border-border file:bg-secondary file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-muted" />
          {importMsg && <p className="text-sm text-positive">{importMsg}</p>}
          {importErr && <p className="text-sm text-negative">{importErr}</p>}
        </CardContent>
      </Card>

      {/* Manuell hinzufügen */}
      <Card>
        <CardContent className="p-4 space-y-4">
          <div className="flex items-center gap-2 text-sm font-medium"><Plus className="h-4 w-4" /> Position manuell hinzufügen</div>

          {/* Aktie */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 items-end">
            <div><label className="text-xs text-muted-foreground">Aktie · Symbol</label>
              <Input value={stockForm.symbol} onChange={(e) => setStockForm({ ...stockForm, symbol: e.target.value })} placeholder="AAPL" /></div>
            <div><label className="text-xs text-muted-foreground">Stück</label>
              <Input type="number" value={stockForm.qty} onChange={(e) => setStockForm({ ...stockForm, qty: Number(e.target.value) })} /></div>
            <div><label className="text-xs text-muted-foreground">Richtung</label>
              <select value={stockForm.direction} onChange={(e) => setStockForm({ ...stockForm, direction: e.target.value as any })}
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"><option>Long</option><option>Short</option></select></div>
            <Button onClick={addStock} className="md:col-span-2">Aktie hinzufügen</Button>
          </div>

          <div className="border-t border-border" />

          {/* Option */}
          <div className="grid grid-cols-2 md:grid-cols-7 gap-2 items-end">
            <div><label className="text-xs text-muted-foreground">Option · Symbol</label>
              <Input value={optForm.symbol} onChange={(e) => setOptForm({ ...optForm, symbol: e.target.value })} placeholder="AAPL" /></div>
            <div><label className="text-xs text-muted-foreground">Typ</label>
              <select value={optForm.contract_type} onChange={(e) => setOptForm({ ...optForm, contract_type: e.target.value as any })}
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"><option value="call">call</option><option value="put">put</option></select></div>
            <div><label className="text-xs text-muted-foreground">Strike</label>
              <Input type="number" value={optForm.strike} onChange={(e) => setOptForm({ ...optForm, strike: Number(e.target.value) })} /></div>
            <div><label className="text-xs text-muted-foreground">Verfall</label>
              <Input value={optForm.expiry} onChange={(e) => setOptForm({ ...optForm, expiry: e.target.value })} placeholder="2026-08-15" /></div>
            <div><label className="text-xs text-muted-foreground">Kontrakte</label>
              <Input type="number" value={optForm.contracts} onChange={(e) => setOptForm({ ...optForm, contracts: Number(e.target.value) })} /></div>
            <div><label className="text-xs text-muted-foreground">Richtung</label>
              <select value={optForm.direction} onChange={(e) => setOptForm({ ...optForm, direction: e.target.value as any })}
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"><option>Long</option><option>Short</option></select></div>
            <Button onClick={addOption}>Option hinzufügen</Button>
          </div>
        </CardContent>
      </Card>

      {positions.length === 0 ? (
        <Card><CardContent className="p-8 text-center text-muted-foreground">
          Noch keine Positionen. Oben eine Aktie/Option hinzufügen oder ein CSV importieren.
        </CardContent></Card>
      ) : (
        <>
          {/* Netto-Delta-Banner */}
          <div className="rounded-lg border px-5 py-4" style={{ background: regime.bg, borderColor: regime.border }}>
            <div className="flex items-baseline gap-3 flex-wrap">
              <span className="text-2xl font-extrabold text-foreground">{regime.label}</span>
              <span className="text-base font-semibold text-foreground">
                · Netto-Delta: <span style={{ color: regime.border }}>{totalDelta >= 0 ? '+' : ''}{totalDelta.toFixed(1)}</span>
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Bei einer 1%-Bewegung des Marktes ändert sich dein Portfolio um ca.{' '}
              <b className="text-foreground">{(totalDelta * 0.01).toFixed(2)} × Kurswert</b> pro Aktie.
            </p>
          </div>

          {/* Metriken */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Metric label="Netto-Delta" value={`${totalDelta >= 0 ? '+' : ''}${totalDelta.toFixed(1)}`} />
            <Metric label="Positionen" value={String(positions.length)} />
            <Metric label="Bullish Delta" value={`+${bullish.toFixed(1)}`} />
            <Metric label="Bearish Delta" value={bearish.toFixed(1)} />
          </div>

          {/* Positions-Tabelle */}
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">📊 Delta pro Position</h2>
            <Button variant="outline" size="sm" onClick={clear} className="text-negative">
              <Trash2 className="h-3.5 w-3.5 mr-1" /> Alle löschen
            </Button>
          </div>
          <DataTable data={rows} columns={columns} maxHeight="480px" />

          {/* Einzeln entfernen */}
          <div className="flex flex-wrap gap-2">
            {rows.map((r) => (
              <button key={r.idx} onClick={() => removePosition(r.idx)}
                className="inline-flex items-center gap-1 rounded-full border border-border bg-secondary px-3 py-1 text-xs hover:bg-muted">
                <X className="h-3 w-3" /> {r.Symbol} — {r.Details}
              </button>
            ))}
          </div>

          {/* Hedge-Rechner, Vorschläge, Kandidaten-Tabs */}
          <HedgeSection positions={positions} totalDelta={totalDelta} prices={prices} />

          {/* Risikograf */}
          <RiskGraph positions={positions} prices={prices} />
        </>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Card><CardContent className="p-4">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-2xl font-bold mt-0.5">{value}</div>
    </CardContent></Card>
  );
}
