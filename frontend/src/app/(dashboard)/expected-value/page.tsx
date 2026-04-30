'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { simulateExpectedValue } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { LoadingState } from '@/components/ui/spinner';

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
      <h1 className="text-2xl font-bold">Expected Value - Monte Carlo</h1>
      <p className="text-sm text-muted-foreground">Simulate the expected value of an options strategy using Monte Carlo simulation.</p>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Simulation Parameters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">Current Price</label>
              <Input type="number" step="0.01" value={params.current_price} onChange={(e) => setParams({ ...params, current_price: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">DTE</label>
              <Input type="number" value={params.dte} onChange={(e) => setParams({ ...params, dte: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Volatility</label>
              <Input type="number" step="0.01" value={params.volatility} onChange={(e) => setParams({ ...params, volatility: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Risk-Free Rate</label>
              <Input type="number" step="0.001" value={params.risk_free_rate} onChange={(e) => setParams({ ...params, risk_free_rate: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Simulations</label>
              <Input type="number" step="10000" value={params.num_simulations} onChange={(e) => setParams({ ...params, num_simulations: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Random Seed</label>
              <Input type="number" value={params.random_seed} onChange={(e) => setParams({ ...params, random_seed: +e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">IV Correction</label>
              <select className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" value={params.iv_correction} onChange={(e) => setParams({ ...params, iv_correction: e.target.value })}>
                <option value="auto">Auto</option>
                <option value="none">None</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Dividend Yield</label>
              <Input type="number" step="0.001" value={params.dividend_yield} onChange={(e) => setParams({ ...params, dividend_yield: +e.target.value })} />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Options Legs */}
      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-base">Option Legs</CardTitle>
          <Button variant="outline" size="sm" onClick={addOption}>Add Leg</Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {options.map((opt, i) => (
            <div key={i} className="flex gap-3 items-end border p-3 rounded-md">
              <div className="flex-1">
                <label className="text-xs text-muted-foreground">Strike</label>
                <Input type="number" step="0.5" value={opt.strike} onChange={(e) => updateOption(i, 'strike', +e.target.value)} />
              </div>
              <div className="flex-1">
                <label className="text-xs text-muted-foreground">Premium</label>
                <Input type="number" step="0.01" value={opt.premium} onChange={(e) => updateOption(i, 'premium', +e.target.value)} />
              </div>
              <div className="flex-1">
                <label className="text-xs text-muted-foreground">Type</label>
                <select className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" value={opt.type} onChange={(e) => updateOption(i, 'type', e.target.value)}>
                  <option>Put Sold</option>
                  <option>Put Bought</option>
                  <option>Call Sold</option>
                  <option>Call Bought</option>
                </select>
              </div>
              <Button variant="destructive" size="sm" onClick={() => removeOption(i)}>X</Button>
            </div>
          ))}
        </CardContent>
      </Card>

      <Button onClick={() => mutation.mutate()} disabled={mutation.isPending} className="w-full">
        {mutation.isPending ? 'Simulating...' : 'Start Simulation'}
      </Button>

      {mutation.data && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Results</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Expected Value</p>
                <p className="text-2xl font-bold">${mutation.data.expected_value}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Corrected Volatility</p>
                <p className="text-lg">{mutation.data.corrected_volatility}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">IV Correction Factor</p>
                <p className="text-lg">{mutation.data.iv_correction_factor}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
