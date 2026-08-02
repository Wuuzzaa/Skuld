/**
 * Black-Scholes-Optionsbewertung — Portierung von `src/black_scholes.py`.
 * Wird client-seitig im Risikograf für die IV-Shift-Neubewertung genutzt.
 *
 * `t` ist in TAGEN (wie im Python-Original), intern → Jahre.
 */

/** Standardnormal-CDF via Abramowitz-Stegun 7.1.26 (Ersatz für scipy norm.cdf). */
export function normCdf(x: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = 0.3989422804014327 * Math.exp(-(x * x) / 2); // 1/sqrt(2π) * e^(-x²/2)
  let p =
    d *
    t *
    (0.319381530 +
      t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
  p = 1 - p;
  return x >= 0 ? p : 1 - p;
}

/** Call-Preis nach Black-Scholes. S=Kurs, K=Strike, sigma=IV, t=Tage, r=Zins. */
export function callValue(S: number, K: number, sigma: number, t: number, r: number): number {
  const t1 = t / 365 + 1e-8;
  const sqrtT = sigma * Math.sqrt(t1);
  if (sqrtT === 0 || S <= 0 || K <= 0) return Math.max(S - K, 0);
  const d1 = (Math.log(S / K) + t1 * (r + (sigma * sigma) / 2)) / sqrtT;
  const d2 = d1 - sqrtT;
  return S * normCdf(d1) - K * Math.exp(-r * t1) * normCdf(d2);
}

/** Put-Preis via Put-Call-Parität (wie im Python-Original). */
export function putValue(S: number, K: number, sigma: number, t: number, r: number): number {
  const cv = callValue(S, K, sigma, t, r);
  const t2 = t / 365 + 1e-8;
  return cv - S + K * Math.exp(-r * t2);
}
