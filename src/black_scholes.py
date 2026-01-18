import scipy.stats as stats
import math

def CallValue(S: float, K: float, sigma: float, t: float, r: float) -> float:
    """
    Berechnet den Preis einer Call-Option nach dem Black-Scholes-Modell.

    Parameter:
    -----------
    S: float
        Aktueller Aktienkurs (Current Stock Price)
    K: float
        Ausübungspreis der Option (Strike Price)
    sigma: float
        Volatilität der Aktie (annualisierte Standardabweichung der Renditen)
    t: float
        Zeit bis zur Fälligkeit in Tagen (Days to Maturity)
    r: float
        Risikofreier Zinssatz (annualisiert, z.B. 0.05 für 5%)

    Rückgabewert:
    -------------
    float: Preis der Call-Option
    """
    t1 = t / 365 + 0.00000001  # Umrechnung der Tage in Jahre + kleiner Puffer, um Division durch Null zu vermeiden
    d1 = (math.log(S / K) + t1 * (r + sigma ** 2 / 2)) / (sigma * math.sqrt(t1))
    d2 = d1 - sigma * math.sqrt(t1)
    c1 = S * stats.norm.cdf(d1, 0, 1)  # S * N(d1)
    c2 = K * math.exp(-r * t1) * stats.norm.cdf(d2, 0, 1)  # K * e^(-r*t) * N(d2)
    CallValue = c1 - c2
    return CallValue

def PutValue(S: float, K: float, sigma: float, t: float, r: float) -> float:
    """
    Berechnet den Preis einer Put-Option nach dem Black-Scholes-Modell unter Verwendung der Put-Call-Parität.

    Parameter:
    -----------
    S: float
        Aktueller Aktienkurs (Current Stock Price)
    K: float
        Ausübungspreis der Option (Strike Price)
    sigma: float
        Volatilität der Aktie (annualisierte Standardabweichung der Renditen)
    t: float
        Zeit bis zur Fälligkeit in Tagen (Days to Maturity)
    r: float
        Risikofreier Zinssatz (annualisiert, z.B. 0.05 für 5%)

    Rückgabewert:
    -------------
    float: Preis der Put-Option
    """
    cv = CallValue(S, K, sigma, t, r)  # Preis der Call-Option
    t2 = t / 365 + 0.00000001  # Umrechnung der Tage in Jahre + kleiner Puffer
    PutValue = cv - S + K * math.exp(-r * t2)  # Put-Call-Parität: Put = Call - S + K * e^(-r*t)
    return PutValue

def ProbLessThan(x: float, S: float, IV: float, t: float, r: float) -> float:
    """
    Berechnet die Wahrscheinlichkeit, dass der Aktienkurs unter einem bestimmten Wert x liegt,
    basierend auf dem Black-Scholes-Modell.

    Parameter:
    -----------
    x: float
        Zielwert des Aktienkurses (z.B. Strike Price)
    S: float
        Aktueller Aktienkurs (Current Stock Price)
    IV: float
        Implizite Volatilität (Implied Volatility)
    t: float
        Zeit bis zur Fälligkeit in Tagen (Days to Maturity)
    r: float
        Risikofreier Zinssatz (annualisiert, z.B. 0.05 für 5%)

    Rückgabewert:
    -------------
    float: Wahrscheinlichkeit, dass der Aktienkurs unter x liegt
    """
    if x == 0:
        x = 0.0001  # Vermeidet Division durch Null oder numerische Probleme
    prob_less_than = stats.norm.cdf((math.log(x / S) - r * (t / 365)) / (IV * math.sqrt(t / 365)))
    return prob_less_than
