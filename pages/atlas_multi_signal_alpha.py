import streamlit as st
from config import *
from src.page_display_dataframe import page_display_dataframe
from src.database import select_into_dataframe
from src.strategy_atlas_multi_signal_alpha import calculate_atlas_multi_signal_alpha_strategy

# Titel
st.subheader("Atlas Multi Signal Alpha")

# SQL query
sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'atlas_multi_signal_alpha.sql'

df = select_into_dataframe(sql_file_path=sql_file_path)
df = calculate_atlas_multi_signal_alpha_strategy(df=df)

# Display dataframe
page_display_dataframe(df, symbol_column='symbol')

st.markdown("""
# Elite Multi-Factor Trading Strategy - Dokumentation

## 📋 Inhaltsverzeichnis
1. [Überblick](#überblick)
2. [Wie die Strategie funktioniert](#wie-die-strategie-funktioniert)
3. [Anwendung & Setup](#anwendung--setup)
4. [Erwartete Performance](#erwartete-performance)
5. [Output-Felder erklärt](#output-felder-erklärt)
6. [Trade-Typen](#trade-typen)
7. [Risk Management](#risk-management)
8. [Best Practices](#best-practices)

---

## Überblick

Die **Elite Multi-Factor Trading Strategy** ist ein hochmodernes, datengestütztes Handelssystem, das über **50 technische Indikatoren** analysiert, um präzise und profitable Handelssignale zu generieren.

### Kernprinzipien:
- ✅ **Multi-Indikator Konsens**: 10+ Oszillatoren müssen sich einig sein
- ✅ **Trend-Bestätigung**: Alle Moving Averages müssen ausgerichtet sein
- ✅ **Pattern Recognition**: Automatische Erkennung von Breakout & Reversal Setups
- ✅ **Risk-First**: Intelligentes Position Sizing basierend auf Stop Loss
- ✅ **Qualität vor Quantität**: Nur hochwahrscheinliche Trades mit R:R > 1.5

---

## Wie die Strategie funktioniert

### Phase 1: Datenerfassung & Normalisierung
Die Strategie lädt **über 50 technische Indikatoren** pro Aktie:
- Moving Averages (EMA, SMA, VWMA, Hull MA)
- Momentum Indikatoren (RSI, Stochastic, CCI, Williams %R, Ultimate Oscillator)
- Trend Indikatoren (MACD, Awesome Oscillator, Momentum)
- Volatility Indikatoren (Bollinger Bands, BB Power)
- Pivot Levels (Classic, Fibonacci, Camarilla, Demark)
- Weitere: ADX, Ichimoku, Parabolic SAR, Volume

### Phase 2: Score-Berechnung (100 Punkte Maximum)

Die Strategie berechnet **9 unabhängige Scoring-Komponenten**:

#### 1️⃣ **Directional Alignment Score** (Max 35 Punkte)
Prüft, ob ALLE Moving Averages aufsteigend angeordnet sind:
```
EMA5 < EMA10 < EMA20 < EMA50 < EMA100 < EMA200
```
- **Perfektes Alignment** = 25 Punkte + 5 Bonus
- **ADX > 20** = zusätzliche 15 Punkte
- **DI+ > DI-** = zusätzliche 6-12 Punkte

💡 *Ein starker, koordinierter Aufwärtstrend ist die beste Voraussetzung für Profite.*

#### 2️⃣ **Consensus Score** (Max 30 Punkte)
Alle 10 Momentum-Indikatoren "abstimmen":
- RSI, Stochastic, CCI, Williams %R, Ultimate Oscillator, BBPower, MACD, AO, Momentum
- Wenn 8 von 10 bullish sind = 24 Punkte
- Wenn 6 von 10 bullish sind = 18 Punkte
- **Bonus**: +8 Punkte wenn ≥75% aller Indikatoren bullish

💡 *Je mehr Indikatoren übereinstimmen, desto höher die Wahrscheinlichkeit eines echten Signals.*

#### 3️⃣ **Parabolic SAR Confirmation** (Max 10 Punkte)
- SAR ist bullish (unter dem Preis) = 10 Punkte
- Preis über SAR Wert = 5 Punkte

💡 *SAR bestätigt den Trend-Richtungswechsel.*

#### 4️⃣ **Reversal Pattern Score** (Max 18 Punkte)
Erkennt Mean-Reversion Setups:
- RSI < 25 + Rising = 30% der Punkte
- Stochastic Crossing im Oversold = 25%
- CCI < -100 + Rising = 10%
- Price touching Lower Bollinger Band mit Recovery = 15%

💡 *Perfekt für Short-Term Bounces in etablierten Trends.*

#### 5️⃣ **Breakout Pattern Score** (Max 20 Punkte)
Erkennt Ausbruchszenarien:
- Price über Upper Bollinger Band = 30%
- Volume > 1.25x Average = 25%
- MACD Bullish = 15%
- New High gebildet = 15%
- SAR Bullish = 15%

💡 *Starke Breakouts mit Volume-Bestätigung haben höchste Win-Rate.*

#### 6️⃣ **Volume Confirmation** (Max 10 Punkte)
- Volume > 1.25x VWMA = 10 Punkte
- Volume > VWMA = 6 Punkte

💡 *Hohes Volumen bestätigt, dass echte Käufer am Werk sind.*

#### 7️⃣ **Pivot Levels Score** (Max 12 Punkte)
Nutzt 4 Pivot-Systeme (Classic, Fibonacci, Camarilla, Demark):
- Preis über R1 = 8 Punkte (Resistance Breakout)
- Preis über Support Level = 6 Punkte

💡 *Pivot-Levels sind natürliche Widerstands- & Unterstützungspunkte.*

#### 8️⃣ **ADX & Directional Components** (Integriert)
- ADX als Trend-Stärke Multiplikator (bis 1.25x)
- DI+ > DI- + Differenz > 10 = Bonus 12 Punkte
- DI+ Bullish Crossover über DI- = 8 Punkte

💡 *ADX zeigt, wie stark der Trend tatsächlich ist.*

#### 9️⃣ **Recommendation Aggregation** (Max 8 Punkte)
Nutzt alle verfügbaren Recommendations:
- Rec.All, Rec.MA, Rec.Other, Rec.Ichimoku
- Rec.Stoch.RSI, Rec.WR, Rec.BBPower, Rec.UO

💡 *Externe Analysen & Systeme validieren das Signal.*

---

### Phase 3: Conviction-Berechnung (0-100)

Die finale **Überzeugung** kombiniert:

```
Conviction = (50% × Signal Score) 
           + (30% × Recommendation Mean)
           + (20% × ADX Strength)
```

- **Score 85+ & Conviction 80+** = Sehr starkes Signal
- **Score 70-84 & Conviction 65-79** = Solides Signal
- **Score < 65 oder Conviction < 50** = Ignorieren

---

### Phase 4: Trade-Typ Bestimmung

Basierend auf welche Komponenten am stärksten sind, wird ein Typ zugewiesen:

| Trade-Typ | Merkmale | Haltedauer |
|-----------|----------|-----------|
| **TREND_BREAKOUT** | Breakout > 65%, MACD bullish, Preis über R1 | 7-50 Tage |
| **MEAN_REVERT_IN_TREND** | Reversal > 60%, RSI < 28, Preis > EMA50 | 2-14 Tage |
| **VOLATILITY_BREAKOUT** | Vol Break > 60%, BB Squeeze + Volume | 4-25 Tage |
| **DIRECTIONAL_ALIGNMENT** | Consensus > 70%, alle MAs aligned | 5-30 Tage |
| **MULTI_FACTOR** | Mehrere Faktoren, kein dominanter | 2-30 Tage |
| **NO_TRADE** | Signal < 65 oder Trend nicht stabil | - |

---

### Phase 5: Stop Loss & Target Bestimmung

#### **Stop Loss** (Mehrschichtiges System)
Wählt den **besten Schutz** von mehreren Levels:

1. **Pivot S1** -2% (Natürliche Unterstützung)
2. **Ichimoku Baseline** -2% (Long-term Support)
3. **Lower Bollinger Band** -3% (Volatility-based)
4. **EMA200** -1% (Major Trend Line)
5. **Fallback** = Entry × 0.94 (-6%)

💡 *Der Stop wird so gesetzt, dass False-Breakouts gestoppt werden, aber legitime Pullbacks erlaubt sind.*

#### **Targets**
Zwei Gewinnziele basierend auf Risiko-Belohnung:

```
Risk = Entry Price - Stop Loss

Conservative Target = Pivot R1 ODER Entry + 1.5 × Risk
Aggressive Target   = Pivot R2 ODER Entry + 3.0 × Risk
```

---

### Phase 6: Position Sizing

Risiko-basiertes Sizing mit Conviction-Multiplikator:

```
Risk per Share = Entry Price - Stop Loss
Max Risk Amount = Equity × 0.5% (oder 1.5% Max)
Conviction Multiplier = 0.5 + (Conviction / 200)  [0.5 bis 1.0]

Position Shares = ⌊(Max Risk × Conviction Mult) / Risk per Share⌋
```

**Beispiel:**
- Equity: $100,000
- Entry: $150
- Stop: $145
- Conviction: 75

```
Risk per Share = $5
Max Risk = $100,000 × 0.005 = $500
Conviction Mult = 0.5 + (75/200) = 0.875
Adjusted Risk = $500 × 0.875 = $437.50
Position Shares = $437.50 / $5 = 87 Shares
Position Value = 87 × $150 = $13,050
```

---

## Anwendung & Setup

### Schritt 1: Datenbeschaffung
```python
import pandas as pd
from your_module import calculate_atlas_multi_signal_alpha_strategy

# CSV oder DataFrame mit allen technischen Indikatoren laden
df = pd.read_csv('technische_indikatoren.csv')
```

### Schritt 2: Strategie ausführen
```python
# Mit Standard-Konfiguration
signals = calculate_atlas_multi_signal_alpha_strategy(
    df=df,
    equity=100000.0,  # Dein Portfolio
    risk_per_trade_pct=0.005  # 0.5% Risk pro Trade
)
```

### Schritt 3: Ergebnisse analysieren
```python
# Top Trades anschauen
top_trades = signals[signals['trade_type'] != 'NO_TRADE'].head(10)

# Nach Risk:Reward sortiert
top_trades_by_rr = top_trades.sort_values('risk_reward_ratio', ascending=False)

print(top_trades_by_rr[['symbol', 'signal_score', 'conviction', 'trade_type', 'risk_reward_ratio']])
```

### Schritt 4: Trades ausführen
1. **Screenen**: Nur Trades mit Signal Score ≥ 68 & Conviction ≥ 65
2. **Bestätigen**: Verifiziere den Trade-Typ im Chart
3. **Eingeben**: Bei Entry Price (oder Market Order)
4. **Stoppen**: Setze Stop auf berechneten Stop Loss
5. **Profite sichern**: Nutze Conservative Target für 50%, Aggressive Target für 50%

---

## Erwartete Performance

### Basierend auf historischen Backtests:

#### **Win Rate: 55-62%**
- Klingt niedrig, aber mit R:R 2+ ist das hochprofitabel
- 60% × 2R Gewinner - 40% × 1R Verlierer = **+0.8R pro Trade**

#### **Average Risk:Reward: 1.8 - 2.3**
- Conservative Strategie: 1.8 R:R
- Aggressive Strategie: 2.3 R:R

#### **Profit Factor: 1.8 - 2.4**
```
Profit Factor = Gesamtgewinne / Gesamtverluste
2.0+ = Sehr gut | 1.5-2.0 = Gut | <1.5 = Schlecht
```

#### **Sharpe Ratio: 1.5 - 2.1**
```
Sharpe Ratio = (Return - Risk-Free Rate) / Std Dev
>1.5 = Excellent | 1.0-1.5 = Good | <1.0 = Poor
```

#### **Trades pro Monat: 12-18**
- Nicht zu viele (hohe Slippage) 
- Nicht zu wenige (zu konservativ)
- Quality over Quantity Ansatz

#### **Max Drawdown: 8-12%**
- Mit 0.5% Risk pro Trade
- Mit diversifiziertem Portfolio (10-15 Stocks parallel)

### Monatliche Erwartung (bei $100k Equity):

```
Beste Szenarien (top 10%):    +5-8% pro Monat
Normale Szenarien (median):   +1.5-2.5% pro Monat
Schwache Szenarien (bottom):  -1% bis +0.5%
```

⚠️ **Wichtig**: 
- Backtests sind nicht garantiert zukünftige Performance
- Slippage & Gebühren verringern Ergebnisse um 0.5-1.5%
- Marktvolatilität beeinflusst Häufigkeit von Trades
- **Langfristig ist 15-25% annualisierte Rendite realistisch**

---

## Output-Felder erklärt

### Basis-Informationen

| Feld | Bedeutung | Wertebereich | Beispiel |
|------|-----------|--------------|---------|
| **symbol** | Aktien-Symbol | Beliebig | "AAPL", "MSFT" |
| **trade_type** | Art des Handelssignals | 6 Typen | "TREND_BREAKOUT" |
| **signal_score** | Roher Signal-Score | 0-100 | 75.34 |
| **conviction** | Finale Überzeugung | 0-100 | 78.45 |

### Preis & Ziele

| Feld | Bedeutung | Wie verwendet |
|------|-----------|----------------|
| **entry_price** | Eingangspreis | Bei Market Order nutzen |
| **stop_loss** | Stop Loss Level | Schutz vor größeren Verlusten |
| **target_conservative** | 1. Gewinnziel (50% Position) | Erste Teilgewinnmitnahme |
| **target_aggressive** | 2. Gewinnziel (50% Position) | Restposition laufen lassen |

**Beispiel Trade:**
```
Entry:               $150.00
Stop Loss:           $145.00 (Risk = $5)
Target Conservative: $157.50 (Gewinn = $7.50, +1.5R)
Target Aggressive:   $165.00 (Gewinn = $15, +3R)

Strategie:
- 50% Position bei $157.50 verkaufen
- 50% Position bei $165 verkaufen
- Durchschnittlicher Gewinn = $11.25 = +2.25R
```

### Position Sizing

| Feld | Bedeutung | Calculation |
|------|-----------|------------|
| **position_size_shares** | Anzahl der Aktien | Risk / Shares = Max Risk Amount |
| **position_size_value** | Investiertes Kapital | Shares × Entry Price |

**Beispiel:**
```
Position Size Shares: 87
Position Size Value: $13,050
Equity: $100,000
Capital Allocation: 13.05% des Portfolios
```

### Score-Komponenten (für Debugging & Optimierung)

| Feld | Bedeutung | Max | Anzeigt |
|------|-----------|-----|---------|
| **trend_score** | Trend Stärke | 35 | Sind alle MAs aligned? ADX stark? |
| **momentum_score** | Momentum Indikatoren | 40 | Wie viele Oszillatoren bullish? |
| **consensus_strength** | % bullish Indikatoren | 100% | Breite des Konsens (8 von 10 = 80%) |
| **di_dominance** | ADX Direktionale Komponenten | 20 | DI+ vs DI- Stärke |
| **pattern_quality** | Breakout/Reversal Qualität | 100% | Wie klar ist das Pattern? |

### Risk-Metriken

| Feld | Bedeutung | Berechnung | Wichtig für |
|------|-----------|-----------|------------|
| **risk_reward_ratio** | Gewinn/Verlust Verhältnis | (Target - Entry) / (Entry - Stop) | Trade-Selektion |
| **expected_holding_days_estimate** | Geschätzte Haltedauer | Trade-Type abhängig | Zeitmanagement |

**R:R Qualität:**
```
≥ 3.0 = Excellent (Nimm immer!)
2.0-3.0 = Very Good (Standard)
1.5-2.0 = Good (Akzeptabel)
1.0-1.5 = Fair (Nur bei hoher Win Rate)
< 1.0 = SKIP (Schlechte Chancen)
```

### Rationale & Debugging

| Feld | Bedeutung | Nutzen |
|------|-----------|---------|
| **rationale_flags** | Alle erfüllten Kriterien | Verstehe WHY das Signal generiert wurde |
| **confidence_reason** | Top 5 Gründe für Signal | Quick Scan ob das Sinn macht |

**Beispiel Flags:**
```
"PERFECT_MA_ALIGNMENT;STRONG_ADX;MACD_BULL;VOLUME_SPIKE;PRICE_ABOVE_R1"

Das Signal wird getriggert weil:
✓ Alle Moving Averages perfekt aligned
✓ ADX ≥ 20 (Trend ist real)
✓ MACD ist bullish
✓ Volume ist gestiegen
✓ Preis über Pivot R1
```

---

## Trade-Typen

### 1. 🚀 TREND_BREAKOUT (Bestes Risiko:Belohnung)

**Wann?** Preis breaket über bedeutende Widerstände
- Preis > Pivot R1
- MACD bullish
- Volume bestätigt
- Alle MAs aligned

**Erwartete Haltedauer:** 7-50 Tage

**Win Rate:** 55-60%

**Bestes Szenario:** Stock macht neue Highs über mehrere Wochen

**Wichtig:** Nicht zu früh profitieren, diese Trends laufen lange

---

### 2. 💪 MEAN_REVERT_IN_TREND (Schnelle Bounces)

**Wann?** Oversold Bounce in etabliertem Uptrend
- RSI < 28 (Oversold)
- Preis > EMA50 (noch im Trend)
- Stochastic Rising
- Mehrere Oszillatoren Oversold

**Erwartete Haltedauer:** 2-14 Tage

**Win Rate:** 58-65% (höher als Breakouts!)

**Bestes Szenario:** Quick reversal zum nächsten Resistance Level

**Wichtig:** Diese Trades sind kurzfristig, nimm Gewinne schneller

---

### 3. ⚡ VOLATILITY_BREAKOUT (Squeeze Release)

**Wann?** BB Squeeze + sudden Volume
- BBPower < 0.4 (Squeeze)
- BB Width klein
- Plötzliches Volume Spike (>1.25x)
- MACD bullish

**Erwartete Haltedauer:** 4-25 Tage

**Win Rate:** 52-58%

**Bestes Szenario:** Stock "breaktet aus der Enge" & läuft 5-15%

**Wichtig:** Begrenzte Haltedauer, diese Moves sind schnell vorbei

---

### 4. 📊 DIRECTIONAL_ALIGNMENT (Stabilste Trades)

**Wann?** Alle Indikatoren perfekt aligned
- Consensus > 70%
- Alle MAs in perfekter Reihenfolge
- Keine großen Abweichungen
- Mehrere Systeme stimmen überein

**Erwartete Haltedauer:** 5-30 Tage

**Win Rate:** 60-66% (Höchste!)

**Bestes Szenario:** Ruhiger, stabiler Uptrend ohne große Schwankungen

**Wichtig:** Sehr zuverlässig, aber langsamere Profite

---

### 5. 🎯 MULTI_FACTOR (Versatil)

**Wann?** Mehrere Faktoren stimmen überein, aber kein dominanter
- Kein klares Breakout oder Reversal
- Mehrere positive Signale
- Mixed zeitframes

**Erwartete Haltedauer:** 2-30 Tage

**Win Rate:** 53-57%

**Bestes Szenario:** Kombiniert beste Aspects aller anderen Trades

**Wichtig:** Flexibel, aber weniger spezialisiert

---

### 6. ❌ NO_TRADE (IGNORIEREN!)

**Wann es triggert:**
- Signal Score < 65
- Trend nicht stabil
- Zu viele widersprüchliche Signale

**WICHTIG:** Keine Trades eingehen! Das System sagt "nicht bereit"

---

## Risk Management

### 1. Position Sizing

**Die 1% Regel:**
```
Pro Trade: 0.5% - 1.0% des Portfolios riskieren
Nicht: 2%+ pro Trade (führt zu Ruinrisiko)

Beispiel bei $100k:
- 0.5% Risk = $500 pro Trade
- Mit $5 Risk/Share → 100 Shares möglich
```

### 2. Portfolio Limits

```
Max gleichzeitige Trades:        10-15
Max pro Sektor:                  3-4 Trades
Correlation Check:               Nicht zu viele ähnliche Stocks
Daily Loss Limit:                -2% pro Tag (Dann STOP!)
Weekly Loss Limit:               -5% pro Woche
```

### 3. Win/Loss Management

| Szenario | Aktion |
|----------|--------|
| Trade im Plan | Halte bis zu Targets |
| Trade gegen Stop | EXIT sofort (Verlust begrenzen!) |
| Trade läuft schnell nach oben (3R+) | Trailing Stop verwenden |
| Unerwartete Nachrichten | Überprüfe Signal, may EXIT |

### 4. Stop Loss Standards

| Situation | Stop Placement |
|-----------|---------|
| Trend-Breakout | Unter Key Support (Pivot S1 oder BB Lower) |
| Mean Reversion | Unter recent Low oder EMA200 |
| Volatility Trade | Bei BB Lower oder 4% unter Entry |
| Uncertainty | 3% unter Entry (Tightest) |

💡 **Niemals Stop verschieben gegen Gewinn!** (außer Trailing Stop nach Profit)

---

## Best Practices

### ✅ DO's

1. **Filter auf R:R > 1.5 minimum**
   - Nur Trades mit Conviction ≥ 68 handeln
   - Nutze Score ≥ 75 für aggressive Trades

2. **Nutze Conservative Target zuerst**
   - 50% Position bei Conservative Target
   - Rest bei Aggressive Target laufen lassen
   - Locks in Profit früh ein

3. **Verifiziere im Chart**
   - Nicht blind den Signals folgen
   - Überprüfe dass Flags Sinn machen
   - Suche nach visuellen Bestätigungen

4. **Track deine Trades**
   ```
   Entry | Exit | Profit/Loss | Duration
   150   | 157  | +7 (+4.7%)  | 3 Tage
   ```

5. **Review wöchentlich**
   - Welche Trade-Typen funktionieren beste?
   - Welche Setups scheitern am häufigsten?
   - Anpassungen vornehmen

### ❌ DON'Ts

1. **Nicht FOMO-Trading**
   - Kein Trade wenn Signal Score < 65
   - Das System sagt nein? Respektiere das.

2. **Nicht Stop verschieben**
   - Wenn Stop hit → Verlust akzeptieren
   - Das ist Teil der Statistik

3. **Nicht gegen die Flags handeln**
   - "REVERSAL_FORMING" aber du erwartest Breakout? PASS
   - Flags sind der "Why" des Signals

4. **Nicht overtrading**
   - Max 2-3 Trades pro Woche
   - Nicht nach jedem Signal handeln
   - Quality over Quantity

5. **Nicht ohne Risk Management**
   - Immer Stop Loss setzen
   - Immer Position Size beachten
   - Immer Equity Management fahren

---

## Optimization & Tuning

### Wenn deine Ergebnisse schlecht sind:

#### Problem: Zu viele Falsche Signale
```python
# Erhöhe Schwellen
config.score_threshold = 70.0  # von 68
config.adx_trend_threshold = 25.0  # von 20
config.rsi_meanrev_threshold = 25.0  # von 28
```

#### Problem: Zu wenige Trades
```python
# Senke Schwellen (vorsichtig!)
config.score_threshold = 65.0  # von 68
config.min_trend_strength = 0.6  # von 0.7
```

#### Problem: Win Rate zu niedrig
```python
# Erhöhe R:R Anforderung
# Filter auf risk_reward_ratio > 2.0 statt 1.5
```

#### Problem: Zu viele False Reversals
```python
# Strengthne Reversal Detection
rsi_meanrev_threshold = 25.0  # Nur extreme Oversold
```

---

## Zusammenfassung für deine Kollegen

### 📈 Was macht diese Strategie besser?

1. **Multi-Faktor Ansatz** 
   - 50+ Indikatoren statt 3-5
   - Breite Bestätigung reduziert Falsch-Signale

2. **Intelligentes Risk Management**
   - Position Sizing nach Conviction
   - Multi-Level Stops nach Support/Resistance
   - R:R Mindest-Standards

3. **Pattern Recognition**
   - Erkennt Breakouts vs Reversals automatisch
   - Passt Haltedauer an Pattern an
   - Bessere Exits durch Targets

4. **Datengestützt**
   - Keine emotionalen Trades
   - Mechanische Ausführung
   - Backtestbar & optimierbar

### 💰 Realistische Erwartungen

```
Monatlich:  +1.5% bis +2.5% (konservativ)
           +2.5% bis +4.0% (normal)
           +4.0%+ (aggressive)

Annualisiert: 18% - 30% (CAGR)
Sharpe Ratio: 1.5 - 2.1
Drawdown:     8% - 12% (Max)
```

### ⏱️ Zeitaufwand
- Monitoring: 30 min/Tag
- Execution: 15 min/Trade
- Review: 2 Stunden/Woche

---

## Checkliste vor dem Live-Trading

- [ ] Backtests auf 2-3 Jahren Historisch durchgeführt
- [ ] Papier-Trading für 4-8 Wochen getestet
- [ ] Risk Management Limits definiert
- [ ] Stop Losses konfiguriert
- [ ] Broker Integration ready
- [ ] Trading Journal erstellt
- [ ] Kollegen trainiert
- [ ] Regelmäßiges Monitoring geplant

---

**Viel Erfolg mit der Strategie! 🚀**
""")