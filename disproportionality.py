"""Disproportionality statistics for spontaneous report databases.

All measures work on the 2 x 2 table for a drug and event pair:

=================  ==============  =================
                   event reported  event not reported
drug reported      a               b
drug not reported  c               d
=================  ==============  =================

Frequentist measures (PRR, ROR, chi square) follow Evans et al. (2001) and
van Puijenbroek et al. (2002). Bayesian measures are the information
component of the BCPNN (Bate et al. 1998; credibility interval approximation
from Noren et al. 2013) and the empirical Bayes geometric mean of the Multi
item Gamma Poisson Shrinker (DuMouchel 1999), with its two component gamma
prior fitted by maximum likelihood per database.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import optimize, special, stats

Z95 = 1.959963984540054


def _arr(x) -> np.ndarray:
    return np.asarray(x, dtype=np.float64)


def expected(a, b, c, d) -> np.ndarray:
    a, b, c, d = map(_arr, (a, b, c, d))
    n = a + b + c + d
    return (a + b) * (a + c) / np.where(n > 0, n, 1.0)


def prr(a, b, c, d) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Proportional reporting ratio with a 95% confidence interval.

    A continuity correction of 0.5 is added to every cell when any cell is
    zero, so pairs with no reports still return finite values.
    """
    a, b, c, d = map(_arr, (a, b, c, d))
    corr = np.where((a == 0) | (b == 0) | (c == 0) | (d == 0), 0.5, 0.0)
    a2, b2, c2, d2 = a + corr, b + corr, c + corr, d + corr
    est = (a2 / (a2 + b2)) / (c2 / (c2 + d2))
    se = np.sqrt(np.maximum(1 / a2 - 1 / (a2 + b2) + 1 / c2 - 1 / (c2 + d2), 0))
    return est, np.exp(np.log(est) - Z95 * se), np.exp(np.log(est) + Z95 * se)


def ror(a, b, c, d) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reporting odds ratio (Haldane correction when any cell is zero)."""
    a, b, c, d = map(_arr, (a, b, c, d))
    corr = np.where((a == 0) | (b == 0) | (c == 0) | (d == 0), 0.5, 0.0)
    a2, b2, c2, d2 = a + corr, b + corr, c + corr, d + corr
    est = (a2 * d2) / (b2 * c2)
    se = np.sqrt(1 / a2 + 1 / b2 + 1 / c2 + 1 / d2)
    return est, np.exp(np.log(est) - Z95 * se), np.exp(np.log(est) + Z95 * se)


def chi_square_yates(a, b, c, d) -> np.ndarray:
    a, b, c, d = map(_arr, (a, b, c, d))
    n = a + b + c + d
    num = n * np.maximum(np.abs(a * d - b * c) - n / 2, 0) ** 2
    den = (a + b) * (c + d) * (a + c) * (b + d)
    return np.where(den > 0, num / np.where(den > 0, den, 1), 0.0)


def information_component(a, b, c, d) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """BCPNN information component with the shrinkage used by the UMC.

    IC = log2((a + 0.5) / (E + 0.5)); the 95% credibility interval uses the
    closed form approximation of Noren et al. (Stat Methods Med Res 2013).
    """
    a = _arr(a)
    e = expected(a, b, c, d)
    ic = np.log2((a + 0.5) / (e + 0.5))
    lo = ic - 3.3 * (a + 0.5) ** -0.5 - 2.0 * (a + 0.5) ** -1.5
    hi = ic + 2.4 * (a + 0.5) ** -0.5 - 0.5 * (a + 0.5) ** -1.5
    return ic, lo, hi


# ---------------------------------------------------------------------------
# Multi item Gamma Poisson Shrinker
# ---------------------------------------------------------------------------
@dataclass
class GammaMixturePrior:
    alpha1: float
    beta1: float
    alpha2: float
    beta2: float
    p: float
    loglik: float

    def as_dict(self) -> dict:
        return {k: round(float(v), 6) for k, v in self.__dict__.items()}


def _log_nb(n: np.ndarray, e: np.ndarray, alpha: float, beta: float) -> np.ndarray:
    """log P(N = n | E) for N ~ Poisson(lambda E), lambda ~ Gamma(alpha, beta)."""
    return (
        special.gammaln(alpha + n)
        - special.gammaln(alpha)
        - special.gammaln(n + 1)
        + alpha * np.log(beta / (beta + e))
        + n * np.log(e / (beta + e))
    )


def fit_gamma_mixture(n, e, seed: int = 0) -> GammaMixturePrior:
    """Maximum likelihood fit of DuMouchel's two component gamma prior.

    Parameters are optimised on an unconstrained scale (log for shape and
    rate, logit for the mixing weight) from several starting points, keeping
    the best likelihood. Pairs with E close to zero carry no information and
    are excluded from the fit.
    """
    n, e = _arr(n), _arr(e)
    keep = e > 1e-8
    n, e = n[keep], e[keep]

    def nll(theta: np.ndarray) -> float:
        a1, b1, a2, b2 = np.exp(theta[:4])
        p = special.expit(theta[4])
        l1 = _log_nb(n, e, a1, b1) + np.log(p)
        l2 = _log_nb(n, e, a2, b2) + np.log1p(-p)
        return -float(np.sum(np.logaddexp(l1, l2)))

    starts = [
        np.log([0.2, 0.1, 2.0, 4.0]).tolist() + [special.logit(1 / 3)],
        np.log([0.5, 0.5, 2.0, 2.0]).tolist() + [special.logit(0.2)],
        np.log([1.0, 0.2, 3.0, 3.0]).tolist() + [special.logit(0.1)],
        np.log([0.05, 0.05, 1.0, 1.0]).tolist() + [special.logit(0.5)],
    ]
    best = None
    for s in starts:
        res = optimize.minimize(nll, np.array(s), method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-6, "fatol": 1e-6})
        res = optimize.minimize(nll, res.x, method="L-BFGS-B")
        if best is None or res.fun < best.fun:
            best = res
    a1, b1, a2, b2 = np.exp(best.x[:4])
    p = float(special.expit(best.x[4]))
    # Convention: component 1 is the one with the larger mean (signal component)
    if a1 / b1 < a2 / b2:
        a1, b1, a2, b2, p = a2, b2, a1, b1, 1 - p
    return GammaMixturePrior(float(a1), float(b1), float(a2), float(b2), p, -float(best.fun))


def ebgm(n, e, prior: GammaMixturePrior) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Empirical Bayes geometric mean with the 5th and 95th posterior percentiles."""
    n, e = _arr(n), _arr(e)
    e = np.maximum(e, 1e-12)
    l1 = _log_nb(n, e, prior.alpha1, prior.beta1) + np.log(prior.p)
    l2 = _log_nb(n, e, prior.alpha2, prior.beta2) + np.log1p(-prior.p)
    q = np.exp(l1 - np.logaddexp(l1, l2))  # posterior weight of component 1
    s1, r1 = prior.alpha1 + n, prior.beta1 + e
    s2, r2 = prior.alpha2 + n, prior.beta2 + e
    elog = q * (special.digamma(s1) - np.log(r1)) + (1 - q) * (special.digamma(s2) - np.log(r2))
    gm = np.exp(elog)

    def quantile(prob: float) -> np.ndarray:
        lo = np.full_like(n, 1e-6)
        hi = np.maximum(gm * 50, 50.0)
        for _ in range(60):
            mid = (lo + hi) / 2
            cdf = q * stats.gamma.cdf(mid, s1, scale=1 / r1) + (1 - q) * stats.gamma.cdf(mid, s2, scale=1 / r2)
            lo = np.where(cdf < prob, mid, lo)
            hi = np.where(cdf >= prob, mid, hi)
        return (lo + hi) / 2

    return gm, quantile(0.05), quantile(0.95)


def benjamini_hochberg(p: np.ndarray) -> np.ndarray:
    p = _arr(p)
    order = np.argsort(p)
    ranked = p[order] * len(p) / (np.arange(len(p)) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(q)
    out[order] = np.minimum(q, 1.0)
    return out


def score_table(df: pd.DataFrame, prior: GammaMixturePrior | None = None) -> tuple[pd.DataFrame, GammaMixturePrior]:
    """Add every disproportionality measure to a frame with columns a, b, c, d."""
    out = df.copy()
    a, b, c, d = (out[k].to_numpy(np.float64) for k in "abcd")
    out["expected"] = expected(a, b, c, d)
    out["prr"], out["prr_lo"], out["prr_hi"] = prr(a, b, c, d)
    out["ror"], out["ror_lo"], out["ror_hi"] = ror(a, b, c, d)
    out["chi2"] = chi_square_yates(a, b, c, d)
    out["p_value"] = stats.chi2.sf(out["chi2"], 1)
    out["q_value"] = benjamini_hochberg(out["p_value"].to_numpy())
    out["ic"], out["ic025"], out["ic975"] = information_component(a, b, c, d)
    prior = prior or fit_gamma_mixture(a, out["expected"].to_numpy())
    out["ebgm"], out["eb05"], out["eb95"] = ebgm(a, out["expected"].to_numpy(), prior)
    out["evans"] = (a >= 3) & (out["prr"] >= 2) & (out["chi2"] >= 4)
    out["ror_signal"] = (a >= 3) & (out["ror_lo"] > 1)
    out["ic_signal"] = out["ic025"] > 0
    out["eb_signal"] = out["eb05"] >= 2
    out["signal_votes"] = out[["evans", "ror_signal", "ic_signal", "eb_signal"]].sum(axis=1)
    return out, prior


def score_all(faers: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Score each FAERS dataset separately (each has its own background)."""
    frames, priors = [], {}
    for name, part in faers.groupby("dataset", sort=True):
        scored, prior = score_table(part)
        frames.append(scored)
        priors[name] = prior.as_dict()
    return pd.concat(frames, ignore_index=True), priors


def detect_report_clusters(df: pd.DataFrame, min_cases: int = 100, tolerance: float = 0.01, min_size: int = 5, min_median_eb05: float = 3.0) -> pd.Series:
    """Flag pairs that belong to a suspicious cluster of near identical counts.

    When one batch of reports (a litigation series, a patient support
    programme, duplicated case versions) lists the same long set of preferred
    terms, many terms for one drug end up with almost exactly the same count
    and extreme disproportionality. Such clusters are a classic cause of false
    signals, so pairs inside them are flagged for de duplication review.
    """
    flag = pd.Series(False, index=df.index)
    for _, part in df[df["a"] >= min_cases].groupby(["dataset", "drug"]):
        counts = part["a"].sort_values()
        vals = counts.to_numpy(np.float64)
        idx = counts.index.to_numpy()
        start = 0
        for end in range(1, len(vals) + 1):
            if end == len(vals) or vals[end] > vals[end - 1] * (1 + tolerance):
                if end - start >= min_size and float(np.median(part.loc[idx[start:end], "eb05"])) >= min_median_eb05:
                    flag.loc[idx[start:end]] = True
                start = end
    return flag
