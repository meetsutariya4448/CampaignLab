"""T3 experimental estimators: arithmetic, signs, units, multiplicity, covariance, degenerate cases, resampling."""
import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from scipy import stats

from campaignlab import inference as inf


def oracle_holm(p):
    """Independent Holm implementation used as a test oracle."""
    p = np.asarray(p, float)
    m = len(p)
    order = np.argsort(p)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[i]))
        adj[i] = running
    return adj


def test_hand_calculated_difference():
    r = inf.mean_difference([1, 0, 1, 1], [0, 0, 1, 0])
    assert r["estimate"] == pytest.approx(0.5)
    # s_t^2 = s_c^2 = 0.25 with n-1 denominators -> SE = sqrt(0.25/4 + 0.25/4)
    assert r["se"] == pytest.approx(np.sqrt(0.125))
    z = 0.5 / np.sqrt(0.125)
    assert r["p_value"] == pytest.approx(2 * stats.norm.sf(z))
    assert r["ci_low"] == pytest.approx(0.5 - 1.959964 * np.sqrt(0.125), abs=1e-6)


def test_sign_reversal_offset_and_scale():
    rng = np.random.default_rng(0)
    yt, yc = rng.gamma(1, 10, 200), rng.gamma(1, 12, 220)
    a, b = inf.mean_difference(yt, yc), inf.mean_difference(yc, yt)
    assert a["estimate"] == pytest.approx(-b["estimate"]) and a["se"] == pytest.approx(b["se"])
    off = inf.mean_difference(yt + 7.5, yc + 7.5)
    assert off["estimate"] == pytest.approx(a["estimate"]) and off["se"] == pytest.approx(a["se"])
    sc = inf.mean_difference(100 * yt, 100 * yc)
    assert sc["estimate"] == pytest.approx(100 * a["estimate"]) and sc["se"] == pytest.approx(100 * a["se"])
    assert sc["ci_high"] - sc["ci_low"] == pytest.approx(100 * (a["ci_high"] - a["ci_low"]))


def test_symmetric_null_has_p_one():
    r = inf.mean_difference([0, 1, 0, 1], [1, 0, 1, 0])
    assert r["estimate"] == 0 and r["p_value"] == pytest.approx(1.0)


@pytest.mark.parametrize("yt,yc,status", [([0, 0, 0], [0, 0, 0], "degenerate_zero_variance"),
                                          ([1, 1, 1], [1, 1], "degenerate_zero_variance"),
                                          ([1], [0, 1], "insufficient_n")])
def test_degenerate_inputs_are_flagged(yt, yc, status):
    r = inf.mean_difference(yt, yc)
    assert r["status"] == status and np.isnan(r["p_value"]) and np.isnan(r["se"])


def test_holm_fixtures_and_properties():
    assert np.allclose(inf.holm([0.01, 0.04]), [0.02, 0.04])
    assert np.allclose(inf.holm([0.03, 0.04]), [0.06, 0.06])
    assert np.allclose(inf.holm([0.04, 0.01]), [0.04, 0.02])  # input order restored
    rng = np.random.default_rng(1)
    for _ in range(200):
        p = rng.uniform(0, 0.2, size=rng.integers(2, 6))
        adj = inf.holm(p)
        assert np.allclose(adj, oracle_holm(p))
        assert (adj >= p - 1e-15).all()
        assert (np.diff(adj[np.argsort(p)]) >= -1e-15).all()
    with pytest.raises(ValueError):
        inf.holm([0.01, np.nan])


def test_bonferroni_interval_level():
    lo, hi, lvl = inf.bonferroni_interval(0.0, 1.0, 2)
    assert lvl == pytest.approx(0.975) and hi == pytest.approx(stats.norm.ppf(1 - 0.05 / 4))


def test_effect_table_labels_ordinary_vs_simultaneous(cfg, toy_frame):
    t = inf.effect_table(toy_frame, cfg, "SYNTHETIC", "sha")
    prim = t[t.family == "primary"]
    assert len(prim) == 2 and set(prim.contrast) == {"M - 0", "W - 0"}
    assert len(t[t.family == "secondary"]) == 4
    assert all("not multiplicity-adjusted" in m for m in t.ci_method)
    assert not any("holm" in m.lower() for m in t.ci_method)
    assert all("Bonferroni" in m for m in prim.simul_ci_method)
    assert (prim.simul_ci_high - prim.simul_ci_low > prim.ci_high - prim.ci_low).all()
    assert np.allclose(prim.p_adj, oracle_holm(prim.p_raw))
    assert np.allclose(prim.estimate_pp, 100 * prim.estimate)


def test_unadjusted_hc2_regression_equals_neyman(toy_frame):
    arm, y = toy_frame.arm.to_numpy(), toy_frame.visit.to_numpy(float)
    reg = inf.unadjusted_ols(y, arm, "HC2")["contrasts"]
    for t, label in ((1, "M - 0"), (2, "W - 0")):
        raw = inf.mean_difference(y[arm == t], y[arm == 0])
        assert reg[label]["estimate"] == pytest.approx(raw["estimate"], abs=1e-12)
        assert reg[label]["se"] == pytest.approx(raw["se"], rel=1e-10)


def test_interacted_design_centering_contrasts_and_library_agreement(cfg, toy_frame):
    arm = toy_frame.arm.to_numpy()
    basis = inf.raw_basis(toy_frame)
    X, names, center = inf.interacted_design(arm, basis)
    assert np.allclose(X[:, 3:12].mean(axis=0), 0, atol=1e-12)  # centered on analyzed sample
    assert names[:3] == ["const", "arm_M", "arm_W"] and len(names) == 30
    y = toy_frame.visit.to_numpy(float)
    out = inf.ols_contrasts(y, X, "HC2")
    res = sm.OLS(y, X).fit(cov_type="HC2")
    cov = np.asarray(res.cov_params())
    L = np.zeros(30)
    L[2], L[1] = 1, -1
    assert out["contrasts"]["W - M"]["estimate"] == pytest.approx(res.params[2] - res.params[1])
    assert out["contrasts"]["W - M"]["se"] == pytest.approx(np.sqrt(L @ cov @ L))
    naive = np.sqrt(cov[1, 1] + cov[2, 2])
    assert out["contrasts"]["W - M"]["se"] != pytest.approx(naive, rel=1e-6)  # covariance term matters
    hc3 = inf.ols_contrasts(y, X, "HC3")["contrasts"]["M - 0"]["se"]
    assert hc3 >= out["contrasts"]["M - 0"]["se"]


def test_rank_deficient_design_fails_clearly(toy_frame):
    basis = inf.raw_basis(toy_frame)
    basis["dup"] = basis["recency"] * 2
    X, _, _ = inf.interacted_design(toy_frame.arm.to_numpy(), basis)
    with pytest.raises(inf.RankDeficiencyError):
        inf.check_design(X)


def test_adjusted_table_runs_and_retains_unadjusted(cfg, toy_frame):
    t, diag = inf.adjusted_table(toy_frame, cfg, "SYNTHETIC")
    assert set(t.covariance) == {"HC2", "HC3"} and diag["rank"] == 30
    assert "HC2" in diag["joint_interaction_test_visit"]
    raw = inf.mean_difference(toy_frame.visit[toy_frame.arm == 1], toy_frame.visit[toy_frame.arm == 0])
    row = t[(t.outcome == "visit") & (t.contrast == "M - 0") & (t.covariance == "HC2")].iloc[0]
    assert row.unadj_estimate == pytest.approx(raw["estimate"])


def test_bootstrap_counts_preserve_arm_sizes_and_seed():
    c = inf.resample_counts(57, 40, np.random.default_rng(3))
    assert c.shape == (40, 57) and (c.sum(axis=1) == 57).all()
    c2 = inf.resample_counts(57, 40, np.random.default_rng(3))
    assert np.array_equal(c, c2)


def test_bootstrap_table_matches_analytic_scale(toy_frame):
    t = inf.bootstrap_table(toy_frame, "spend", 2000, np.random.default_rng(5), "SYNTHETIC")
    for r in t.itertuples():
        assert r.bootstrap_se == pytest.approx(r.analytic_se, rel=0.15)
        assert r.bootstrap_ci_low < r.estimate < r.bootstrap_ci_high


def test_permutation_binary_matches_generic_and_never_zero():
    rng = np.random.default_rng(7)
    yt, yc = (rng.random(60) < 0.4).astype(int), (rng.random(60) < 0.25).astype(int)
    fast = inf.permutation_test_binary(yt, yc, 4000, np.random.default_rng(8))
    slow = inf.permutation_test_mean_diff(yt, yc, 4000, np.random.default_rng(9))
    assert fast["p_value"] == pytest.approx(slow["p_value"], abs=0.03)
    assert fast["p_value"] > 0
    big = inf.permutation_test_binary(np.ones(500, int), np.zeros(500, int), 999, np.random.default_rng(1))
    assert big["p_value"] == pytest.approx(1 / 1000)
    null = inf.permutation_test_binary(np.zeros(50, int), np.zeros(40, int), 999, np.random.default_rng(1))
    assert null["p_value"] == 1.0 and "sharp" in null["null"]


def test_subgroups_reconcile_and_cover_rows(toy_frame):
    for g in ("newbie", "purchase_profile", "channel"):
        sub, het = inf.subgroup_table(toy_frame, g, "SYNTHETIC", 200, 20)
        totals = sub[sub.contrast == "M - 0"].groupby("subgroup")["n_subgroup"].first()
        assert totals.sum() == len(toy_frame)
        labels = inf.subgroup_labels(toy_frame, g)
        assert labels.notna().all()
        assert (sub.support_flag == ((sub[["n_treat", "n_control"]].min(axis=1) < 200) | (sub[["visits_treat", "visits_control"]].min(axis=1) < 20))).all()
    sub, het = inf.subgroup_table(toy_frame, "newbie", "SYNTHETIC", 200, 20)
    row = het[het.contrast == "M - 0"].iloc[0]
    e = sub[sub.contrast == "M - 0"].set_index("subgroup")["estimate"]
    assert row.difference == pytest.approx(e.iloc[1] - e.iloc[0])


def test_balance_smd_properties(toy_frame):
    same = pd.concat([toy_frame.iloc[:300]] * 3, ignore_index=True)
    arm = np.repeat([0, 1, 2], 300)
    t = inf.balance_table(same, arm, "SYN")
    assert np.allclose(t.smd.fillna(0), 0)
    t1 = inf.balance_table(toy_frame, toy_frame.arm.to_numpy(), "SYN")
    swapped = toy_frame.arm.map({0: 1, 1: 0, 2: 2}).to_numpy()
    t2 = inf.balance_table(toy_frame, swapped, "SYN")
    a = t1[t1.comparison == "M vs 0"].set_index("feature").smd
    b = t2[t2.comparison == "M vs 0"].set_index("feature").smd
    assert np.allclose(a, -b)
    f = inf.balance_features(toy_frame)
    assert np.allclose(f[["channel_Phone", "channel_Web", "channel_Multichannel"]].sum(axis=1), 1)
    assert np.allclose(f[["zip_Rural", "zip_Urban", "zip_Surburban"]].sum(axis=1), 1)


def test_newcombe_interval_contains_estimate():
    lo, hi = inf.newcombe_interval(12, 1000, 5, 1000)
    assert lo < 0.007 < hi
