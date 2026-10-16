// Port of vigilix/signals/disproportionality.py for the calculator.

const Z95 = 1.959963984540054;

export function lgamma(x: number): number {
  const g = 7;
  const c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
  if (x < 0.5) return Math.log(Math.PI / Math.abs(Math.sin(Math.PI * x))) - lgamma(1 - x);
  x -= 1;
  let a = c[0];
  const t = x + g + 0.5;
  for (let i = 1; i < g + 2; i++) a += c[i] / (x + i);
  return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(a);
}

export function digamma(x: number): number {
  let r = 0;
  while (x < 6) {
    r -= 1 / x;
    x += 1;
  }
  const f = 1 / (x * x);
  return r + Math.log(x) - 0.5 / x - f * (1 / 12 - f * (1 / 120 - f * (1 / 252 - f * (1 / 240 - f / 132))));
}

/** Regularised lower incomplete gamma P(a, x). */
export function gammaP(a: number, x: number): number {
  if (x <= 0) return 0;
  if (x < a + 1) {
    let sum = 1 / a,
      del = sum,
      ap = a;
    for (let n = 0; n < 500; n++) {
      ap += 1;
      del *= x / ap;
      sum += del;
      if (Math.abs(del) < Math.abs(sum) * 1e-14) break;
    }
    return sum * Math.exp(-x + a * Math.log(x) - lgamma(a));
  }
  let b = x + 1 - a,
    c = 1e300,
    d = 1 / b,
    h = d;
  for (let i = 1; i < 500; i++) {
    const an = -i * (i - a);
    b += 2;
    d = an * d + b;
    if (Math.abs(d) < 1e-300) d = 1e-300;
    c = b + an / c;
    if (Math.abs(c) < 1e-300) c = 1e-300;
    d = 1 / d;
    const del = d * c;
    h *= del;
    if (Math.abs(del - 1) < 1e-14) break;
  }
  return 1 - Math.exp(-x + a * Math.log(x) - lgamma(a)) * h;
}

function erfc(x: number): number {
  const z = Math.abs(x);
  const t = 1 / (1 + 0.5 * z);
  const r = t * Math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418 + t * (-0.18628806 + t * (0.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277)))))))));
  return x >= 0 ? r : 2 - r;
}

export interface Prior {
  alpha1: number;
  beta1: number;
  alpha2: number;
  beta2: number;
  p: number;
}

function logNB(n: number, e: number, a: number, b: number) {
  return lgamma(a + n) - lgamma(a) - lgamma(n + 1) + a * Math.log(b / (b + e)) + n * Math.log(e / (b + e));
}

export function score(a: number, b: number, c: number, d: number, prior: Prior) {
  const N = a + b + c + d;
  const expected = N > 0 ? ((a + b) * (a + c)) / N : 0;
  const corr = a === 0 || b === 0 || c === 0 || d === 0 ? 0.5 : 0;
  const [a2, b2, c2, d2] = [a + corr, b + corr, c + corr, d + corr];
  const prr = a2 / (a2 + b2) / (c2 / (c2 + d2));
  const sePrr = Math.sqrt(Math.max(1 / a2 - 1 / (a2 + b2) + 1 / c2 - 1 / (c2 + d2), 0));
  const ror = (a2 * d2) / (b2 * c2);
  const seRor = Math.sqrt(1 / a2 + 1 / b2 + 1 / c2 + 1 / d2);
  const den = (a + b) * (c + d) * (a + c) * (b + d);
  const chi2 = den > 0 ? (N * Math.max(Math.abs(a * d - b * c) - N / 2, 0) ** 2) / den : 0;
  const ic = Math.log2((a + 0.5) / (expected + 0.5));
  const ic025 = ic - 3.3 * (a + 0.5) ** -0.5 - 2 * (a + 0.5) ** -1.5;
  const ic975 = ic + 2.4 * (a + 0.5) ** -0.5 - 0.5 * (a + 0.5) ** -1.5;
  const e = Math.max(expected, 1e-12);
  const l1 = logNB(a, e, prior.alpha1, prior.beta1) + Math.log(prior.p);
  const l2 = logNB(a, e, prior.alpha2, prior.beta2) + Math.log(1 - prior.p);
  const m = Math.max(l1, l2);
  const q = Math.exp(l1 - (m + Math.log(Math.exp(l1 - m) + Math.exp(l2 - m))));
  const s1 = prior.alpha1 + a,
    r1 = prior.beta1 + e,
    s2 = prior.alpha2 + a,
    r2 = prior.beta2 + e;
  const ebgm = Math.exp(q * (digamma(s1) - Math.log(r1)) + (1 - q) * (digamma(s2) - Math.log(r2)));
  const quantile = (prob: number) => {
    let lo = 1e-6,
      hi = Math.max(ebgm * 50, 50);
    for (let i = 0; i < 80; i++) {
      const mid = (lo + hi) / 2;
      const cdf = q * gammaP(s1, mid * r1) + (1 - q) * gammaP(s2, mid * r2);
      if (cdf < prob) lo = mid;
      else hi = mid;
    }
    return (lo + hi) / 2;
  };
  const eb05 = quantile(0.05),
    eb95 = quantile(0.95);
  const pValue = erfc(Math.sqrt(chi2 / 2));
  const evans = a >= 3 && prr >= 2 && chi2 >= 4;
  const rorLo = Math.exp(Math.log(ror) - Z95 * seRor);
  const ror_signal = a >= 3 && rorLo > 1;
  const ic_signal = ic025 > 0;
  const eb_signal = eb05 >= 2;
  return {
    a, b, c, d, expected, chi2, p_value: pValue,
    prr, prr_lo: Math.exp(Math.log(prr) - Z95 * sePrr), prr_hi: Math.exp(Math.log(prr) + Z95 * sePrr),
    ror, ror_lo: rorLo, ror_hi: Math.exp(Math.log(ror) + Z95 * seRor),
    ic, ic025, ic975, ebgm, eb05, eb95,
    evans, ror_signal, ic_signal, eb_signal,
    signal_votes: [evans, ror_signal, ic_signal, eb_signal].filter(Boolean).length,
  };
}
