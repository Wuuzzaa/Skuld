"""
Generate SKULD Strategy Concepts PDF
Dark-themed professional document with trading strategies analysis
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Frame, PageTemplate, BaseDocTemplate, NextPageTemplate,
    KeepTogether, ListFlowable, ListItem
)
from reportlab.platypus.flowables import Flowable
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
import os

# === COLORS ===
DARK_BG = HexColor("#1a1f2e")
DARK_BG_LIGHTER = HexColor("#242b3d")
DARK_BG_CARD = HexColor("#2a3245")
TEAL = HexColor("#14b8a6")
TEAL_DARK = HexColor("#0f8a7d")
WHITE = HexColor("#ffffff")
LIGHT_GRAY = HexColor("#e2e8f0")
MED_GRAY = HexColor("#94a3b8")
DIM_GRAY = HexColor("#64748b")
AMBER = HexColor("#f59e0b")
GREEN = HexColor("#22c55e")
RED = HexColor("#ef4444")
BLUE = HexColor("#3b82f6")
PURPLE = HexColor("#a855f7")

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 20 * mm


class DarkBackground(Flowable):
    """Full page dark background"""
    def __init__(self, width, height, color=DARK_BG):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.color = color

    def draw(self):
        self.canv.setFillColor(self.color)
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=0)


def draw_dark_page(canvas_obj, doc):
    """Draw dark background on every page"""
    canvas_obj.saveState()
    canvas_obj.setFillColor(DARK_BG)
    canvas_obj.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    # Page number
    canvas_obj.setFillColor(MED_GRAY)
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.drawCentredString(PAGE_WIDTH / 2, 12 * mm, f"SKULD Strategy Concepts  |  Seite {doc.page}")
    # Accent line at top
    canvas_obj.setStrokeColor(TEAL)
    canvas_obj.setLineWidth(2)
    canvas_obj.line(MARGIN, PAGE_HEIGHT - 12 * mm, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 12 * mm)
    canvas_obj.restoreState()


def draw_cover_page(canvas_obj, doc):
    """Draw the cover page"""
    canvas_obj.saveState()
    # Dark background
    canvas_obj.setFillColor(DARK_BG)
    canvas_obj.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)

    # Large teal accent rectangle at top
    canvas_obj.setFillColor(TEAL_DARK)
    canvas_obj.rect(0, PAGE_HEIGHT - 80 * mm, PAGE_WIDTH, 80 * mm, fill=1, stroke=0)

    # Gradient overlay effect (darker stripe)
    canvas_obj.setFillColor(Color(0.08, 0.10, 0.15, alpha=0.5))
    canvas_obj.rect(0, PAGE_HEIGHT - 80 * mm, PAGE_WIDTH, 30 * mm, fill=1, stroke=0)

    # Title
    canvas_obj.setFillColor(WHITE)
    canvas_obj.setFont("Helvetica-Bold", 42)
    canvas_obj.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 50 * mm, "SKULD")

    canvas_obj.setFont("Helvetica-Bold", 24)
    canvas_obj.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 62 * mm, "Strategy Concepts")

    # Subtitle
    canvas_obj.setFillColor(LIGHT_GRAY)
    canvas_obj.setFont("Helvetica", 13)
    canvas_obj.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 100 * mm,
                                  "Umsetzbare Trading-Strategien aus YouTube-Transkript-Analyse")

    # Decorative line
    canvas_obj.setStrokeColor(TEAL)
    canvas_obj.setLineWidth(3)
    canvas_obj.line(PAGE_WIDTH / 2 - 60 * mm, PAGE_HEIGHT - 110 * mm,
                    PAGE_WIDTH / 2 + 60 * mm, PAGE_HEIGHT - 110 * mm)

    # Info block
    y_pos = PAGE_HEIGHT - 140 * mm
    canvas_obj.setFillColor(MED_GRAY)
    canvas_obj.setFont("Helvetica", 11)
    info_lines = [
        "Datum: Mai 2026",
        "",
        "Sources: Option Strat, Eric Ludwig, Tasty Trade,",
        "Tasty_live, 10xTrading, Aktienfinder",
        "",
        "Total Videos Analyzed: ~5,000+",
        "",
        "16 Strategien in 3 Tiers kategorisiert",
        "Top 3 Empfehlungen mit Implementierungs-Detail"
    ]
    for line in info_lines:
        canvas_obj.drawCentredString(PAGE_WIDTH / 2, y_pos, line)
        y_pos -= 16

    # Bottom accent
    canvas_obj.setFillColor(TEAL)
    canvas_obj.rect(0, 0, PAGE_WIDTH, 8 * mm, fill=1, stroke=0)

    # Version note
    canvas_obj.setFillColor(DIM_GRAY)
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.drawCentredString(PAGE_WIDTH / 2, 12 * mm, "Internes Strategiedokument - SKULD Options Analysis Platform")

    canvas_obj.restoreState()


def create_styles():
    """Create paragraph styles for dark theme"""
    styles = {}

    styles['h1'] = ParagraphStyle(
        'H1', fontName='Helvetica-Bold', fontSize=20,
        textColor=TEAL, spaceAfter=8 * mm, spaceBefore=4 * mm,
        leading=24
    )
    styles['h2'] = ParagraphStyle(
        'H2', fontName='Helvetica-Bold', fontSize=15,
        textColor=WHITE, spaceAfter=4 * mm, spaceBefore=6 * mm,
        leading=18
    )
    styles['h3'] = ParagraphStyle(
        'H3', fontName='Helvetica-Bold', fontSize=12,
        textColor=TEAL, spaceAfter=3 * mm, spaceBefore=4 * mm,
        leading=15
    )
    styles['body'] = ParagraphStyle(
        'Body', fontName='Helvetica', fontSize=9.5,
        textColor=LIGHT_GRAY, spaceAfter=2 * mm,
        leading=13, alignment=TA_LEFT
    )
    styles['body_small'] = ParagraphStyle(
        'BodySmall', fontName='Helvetica', fontSize=8.5,
        textColor=MED_GRAY, spaceAfter=1.5 * mm,
        leading=11
    )
    styles['bullet'] = ParagraphStyle(
        'Bullet', fontName='Helvetica', fontSize=9.5,
        textColor=LIGHT_GRAY, spaceAfter=1.5 * mm,
        leading=12, leftIndent=8 * mm, bulletIndent=3 * mm
    )
    styles['toc_entry'] = ParagraphStyle(
        'TOCEntry', fontName='Helvetica', fontSize=10,
        textColor=LIGHT_GRAY, spaceAfter=3 * mm,
        leading=14, leftIndent=5 * mm
    )
    styles['toc_tier'] = ParagraphStyle(
        'TOCTier', fontName='Helvetica-Bold', fontSize=11,
        textColor=TEAL, spaceAfter=3 * mm, spaceBefore=5 * mm,
        leading=14
    )
    styles['caption'] = ParagraphStyle(
        'Caption', fontName='Helvetica-Oblique', fontSize=8,
        textColor=DIM_GRAY, spaceAfter=3 * mm, spaceBefore=1 * mm,
        alignment=TA_CENTER
    )
    styles['formula'] = ParagraphStyle(
        'Formula', fontName='Courier', fontSize=9,
        textColor=AMBER, spaceAfter=2 * mm, spaceBefore=2 * mm,
        leading=12, leftIndent=5 * mm, backColor=DARK_BG_CARD
    )
    styles['highlight'] = ParagraphStyle(
        'Highlight', fontName='Helvetica-Bold', fontSize=10,
        textColor=TEAL, spaceAfter=2 * mm,
        leading=13
    )

    return styles


class HorizontalLine(Flowable):
    def __init__(self, width, color=TEAL, thickness=1.5):
        Flowable.__init__(self)
        self.width = width
        self.color = color
        self.thickness = thickness
        self.height = 4 * mm

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 2 * mm, self.width, 2 * mm)


class CardBox(Flowable):
    """A card-like box with dark background"""
    def __init__(self, width, height, content_func=None):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.content_func = content_func

    def draw(self):
        self.canv.setFillColor(DARK_BG_CARD)
        self.canv.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        if self.content_func:
            self.content_func(self.canv, self.width, self.height)


def make_strategy_table(data, col_widths=None):
    """Create a styled table with dark theme"""
    if col_widths is None:
        col_widths = None

    table = Table(data, colWidths=col_widths, repeatRows=1)

    style = TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), TEAL_DARK),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        # Body
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TEXTCOLOR', (0, 1), (-1, -1), LIGHT_GRAY),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, DIM_GRAY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ])

    # Alternating row colors
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.add('BACKGROUND', (0, i), (-1, i), DARK_BG_CARD)
        else:
            style.add('BACKGROUND', (0, i), (-1, i), DARK_BG_LIGHTER)

    table.setStyle(style)
    return table


def build_toc(styles):
    """Build table of contents"""
    elements = []
    elements.append(Paragraph("Inhaltsverzeichnis", styles['h1']))
    elements.append(Spacer(1, 5 * mm))

    elements.append(Paragraph("TIER 1: SOFORT UMSETZBAR", styles['toc_tier']))
    tier1 = [
        "1. Earnings IV Crush Screener",
        "2. HAA Simple (Hybrid Asset Allocation)",
        "3. Jade Lizard Screener",
        "4. 0 DTE Iron Condor/Fly Signals",
        "5. Bullish Strangle (30/16 Delta)",
        "6. VIX Overnight Entry Signal",
        "7. Kelly Criterion Position Sizer",
    ]
    for item in tier1:
        elements.append(Paragraph(f"    {item}", styles['toc_entry']))

    elements.append(Paragraph("TIER 2: UMSETZBAR MIT ERWEITERUNGEN", styles['toc_tier']))
    tier2 = [
        "8. Earnings Post-Move Continuation",
        "9. SPX Broken Wing Butterfly (BWB)",
        "10. Hindenburg Omen",
        "11. Short Squeeze Scanner",
        "12. Flyagonal (Flagal)",
    ]
    for item in tier2:
        elements.append(Paragraph(f"    {item}", styles['toc_entry']))

    elements.append(Paragraph("TIER 3: INTERESSANT ABER AUFWENDIGER", styles['toc_tier']))
    tier3 = [
        "13. 5-Star Options Backtester",
        "14. Aktienfinder Quality Screener",
        "15. Kassandra Market Regime Indicator",
        "16. ZEBRA (Stock Replacement)",
    ]
    for item in tier3:
        elements.append(Paragraph(f"    {item}", styles['toc_entry']))

    elements.append(Spacer(1, 8 * mm))
    elements.append(Paragraph("TOP 3 EMPFEHLUNGEN - DETAILLIERT", styles['toc_tier']))
    top3 = [
        "A. Earnings IV Crush Screener (Full Breakdown)",
        "B. Jade Lizard Finder (Full Breakdown)",
        "C. Kelly Position Sizer + Dashboard Signal (Full Breakdown)",
    ]
    for item in top3:
        elements.append(Paragraph(f"    {item}", styles['toc_entry']))

    elements.append(Spacer(1, 5 * mm))
    elements.append(Paragraph("APPENDIX: Data Availability in SKULD", styles['toc_tier']))

    return elements


def build_tier1(styles):
    """Build Tier 1 section"""
    elements = []
    elements.append(PageBreak())
    elements.append(Paragraph("TIER 1: SOFORT UMSETZBAR", styles['h1']))
    elements.append(Paragraph("Alle Daten in SKULD vorhanden - direkt implementierbar", styles['body_small']))
    elements.append(HorizontalLine(PAGE_WIDTH - 2 * MARGIN))
    elements.append(Spacer(1, 3 * mm))

    # Summary table
    summary_data = [
        ['#', 'Strategie', 'Source', 'Win Rate', 'Aufwand'],
        ['1', 'Earnings IV Crush', 'Eric Ludwig / Tasty', '70-85%', 'Medium'],
        ['2', 'HAA Simple', 'Eric Ludwig', '~70% (13.1% p.a.)', 'Low'],
        ['3', 'Jade Lizard', 'Option Strat', 'High (zero upside risk)', 'Medium'],
        ['4', '0 DTE IC/Fly', 'Tasty_live', '~90%', 'Medium'],
        ['5', 'Bullish Strangle', 'Tasty_live', '> symmetric', 'Low'],
        ['6', 'VIX Overnight', 'Tasty_live', 'Edge when VIX up', 'Low'],
        ['7', 'Kelly Sizer', 'Tasty_live', 'N/A (tool)', 'Low'],
    ]
    table = make_strategy_table(summary_data, col_widths=[12*mm, 50*mm, 42*mm, 42*mm, 24*mm])
    elements.append(table)
    elements.append(Spacer(1, 6 * mm))

    # Strategy 1
    elements.append(Paragraph("1. Earnings IV Crush Screener", styles['h2']))
    elements.append(Paragraph("Source: Eric Ludwig + Tasty Trade", styles['body_small']))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(
        "Vor Earnings Short Puts oder Credit Spreads verkaufen und vom IV-Crush profitieren. "
        "Die implizite Volatilitaet ist vor Earnings systematisch ueberbewertet.", styles['body']))
    elements.append(Paragraph("Rules:", styles['highlight']))
    rules = [
        "Sell 25-Delta Put oder Bull Put Spread (25/15 Delta)",
        "Entry: 1-2 Wochen vor Earnings",
        "Exit: Am Earnings-Tag (vor Announcement)",
        "Filter: Nur Aktien mit >=83% Hit Rate ueber letzte 12 Quartale",
    ]
    for r in rules:
        elements.append(Paragraph(f"  \u2022  {r}", styles['bullet']))
    elements.append(Paragraph("Expected Return: 70-85% Win Rate, systematic edge from volatility overpricing", styles['body']))
    elements.append(Paragraph("Data: earnings_date, IV, delta, DTE - ALL in SKULD", styles['body_small']))
    elements.append(Spacer(1, 4*mm))

    # Strategy 2
    elements.append(Paragraph("2. HAA Simple (Hybrid Asset Allocation)", styles['h2']))
    elements.append(Paragraph("Source: Eric Ludwig (Dr. Wouter Keller, Univ. Amsterdam)", styles['body_small']))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(
        "Monthly Momentum-Rotation zwischen SPY, IEF und Cash. Einfaches regelbasiertes System "
        "mit hervorragendem Backtesting-Ergebnis seit 1971.", styles['body']))
    elements.append(Paragraph("Rules:", styles['highlight']))
    rules = [
        "TIP avg return berechnen (1/3/6/12 Monatsdurchschnitt)",
        "Falls TIP > 0: Allokation = SPY (Risk-On)",
        "Falls TIP < 0: Check IEF Momentum",
        "Falls IEF > 0: Allokation = IEF (Bonds)",
        "Sonst: Allokation = Cash (Risk-Off)",
    ]
    for r in rules:
        elements.append(Paragraph(f"  \u2022  {r}", styles['bullet']))
    elements.append(Paragraph("Backtest: 13.1% p.a. seit 1971, Max DD -17.2%, Sharpe 0.80", styles['formula']))
    elements.append(Paragraph("Data: Monthly prices fuer TIP, IEF, SPY (3 ETFs)", styles['body_small']))
    elements.append(Spacer(1, 4*mm))

    # Strategy 3
    elements.append(Paragraph("3. Jade Lizard Screener", styles['h2']))
    elements.append(Paragraph("Source: Option Strat", styles['body_small']))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(
        "Sell Naked Put am Support + Sell Call Spread ueber Resistance = Null Upside-Risiko. "
        "Elegante Kombination die durch Design das Aufwaertsrisiko eliminiert.", styles['body']))
    elements.append(Paragraph("Rules:", styles['highlight']))
    rules = [
        "Total Credit aus Call Spread muss Spread-Breite uebersteigen",
        "Aktie an technischem Support (Breakout-Level, SMA200)",
        "ETFs/Stocks nach Breakout mit neuem Support",
    ]
    for r in rules:
        elements.append(Paragraph(f"  \u2022  {r}", styles['bullet']))
    elements.append(Paragraph(
        "Beispiel: IWM bei 250 Support: Sell 250 Put ($477) + Sell 260/265 Call Spread ($118) = $594 Total Credit",
        styles['formula']))
    elements.append(Spacer(1, 4*mm))

    # Strategy 4
    elements.append(PageBreak())
    elements.append(Paragraph("4. 0 DTE Iron Condor / Iron Fly Signals", styles['h2']))
    elements.append(Paragraph("Source: Tasty_live (2 Jahre Backtesting)", styles['body_small']))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(
        "VIX-basierter Entry-Filter plus Day-of-Week Filter fuer SPX 0DTE Trades. "
        "Hochsystematischer Ansatz mit klaren Regeln.", styles['body']))
    elements.append(Paragraph("Rules:", styles['highlight']))
    rules = [
        "Nur Montag + Mittwoch handeln",
        "20-Delta Short Strikes, $20 breite Wings",
        "Take Profit: 25% (Iron Condor) oder 10% (Iron Fly)",
        "Sweet Spot: IVR 15-25",
        "Donnerstag vermeiden, Entry nur erste 2 Stunden",
    ]
    for r in rules:
        elements.append(Paragraph(f"  \u2022  {r}", styles['bullet']))
    elements.append(Paragraph("Win Rate: ~90% mit 25% Profit Target", styles['formula']))
    elements.append(Spacer(1, 4*mm))

    # Strategy 5
    elements.append(Paragraph("5. Bullish Strangle (30/16 Delta)", styles['h2']))
    elements.append(Paragraph("Source: Tasty_live (20 Jahre Backtest)", styles['body_small']))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(
        "Asymmetrischer Strangle: 30-Delta Put + 16-Delta Call statt symmetrisch 16/16. "
        "Mehr Premium bei bullisher Marktstruktur.", styles['body']))
    elements.append(Paragraph("Rules:", styles['highlight']))
    rules = [
        "45 DTE Entry",
        "Manage bei 21 DTE oder 50% Profit",
        "Nur im Aufwaertstrend anwenden",
        "Vorteil: Mehr Premium ($3.80 vs $3.10 symmetrisch)",
    ]
    for r in rules:
        elements.append(Paragraph(f"  \u2022  {r}", styles['bullet']))
    elements.append(Spacer(1, 4*mm))

    # Strategy 6
    elements.append(Paragraph("6. VIX Overnight Entry Signal", styles['h2']))
    elements.append(Paragraph("Source: Tasty_live (15 Jahre Daten)", styles['body_small']))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(
        "Nur 45-DTE Strangles eingehen wenn VIX ueber Nacht gestiegen ist. "
        "Starke positive P&L vs. nahezu Null bei fallendem VIX.", styles['body']))
    elements.append(Paragraph("Rules:", styles['highlight']))
    rules = [
        "Check VIX Richtung overnight (Previous Close vs Current)",
        "VIX UP: Entry 16-Delta Strangle auf SPY/IWM/QQQ",
        "VIX DOWN: Kein Trade",
    ]
    for r in rules:
        elements.append(Paragraph(f"  \u2022  {r}", styles['bullet']))
    elements.append(Paragraph("Implementierung: Einfacher Signal-Indikator auf Dashboard", styles['body_small']))
    elements.append(Spacer(1, 4*mm))

    # Strategy 7
    elements.append(Paragraph("7. Kelly Criterion Position Sizer", styles['h2']))
    elements.append(Paragraph("Source: Tasty_live", styles['body_small']))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(
        "Mathematisch optimale Positionsgroesse berechnen. Universell einsetzbar fuer alle "
        "Strategien in SKULD.", styles['body']))
    elements.append(Paragraph("Formula:", styles['highlight']))
    elements.append(Paragraph("f = (p x b - q) / b", styles['formula']))
    elements.append(Paragraph("p = Win Rate, q = 1-p, b = Avg Win / Avg Loss", styles['body_small']))
    rules = [
        "Threshold: Odds > 0.176 fuer positive Erwartung bei Iron Condors",
        "50% managed ICs: ~85% Win Rate noetig fuer positives Kelly",
        "Half-Kelly empfohlen fuer reales Trading (weniger Varianz)",
    ]
    for r in rules:
        elements.append(Paragraph(f"  \u2022  {r}", styles['bullet']))

    return elements


def build_tier2(styles):
    """Build Tier 2 section"""
    elements = []
    elements.append(PageBreak())
    elements.append(Paragraph("TIER 2: UMSETZBAR MIT ERWEITERUNGEN", styles['h1']))
    elements.append(Paragraph("Erfordern zusaetzliche Datenquellen oder Berechnungen", styles['body_small']))
    elements.append(HorizontalLine(PAGE_WIDTH - 2 * MARGIN))
    elements.append(Spacer(1, 3 * mm))

    # Summary table
    summary_data = [
        ['#', 'Strategie', 'Source', 'Fehlende Daten', 'Aufwand'],
        ['8', 'Earnings Continuation', 'Tasty_live', 'Expected Move Tracking', 'Medium'],
        ['9', 'SPX BWB', 'Option Strat', 'SPX Options, VIX Spike', 'High'],
        ['10', 'Hindenburg Omen', '10xTrading', 'NYSE Breadth, McClellan', 'High'],
        ['11', 'Short Squeeze', '10xTrading', 'Short Interest/Float', 'Medium'],
        ['12', 'Flyagonal', 'Option Strat', 'Complex multi-leg calc', 'High'],
    ]
    table = make_strategy_table(summary_data, col_widths=[12*mm, 40*mm, 30*mm, 45*mm, 24*mm])
    elements.append(table)
    elements.append(Spacer(1, 6 * mm))

    # Strategy 8
    elements.append(Paragraph("8. Earnings Post-Move Continuation", styles['h2']))
    elements.append(Paragraph("Source: Tasty_live (8 Jahre, Top 15 S&P Stocks)", styles['body_small']))
    elements.append(Paragraph(
        "Wenn der Earnings-Move den Expected Move uebersteigt, zeigt die Aktie eine staerkere "
        "7-Tage Continuation als zufaellig. Systematischer Edge nach ueberraschenden Earnings.", styles['body']))
    elements.append(Paragraph("Fehlend: Tracking von Actual vs Expected Moves post-Earnings", styles['body_small']))
    elements.append(Spacer(1, 4*mm))

    # Strategy 9
    elements.append(Paragraph("9. SPX Broken Wing Butterfly (BWB)", styles['h2']))
    elements.append(Paragraph("Source: Option Strat", styles['body_small']))
    elements.append(Paragraph(
        "BWB bei VIX-Spike einsetzen. Put BWB: 60pt lower / 50pt upper Wing. Zero Upside Risk. "
        "Entry an Sell-Off Tagen, Target 5-10% Profit in 1-3 Wochen.", styles['body']))
    elements.append(Paragraph("Kosten: ~$210 pro BWB, Max Profit ~$4,500-5,000 pro Lot", styles['formula']))
    elements.append(Paragraph("Fehlend: SPX Options in Datenbank, VIX Spike Detection", styles['body_small']))
    elements.append(Spacer(1, 4*mm))

    # Strategy 10
    elements.append(Paragraph("10. Hindenburg Omen", styles['h2']))
    elements.append(Paragraph("Source: 10xTrading", styles['body_small']))
    elements.append(Paragraph(
        "Crash-Warnung 1-3 Monate im Voraus wenn 3 Bedingungen gleichzeitig erfuellt sind:", styles['body']))
    rules = [
        "NYSE ueber 50-SMA",
        ">=2.8% New Highs UND New Lows gleichzeitig",
        "McClellan Oscillator negativ",
    ]
    for r in rules:
        elements.append(Paragraph(f"  \u2022  {r}", styles['bullet']))
    elements.append(Paragraph("Fehlend: NYSE Breadth Data, McClellan Oscillator", styles['body_small']))
    elements.append(Spacer(1, 4*mm))

    # Strategy 11
    elements.append(Paragraph("11. Short Squeeze Scanner", styles['h2']))
    elements.append(Paragraph("Source: 10xTrading", styles['body_small']))
    elements.append(Paragraph(
        "Float Short >30% + Preis >70% unter 52W High + EMA20 Cross = Squeeze-Kandidat. "
        "Moeglich ueber Finviz API.", styles['body']))
    elements.append(Paragraph("Fehlend: Short Interest / Float Short Daten", styles['body_small']))
    elements.append(Spacer(1, 4*mm))

    # Strategy 12
    elements.append(Paragraph("12. Flyagonal (Flagal)", styles['h2']))
    elements.append(Paragraph("Source: Option Strat (94% Win Rate, 150%+ Return in 7 Monaten)", styles['body_small']))
    elements.append(Paragraph(
        "Call BWB + Put Diagonal auf SPX. 8 DTE. Theta ~$9/Tag. Neutral-to-positive Vega. "
        "Komplexe Multi-Leg Strategie mit exzellentem Track Record.", styles['body']))
    elements.append(Paragraph("Fehlend: Complex multi-leg Calculation, sehr kurze DTE Options", styles['body_small']))

    return elements


def build_tier3(styles):
    """Build Tier 3 section"""
    elements = []
    elements.append(PageBreak())
    elements.append(Paragraph("TIER 3: INTERESSANT ABER AUFWENDIGER", styles['h1']))
    elements.append(Paragraph("Erfordern erhebliche neue Infrastruktur oder externe Daten", styles['body_small']))
    elements.append(HorizontalLine(PAGE_WIDTH - 2 * MARGIN))
    elements.append(Spacer(1, 3 * mm))

    # Summary table
    summary_data = [
        ['#', 'Strategie', 'Source', 'Haupthindernis'],
        ['13', '5-Star Backtester', 'Eric Ludwig', 'Historische Options-Daten noetig'],
        ['14', 'Aktienfinder Quality', 'Aktienfinder', '10+ Jahre Fundamental-Daten'],
        ['15', 'Kassandra Regime', 'Eric Ludwig', '35-40 Sub-Indikatoren'],
        ['16', 'ZEBRA', 'Option Strat', 'LEAPS Daten + Position Calculator'],
    ]
    table = make_strategy_table(summary_data, col_widths=[12*mm, 45*mm, 35*mm, 65*mm])
    elements.append(table)
    elements.append(Spacer(1, 6 * mm))

    # Strategy 13
    elements.append(Paragraph("13. 5-Star Options Backtester", styles['h2']))
    elements.append(Paragraph("Source: Eric Ludwig", styles['body_small']))
    elements.append(Paragraph(
        "6-Jahre systematischer Backtest pro Aktie. Score nach Return, Safety Cushion, Hit Rate. "
        "Benoetigt historische Options-Daten die nicht in SKULD verfuegbar sind.", styles['body']))
    elements.append(Spacer(1, 4*mm))

    # Strategy 14
    elements.append(Paragraph("14. Aktienfinder Quality Screener", styles['h2']))
    elements.append(Paragraph("Source: Aktienfinder", styles['body_small']))
    elements.append(Paragraph(
        "10-Jahre Earnings-Stabilitaet (R-Squared >= 0.8) + Wachstum >=5% + unter Fair Value. "
        "Fundamental-orientierter Qualitaetsfilter fuer Optionsbasis.", styles['body']))
    elements.append(Spacer(1, 4*mm))

    # Strategy 15
    elements.append(Paragraph("15. Kassandra Market Regime Indicator", styles['h2']))
    elements.append(Paragraph("Source: Eric Ludwig", styles['body_small']))
    elements.append(Paragraph(
        "35-40 Sub-Indikatoren als Composite Signal fuer Risk-On/Risk-Off. "
        "Aufwaendiger Build aber potenziell sehr wertvoll fuer Timing.", styles['body']))
    elements.append(Spacer(1, 4*mm))

    # Strategy 16
    elements.append(Paragraph("16. ZEBRA (Stock Replacement)", styles['h2']))
    elements.append(Paragraph("Source: Option Strat", styles['body_small']))
    elements.append(Paragraph(
        "Buy 2x 70-Delta Calls + Sell 1x 50-Delta Call = Synthetische Aktie fuer 10% Kapital. "
        "Benoetigt LEAPS-Daten und Position Calculator.", styles['body']))

    return elements


def build_recommendation_1(styles):
    """Full page breakdown: Earnings IV Crush Screener"""
    elements = []
    elements.append(PageBreak())
    elements.append(Paragraph("TOP 3 EMPFEHLUNG #1", styles['body_small']))
    elements.append(Paragraph("Earnings IV Crush Screener", styles['h1']))
    elements.append(HorizontalLine(PAGE_WIDTH - 2 * MARGIN))
    elements.append(Spacer(1, 3 * mm))

    elements.append(Paragraph("Warum diese Strategie:", styles['h3']))
    reasons = [
        "Daten 100% vorhanden (earnings_date, IV, delta, options chains)",
        "Klar definierte Rules (Delta 25, 45 DTE, Exit on Earnings Day)",
        "Hohe Nachfrage (jeder Options-Trader sucht Earnings-Trades)",
        "Passt zu bestehendem SKULD-Konzept (Screener + Filter)",
    ]
    for r in reasons:
        elements.append(Paragraph(f"  \u2713  {r}", styles['bullet']))
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph("Page Layout Concept:", styles['h3']))
    layout_items = [
        'Header: "Earnings This Week" mit Kalender-Ansicht',
        "Filters: DTE Range, Min IV Rank, Min Hit Rate Threshold",
        "Detail Panel: IV Term Structure Chart, Past Earnings Moves, Suggested Strikes",
    ]
    for item in layout_items:
        elements.append(Paragraph(f"  \u2022  {item}", styles['bullet']))
    elements.append(Spacer(1, 2 * mm))

    # Table columns
    elements.append(Paragraph("Screener-Tabelle Spalten:", styles['highlight']))
    col_data = [
        ['Spalte', 'Beschreibung', 'Quelle'],
        ['Symbol', 'Ticker', 'StockData'],
        ['Earnings Date', 'Naechstes Earnings-Datum', 'StockData'],
        ['DTE', 'Days to Earnings', 'Berechnet'],
        ['IV Rank', 'IV Percentile aktuell', 'StockData'],
        ['IV Front/Back', 'Term Structure Ratio', 'OptionDataMerged'],
        ['Expected Move', 'Stock x IV x sqrt(DTE/365)', 'Berechnet'],
        ['Strategy', 'Short Put / Bull Put Spread', 'Empfehlung'],
        ['Est. Credit', 'Geschaetzter Premium-Erloes', 'OptionDataMerged'],
        ['Hit Rate', 'Historische Erfolgsquote', 'Berechnet'],
    ]
    table = make_strategy_table(col_data, col_widths=[30*mm, 60*mm, 40*mm])
    elements.append(table)
    elements.append(Spacer(1, 5 * mm))

    elements.append(Paragraph("Formulas:", styles['h3']))
    formulas = [
        "IV Ratio = Front-Week IV / Back-Month IV  (>1.5 = good, >2.0 = excellent)",
        "Expected Move = Stock Price x Front IV x sqrt(DTE/365)",
        "Max Profit (Short Put) = Premium received",
        "Max Profit (Bull Put Spread) = Net Credit",
        "Break-Even = Short Strike - Premium",
    ]
    for f in formulas:
        elements.append(Paragraph(f, styles['formula']))
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph("Implementation Effort: MEDIUM", styles['highlight']))
    elements.append(Paragraph("New page + new SQL query + frontend components", styles['body_small']))

    return elements


def build_recommendation_2(styles):
    """Full page breakdown: Jade Lizard Finder"""
    elements = []
    elements.append(PageBreak())
    elements.append(Paragraph("TOP 3 EMPFEHLUNG #2", styles['body_small']))
    elements.append(Paragraph("Jade Lizard Finder", styles['h1']))
    elements.append(HorizontalLine(PAGE_WIDTH - 2 * MARGIN))
    elements.append(Spacer(1, 3 * mm))

    elements.append(Paragraph("Warum diese Strategie:", styles['h3']))
    reasons = [
        "Elegante Strategie: Null Upside-Risiko durch Design",
        "Alle Daten vorhanden (Puts + Calls + Strikes)",
        "Einzigartig - kein anderer Screener bietet das",
        "Kombinierbar mit Wheel-Strategie",
    ]
    for r in reasons:
        elements.append(Paragraph(f"  \u2713  {r}", styles['bullet']))
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph("Key Calculation:", styles['h3']))
    formulas = [
        "Total Credit = Put Premium + (Short Call - Long Call)",
        "Zero Upside Risk: Total Credit >= Call Spread Width",
        "Effective Cost Basis = Put Strike - Total Credit",
        "Max Downside Risk = Put Strike - Total Credit",
    ]
    for f in formulas:
        elements.append(Paragraph(f, styles['formula']))
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph("Filter Logic:", styles['h3']))
    filters = [
        "Aktie an/nahe technischem Support (within 3% of SMA200 oder 52W Support)",
        "Put Strike am Support-Level",
        "Call Spread Strikes ueber Recent Resistance",
        "Total Credit > Call Spread Width (MUSS wahr sein fuer gueltigen Jade Lizard)",
    ]
    for f in filters:
        elements.append(Paragraph(f"  \u2192  {f}", styles['bullet']))
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph("Screener-Tabelle:", styles['highlight']))
    col_data = [
        ['Spalte', 'Beschreibung'],
        ['Symbol', 'Ticker + aktueller Kurs'],
        ['Put Strike', 'Am Support-Level'],
        ['Put Premium', 'Erloes aus Naked Put'],
        ['Call Spread', 'Short/Long Call Strikes'],
        ['CS Credit', 'Call Spread Erloes'],
        ['Total Credit', 'Gesamt-Premium'],
        ['Max Risk', 'Downside-Risiko'],
        ['Zero-Risk', '\u2713 wenn Total Credit >= Spread Width'],
    ]
    table = make_strategy_table(col_data, col_widths=[35*mm, 95*mm])
    elements.append(table)
    elements.append(Spacer(1, 5 * mm))

    elements.append(Paragraph("Implementation Effort: MEDIUM", styles['highlight']))
    elements.append(Paragraph("New calculation module + new page + support level detection", styles['body_small']))

    return elements


def build_recommendation_3(styles):
    """Full page breakdown: Kelly + Dashboard"""
    elements = []
    elements.append(PageBreak())
    elements.append(Paragraph("TOP 3 EMPFEHLUNG #3", styles['body_small']))
    elements.append(Paragraph("Kelly Position Sizer + Dashboard Signal", styles['h1']))
    elements.append(HorizontalLine(PAGE_WIDTH - 2 * MARGIN))
    elements.append(Spacer(1, 3 * mm))

    elements.append(Paragraph("Warum diese Strategie:", styles['h3']))
    reasons = [
        "Sofort umsetzbar (reine Mathematik, kein neuer Daten-Endpunkt)",
        "Nuetzlich fuer ALLE Strategien in SKULD",
        "Kann als Widget auf jeder Seite eingebettet werden",
        "Professionelles Feature das Mehrwert zeigt",
    ]
    for r in reasons:
        elements.append(Paragraph(f"  \u2713  {r}", styles['bullet']))
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph("Calculator Interface:", styles['h3']))
    elements.append(Paragraph("Input Fields:", styles['highlight']))
    inputs = [
        "Win Rate (%) - aus historischen Trades oder Backtest",
        "Average Win ($) - durchschnittlicher Gewinn pro Trade",
        "Average Loss ($) - durchschnittlicher Verlust pro Trade",
        "Account Size ($) - Gesamtkapital",
    ]
    for i in inputs:
        elements.append(Paragraph(f"  \u2022  {i}", styles['bullet']))
    elements.append(Spacer(1, 2*mm))

    elements.append(Paragraph("Output:", styles['highlight']))
    outputs = [
        "Kelly Fraction (%) - optimaler Kapitaleinsatz",
        "Half-Kelly (%) - empfohlener konservativer Einsatz",
        "Recommended Position Size ($)",
        "Max Contracts basierend auf Max Loss",
    ]
    for o in outputs:
        elements.append(Paragraph(f"  \u2192  {o}", styles['bullet']))
    elements.append(Spacer(1, 3*mm))

    elements.append(Paragraph("Formulas:", styles['h3']))
    formulas = [
        "Kelly% = (Win_Rate x Avg_Win - Loss_Rate x Avg_Loss) / Avg_Win",
        "Half-Kelly = Kelly% / 2  (empfohlen fuer reales Trading)",
        "Position Size = Account x Half-Kelly",
        "Max Contracts = Position Size / (Max Loss per Contract)",
    ]
    for f in formulas:
        elements.append(Paragraph(f, styles['formula']))
    elements.append(Spacer(1, 5 * mm))

    elements.append(Paragraph("Bonus: Daily Signal Dashboard", styles['h3']))
    signal_data = [
        ['Signal', 'Logik', 'Anzeige'],
        ['VIX Level', 'Current VIX + Overnight Direction', 'Gauge Widget'],
        ['Trade Today?', 'Mon/Wed = Green, Thu = Red', 'Traffic Light'],
        ['IVR Bucket', '0-10, 10-15, 15-25, 25+', 'Profit Target Empf.'],
        ['HAA Signal', 'TIP/IEF Momentum Check', 'SPY / IEF / Cash'],
    ]
    table = make_strategy_table(signal_data, col_widths=[30*mm, 55*mm, 45*mm])
    elements.append(table)
    elements.append(Spacer(1, 5 * mm))

    elements.append(Paragraph("Implementation Effort: LOW", styles['highlight']))
    elements.append(Paragraph("Frontend-only Calculator, kein neuer API-Endpunkt noetig", styles['body_small']))

    return elements


def build_appendix(styles):
    """Build data availability appendix"""
    elements = []
    elements.append(PageBreak())
    elements.append(Paragraph("APPENDIX: Data Availability in SKULD", styles['h1']))
    elements.append(HorizontalLine(PAGE_WIDTH - 2 * MARGIN))
    elements.append(Spacer(1, 5 * mm))

    data = [
        ['Data Point', 'Status', 'Quelle'],
        ['Options Chains (Strikes, Premiums, Greeks)', '\u2713', 'OptionDataMerged'],
        ['IV, IV Rank, IV Percentile', '\u2713', 'StockData'],
        ['Earnings Date, Days to Earnings', '\u2713', 'StockData'],
        ['Delta, Theta, Gamma, Vega', '\u2713', 'OptionDataMerged'],
        ['Stock Price, 52W High/Low', '\u2713', 'StockData'],
        ['SMA/EMA (5-200 day)', '\u2713', 'StockData'],
        ['RSI, MACD, Bollinger Bands', '\u2713', 'StockData'],
        ['RSL (Relative Strength Levy)', '\u2713', 'StockData'],
        ['Sector, Industry, Country', '\u2713', 'StockData'],
        ['S&P 500 Membership', '\u2713', 'sp500_constituents.py'],
        ['Dividend Data', '\u2713', 'StockData'],
        ['Volume, Open Interest', '\u2713', 'OptionDataMerged'],
        ['Beta', '\u2713', 'StockData'],
        ['VIX Level', '\u2717', 'Not stored (could add)'],
        ['Short Interest / Float Short', '\u2717', 'Not available'],
        ['NYSE Breadth / McClellan', '\u2717', 'Not available'],
        ['Historical Options Prices', '\u2717', 'Only current snapshot'],
        ['LEAPS (>1 year DTE)', '?', 'Depends on data refresh'],
    ]

    table = Table(data, colWidths=[70*mm, 15*mm, 55*mm], repeatRows=1)
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), TEAL_DARK),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 1), (-1, -1), LIGHT_GRAY),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, DIM_GRAY),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]

    # Color the status column
    for i in range(1, len(data)):
        if data[i][1] == '\u2713':
            style_cmds.append(('TEXTCOLOR', (1, i), (1, i), GREEN))
        elif data[i][1] == '\u2717':
            style_cmds.append(('TEXTCOLOR', (1, i), (1, i), RED))
        else:
            style_cmds.append(('TEXTCOLOR', (1, i), (1, i), AMBER))

        if i % 2 == 0:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), DARK_BG_CARD))
        else:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), DARK_BG_LIGHTER))

    table.setStyle(TableStyle(style_cmds))
    elements.append(table)

    elements.append(Spacer(1, 8 * mm))
    elements.append(Paragraph(
        "Legende:  \u2713 = Verfuegbar  |  \u2717 = Nicht verfuegbar  |  ? = Unsicher",
        styles['caption']
    ))

    return elements


def generate_pdf():
    """Main function to generate the PDF"""
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SKULD_Strategy_Concepts.pdf")

    doc = BaseDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="SKULD - Strategy Concepts",
        author="SKULD Options Analysis Platform",
    )

    # Page templates
    cover_frame = Frame(0, 0, PAGE_WIDTH, PAGE_HEIGHT, id='cover')
    content_frame = Frame(
        MARGIN, 18 * mm,
        PAGE_WIDTH - 2 * MARGIN, PAGE_HEIGHT - 36 * mm,
        id='content'
    )

    cover_template = PageTemplate(id='Cover', frames=cover_frame, onPage=draw_cover_page)
    content_template = PageTemplate(id='Content', frames=content_frame, onPage=draw_dark_page)

    doc.addPageTemplates([cover_template, content_template])

    # Build content
    styles = create_styles()
    elements = []

    # Cover page (empty - drawn by template)
    elements.append(NextPageTemplate('Content'))
    elements.append(PageBreak())

    # Table of contents
    elements.extend(build_toc(styles))

    # Tier 1
    elements.extend(build_tier1(styles))

    # Tier 2
    elements.extend(build_tier2(styles))

    # Tier 3
    elements.extend(build_tier3(styles))

    # Top 3 Recommendations
    elements.extend(build_recommendation_1(styles))
    elements.extend(build_recommendation_2(styles))
    elements.extend(build_recommendation_3(styles))

    # Appendix
    elements.extend(build_appendix(styles))

    # Build PDF
    doc.build(elements)
    print(f"PDF generated: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_pdf()
