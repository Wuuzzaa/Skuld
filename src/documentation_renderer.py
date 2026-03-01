import pandas as pd

def render_documentation(
    example_row: pd.Series,
    current_price: float,
    cost_basis: float,
    collar_enabled: bool = False,
    call_price: float = None,
    call_strike: float = None,
) -> str:
    """
    Rendert die Inline-Dokumentation basierend auf der ersten Tabellenzeile.
    
    Args:
        example_row: Erste Zeile des angezeigten DataFrames (pd.Series)
        current_price: Aktueller Aktienkurs
        cost_basis: Einstandskurs des Nutzers
        collar_enabled: Ist ein Call ausgewählt?
        call_price: Preis des ausgewählten Calls (nur bei Collar)
        call_strike: Strike des ausgewählten Calls (nur bei Collar)
    """
    
    # Werte extrahieren (angepasst an married_put_finder Spaltennamen)
    strike = float(example_row.get('strike_price', 0.0))
    put_price = float(example_row.get('put_midpoint_price', 0.0))
    dte = int(example_row.get('days_to_expiration', 1))
    label = str(example_row.get('put_label', ''))
    
    # Berechnete Spalten
    intrinsic = float(example_row.get('intrinsic_value', max(0.0, strike - current_price)))
    time_value = float(example_row.get('put_time_value', 0.0))
    tv_per_month = float(example_row.get('put_time_value_per_mo', 0.0))
    new_cb = float(example_row.get('new_cost_basis', 0.0))
    locked_in = float(example_row.get('locked_in_profit', 0.0))
    locked_in_pct = float(example_row.get('locked_in_profit_pct', 0.0))
    
    # Zusätzliche Metriken (falls vorhanden)
    insurance_cost_pct = example_row.get('insurance_cost_pct', None)
    downside_pct = example_row.get('downside_protection_pct', None)
    annualized_cost = example_row.get('annualized_cost', None)
    annualized_cost_pct = example_row.get('annualized_cost_pct', None)
    
    # Bestimme ob Put ITM oder OTM ist
    is_itm = strike > current_price
    if strike > current_price:
        itm_otm_label = "ITM (im Geld)"
    elif strike < current_price:
        itm_otm_label = "OTM (aus dem Geld)"
    else:
        itm_otm_label = "ATM (am Geld)"
        
    itm_text = (
        f"Der Put ist **ITM** (Strike {strike:.2f}$ > Kurs {current_price:.2f}$), daher hat er inneren Wert. "
        f"Du könntest theoretisch die Aktie bei {strike:.2f}$ verkaufen, obwohl sie nur {current_price:.2f}$ wert ist – das ist {intrinsic:.2f}$ Gewinn."
    ) if is_itm else (
        f"Der Put ist **OTM** (Strike {strike:.2f}$ ≤ Kurs {current_price:.2f}$), daher ist der innere Wert 0. "
        f"Es wäre sinnlos, die Aktie bei {strike:.2f}$ zu verkaufen, wenn sie am Markt {current_price:.2f}$ wert ist."
    )

    tv_warn_text = (
        f"**⚠️ Achtung:** Bei nur {dte} Tagen Restlaufzeit ist der Zeitwert pro Monat besonders hoch ({tv_per_month:.2f}$). "
        "Das bedeutet NICHT, dass diese Option teuer ist – sondern dass der Zeitverfall bei kurzer Laufzeit überproportional hoch ist. "
        "Vergleiche immer Optionen mit ähnlicher Laufzeit."
    ) if dte < 30 else (
        f"Bei {dte} Tagen Laufzeit zahlst du {tv_per_month:.2f}$ pro Monat an Zeitwert. "
        "Je niedriger dieser Wert, desto effizienter ist die Absicherung."
    )

    locked_in_text = (
        f"✅ **Positiv ({locked_in:.2f}$):** Dir sind mindestens {locked_in:.2f}$ Gewinn pro Aktie sicher. "
        f"Selbst im Worst Case (Aktie crasht) kannst du bei {strike:.2f}$ verkaufen, und dein Einstand war {new_cb:.2f}$."
    ) if locked_in > 0 else (
        f"⚠️ **Negativ ({locked_in:.2f}$):** Der Put sichert nicht deinen vollen Einstand ab. "
        f"Im Worst Case hättest du einen Verlust von {abs(locked_in):.2f}$ pro Aktie. "
        f"Der Strike ({strike:.2f}$) liegt unter deinem neuen Einstandskurs ({new_cb:.2f}$)."
    )

    locked_in_pct_text = (
        f"Das bedeutet: Du hast {new_cb:.2f}$ investiert (Aktie + Put) und dir sind mindestens **{locked_in_pct:.1f}% Rendite** sicher."
    ) if locked_in_pct > 0 else (
        f"Das bedeutet: Es besteht ein maximales Restrisiko von {abs(locked_in_pct):.1f}% auf deinen Einstand."
    )
    
    md = f"""
### 📖 Berechnungsbeispiel anhand: **{label}**

Alle Berechnungen unten verwenden diese Option als durchgängiges Beispiel. 
Die Werte stammen direkt aus der Tabelle oben – du kannst sie dort in der entsprechenden Zeile wiederfinden.

---

**Ausgangslage:**
| Parameter | Wert | Quelle |
|---|---|---|
| Aktueller Aktienkurs | **{current_price:.2f}$** | Live-Kurs |
| Dein Einstandskurs (Cost Basis) | **{cost_basis:.2f}$** | Deine Eingabe |
| Put Strike | **{strike:.2f}$** | {itm_otm_label} |
| Put Preis (Midpoint) | **{put_price:.2f}$** | Marktdaten |
| Tage bis Verfall (DTE) | **{dte}** | Berechnet |

---

#### 1️⃣ Innerer Wert (Intrinsic Value)

Der innere Wert ist der "echte" Wert des Puts – was er wert wäre, wenn du ihn **sofort** ausüben würdest.

**Formel:**
Innerer Wert = max(0, Strike - Aktueller Kurs)
= max(0, {strike:.2f} - {current_price:.2f})
= {intrinsic:.2f}$

{itm_text}

---

#### 2️⃣ Zeitwert (Time Value)

Der Zeitwert ist der Teil des Put-Preises, der **über** den inneren Wert hinausgeht. Er spiegelt die Wahrscheinlichkeit wider, dass der Put bis zum Verfall noch wertvoller wird. Das ist der eigentliche "Preis der Versicherung".

**Formel:**
Zeitwert = Put Preis - Innerer Wert
= {put_price:.2f} - {intrinsic:.2f}
= {time_value:.2f}$

---

#### 3️⃣ Zeitwert pro Monat (Time Value /Mo)

Damit du Optionen mit verschiedenen Laufzeiten vergleichen kannst, wird der Zeitwert auf einen Monat normalisiert.

**Formel:**
Zeitwert/Monat = Zeitwert / (DTE / 30)
= {time_value:.2f} / ({dte} / 30)
= {time_value:.2f} / {dte/30:.4f}
= {tv_per_month:.2f}$

{tv_warn_text}

---

#### 4️⃣ Neuer Einstandskurs (New Cost Basis)

Wenn du den Put kaufst, erhöht sich dein effektiver Einstandskurs um den Put-Preis.

**Formel:**
Neuer Einstandskurs = Cost Basis + Put Preis
= {cost_basis:.2f} + {put_price:.2f}
= {new_cb:.2f}$

Dein "All-in" Preis für die abgesicherte Position ist also **{new_cb:.2f}$** pro Aktie (Aktie + Versicherung).

---

#### 5️⃣ Locked-in Profit ($)

Das ist der **garantierte Mindestgewinn** – der Betrag, den du auf jeden Fall behältst, egal was mit dem Aktienkurs passiert. Selbst wenn die Aktie auf 0$ fällt, kannst du sie zum Put-Strike verkaufen.

**Formel:**
Locked-in Profit = Strike - Neuer Einstandskurs
= {strike:.2f} - {new_cb:.2f}
= {locked_in:.2f}$

{locked_in_text}

---

#### 6️⃣ % Locked-in Profit

Derselbe garantierte Gewinn, aber als Prozentwert bezogen auf deinen Einstandskurs.

**Formel:**
% Locked-in Profit = (Locked-in Profit / Neuer Einstandskurs) × 100
= ({locked_in:.2f} / {new_cb:.2f}) × 100
= {locked_in_pct:.2f}%

{locked_in_pct_text}
"""

    if pd.notna(insurance_cost_pct):
        md += f"""
---

#### 7️⃣ Versicherungskosten (% des Positionswerts)

Wie viel Prozent des aktuellen Aktienwerts kostet dich die Absicherung? Vergleichbar mit einer Versicherungsprämie.

**Formel:**
Versicherung (%) = (Put Preis / Aktueller Kurs) × 100
= ({put_price:.2f} / {current_price:.2f}) × 100
= {insurance_cost_pct:.2f}%

Du zahlst **{insurance_cost_pct:.2f}%** des Aktienwerts für die Absicherung.
"""

    if pd.notna(downside_pct):
        downside_text = (
            f"**Negativ ({downside_pct:.2f}%):** Der Put ist ITM – er greift bereits ÜBER dem aktuellen Kurs. Du bist sogar für einen Kursanstieg-dann-Rückfall geschützt." 
            if downside_pct < 0 else 
            f"**Positiv ({downside_pct:.2f}%):** Die Aktie muss erst {downside_pct:.1f}% fallen, bevor der Put greift. Das ist dein Selbstbehalt."
        )
        md += f"""
---

#### 8️⃣ Absicherungstiefe (Downside Protection %)

Wie viel Prozent muss die Aktie fallen, bevor der Put greift?

**Formel:**
Absicherungstiefe = ((Aktueller Kurs - Strike) / Aktueller Kurs) × 100
= (({current_price:.2f} - {strike:.2f}) / {current_price:.2f}) × 100
= {downside_pct:.2f}%

{downside_text}
"""

    if pd.notna(annualized_cost) and pd.notna(annualized_cost_pct):
        md += f"""
---

#### 9️⃣ Annualisierte Kosten

Der Zeitwert auf ein Jahr hochgerechnet – damit du Laufzeiten direkt vergleichen kannst.

**Formel:**
Kosten p.a. ($) = (Zeitwert / DTE) × 365
= ({time_value:.2f} / {dte}) × 365
= {annualized_cost:.2f}$
Kosten p.a. (%) = (Kosten p.a. / Aktueller Kurs) × 100
= ({annualized_cost:.2f} / {current_price:.2f}) × 100
= {annualized_cost_pct:.2f}%

Die Absicherung kostet hochgerechnet **{annualized_cost_pct:.2f}% pro Jahr** des Aktienwerts.
"""

    # Collar-Metriken (nur wenn aktiviert)
    if collar_enabled and call_price is not None and call_strike is not None:
        collar_ncb = cost_basis + put_price - call_price
        collar_lip = strike - collar_ncb
        collar_lip_pct = (collar_lip / collar_ncb) * 100 if collar_ncb != 0 else 0.0
        collar_net = put_price - call_price
        collar_max = call_strike - collar_ncb
        collar_max_pct = (collar_max / collar_ncb) * 100 if collar_ncb != 0 else 0.0
        pct_assigned = (call_strike - collar_ncb) / collar_ncb * 100 if collar_ncb != 0 else 0.0
        put_value_at_call = max(0.0, strike - call_strike)
        pct_assigned_wp = (call_strike - collar_ncb + put_value_at_call) / collar_ncb * 100 if collar_ncb != 0 else 0.0
        
        collar_net_text = (
            f"✅ **Netto-Credit ({collar_net:.2f}$):** Du bekommst sogar Geld dafür! Die Call-Prämie übersteigt die Put-Kosten." if collar_net < 0 
            else f"Die Absicherung kostet dich netto **{collar_net:.2f}$**." if collar_net > 0 
            else "🎉 **Costless Collar:** Die Call-Prämie deckt die Put-Kosten exakt. Absicherung zum Nulltarif!"
        )
        
        put_val_text = (
            "In diesem Fall ist % Assigned With Put = % Assigned, weil der Put bei Assignment keinen inneren Wert mehr hat (Call Strike ≥ Put Strike)." 
            if put_value_at_call <= 0.001 else 
            f"Der Put hat bei Assignment noch {put_value_at_call:.2f}$ Restwert, weil der Put-Strike ({strike:.2f}$) über dem Call-Strike ({call_strike:.2f}$) liegt."
        )

        md += f"""
---

### 🔗 Collar-Metriken (mit verkauftem Call)

**Zusätzliche Daten (verkaufter Call):**
| Parameter | Wert |
|---|---|
| Call Strike | **{call_strike:.2f}$** |
| Call Prämie (eingenommen) | **{call_price:.2f}$** |

---

#### C1: Neuer Einstandskurs (Collar)

Die Call-Prämie reduziert deinen Einstandskurs.

**Formel:**
Neuer Einstand (Collar) = Cost Basis + Put Preis - Call Prämie
= {cost_basis:.2f} + {put_price:.2f} - {call_price:.2f}
= {collar_ncb:.2f}$

**Vergleich:** Ohne Call wäre dein Einstand {new_cb:.2f}$, mit Call nur {collar_ncb:.2f}$ – du sparst {call_price:.2f}$.

---

#### C2: Netto-Kosten der Absicherung

Was kostet die Collar-Strategie insgesamt?

**Formel:**
Netto-Kosten = Put Preis - Call Prämie
= {put_price:.2f} - {call_price:.2f}
= {collar_net:.2f}$

{collar_net_text}

---

#### C3: Locked-in Profit (Collar)

**Formel:**
Locked-in Profit (Collar) = Put Strike - Neuer Einstand (Collar)
= {strike:.2f} - {collar_ncb:.2f}
= {collar_lip:.2f}$ ({collar_lip_pct:.2f}%)

---

#### C4: Max. Gewinn (Cap)

Durch den verkauften Call ist dein Gewinn nach oben begrenzt.

**Formel:**
Max. Gewinn = Call Strike - Neuer Einstand (Collar)
= {call_strike:.2f} - {collar_ncb:.2f}
= {collar_max:.2f}$ ({collar_max_pct:.2f}%)

Wenn die Aktie über **{call_strike:.2f}$** steigt, wirst du assigned – du verkaufst bei {call_strike:.2f}$ und realisierst maximal {collar_max:.2f}$ Gewinn.

---

#### C5: % Assigned

Rendite bei Assignment (Aktie wird beim Call-Strike abgerufen).

**Formel:**
% Assigned = (Call Strike - Neuer Einstand) / Neuer Einstand × 100
= ({call_strike:.2f} - {collar_ncb:.2f}) / {collar_ncb:.2f} × 100
= {pct_assigned:.2f}%

---

#### C6: % Assigned With Put

Wie % Assigned, aber berücksichtigt den Restwert des Puts bei Assignment.

**Formel:**
Put-Wert bei Call-Strike = max(0, Put Strike - Call Strike)
= max(0, {strike:.2f} - {call_strike:.2f})
= {put_value_at_call:.2f}$
% Assigned With Put = (Call Strike - Neuer Einstand + Put-Wert) / Neuer Einstand × 100
= ({call_strike:.2f} - {collar_ncb:.2f} + {put_value_at_call:.2f}) / {collar_ncb:.2f} × 100
= {pct_assigned_wp:.2f}%

{put_val_text}
"""

    # Abschluss: Zusammenfassungstabelle
    md += f"""
---

### 📋 Zusammenfassung aller Werte

| Metrik | Formel | Ergebnis |
|---|---|---|
| Innerer Wert | max(0, {strike:.2f} - {current_price:.2f}) | **{intrinsic:.2f}$** |
| Zeitwert | {put_price:.2f} - {intrinsic:.2f} | **{time_value:.2f}$** |
| Zeitwert/Monat | {time_value:.2f} / ({dte}/30) | **{tv_per_month:.2f}$** |
| Neuer Einstandskurs | {cost_basis:.2f} + {put_price:.2f} | **{new_cb:.2f}$** |
| Locked-in Profit | {strike:.2f} - {new_cb:.2f} | **{locked_in:.2f}$** |
| % Locked-in Profit | ({locked_in:.2f} / {new_cb:.2f}) × 100 | **{locked_in_pct:.2f}%** |
"""

    if pd.notna(insurance_cost_pct):
        md += f"| Versicherung (%) | ({put_price:.2f} / {current_price:.2f}) × 100 | **{insurance_cost_pct:.2f}%** |\n"
    if pd.notna(downside_pct):
        md += f"| Absicherungstiefe | (({current_price:.2f} - {strike:.2f}) / {current_price:.2f}) × 100 | **{downside_pct:.2f}%** |\n"
    if pd.notna(annualized_cost_pct):
        md += f"| Kosten p.a. (%) | ({time_value:.2f} / {dte}) × 365 / {current_price:.2f} × 100 | **{annualized_cost_pct:.2f}%** |\n"

    return md
