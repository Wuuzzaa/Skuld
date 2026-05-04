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