import numpy as np
import pandas as pd

from vigilix.signals import disproportionality as dp


def test_prr_and_ror_reference_values():
    prr, lo, hi = dp.prr([20], [980], [400], [200000])
    assert abs(prr[0] - 10.0199) < 1e-3 and lo[0] < prr[0] < hi[0]
    ror, lo, hi = dp.ror([20], [980], [400], [200000])
    assert abs(ror[0] - 10.2041) < 1e-3


def test_zero_cells_are_corrected():
    prr, lo, hi = dp.prr([0], [100], [5], [1000])
    assert np.isfinite(prr[0]) and np.isfinite(hi[0])


def test_information_component_shrinks_small_counts():
    ic_small, lo_small, _ = dp.information_component([1], [99], [10], [100000])
    ic_big, lo_big, _ = dp.information_component([100], [9900], [1000], [10000000])
    assert lo_small[0] < 0 < lo_big[0]


def test_gamma_mixture_fit_and_ebgm_shrinkage():
    rng = np.random.default_rng(0)
    e = rng.gamma(1.0, 2.0, size=3000)
    lam = np.where(rng.random(3000) < 0.1, rng.gamma(4, 1, 3000), rng.gamma(10, 0.1, 3000))
    n = rng.poisson(lam * e)
    prior = dp.fit_gamma_mixture(n, e)
    assert 0 < prior.p < 1
    gm, lo, hi = dp.ebgm(np.array([1.0, 200.0]), np.array([0.1, 5.0]), prior)
    # one report against an expectation of 0.1 is shrunk far below the raw ratio of 10
    assert gm[0] < 10 and lo[0] < gm[0] < hi[0]
    assert lo[1] > 2


def test_score_table_flags_consistent_signals():
    df = pd.DataFrame({"a": [50, 2], "b": [950, 998], "c": [500, 5000], "d": [1000000, 1000000]})
    out, _ = dp.score_table(df, prior=dp.GammaMixturePrior(0.5, 0.5, 2.0, 2.0, 0.2, 0.0))
    assert bool(out.loc[0, "evans"]) and bool(out.loc[0, "eb_signal"])
    assert not bool(out.loc[1, "evans"])


def test_benjamini_hochberg_monotone():
    q = dp.benjamini_hochberg(np.array([0.01, 0.04, 0.03, 0.5]))
    assert np.all(q >= np.array([0.01, 0.04, 0.03, 0.5]) - 1e-12) and q.max() <= 1


def test_report_cluster_detection():
    counts = [3700, 3712, 3725, 3740, 3751, 120, 900, 15]
    df = pd.DataFrame({"dataset": "x", "drug": "d", "a": counts, "eb05": [30, 30, 30, 30, 30, 1, 2, 1]})
    flags = dp.detect_report_clusters(df)
    assert flags.tolist() == [True] * 5 + [False] * 3
