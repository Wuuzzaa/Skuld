import streamlit as st
import pandas as pd
import urllib.parse


def _add_tradingview_link(df:pd.DataFrame, symbol_column='symbol'):
    df['TradingView'] = df[symbol_column].apply(
        lambda x: f'https://www.tradingview.com/symbols/{x}/'
    )
    return df

def _add_tradingview_superchart_link(df:pd.DataFrame, symbol_column='symbol'):
    df['Chart'] = df[symbol_column].apply(
        lambda x: f'https://www.tradingview.com/chart/?symbol={x}'
    )
    return df


def _add_claude_analysis_link(df: pd.DataFrame, symbol_column='symbol'):
    """Adds Claude AI analysis link with pre-filled prompt"""

    def create_claude_prompt(symbol):
        # prompt = f"""
        #     Erstelle eine kompakte Aktienanalyse für {symbol}:
        #     Unternehmen: Geschäftsmodell und Branche in 1-2 Sätzen
        #     Aktuelle News: Wichtigste Entwicklungen der letzten 4 Wochen
        #     Anstehende Events: Earnings, Produktlaunches oder relevante Termine
        #     Einschätzung:
        #
        #     Kauf/Halten/Verkaufen mit Begründung
        #     Aktuelles Kursziel (Analystenkonsens)
        #     Wichtigste Chance und größtes Risiko
        #
        #     Format: Prägnant, faktenbasiert, keine Füllwörter, max. eine Seite.
        # """

        prompt = f"""
            Erstelle eine kompakte Aktienanalyse für {symbol}:
            Unternehmen: Geschäftsmodell und Branche in 1-2 Sätzen
            Aktuelle News: Wichtigste Entwicklungen der letzten 4 Wochen
            Anstehende Events: Earnings, Produktlaunches oder relevante Termine
            Einschätzung:

            Kauf/Halten/Verkaufen mit Begründung
            Aktuelles Kursziel (Analystenkonsens)
            Eigenes Kursziel durch Fundamentaldaten, News, Technische Analyse State of the Art
            Wichtigste Chance und größtes Risiko

            Format: Prägnant, faktenbasiert, keine Füllwörter, max. eine Seite.
        """



#         prompt = f"""
# Erstelle eine kompakte, faktenbasierte Aktienanalyse für {symbol}.
# Maximal eine Seite, prägnant, keine Füllwörter. Verwende verfügbare Quellen aus Fundamentaldaten, technischen Indikatoren, Analystenkonsens und relevanten News der letzten 4 Wochen. Gib stets konkrete Datenpunkte oder Quellen an (Kurswerte, Datum, Quelle).
#
# 1. Unternehmen (1–2 Sätze)
#
# Beschreibe Geschäftsmodell, Branche und wichtigste Umsatztreiber.
#
# 2. Aktuelle News (letzte 4 Wochen)
#
# Fasse die 3–5 wichtigsten Entwicklungen mit Datum und Quelle/Kurztitel zusammen.
#
# 3. Anstehende Events
#
# Nenne bevorstehende Earnings, Produktlaunches oder relevante Termine mit Datum und kurzer Bedeutung.
#
# 4. Einschätzung
#
# Empfehlung: Kauf / Halten / Verkaufen (ein Wort)
# Begründung (2–4 Bulletpoints):
#
# Wichtigste Treiber der Empfehlung auf Basis von Fundamental-, Technik- und News-Daten
#
# Analystenkonsens:
#
# Aktuelles Kursziel (Mittelwert oder Median)
#
# Anzahl der Analysten
#
# Quelle
#
# Eigene Kursvorhersage:
#
# Kursziel (konkrete Zahl mit Währung) und Zeithorizont (z. B. 3M / 12M)
#
# Kurze Methodikbegründung (max. 2 Sätze): Welche Kombination von Modellen (Fundamental, technisch, News) genutzt wurde
#
# Angabe der Gewichtung (z. B. Fundamental 50 %, Technisch 30 %, News 20 %) und Begründung für diese Gewichtung
#
# Wichtige Annahmen (z. B. Gewinnwachstum, KGV-Erwartung, Widerstands- oder Unterstützungsniveaus, Eventeinfluss)
#
# Konfidenzstufe (niedrig / mittel / hoch) und Wahrscheinlichkeit in % mit kurzer Begründung
#
# Wichtigste Chance: (1 Satz)
# Größtes Risiko: (1 Satz)
#
# Formatanforderungen
#
# Klare Struktur wie oben
#
# Maximal eine Seite
#
# Alle numerischen Werte mit Währung und Datum (z. B. „EUR 12,34 – Schlusskurs 2025-10-24“)
#
# Web- oder Datenquellen kurz zitieren (Name / Datum)
#
# Nur prägnante, belegbare Fakten – keine allgemeinen Phrasen
#
# Methodenhinweis für die Kursvorhersage
#
# Nutze eine kombinierte Bewertung aus:
#
# Fundamentalmodell: Bewertungskennzahlen wie Umsatz, EPS, Margen, KGV, EV/EBITDA → Schätzung des fairen Werts
#
# Technisches Modell: Trendindikatoren (50/200-Tage-Linien), RSI, MACD, Momentum, Unterstützungen/Widerstände → kurzfr. Dynamik
#
# News- & Sentiment-Modell: Analyse der letzten 4 Wochen (positiv/neutral/negativ, Relevanz) → Einflussfaktor auf Marktstimmung
#
# Kombiniere die Modelle gewichtet (z. B. Fundamental 50 % / Technisch 30 % / News 20 %) und begründe kurz, warum diese Gewichtung für das betrachtete Unternehmen sinnvoll ist.
#         """


#         prompt = f"""
# # Aktienanalyse-Prompt für {symbol}
#
# Erstelle eine kompakte, visuell strukturierte Aktienanalyse für {symbol}.
# Maximal eine Seite, prägnant, keine Füllwörter. Verwende verfügbare Quellen aus Fundamentaldaten, technischen Indikatoren, Analystenkonsens und relevanten News der letzten 4 Wochen. Gib stets konkrete Datenpunkte oder Quellen an (Kurswerte, Datum, Quelle).
#
# Die Ausgabe soll visuell ansprechend formatiert sein mit klaren Trennlinien, Tabellen und strukturierten Darstellungen für Kursziele, Widerstände und Unterstützungen.
#
# ---
#
# ## 1. UNTERNEHMEN (1–2 Sätze)
#
# Beschreibe Geschäftsmodell, Branche und wichtigste Umsatztreiber.
#
# ---
#
# ## 2. AKTUELLE NEWS (letzte 4 Wochen)
#
# Fasse die 3–5 wichtigsten Entwicklungen zusammen im Format:
# - [DATUM] – [Kurztitel] (Quelle) – [Kursreaktion falls relevant: z.B. +3,2%]
#
# ---
#
# ## 3. ANSTEHENDE EVENTS
#
# Nenne bevorstehende Earnings, Produktlaunches oder relevante Termine im Format:
# - [DATUM] – [Event] – [Bedeutung in einem Satz]
#
# ---
#
# ## 4. TECHNISCHE ANALYSE
#
# ### KURSNIVEAUS & ZIELE
#
# Stelle Widerstände und Unterstützungen in folgender tabellarischer Form dar:
#
# ```
# WIDERSTÄNDE:
# Widerstand 3: EUR XXX.XX (+XX.X% vom aktuellen Kurs) | Begründung/Quelle
# Widerstand 2: EUR XXX.XX (+XX.X% vom aktuellen Kurs) | Begründung/Quelle
# Widerstand 1: EUR XXX.XX (+XX.X% vom aktuellen Kurs) | Begründung/Quelle
#
# AKTUELLER KURS:
# EUR XXX.XX (Stand: YYYY-MM-DD, Quelle)
#
# UNTERSTÜTZUNGEN:
# Unterstützung 1: EUR XXX.XX (-XX.X% vom aktuellen Kurs) | Begründung/Quelle
# Unterstützung 2: EUR XXX.XX (-XX.X% vom aktuellen Kurs) | Begründung/Quelle
# Unterstützung 3: EUR XXX.XX (-XX.X% vom aktuellen Kurs) | Begründung/Quelle
# ```
#
# ### TECHNISCHE INDIKATOREN
#
# Stelle die wichtigsten Indikatoren in Tabellenform dar:
#
# | Indikator | Wert | Signal | Interpretation |
# |-----------|------|--------|----------------|
# | RSI (14) | XX.X | Überkauft/Neutral/Überverkauft | [Kurze Bedeutung] |
# | MACD | XX.XX | Bullish/Bearish | [Kurze Bedeutung] |
# | 50-Tage-Durchschnitt | EUR XXX.XX | Über/Unter Kurs | [Abstand: +/-X%] |
# | 200-Tage-Durchschnitt | EUR XXX.XX | Über/Unter Kurs | [Abstand: +/-X%] |
# | Momentum (4 Wochen) | +/-XX.X% | Stark/Moderat/Schwach | [Kurze Bedeutung] |
#
# **Gesamttrend:** [Aufwärts/Seitwärts/Abwärts] – Begründung in einem Satz
#
# ---
#
# ## 5. ANALYSTENKONSENS
#
# Stelle die Analystenmeinungen strukturiert dar:
#
# ```
# Höchstes Kursziel: EUR XXX.XX
# Durchschnittliches Kursziel: EUR XXX.XX
# Niedrigstes Kursziel: EUR XXX.XX
# Anzahl Analysten: XX
# Empfehlungsverteilung: XX% Kauf | XX% Halten | XX% Verkaufen
# Quelle: [Name, Datum]
# ```
#
# ---
#
# ## 6. EINSCHÄTZUNG
#
# ### EMPFEHLUNG: [KAUF / HALTEN / VERKAUFEN]
#
# **Begründung (2–4 Bulletpoints):**
# - [Wichtigster Treiber der Empfehlung basierend auf Fundamentaldaten]
# - [Wichtigster technischer Faktor]
# - [Wichtigster News-/Sentiment-Faktor]
# - [Weiterer relevanter Punkt]
#
# ---
#
# ## 7. EIGENE KURSVORHERSAGE
#
# ### KURSZIEL & POTENZIAL
#
# ```
# Kursziel: EUR XXX.XX
# Zeithorizont: [3M / 6M / 12M]
# Potenzial vom aktuellen Kurs: +/-XX.X%
# ```
#
# ### PROGNOSE-METHODIK
#
# **Modellgewichtung:**
# - Fundamentalanalyse: XX%
# - Technische Analyse: XX%
# - News & Sentiment: XX%
#
# **Begründung der Gewichtung:**
# [1–2 Sätze, warum diese Verteilung für {symbol} in der aktuellen Marktlage sinnvoll ist]
#
# **Wichtigste Annahmen:**
# - Fundamental: [z.B. EPS-Wachstum XX% p.a., KGV-Ziel XX, Margenerweiterung auf XX%]
# - Technisch: [z.B. Durchbruch Widerstand bei EUR XXX, Unterstützung hält bei EUR XXX]
# - News/Events: [z.B. Positiver Earnings-Call Effekt, Produktlaunch steigert Sentiment]
#
# **Konfidenzstufe:** [NIEDRIG / MITTEL / HOCH]
# **Wahrscheinlichkeit:** XX%
# **Begründung:** [1–2 Sätze zur Datenlage, Marktvolatilität und Unsicherheitsfaktoren]
#
# ---
#
# ## 8. CHANCEN & RISIKEN
#
# **GRÖSSTE CHANCE:**
# [1 prägnanter Satz mit konkretem Upside-Szenario]
#
# **GRÖSSTES RISIKO:**
# [1 prägnanter Satz mit konkretem Downside-Szenario]
#
# ---
#
# ## FORMATANFORDERUNGEN
#
# - Klare Struktur wie oben mit Trennlinien zwischen Sektionen
# - Maximal eine Seite
# - Alle numerischen Werte mit Währung und Datum (z.B. "EUR 12,34 – Stand 2025-10-24")
# - Prozentuale Abstände bei Widerständen/Unterstützungen
# - Web- oder Datenquellen kurz zitieren (Name/Datum)
# - Tabellen für Indikatoren, Kursniveaus und Analystenkonsens verwenden
# - Nur prägnante, belegbare Fakten – keine allgemeinen Phrasen
# - Konsistente Währungsangabe (EUR/USD/etc.) durchgehend verwenden
#         """
        # URL-encode the prompt
        encoded_prompt = urllib.parse.quote(prompt)
        return f'https://claude.ai/new?q={encoded_prompt}'

    df['Claude'] = df[symbol_column].apply(create_claude_prompt)
    return df



def page_display_dataframe(
    df: pd.DataFrame,
    symbol_column='symbol',
    column_config: dict = None
):
    """
    Displays DataFrame with TradingView links configured.
    All float columns are formatted to 2 decimal places by default.

    Args:
        df: DataFrame
        symbol_column: Name of the column containing symbols (default: 'symbol')
        column_config: Optional dictionary of column configurations to merge with TradingView config.
                        These settings have higher priority than the default settings.
    """
    df = _add_tradingview_link(df, symbol_column)
    df = _add_tradingview_superchart_link(df, symbol_column)
    df = _add_claude_analysis_link(df, symbol_column)

    # default configuration
    default_config = {
        "TradingView": st.column_config.LinkColumn(
            label="",
            help="TradingView Symbolinfo",
            display_text="📊",
        ),
        "Chart": st.column_config.LinkColumn(
            label="",
            help="TradingView Superchart",
            display_text="📈",
        ),
        "Claude": st.column_config.LinkColumn(
            label="",
            help="Analyze with Claude AI",
            display_text="🤖",
        )
    }

    # Auto-format all float columns to 2 decimal places
    for col in df.columns:
        if df[col].dtype in ['float64', 'float32']:
            default_config[col] = st.column_config.NumberColumn(
                col,
                format="%.2f"
            )

    # Color negative numbers red
    df = df.style.map(
        lambda val: 'color: red' if val < 0 else '',
        subset=df.select_dtypes(include=['number']).columns
    )

    # Merge with provided column_config if exists.
    # column_config has a higher priority than the default.
    if column_config:
        default_config.update(column_config)

    st.dataframe(
        df,
        column_config=default_config,
        hide_index=True,
        use_container_width=True
    )