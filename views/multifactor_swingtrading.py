import streamlit as st
from config import *
from src.multifactor_swingtrading_strategy import calculate_multifactor_swingtrading_strategy
from src.page_display_dataframe import page_display_dataframe
from src.database import select_into_dataframe

# Titel
st.subheader("Multifactor Swingtrading")

# Parameter inputs
col1, col2, col3, col4 = st.columns(4)

with col1:
    top_percentile_value_score = st.slider(
        "Top Percentile Value Score",
        min_value=5.0,
        max_value=100.0,
        value=20.0,
        step=5.0,
        help="Percentile for value score (e.g. 20 = top 20%)"
    )

with col2:
    top_n = st.number_input(
        "Top N Stocks",
        min_value=1,
        max_value=200,
        value=50,
        step=5,
        help="Number of top stocks to select"
    )

with col3:
    drop_missing_values = st.checkbox(
        "Drop Missing Values",
        value=False,
        help="Exclude stocks with missing values from analysis"
    )

with col4:
    drop_weak_value_factors = st.checkbox(
        "Drop Weak Value Factors",
        value=False,
        help="Exclude stocks with weak value factors"
    )

st.divider()

# SQL query
sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'multifactor_swingtrading.sql'

# Load data and calculate strategy (runs on every parameter change)
with st.spinner('Loading data and calculating strategy...'):
    # Load data
    df = select_into_dataframe(sql_file_path=sql_file_path)

    # Calculate strategy
    df = calculate_multifactor_swingtrading_strategy(
        df,
        top_percentile_value_score=top_percentile_value_score,
        top_n=top_n,
        drop_missing_values=drop_missing_values,
        drop_weak_value_factors=drop_weak_value_factors
    )

# Display dataframe
page_display_dataframe(df, symbol_column='symbol')

st.markdown("""
# Leitfaden zu Fundamentalkennzahlen für die Aktienanalyse

## Überblick

Die folgenden sechs Kennzahlen helfen Ihnen, die fundamentale Bewertung und Qualität von Aktien zu beurteilen. Sie basieren auf dem Verhältnis zwischen Aktienkurs und verschiedenen finanziellen Größen des Unternehmens.

---
## Zusammenfassung

| Metrik | Sehr Gut | Gut | Moderat | Schwach |
|--------|----------|------|---------|---------|
| P/B | 0,5–1,0 | 1,0–1,5 | 1,5–2,0 | >2,0 oder <0,3 |
| P/E | 8–12 | 12–20 | 20–30 | <5 oder >30 |
| P/S | <0,8 | 0,8–1,5 | 1,5–2,0 | >2,0 |
| EBITDA/EV | >0,15 | 0,10–0,15 | 0,05–0,10 | <0,05 |
| P/CF | >0,10 | 0,05–0,10 | 0,00–0,05 | Negativ |
| 1Y Performance | >+10% | 0–+10% | -10–0% | <-30% |
---

## 1. Price-to-Book (P/B) – Kurs-Gewinn-Verhältnis zum Buchwert

**Was bedeutet es?**
Der Price-to-Book-Ratio vergleicht den Aktienkurs mit dem Buchwert pro Aktie (Eigenkapital dividiert durch Anzahl der Aktien). Er zeigt, wie viel Anleger für jeden Euro Eigenkapital zahlen.

**Was ist ein guter Wert?**
- **0,5 bis 1,5:** Ideal. Das Unternehmen ist fair bewertet oder leicht unterbewertet
- **Unter 0,5:** Potenziell unterbewertet, kann aber auch strukturelle Probleme signalisieren
- **Über 2,0:** Tendenziell überbewertet oder das Unternehmen hat hohe Wachstumserwartungen

**Interpretation:**
Nutzen Sie P/B in Kombination mit anderen Metriken. Ein sehr niedriger P/B könnte ein Value-Schnäppchen oder ein Warnzeichen sein.

---

## 2. Price-to-Earnings (P/E) – Kurs-Gewinn-Verhältnis

**Was bedeutet es?**
Das P/E-Verhältnis teilt den Aktienkurs durch den Gewinn pro Aktie. Es zeigt, wie viele Jahre Sie warten müssen, bis der Gewinn des Unternehmens dem Aktienkurs entspricht.

**Was ist ein guter Wert?**
- **8 bis 15:** Sehr attraktiv, oft ein Zeichen für Unterbewertung
- **15 bis 25:** Fair bewertet, typisch für den Marktdurchschnitt
- **Über 25:** Teuer, deutet auf hohe Wachstumserwartungen hin
- **Negative Werte oder sehr niedrig (unter 5):** Warnsignal – das Unternehmen macht möglicherweise keinen oder sehr wenig Gewinn

**Interpretation:**
Ein niedriges P/E kann ein Value-Signal sein, aber prüfen Sie, warum der Kurs so niedrig ist. Manchmal sind niedrige P/E-Verhältnisse berechtigt.

---

## 3. Price-to-Sales (P/S) – Kurs-Umsatz-Verhältnis

**Was bedeutet es?**
Der Price-to-Sales-Ratio teilt die Marktkapitalisierung durch den Gesamtumsatz. Er zeigt, wie viel Anleger für jeden Euro Umsatz zahlen. Diese Metrik ist schwerer zu manipulieren als der Gewinn, da Umsätze schwächer zu verfälschen sind.

**Was ist ein guter Wert?**
- **Unter 1,0:** Attraktiv, das Unternehmen generiert viel Umsatz pro investiertem Euro
- **1,0 bis 2,0:** Fair bis moderat
- **Über 2,0:** Teuer, hohe Wachstumserwartungen eingepreist
- **Sehr niedrig (unter 0,3):** Kann auf Profitabilitätsprobleme hindeuten

**Interpretation:**
P/S ist besonders hilfreich bei Unternehmen mit niedrigen oder negativen Gewinnen, da Umsätze konsistenter sind als Gewinne.

---

## 4. EBITDA-to-Enterprise-Value (EV/EBITDA) – Umgekehrtes EV/EBITDA-Verhältnis

**Was bedeutet es?**
Diese Metrik ist die Umkehrung des bekannten EV/EBITDA-Verhältnisses. Sie teilt das operative Ergebnis (EBITDA: Gewinn vor Zinsen, Steuern, Abschreibungen und Amortisationen) durch den Unternehmenswert. Ein höherer Wert bedeutet, dass das Unternehmen mehr operativen Gewinn pro Bewertungseinheit generiert.

**Was ist ein guter Wert?**
- **Über 0,15:** Sehr attraktiv, das Unternehmen generiert starken operativen Gewinn
- **0,10 bis 0,15:** Gut, solide operative Profitabilität
- **0,05 bis 0,10:** Moderat, kann bei wachstumsstarken Unternehmen akzeptabel sein
- **Unter 0,05:** Schwach, deutet auf geringe operative Rentabilität hin

**Interpretation:**
Dies ist eine der besten Metriken zur Bewertung der tatsächlichen Profitabilität. Ein hoher Wert hier ist ein sehr positives Zeichen.

---

## 5. Price-to-Cashflow (P/CF) – Kurs-Cashflow-Verhältnis

**Was bedeutet es?**
Das P/CF-Verhältnis teilt den Aktienkurs durch den freien Cashflow pro Aktie. Es zeigt, wie viel Anleger für jeden Euro Cashflow zahlen. Cashflow ist oft zuverlässiger als Buchengewinn, da er schwerer zu manipulieren ist.

**Was ist ein guter Wert?**
- **Über 0,10:** Das Unternehmen hat positiven und stabilen Cashflow
- **0,05 bis 0,10:** Moderat, akzeptabel
- **Unter 0,05 oder Null:** Schwach bis keine Cashflow-Generierung
- **Negative Werte:** Warnsignal – das Unternehmen hat negativen Cashflow und verbrennt Bargeld

**Interpretation:**
Negative oder fehlende Cashflows sind ein ernstes Warnzeichen. Sie deuten darauf hin, dass das Unternehmen nicht genug flüssiges Geld generiert. Seien Sie bei solchen Unternehmen vorsichtig, auch wenn andere Metriken gut aussehen.

---

## 6. 1-Year Price Appreciation – Einjährige Kursperformance

**Was bedeutet es?**
Dies zeigt die prozentuale Veränderung des Aktienkurses über die letzten 12 Monate. Ein positiver Wert zeigt Kurssteigerung, ein negativer zeigt Kursrückgang.

**Was ist ein guter Wert?**
- **Über +10%:** Starke Performance, positive Dynamik
- **0% bis +10%:** Moderat stabil
- **-10% bis 0%:** Schwache bis fallende Performance
- **Unter -30%:** Deutliche Underperformance, kann Warnsignal oder Kaufgelegenheit sein

**Interpretation:**
Negative Performance kann bedeuten, dass der Markt das Unternehmen negativ sieht – oder es könnte eine Kaufgelegenheit sein, wenn die Fundamentals stark sind. Dies sollte mit anderen Metriken kombiniert werden.

---

## Wie man diese Metriken zusammen nutzt

Die beste Analyse kombiniert mehrere Metriken:

**Szenario 1: Value-Kandidat**
- Niedriges P/B und P/E
- Solides P/CF (positiv)
- Hohe EBITDA/EV
- Negative oder schwache Kursperformance (zyklisch oder Marktrückgang)

**Szenario 2: Warnsignal**
- Niedriges P/B und P/E, aber...
- Negatives P/CF oder 0,00
- Schwache Kursperformance
- → Prüfen Sie, warum! Es könnte strukturelle Probleme geben.

**Szenario 3: Faires Unternehmen**
- Moderate Bewertungen (P/B 1,0-1,5, P/E 15-20)
- Positiver Cashflow
- Solide EBITDA/EV (über 0,10)
- → Dies ist ein ausgewogener Kandidat.
""")