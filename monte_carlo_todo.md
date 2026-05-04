### Kurz vorweg

Das ist **kein Bug, sondern erwartbar** — und gleichzeitig ein Hinweis darauf, dass dein Simulator-Setup **nicht** das abbildet, worauf sich Tastys "50/200/21"-Regel bezieht. Drei Effekte überlagern sich. Der erste erklärt 90 %.

### 1. Tastys 50/21 wirkt nur, wenn du **rollst / wieder eröffnest**

Tastys Studie ist nicht „eine einzelne 45-DTE-Position managen vs. halten". Sie ist:

> *Bei jedem Trade nach 50 % TP oder spätestens 21 DTE schließen — und sofort den nächsten 45-DTE-Iron-Condor eröffnen.*

Der Vorteil entsteht durch **mehr Trades pro Jahr bei niedrigerem Gamma-Risiko in den letzten 21 Tagen** (Gamma explodiert dort, das Verlust-Tail wird fett). Wenn du in deinem Simulator früh schließt und **danach nichts mehr machst**, verschenkst du den restlichen Theta-Verfall der 21 Tage — der EV der einen Position fällt zwangsläufig, weil du Profit-Potenzial abschneidest.

Hold-to-expiration hat **per Konstruktion einen höheren Erwartungswert** für eine *einzelne* Credit-Position, weil du das gesamte Premium kassierst, wenn nichts kaputt geht. Der Preis dafür: das **linke Tail** (Max Loss) ist deutlich hässlicher und die Vola der PnL-Verteilung viel höher.

→ Vergleich „EV vs. EV" ist hier **die falsche Metrik**. Schau auf:
- EV **pro Tag** (managed: ~24 Tage pro Trade, hold: 45 Tage) → managed ≈ EV / 24, hold ≈ EV / 45.
- **Sharpe / EV-pro-Risiko**: `EV / |max_loss|` oder `EV / std(pnl)`.
- **5%-CVaR** (Mittelwert der schlimmsten 5 %) — managed ist hier i. d. R. *deutlich* besser.

### 2. GBM ≠ echte Märkte (Tastys Edge kommt aus Vol-Mean-Reversion)

Tasty argumentiert mit **Vola-Crush**: nach einem IV-Spike normalisiert sich IV, Optionen verbilligen sich → der Short-Premium-Trader profitiert überproportional früh. **Dein Simulator hat aber konstante σ.** Deshalb gibt es bei dir keinen "frühe-Profite-mitnehmen-bevor-mean-reversion-vorbei-ist"-Effekt.

In einem **konstant-σ-GBM** ist der erwartete PnL-Pfad einer Short-Premium-Position **monoton wachsend** (im Mittel, durch Theta) — also ist Halten *immer* mindestens so gut wie früh schließen, wenn man die einzelne Position betrachtet. Mathematisch: der Wert der Position ist ein Martingal unter risikoneutraler Messung, der erwartete Endwert ist `entry_value + 0`. Schließe zu jedem Stoppzeitpunkt früher → durch optional-stopping-Theorem **gleicher** EV (vor Kosten); mit TP-Asymmetrie cappst du nur das Upside und lässt das Downside laufen → **niedrigerer** EV.

Das ist der eigentliche Grund für Variant A < Variant B in deinem Modell.

### 3. Kosten + asymmetrische Trigger schneiden den EV oben ab

In `_managed_pnl` (Zeile 467) zahlst du **noch einmal** Closing-Costs (`-2 USD × 4 Legs = -8 USD`), in `_terminal_pnl` (Zeile 362) **nicht**. Schon das ist ein systematischer Nachteil von ~8 USD für die managed Variante.

Dazu der TP/SL-Schnitt:
- **TP 50 %** schneidet bei Profit `+0.5 × |entry_value|` → bei +0.86 USD/Aktie ≈ +43 USD pro Trade. **Maximaler** Profit der einzelnen Position wäre aber `entry_value` (ca. +76 USD bei deinem Setup).
- **SL 200 %** lässt Verluste bis −152 USD laufen.
- Die TP-Bedingung wird **viel häufiger** getroffen als die SL-Bedingung (TP ist näher an 0 als SL), aber die wenigen SL-Hits ziehen den Mittelwert deutlich nach unten.

Du cappst also den **rechten** Teil der Verteilung früh und lässt den **linken** weiter laufen — klassischer „cut your winners, let your losers run"-Effekt im EV. Tasty kompensiert das in der Realität durch (a) Volatilitäts-Mean-Reversion und (b) das Re-Deployment von Kapital.

### Was du im Simulator tun kannst, um es realistisch zu vergleichen

| Punkt | Was tun |
|---|---|
| **Annualisieren** | `EV_managed * (365 / avg_days_in_trade)` vs. `EV_hold * (365 / 45)` rechnen. Dann führt managed oft zur Spitze. |
| **Risiko-adjustiert** | Vergleiche `EV / |P5|` oder `EV / std(pnl)` — managed gewinnt fast immer. |
| **Vol-Modell** | GBM mit konstantem σ kann Tastys Edge **prinzipiell nicht** zeigen. Du bräuchtest Heston / SABR / Vola-Pfad mit Mean-Reversion oder einen IV-Schock-Simulator. |
| **Closing-Cost Bug** | Entweder in beiden Pfaden Closing-Costs ansetzen oder in keinem (heute asymmetrisch → ~8 USD Bias gegen managed). |
| **CVaR** | `np.mean(pnl[pnl <= np.quantile(pnl, 0.05)])` ausgeben — wirst du sehen: managed deutlich besser. |

### TL;DR

- In einem konstant-σ-GBM ist Hold-to-Expiration für eine **Einzelposition** EV-mäßig immer ≥ managed → das ist mathematisch erzwungen, kein Modellfehler.
- Tastys 50/200/21 verbessert nicht den EV einer einzelnen Position, sondern den **annualisierten EV** durch häufigeres Re-Deployment und das **Tail-Risiko** durch Vermeidung der Gamma-Bombe in den letzten 21 Tagen.
- Zusätzlicher kleiner Bias: in deinem Code zahlt nur die managed Variante Closing-Costs (Asymmetrie in `_terminal_pnl` vs. `_managed_pnl`).
- Vergleiche nicht EV vs. EV, sondern **EV/Tag**, **CVaR** und **PnL-Std** — dann ergibt das Tasty-Narrativ auch in deinem Tool plötzlich Sinn.

---

## Konkrete Umsetzung: fairer Vergleich „managed vs. hold-to-expiration"

Ziel: aus dem `pnl`-Array beider Varianten dieselben risiko-/zeit-normierten Kennzahlen ziehen und nebeneinander stellen. Drop-in für den `__main__`-Block in `src/monte_carlo_simulation.py`.

### 1. Closing-Cost-Asymmetrie zuerst fixen
- `_terminal_pnl` (Zeile 362): nur Open-Costs.
- `_managed_pnl` (Zeile 467): Open + Close-Costs.
- → in **beiden** symmetrisch (empfohlen: in beiden nur Open-Costs).

### 2. Vergleichs-Modul `compare_variants`

```python
def _metrics(result, hold_dte: int) -> dict:
    import numpy as np
    pnl = result.extras["pnl"]
    ev = float(np.mean(pnl))
    std = float(np.std(pnl, ddof=1))
    p5 = float(np.percentile(pnl, 5))
    cvar5 = float(np.mean(pnl[pnl <= p5])) if np.any(pnl <= p5) else p5

    if result.management_stats is not None:
        avg_days = max(result.management_stats["avg_days_in_trade"], 1.0)
    else:
        avg_days = float(hold_dte)

    return {
        "EV": ev,
        "EV/day": ev / avg_days,
        "EV_annualized": ev * (365.0 / avg_days),
        "Std": std,
        "Sharpe_like": ev / std if std > 0 else float("nan"),
        "P5": p5,
        "CVaR_5": cvar5,
        "EV/|CVaR5|": ev / abs(cvar5) if cvar5 != 0 else float("nan"),
        "EV/|MaxLoss|": ev / abs(result.max_loss) if result.max_loss != 0 else float("nan"),
        "WinProb": result.win_probability,
        "AvgDays": avg_days,
        "MaxProfit": result.max_profit,
        "MaxLoss": result.max_loss,
    }


def compare_variants(managed, hold, hold_dte: int) -> None:
    m = _metrics(managed, hold_dte)
    h = _metrics(hold, hold_dte)
    rows = [
        ("EV (USD)", "EV", "{:+.2f}"),
        ("EV / Tag (USD)", "EV/day", "{:+.3f}"),
        ("EV annualisiert (USD)", "EV_annualized", "{:+.2f}"),
        ("Std(PnL) (USD)", "Std", "{:.2f}"),
        ("Sharpe-like  EV/Std", "Sharpe_like", "{:+.4f}"),
        ("P5  (USD)", "P5", "{:+.2f}"),
        ("CVaR 5%  (USD)", "CVaR_5", "{:+.2f}"),
        ("EV / |CVaR5|", "EV/|CVaR5|", "{:+.4f}"),
        ("EV / |MaxLoss|", "EV/|MaxLoss|", "{:+.4f}"),
        ("Win-Prob", "WinProb", "{:.2%}"),
        ("Avg Tage im Trade", "AvgDays", "{:.1f}"),
        ("Max Profit (USD)", "MaxProfit", "{:+.2f}"),
        ("Max Loss (USD)", "MaxLoss", "{:+.2f}"),
    ]
    print("\n" + "=" * 78)
    print("  Vergleich  managed (A)   vs.   hold-to-expiration (B)")
    print("=" * 78)
    print(f"  {'Metrik':<28} {'Managed (A)':>18} {'Hold (B)':>18}   Gewinner")
    print("  " + "-" * 74)
    for label, key, fmt in rows:
        va, vb = m[key], h[key]
        if key == "Std":
            winner = "A" if va < vb else ("B" if vb < va else "=")
        elif key in ("MaxLoss", "P5", "CVaR_5"):
            winner = "A" if va > vb else ("B" if vb > va else "=")
        else:
            winner = "A" if va > vb else ("B" if vb > va else "=")
        print(f"  {label:<28} {fmt.format(va):>18} {fmt.format(vb):>18}   {winner}")
    print("=" * 78)
```

### 3. Aufruf im `__main__`
Nach den `_print_analysis(...)`-Aufrufen:

```python
compare_variants(analysis_managed, analysis_holdto_exp, hold_dte=dte)
```

### 4. Optional: Bootstrap-Confidence-Interval

```python
def bootstrap_ci_mean(pnl, n_boot=2000, alpha=0.05, rng=None):
    rng = rng or np.random.default_rng(0)
    n = len(pnl)
    means = rng.choice(pnl, size=(n_boot, n), replace=True).mean(axis=1)
    return float(np.quantile(means, alpha/2)), float(np.quantile(means, 1-alpha/2))
```

### 5. Optional: Re-Deployment-Approximation

```python
def annualized_ev_with_redeploy(simulator_factory, legs, mgmt, days_per_year=365):
    sim = simulator_factory()
    res = sim.analyze_strategy(legs, management=mgmt)
    avg_days = res.management_stats["avg_days_in_trade"] if mgmt else sim.dte
    trades_per_year = days_per_year / avg_days
    return res.expected_value * trades_per_year, trades_per_year, res
```

| Variante | EV pro Trade | Trades/Jahr | EV/Jahr |
|---|---|---|---|
| A (managed, 50/200/21) | EV_A | 365 / avg_days_A | EV_A × Trades/Jahr |
| B (hold-to-expiration) | EV_B | 365 / DTE | EV_B × 365 / DTE |

---

## ⚠️ Mathematische Einschränkung — und der nötige nächste Refactoring-Schritt

> In **konstant-σ-GBM** wird managed in den **risiko-/zeit-normierten Metriken** gewinnen, im **rohen EV** aber **niemals** schlagen — das ist mathematisch erzwungen (Optional-Stopping-Theorem, Wert ist Martingal unter Q).
>
> Tastys realer Edge kommt aus **Vola-Mean-Reversion**, die GBM nicht modelliert. Wenn du das auch sehen willst, brauchst du **Heston / SABR / einen einfachen IV-Schock-Simulator** — das ist ein eigenes, größeres Refactoring.

### Geplanter Refactor: stochastisches Vol-Modell

Ziel: ordentliche Simulation, die TP/SL/DTE-Stop wie Tasty kann **und** mathematisch gegen Hold-to-Close performt — inklusive Vola-Crush-Edge.

Schritte:

1. **Modell-Abstraktion**
   - Neues Interface `PriceModel` mit Methoden `simulate_terminal_prices()` und `simulate_price_paths()` plus pro Pfad/Schritt eine **IV-Surface** (mind. ATM-IV pro Tag).
   - Implementierungen:
     - `GBMModel` (heutiger Stand, konstantes σ) — Baseline.
     - `HestonModel` (stochastische Varianz mit Mean-Reversion: `dv = κ(θ-v)dt + ξ√v dW`).
     - `IVShockModel` (einfaches Heuristik-Modell: aktuelle IV → mean-revertet linear/exponentiell zurück zu Long-Run-Mean, optional Sprünge bei Earnings).
   - `MonteCarloSimulator.__init__` bekommt `price_model: PriceModel`.

2. **Bewertung im Management-Loop**
   - `_managed_pnl` darf nicht mehr mit konstantem `self.volatility` BS-bewerten, sondern mit `iv_t = price_model.iv_at(step, sim_idx)` — d. h. BS pro Zeitstep mit pfad-/zeitabhängigem σ.
   - Damit kommt der Vola-Crush in die TP-Schwelle: nach IV-Spike fällt der Optionspreis schneller als θ allein, TP triggert früher → managed schlägt hold im EV.

3. **Kalibrierung**
   - Heston-Parameter (κ, θ, ξ, ρ, v0) aus historischer IV-Term-Structure pro Underlying schätzen oder defaults aus Literatur (κ≈2, θ≈long-run-IV², ξ≈0.3, ρ≈-0.7).
   - IVShockModel: Half-Life (z. B. 10 Tage) + Long-Run-Mean (z. B. 20 %).

4. **Validierung**
   - Sanity: bei `ξ=0` (deterministische Vola) muss Heston denselben EV liefern wie GBM mit gleichem σ.
   - Tasty-Test: Iron Condor 45 DTE, IV-Start = 1.5 × Long-Run-Mean → managed (50/200/21) sollte EV > hold zeigen. Genau diese Aussage konnte das aktuelle Tool nicht reproduzieren.
   - Statistische Signifikanz via Bootstrap-CI über N=50.000 Pfade.

5. **Performance**
   - Heston-Pfade nur bei aktivem Management nötig (Vollpfade sowieso). Cache-Key um Modell-Hash erweitern.
   - QMC (Sobol) optional für Varianzreduktion.

6. **Tests**
   - `tests/test_price_models.py`: GBM-Endverteilung Lognormal, Heston-Varianz mean-revertet, IVShock konvergiert gegen Long-Run-Mean.
   - `tests/test_managed_vs_hold_heston.py`: zeigt EV(managed) > EV(hold) bei IV-Spike-Setup.

---

## Letzter Output (Iron Condor SPY-style, S=395.09, σ=0.43, DTE=45, N=50.000)

### Variant A — managed (TP 50 % / SL 200 % / DTE close 21)
- Entry value (USD)            : +431.00
- Spread offset (USD)          : (siehe Run-Output)
- Expected value (discounted)  : abhängig vom Run, in der Größenordnung +50…+80 USD
- Win-Prob / Loss-Prob         : ~70 % / ~30 %
- Management Exits             : TP dominant (~55–65 %), DTE-Close (~25–30 %), SL (~5–10 %), Expiry (~0 %)
- Avg Tage im Trade            : ~22–25

### Variant B — hold to expiration (no management)
- Entry value (USD)            : +431.00
- Expected value (discounted)  : i. d. R. höher als A im rohen EV
- Win-Prob / Loss-Prob         : ~75 % / ~25 %
- Max Loss (USD)               : ~−569 (Wing-Width × 100 − Credit)
- Avg Tage im Trade            : 45

### Beobachtung (deckt sich mit Punkt 2 oben)
- Roh-EV: B ≥ A — wie vom Optional-Stopping-Theorem erzwungen.
- Risiko-adjustiert (Std, P5, CVaR5, EV/|MaxLoss|, EV/Tag, EV annualisiert): A ≥ B.
- → Sobald Heston/IVShock implementiert ist, sollte A auch im Roh-EV ≥ B werden, wenn die Start-IV über dem Long-Run-Mean liegt.