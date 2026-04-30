'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { simulateExpectedValue } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { LoadingState } from '@/components/ui/spinner';
import { Calculator, Plus, X, Play } from 'lucide-react';

type OptionType = 'Call Bought' | 'Call Sold' | 'Put Bought' | 'Put Sold';

interface OptionLeg {
  strike: number;
  premium: number;
  type: OptionType;
}

export default function ExpectedValuePage() {
  const [params, setParams] = useState({
    current_price: 170.94,
    dte: 63,
    volatility: 0.42,
    risk_free_rate: 0.03,
    dividend_yield: 0.0,
    num_simulations: 100000,
    random_seed: 42,
    iv_correction: 'auto',
  });

  const [options, setOptions] = useState<OptionLeg[]>([
    { strike: 150.0, premium: 3.47, type: 'Put Sold' },
    { strike: 145.0, premium: 1.72, type: 'Put Sold' },
  ]);

  const mutation = useMutation({
    mutationFn: () => simulateExpectedValue({ ...params, options }),
  });

  function addOption() {
    setOptions([...options, { strike: 150.0, premium: 3.0, type: 'Put Sold' }]);
  }

  function removeOption(index: number) {
    setOptions(options.filter((_, i) => i !== index));
  }

  function updateOption(index: number, field: keyof OptionLeg, value: any) {
    const updated = [...options];
    updated[index] = { ...updated[index], [field]: value };
    setOptions(updated);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold">Expected Value</h1>
        <span className="text-xs text-muted-foreground bg-secondary/60 px-2 py-0.5 rounded-full">Monte Carlo</span>
      </div>

      {/* Simulation Parameters */}
      <Card className="border-yellow-500/20">
        <CardContent className="pt-4">
          <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-3">Simulation Parameters</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Current Price</label>
              <Input type="number" step="0.01" value={params.current_price} onChange={(e) => setParams({ ...params, current_price: +e.target.value })} className="h-8 mt-1" />
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground uppercase tracking-wider">DTE</label>
              <Input type="number" value={params.dte} onChange={(e) => setParams({ ...params, dte: +e.target.value })} className="h-8 mt-1" />
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Volatility</label>
              <Input type="number" step="0.01" value={params.volatility} onChange={(e) => setParams({ ...params, volatility: +e.target.value })} className="h-8 mt-1" />
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Risk-Free Rate</label>
              <Input type="number" step="0.001" value={params.risk_free_rate} onChange={(e) => setParams({ ...params, risk_free_rate: +e.target.value })} className="h-8 mt-1" />
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Simulations</label>
              <Input type="number" step="10000" value={params.num_simulations} onChange={(e) => setParams({ ...params, num_simulations: +e.target.value })} className="h-8 mt-1" />
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Random Seed</label>
              <Input type="number" value={params.random_seed} onChange={(e) => setParams({ ...params, random_seed: +e.target.value })} className="h-8 mt-1" />
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground uppercase tracking-wider">IV Correction</label>
              <select className="w-full h-8 mt-1 rounded-md border border-input bg-background px-2 text-sm" value={params.iv_correction} onChange={(e) => setParams({ ...params, iv_correction: e.target.value })}>
                <option value="auto">Auto</option>
                <option value="none">None</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground uppercase tracking-wider">Dividend Yield</label>
              <Input type="number" step="0.001" value={params.dividend_yield} onChange={(e) => setParams({ ...params, dividend_yield: +e.target.value })} className="h-8 mt-1" />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Option Legs */}
      <Card className="border-yellow-500/20">
        <CardContent className="pt-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Option Legs</p>
            <Button variant="outline" size="sm" onClick={addOption} className="h-7 text-xs gap-1">
              <Plus className="w-3 h-3" /> Add Leg
            </Button>
          </div>
          {options.map((opt, i) => (
            <div key={i} className="flex gap-3 items-center p-3 rounded-lg border border-border/40 bg-muted/20">
              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                opt.type.includes('Sold') ? 'bg-red-400' : 'bg-emerald-400'
              }`} />
              <div className="flex-1">
                <label className="text-[10px] text-muted-foreground uppercase">Strike</label>
                <Input type="number" step="0.5" value={opt.strike} onChange={(e) => updateOption(i, 'strike', +e.target.value)} className="h-7 text-sm" />
              </div>
              <div className="flex-1">
                <label className="text-[10px] text-muted-foreground uppercase">Premium</label>
                <Input type="number" step="0.01" value={opt.premium} onChange={(e) => updateOption(i, 'premium', +e.target.value)} className="h-7 text-sm" />
              </div>
              <div className="flex-1">
                <label className="text-[10px] text-muted-foreground uppercase">Type</label>
                <select className="w-full h-7 rounded-md border border-input bg-background px-2 text-sm" value={opt.type} onChange={(e) => updateOption(i, 'type', e.target.value as OptionType)}>
                  <option>Put Sold</option>
                  <option>Put Bought</option>
                  <option>Call Sold</option>
                  <option>Call Bought</option>
                </select>
              </div>
              <Button variant="ghost" size="sm" onClick={() => removeOption(i)} className="h-7 w-7 p-0 text-muted-foreground hover:text-red-400">
                <X className="w-3.5 h-3.5" />
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Run Button */}
      <Button onClick={() => mutation.mutate()} disabled={mutation.isPending} className="w-full h-10 gap-2">
        <Play className="w-4 h-4" />
        {mutation.isPending ? 'Simulating...' : 'Run Simulation'}
      </Button>

      {/* Results */}
      {mutation.data && (
        <div className="grid grid-cols-3 gap-3">
          <div className="flex flex-col gap-1 p-4 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Expected Value</span>
            <span className={`text-2xl font-bold ${mutation.data.expected_value >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              ${mutation.data.expected_value}
            </span>
          </div>
          <div className="flex flex-col gap-1 p-4 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Corrected Vol</span>
            <span className="text-2xl font-bold">{mutation.data.corrected_volatility}</span>
          </div>
          <div className="flex flex-col gap-1 p-4 bg-card rounded-lg border border-border/40">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">IV Correction</span>
            <span className="text-2xl font-bold">{mutation.data.iv_correction_factor}</span>
          </div>
        </div>
      )}
    </div>
  );
}
