# DIVIDENDEN-SCANNER — Short Put Strategie v2.0

> **Vertraulich | Internes Dokument**
> Generiert: 16.Mai 2026 | Quellen: Yahoo Finance API | Interactive Brokers TWS API
> Kein Sektor-Benchmarking | Universumsbasiertes Scoring | 100% Mechanisch

---

## Inhaltsverzeichnis

1. [Philosophie & Grundprinzipien](#1--philosophie--grundprinzipien)
2. [Datenbeschaffung — Yahoo Finance & IB API](#2--datenbeschaffung--yahoo-finance--ib-api)
3. [Screening-Pipeline: Phase 1 — Fundamentalanalyse](#3--screening-pipeline-phase-1--fundamentalanalyse)
4. [Screening-Pipeline: Phase 2 — Technische Analyse](#4--screening-pipeline-phase-2--technische-analyse)
5. [Scoring-Modell: Composite Value Score (CVS)](#5--scoring-modell-composite-value-score-cvs)
6. [Options-Selektion: Der ideale Short Put](#6--options-selektion-der-ideale-short-put)
7. [Entry-Regeln & Auftragslogik](#7--entry-regeln--auftragslogik)
8. [Risikomanagement & Exit-Regeln](#8--risikomanagement--exit-regeln)
9. [Web-UI: Dashboard-Architektur](#9--web-ui-dashboard-architektur)
10. [Implementierungs-Roadmap](#10--implementierungs-roadmap)
- [Anhang: Alle Formeln im Überblick](#a--anhang-alle-formeln-im-überblick)

---

## 1 | Philosophie & Grundprinzipien

Die Strategie kombiniert zwei bewährte Konzepte: **Value Investing** nach Graham/Buffett-Prinzipien und **Optionsprämienverkauf (Short Put)**. Das Ziel ist eine doppelte Renditequelle: erstens Einstieg in Qualitätsaktien zu einem Discount auf den fairen Wert, zweitens Vereinnahmung von Optionsprämie bei Nicht-Zuteilung. **Kein Sektor-Benchmarking** — alle Bewertungen erfolgen absolut oder relativ zum gesamten gescannten Universum.

| Prinzip | Beschreibung |
|---|---|
| **Mechanisch** | Kein Ermessen. Jede Entscheidung folgt einem quantifizierbaren Regelwerk aus API-Daten. |
| **Echtzeit-Daten** | Alle Inputs kommen live aus Yahoo Finance (yfinance) und IB TWS API. Kein Look-Ahead. |
| **Universumsbasiert** | Bewertungsvergleich über alle Aktien im Scan-Universum — kein Sektor-Median, der durch Branchen-Peculiarities verzerrt wird. |
| **Doppelte Sicherheitsmarge** | Aktie muss fundamental unterbewertet sein UND technisch in Schwäche kaufbar sein. |
| **Prämie als Puffer** | Short Put-Prämie senkt den effektiven Einstandspreis um den Prämienbetrag. |
| **Kapitaleffizienz** | Cash Secured Put bindet definiertes Kapital. Kein Leverage, kein Margin-Risiko. |

---

## 2 | Datenbeschaffung — Yahoo Finance & IB API

Alle Inputs sind direkt aus API-Feldern ablesbar. Keine Schätzungen, keine Derivate.

### 2.1 Yahoo Finance (yfinance)

| Feld (yfinance) | Bezeichnung | Verwendung |
|---|---|---|
| `trailingPE` | Trailing P/E | Bewertung |
| `forwardPE` | Forward P/E | Bewertung |
| `priceToBook` | Price/Book | Bewertung |
| `priceToSalesTrailing12Months` | Price/Sales (TTM) | Bewertung |
| `enterpriseToEbitda` | EV/EBITDA | Bewertung |
| `enterpriseToRevenue` | EV/Revenue | Bewertung |
| `dividendYield` | Dividend Yield | Dividende |
| `payoutRatio` | Payout Ratio | Dividende |
| `fiveYearAvgDividendYield` | 5Y Avg Dividend Yield | Dividende |
| `freeCashflow` | Free Cashflow | Qualität |
| `operatingCashflow` | Operating Cashflow | Qualität |
| `returnOnEquity` | Return on Equity | Qualität |
| `returnOnAssets` | Return on Assets | Qualität |
| `profitMargins` | Profit Margin | Qualität |
| `debtToEquity` | Debt/Equity | Risiko |
| `currentRatio` | Current Ratio | Risiko |
| `quickRatio` | Quick Ratio | Risiko |
| `beta` | Beta | Risiko |
| `fiftyTwoWeekHigh` / `fiftyTwoWeekLow` | 52W High / Low | Technisch |
| `fiftyDayAverage` | 50D Moving Avg | Technisch |
| `twoHundredDayAverage` | 200D Moving Avg | Technisch |
| `earningsGrowth` | Earnings Growth (YoY) | Wachstum |
| `revenueGrowth` | Revenue Growth (YoY) | Wachstum |
| `shortRatio` | Short Ratio | Sentiment |
| `marketCap` | Market Cap | Filter |

### 2.2 IB TWS API (ib_insync / ibapi)

| Feld (IB API) | Inhalt |
|---|---|
| `impliedVolatility` | Implizite Volatilität des Strikes |
| `delta` | Delta des Puts (negativ, zwischen -1 und 0) |
| `gamma` | Gamma (Sensitivität des Deltas) |
| `theta` | Täglicher Zeitwertverfall (positiv für Verkäufer) |
| `vega` | Sensitivität auf Vola-Änderung |
| `bid` / `ask` | Geld-/Briefkurs der Option |
| `lastPrice` | Letzter Handelspreis |
| `openInterest` | Offene Kontrakte (Liquiditätsindikator) |
| `volume` | Tagesvolumen |
| `expiry` | Verfallsdatum (YYYYMMDD) |
| `strike` | Strike-Preis in Basiswährung |
| `right` | P = Put, C = Call |
| `HV30` / `HV60` | Historische Volatilität 30/60 Tage (via Kursdaten) |

---

## 3 | Screening-Pipeline: Phase 1 — Fundamentalanalyse

Phase 1 filtert den Gesamtmarkt (S&P 500, Nasdaq 100, DAX, STOXX) auf strukturell gesunde Dividendenzahler. Alle Schwellenwerte sind harte Grenzen — kein Kandidat darf einen einzigen Wert verfehlen. **Es findet kein Sektor-Vergleich statt.**

### 3.1 Pflichtfilter — MUSS-Kriterien (M1–M11)

| # | Kennzahl | Bedingung | Datenfeld | Begründung |
|---|---|---|---|---|
| M1 | Dividendenrendite | >= 2,5% | `dividendYield` | Mindestdividende |
| M2 | Dividendenhistorie | >= 5 Jahre | `dividendHistory` | Verlässlichkeit |
| M3 | Payout Ratio | < 75% | `payoutRatio` | Nachhaltigkeit |
| M4 | Free Cashflow | > 0 | `freeCashflow` | Echte Ertragskraft |
| M5 | Op. Cashflow | > 0 | `operatingCashflow` | Operativer Cashflow |
| M6 | Market Cap | > 2 Mrd USD | `marketCap` | Optionsliquidität |
| M7 | Debt/Equity | < 200% | `debtToEquity` | Bilanzqualität |
| M8 | Current Ratio | >= 1,0 | `currentRatio` | Kurzfrist-Liquidität |
| M9 | Avg Options Vol | > 500 Ktr/Tag | IB: OI + volume | Handelbarkeit |
| M10 | P/E | < 40 | `trailingPE` | Absolutes Bewertungs-Cap |
| M11 | P/B | < 10 | `priceToBook` | Extremwert-Filter |

### 3.2 Absolute Bewertungsanalyse (ohne Sektor-Benchmarking)

Anstelle eines Sektor-Medians wird jede Aktie über ein **inverses Perzentil-Ranking im gesamten gescannten Universum** bewertet. Niedrigere Multiples = besseres Ranking. Dies macht alle Symbole direkt vergleichbar — unabhängig vom Sektor.

| Kennzahl | API-Feld | Scoring-Methode | Logik |
|---|---|---|---|
| P/E | `trailingPE` | Inverses Uni.-Perzentil (0–100) | Niedriges P/E = hoher Score |
| P/B | `priceToBook` | Inverses Uni.-Perzentil (0–100) | Niedriges P/B = hoher Score |
| EV/EBITDA | `enterpriseToEbitda` | Inverses Uni.-Perzentil (0–100) | Niedriger EV/EBITDA = hoher Score |
| P/S | `priceToSalesTrailing12Months` | Inverses Uni.-Perzentil (0–100) | Niedriger P/S = hoher Score |

```python
# Inverses Perzentil-Ranking
def inv_pct_rank(series, value):
    pct = (series < value).sum() / len(series)  # Anteil Werte < value
    return (1 - pct) * 100                       # Invertiert: niedrig = gut

FVS_PE  = inv_pct_rank(universe['trailingPE'],               stock['trailingPE'])
FVS_PB  = inv_pct_rank(universe['priceToBook'],              stock['priceToBook'])
FVS_EV  = inv_pct_rank(universe['enterpriseToEbitda'],       stock['enterpriseToEbitda'])
FVS_PS  = inv_pct_rank(universe['priceToSalesTrailing12Months'], stock['priceToSalesTrailing12Months'])

FVS = 0.35*FVS_PE + 0.25*FVS_PB + 0.25*FVS_EV + 0.15*FVS_PS
```

> **Hinweis:** Fehlende Multiples (z.B. negatives EBITDA) werden mit Score 0 belegt und als Risikosignal gewertet, nicht übersprungen.

### 3.3 Qualitäts-Score (Q-Score)

Alle Kennzahlen werden via Min-Max-Normierung über das gesamte Universum auf [0, 1] skaliert.

```python
Q_score = 0.25*ROE_norm + 0.25*ROA_norm + 0.25*Margin_norm \
        + 0.15*EarningsGrowth_norm + 0.10*RevenueGrowth_norm

# Min-Max-Normierung (höherer Wert = besser):
x_norm = (x - x_min) / (x_max - x_min)   # x_min/max über Universum
```

---

## 4 | Screening-Pipeline: Phase 2 — Technische Analyse

Phase 2 identifiziert den optimalen Einstiegszeitpunkt. Qualität wird in relativer Kursschwäche gekauft — das erhöht die Short Put-Prämie (höhere IV) und verbessert den Einstandspreis. Alle Indikatoren werden aus OHLCV-Daten via `yfinance.download()` berechnet.

### 4.1 Trend-Filter (Richtungsqualifikation)

| Indikator | Berechnung | Bedingung |
|---|---|---|
| SMA 200 | 200-Tage-Closing-Average | Kurs < SMA200 (Kursschwäche) |
| SMA 50 / 200 | 50d vs. 200d SMA | SMA50 > SMA200 (LT-Aufwärtstrend intakt) |
| Kurs vs. 52W-High | `(Kurs - 52W-High) / 52W-High * 100` | < -15% vom ATH |
| Kurs vs. 52W-Low | `(Kurs - 52W-Low) / 52W-Low * 100` | > +10% vom Tief (kein freier Fall) |

### 4.2 Momentum-Indikatoren

| Indikator | Formel | Signal-Schwelle |
|---|---|---|
| RSI (14) | Wilder RSI auf 14-Tage-Closing-Returns | RSI < 45 |
| MACD | EMA12 - EMA26; Signal = EMA9(MACD) | MACD > Signal (Momentum dreht) |
| Stochastic | `%K = (C-L14)/(H14-L14)*100; %D = SMA3(%K)` | %K < 40 oder steigend |
| Bollinger | `BB = SMA20 ± 2*STD20` | Kurs nahe unterem Band |
| ATR (14) | Average True Range 14 Tage | Für Strike-Distanz-Berechnung |

### 4.3 Volatilitäts-Analyse

```python
# Historische Volatilität 30 Tage
HV30 = std(log(Close_t / Close_t-1), 30 Tage) * sqrt(252) * 100

# IV Rank (rolling 52W High/Low der IV aus IB Optionskette)
IV_Rank = (IV_current - IV_52W_Low) / (IV_52W_High - IV_52W_Low) * 100

# IV Percentile (direkter Vergleich letzter 252 Handelstage)
IV_Percentile = Anteil der Tage mit IV < IV_current
```

| IV-Rang | Bewertung | Aktion | Kommentar |
|---|---|---|---|
| < 20 | Sehr günstig | ❌ NEIN | Prämie zu niedrig |
| 20 – 40 | Günstig | ⚠️ MÖGL. | Nur bei sehr hohem CVS |
| 40 – 60 | Ideal | ✅ JA | Optimaler Bereich — Sweet Spot |
| 60 – 80 | Erhöht | ✅ JA | Gute Prämie, Positionsgrösse reduzieren |
| > 80 | Extrem | ❌ NEIN | Tail-Risiko zu hoch |

---

## 5 | Scoring-Modell: Composite Value Score (CVS)

Der CVS aggregiert alle Dimensionen zu einem Ranking-Wert von 0–100. Da alle Sub-Scores universumsbasiert normiert werden, sind **Symbole aus verschiedenen Branchen direkt vergleichbar**. Das Modell ist vollständig deterministisch — gleiche Inputs erzeugen immer gleiche Outputs.

### 5.1 Score-Komponenten & Gewichtung

| Komponente | Gewicht | Berechnung | Zweck |
|---|---|---|---|
| Fundamental Value (FVS) | 30% | Inverses Uni.-Perzentil von P/E, P/B, EV/EBITDA, P/S | Absolutes Bewertungsniveau |
| Dividend Score (DVS) | 25% | Yield × (1 - PayoutRatio) × DivGrowthScore | Qualität und Höhe der Dividende |
| Quality Score (QVS) | 20% | ROE/ROA/Margin/GrowthNorm (Min-Max im Universum) | Unternehmensqualität |
| Technical Score (TVS) | 15% | RSI + Trend + Bollinger + MACD + Stochastic | Einstiegstiming |
| Volatility Score (VVS) | 10% | IV-Rank 40–60 = 100 Pkt, abnehmend nach außen | Prämienqualität |

```python
# Composite Value Score — Hauptformel
CVS = 0.30*FVS + 0.25*DVS + 0.20*QVS + 0.15*TVS + 0.10*VVS
```

### 5.2 Detail: Fundamental Value Score (FVS)

```python
FVS_PE  = inv_pct_rank(universe.trailingPE,               stock.trailingPE)       # Gewicht 35%
FVS_PB  = inv_pct_rank(universe.priceToBook,              stock.priceToBook)      # Gewicht 25%
FVS_EV  = inv_pct_rank(universe.enterpriseToEbitda,       stock.enterpriseToEbitda) # Gewicht 25%
FVS_PS  = inv_pct_rank(universe.priceToSalesTrailing12Months, stock.priceToSalesTrailing12Months) # 15%

FVS = 0.35*FVS_PE + 0.25*FVS_PB + 0.25*FVS_EV + 0.15*FVS_PS
# Ergebnis: 0–100 | 100 = günstigste Aktie im gesamten Universum
```

### 5.3 Detail: Dividend Score (DVS)

```python
DVS = (YieldNorm * 0.5) + ((1 - PayoutRatio) * 0.3) + (DivGrowth5Y_norm * 0.2)

# YieldNorm    : Min-Max-normiert im Universum (höhere Yield = besserer Score)
# PayoutRatio  : Direkt aus yfinance (0–1)
# DivGrowth5Y  : CAGR der Dividende über 5 Jahre, dann Min-Max-normiert
```

### 5.4 Detail: Technical Score (TVS)

| Sub-Score | Berechnung | Max Pkt. |
|---|---|---|
| RSI-Score | `100 - RSI` (falls RSI < 50), sonst 0 | 50 |
| SMA-Distance | `((SMA200 - Kurs) / SMA200) * 200`, gekappt bei 50 | 50 |
| BB-Position | `1 - ((Kurs - BB_lower) / (BB_upper - BB_lower))` | 20 |
| MACD-Score | 10 wenn MACD > Signal, sonst 0 | 10 |
| Stoch-Score | `(40 - %K) / 40 * 10` falls %K < 40, sonst 0 | 10 |

```python
TVS = (RSI_Score + SMA_Dist + BB_Score + MACD_Score + Stoch_Score) / 1.40
```

### 5.5 Detail: Volatility Score (VVS)

```python
VVS = 100 - abs(IV_Rank - 50) * 2   # Maximum bei IV_Rank = 50
# IV_Rank 40–60  =>  VVS 80–100
# IV_Rank < 20 oder > 80  =>  VVS 0–20
```

### 5.6 CVS-Klassifikation & Handelsempfehlung

| CVS-Bereich | Rating | Empfehlung |
|---|---|---|
| 85 – 100 | 🟢 **PREMIUM** | Sofort handeln — maximale Positionsgröße |
| 70 – 84 | 🔵 **STARK** | Handeln — Standard-Positionsgröße |
| 55 – 69 | 🟡 **GUT** | Handeln — reduzierte Positionsgröße |
| 40 – 54 | ⚪ **NEUTRAL** | Beobachten — kein Trade |
| < 40 | 🔴 **SCHWACH** | Kein Trade — Qualitätskriterien unerfüllt |

---

## 6 | Options-Selektion: Der ideale Short Put

Nachdem die Aktie qualifiziert wurde, selektiert der Algorithmus automatisch den optimalen Put aus der IB-Optionskette in drei Schritten: Expiry-Wahl → Strike-Wahl → Liquiditäts-Check.

### 6.1 Laufzeit (Expiry)

| DTE | Theta-Verfall | Eignung | Kommentar |
|---|---|---|---|
| < 14 Tage | Gamma-Risiko sehr hoch | ❌ NEIN | Zu viel Gamma-Risiko |
| 14 – 21 Tage | Theta sehr hoch | ⚠️ MÖGL. | Nur bei Wochen-Optionen |
| 21 – 45 Tage | Ideal — Sweet Spot | ✅ **JA ★** | Bevorzugter Bereich |
| 45 – 60 Tage | Hoch | ✅ JA | Für niedrig volatile Aktien |
| > 60 Tage | Gering | ❌ NEIN | Kapital zu lange gebunden |

```python
# Ziel-Expiry
Expiry = nächster Verfall mit  30 <= DTE <= 45 Tage
```

### 6.2 Strike-Selektion via Delta — Primärmethode

Das **Ziel-Delta für Short Puts beträgt –0.30** (30-Delta). Dies ist der bewährte Kompromiss zwischen Prämieneinnahme (~20–25% ann.) und Ausübungswahrscheinlichkeit (~30%). Abweichungen sind CVS-gesteuert:

| Delta (Put) | Ausüb.-WS | Prämie | Profil | Einsatz |
|---|---|---|---|---|
| –0.40 bis –0.45 | ~40–45% | Hoch | Aggressiv | CVS > 85 |
| –0.30 bis –0.40 | ~30–40% | Mittel-Hoch | Standard | CVS 70–84 |
| **–0.25 bis –0.30** | **~25–30%** | **Mittel** | **Primärziel ★** | **Alle CVS >= 55** |
| –0.20 bis –0.25 | ~20–25% | Mittel | Konservativ | CVS 55–69 |
| –0.15 bis –0.20 | ~15–20% | Niedrig | Sehr konservativ | Nur hohe IV |
| < –0.15 | < 15% | Sehr niedrig | Prämie zu gering | ❌ NEIN |

> **Empfehlung:** Delta **–0.30** als Standardziel | Aggressiv bis **–0.40** (CVS > 85) | Konservativ **–0.20** (hohe IV)

### 6.3 Strike-Distanz via ATR — Zweite Kontrolle

```python
# Mindest-Abstand vom aktuellen Kurs
Min_Strike_Distanz = Kurs - (1.5 * ATR14)

# Technischer Support (zusätzliche Untergrenze)
Support = 60_Tage_Lowest_Low
# Strike muss oberhalb des technischen Supports liegen
```

### 6.4 Liquiditätsprüfung

| Kriterium | Mindest-Anforderung | IB API Feld |
|---|---|---|
| Bid-Ask Spread | < 5% des Bid-Kurses | `(ask - bid) / bid * 100` |
| Open Interest | > 200 offene Kontrakte | `openInterest` |
| Tagesvolumen | > 50 Kontrakte | `volume` |
| Mindest-Prämie | > 0.15 USD/EUR je Aktie | `bid * 0.9` (Mittelkurs-Näherung) |

### 6.5 Options-Score (OS) — Endauswahl

Wenn mehrere Puts die obigen Filter bestehen, wird der beste per Options-Score selektiert:

```python
OS = Ann_Rendite_pct * 0.40 + Delta_Score * 0.30 + Theta_Score * 0.20 + Liq_Score * 0.10

Ann_Rendite_pct = (Praemie / Strike) * (365 / DTE) * 100
Delta_Score     = 1 - abs(delta - (-0.30)) / 0.30   # Nähe zum Ziel-Delta –0.30
Theta_Score     = abs(theta) / Praemie               # Zeitverfall-Effizienz
Liq_Score       = (OI_norm + Volume_norm) / 2        # Min-Max im Optionsketten-Set
```

---

## 7 | Entry-Regeln & Auftragslogik

### 7.1 Finale Entry-Bedingungen (AND-verknüpft)

| Bedingung | Schwelle | Quelle |
|---|---|---|
| CVS >= Minimum | >= 55 | Intern (CVS-Modell) |
| Pflichtfilter Phase 1 | Alle bestanden | Yahoo Finance |
| Technische Bedingung | >= 3 von 5 | OHLCV-Berechnung |
| IV-Rank | 20 – 80 | IB Optionskette |
| Optionsliquidität | Alle OK | IB Optionskette |
| Kein Earnings innerhalb DTE | Ja | `yfinance: earningsDate` |
| Sektor-Diversifikation | Max 3 Aktien/Sektor | Portfolio-Tracker |
| Kapital verfügbar | CSP Margin > 0 | IB Account-Daten |

### 7.2 Positionsgrößen-Berechnung

```python
# Maximales Kapital je Position (5%-Basis, CVS-skaliert)
Max_Kapital = Portfolio_Gesamt * 0.05 * (CVS / 100)

# Kontraktanzahl (immer abrunden — nie aufrunden!)
Kontrakte = floor(Max_Kapital / (Strike * 100))

# Benötigte Margin (Cash Secured = voller Strike-Wert)
Required_Margin = Strike * 100 * Kontrakte
```

### 7.3 Auftragstyp und Ausführung (IB TWS API)

| Parameter | Wert | Begründung |
|---|---|---|
| Order-Typ | `LMT` (Limit Order) | Kein Market-Order bei Optionen |
| Limit-Preis | `Bid + (Ask - Bid) * 0.33` | Unteres Drittel — nahe Bid |
| Time in Force | `DAY` | Täglich neu bewertet |
| Action | `SELL` | Short Put |
| Quantity | Kontrakte (berechnet) | Wie oben |
| Account | IB Cash-Konto | Keine Margin-Aktivierung |
| Retry-Logik | Alle 15 Min Limit +0.01 | Bis Füllung oder Tagesende |

---

## 8 | Risikomanagement & Exit-Regeln

### 8.1 Mechanische Stop-Regeln (Hard Stops)

| Trigger | Aktion | Umsetzung (IB) |
|---|---|---|
| Position > 200% Prämie | Buy-to-Close sofort | GTC Limit, automatisch |
| DTE <= 7 Tage & P&L negativ | Buy-to-Close (Gamma-Risiko) | Regelbasierter Check |
| Earnings < 5 DTE | Buy-to-Close vor Earnings | `yfinance: earningsDate` |
| Aktie fällt > 20% in 5 Tagen | Buy-to-Close (Trend-Bruch) | Täglicher Preis-Check |
| Portfolio-Drawdown > 15% | Alle Positionen reduzieren | Drawdown-Monitor |

### 8.2 Profit-Taking (Gewinnmitnahme)

```python
# Standard: 50% Profit Target Rule
Buy_to_Close wenn Gewinn >= 0.50 * Praemie_erhalten   # DTE > 14

# Kurze Restlaufzeit: 75% Target
Buy_to_Close wenn Gewinn >= 0.75 * Praemie_erhalten   # DTE <= 14
```

### 8.3 Zuteilung (Assignment) — Aktien-Übernahme

Bei Zuteilung wird die Aktie automatisch ins Depot gebucht. Da die Aktie den Qualitätsfiltern entspricht, ist dies kein Fehler — sondern der geplante Plan B.

```python
# Effektiver Kaufpreis nach Zuteilung (inkl. Prämien-Puffer)
Eff_Einstandspreis = Strike - Praemie_erhalten

# Effektive Dividendenrendite auf Einstandspreis
Div_Yield_eff = Jaehrliche_Dividende / Eff_Einstandspreis * 100
```

### 8.4 Covered Call nach Zuteilung

Nach Aktienzuteilung kann automatisch ein Covered Call geschrieben werden (Wheel-Strategie), um den Einstandspreis weiter zu senken.

| Parameter | Wert |
|---|---|
| Strike-Ziel | 52W-High oder SMA200 (höherer Wert) |
| DTE | 30 Tage |
| **Delta-Ziel** | **+0.25 bis +0.30 (Call-Delta — positiv!)** |
| Delta NICHT | < +0.15 (Prämie zu gering) |
| Delta NICHT | > +0.35 (zu viel Upside abgegeben) |
| Zweck | Prämie reduziert Einstandspreis weiter |

> ⚠️ **Wichtig:** Covered Call Delta ist **positiv** (+0.25 bis +0.30). Calls haben positives Delta — der im Original verwendete negative Wert war ein Fehler.

---

## 9 | Web-UI: Dashboard-Architektur

Die Webanwendung zeigt alle Ergebnisse auf einer einzigen übersichtlichen Seite (Single-Page).

### 9.1 Seiten-Layout (Top-Down)

| Zone | Inhalt | Daten-Quelle |
|---|---|---|
| Header | Status-Bar: Marktphase, Portfolio-Auslastung, Cash-Reserve | IB + Marktdaten |
| Scanner-Grid | Top-N Aktien sortiert nach CVS, je als Karte | Scan-Ergebnis |
| Karten-Inhalt | Ticker, Name, CVS-Badge, Key Metrics, Mini-Chart | Yahoo + IB |
| Put-Empfehlung | Strike \| Expiry \| Delta \| Prämie \| Ann.Rendite% | IB Optionskette |
| Analyse-Box | Automatischer Text: warum CVS hoch, was unterbewertet | CVS-Modell |
| Kennzahlen-Tab | Alle Fundamentaldaten als kompakte Tabelle | Yahoo Finance |
| Greeks-Panel | IV, Delta, Gamma, Theta, Vega je selektierter Option | IB API |
| Trade-Button | Direkte Order-Auslösung via IB API (1 Klick) | IB TWS API |
| History-Log | Alle Trades, P&L, Status | Lokale DB |

### 9.2 Automatische Analyse-Texte (Template)

```
[TICKER] wird mit einem P/E von [X] bewertet (Universum-Pct: [Y]%) — besser als [Z]%
aller Aktien im Scan. Die Dividendenrendite von [D]% liegt [P]% über dem 5-Jahres-Durchschnitt.
RSI von [R] signalisiert keine Überhitzung. IV-Rank: [IV] — Optionsprämien erhöht.
Empfehlung: Short Put Strike [S], Expiry [E], Prämie [PR] EUR, ann. [AR]%.
```

### 9.3 Metriken je Aktien-Karte

| Block | Angezeigte Kennzahlen |
|---|---|
| Bewertung | P/E, P/B, EV/EBITDA, P/S — je mit Universum-Perzentil-Ampel |
| Dividende | Yield, Payout-Ratio, 5Y-Avg-Yield, Div-Wachstum 3/5J |
| Qualität | ROE, ROA, Profitmarge, Op.Cashflow, Free Cashflow |
| Technisch | RSI, Kurs vs. SMA50/200, BB-Position, ATR14 |
| Risiko | Beta, Debt/Equity, Current Ratio, Short Ratio |
| Options | Strike, Expiry, DTE, Delta, Theta, IV, Bid/Ask, OI, Ann% |
| CVS Breakdown | Balken-Chart: FVS/DVS/QVS/TVS/VVS Anteil am Score |

---

## 10 | Implementierungs-Roadmap

| Phase | Modul | Kern-Komponenten | Priorität |
|---|---|---|---|
| 1 | Daten-Layer | yfinance Wrapper, IB API Client, Caching (Redis/SQLite) | 🔴 HOCH |
| 1 | Fundamental Screener | Pflichtfilter M1–M11, Universumsbasiertes Scoring (inv. Pct.) | 🔴 HOCH |
| 2 | Scoring Engine | CVS-Berechnung: FVS, DVS, QVS, TVS, VVS | 🔴 HOCH |
| 2 | Technische Indikatoren | RSI, MACD, Bollinger, SMA, Stochastic, ATR | 🔴 HOCH |
| 3 | Options-Selektion | Expiry-Wahl, Delta-Filter (–0.30 Ziel), Liquiditäts-Check, OS | 🔴 HOCH |
| 3 | Order-Management | IB LMT-Orders, Retry-Logik, Confirmation | 🔴 HOCH |
| 4 | Web-Dashboard | FastAPI Backend, React/Vue Frontend, Auto-Texte | 🟡 MITTEL |
| 4 | Risiko-Monitor | Stop-Regeln, Profit-Target-Checker, Drawdown-Monitor | 🟡 MITTEL |
| 5 | Covered Call Modul | Auto-CC nach Assignment: Delta +0.25–0.30, DTE 30 Tage | 🟡 MITTEL |
| 5 | Backtesting-Modul | Historische Simulation aller Regeln auf OHLCV | ⚪ OPTIONAL |
| 5 | Reporting | PDF/CSV Export, Performance-Attribution | ⚪ OPTIONAL |

---

## A | Anhang: Alle Formeln im Überblick

### FVS — Fundamental Value Score (universumsbasiert)

```python
FVS = 0.35 * inv_pct(PE) + 0.25 * inv_pct(PB) + 0.25 * inv_pct(EV_EBITDA) + 0.15 * inv_pct(PS)
# inv_pct(x) = (1 - percentile_rank(x)) * 100    # niedrig = gut
```

### Q-Score — Qualitäts-Score

```python
Q = 0.25*ROE_n + 0.25*ROA_n + 0.25*Margin_n + 0.15*EG_n + 0.10*RG_n
```

### DVS — Dividend Value Score

```python
DVS = YieldNorm*0.5 + (1 - PayoutRatio)*0.3 + DivGrowth5Y_n*0.2
```

### TVS — Technical Value Score

```python
TVS = (RSI_S + SMA_S + BB_S + MACD_S + Stoch_S) / 1.40
```

### VVS — Volatility Score

```python
VVS = 100 - abs(IV_Rank - 50) * 2   # Maximum bei IV_Rank = 50
```

### CVS — Composite Value Score

```python
CVS = 0.30*FVS + 0.25*DVS + 0.20*QVS + 0.15*TVS + 0.10*VVS
```

### HV30 — Historische Volatilität

```python
HV30 = std(log(C_t / C_t_minus_1), 30) * sqrt(252) * 100
```

### IV Rank

```python
IV_R = (IV_cur - IV_low52) / (IV_high52 - IV_low52) * 100
```

### Ann. Prämienrendite

```python
Ann_pct = (Praemie / Strike) * (365 / DTE) * 100
```

### Effektiver Einstandspreis (nach Assignment)

```python
EEK        = Strike - Praemie_erhalten
Div_eff_pct = Jahresdividende / EEK * 100
```

### Positionsgröße

```python
Kontrakte = floor(Portfolio * 0.05 * (CVS / 100) / (Strike * 100))
```

### Min. Strike-Distanz (ATR-basiert)

```python
Min_Strike = Kurs - 1.5 * ATR14
```

### Options Score (OS)

```python
OS = Ann_pct*0.40 + Delta_Score*0.30 + Theta_Score*0.20 + Liq_Score*0.10
Delta_Score = 1 - abs(delta - (-0.30)) / 0.30
```

### Bid-Ask Spread %

```python
Spread_pct = (Ask - Bid) / Bid * 100   # < 5% erforderlich
```

### P/E Universum-Perzentil

```python
PE_pct = inv_pct_rank(universe.trailingPE, stock.trailingPE)
```

### Div Yield Sigma

```python
Sigma = (DivYield - FiveY_Avg) / StdDev(DivYield, 5Y)
```

---

> **Wichtiger Hinweis:** Diese Strategie ist ein mechanisches Regelwerk. Sie ersetzt keine individuelle Anlageberatung. Optionshandel ist mit erheblichen Risiken verbunden. Alle Berechnungen basieren auf historischen Daten und API-Echtzeit-Feeds. Backtesting vor dem Live-Einsatz wird dringend empfohlen.
