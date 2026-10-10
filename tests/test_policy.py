"""T5 policies and value arithmetic: rules, ties, quotas, IPW identities, paired uncertainty, DR, decisions."""
import numpy as np
import pandas as pd
import pytest

from campaignlab import evaluation as ev
from campaignlab import models as md
from campaignlab import policy as pl


def _cov(n=12, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"row_id": [f"r:{i}" for i in range(n)], "recency": rng.integers(1, 13, n), "history": rng.uniform(30, 900, n),
                         "mens": rng.integers(0, 2, n), "womens": rng.integers(0, 2, n), "newbie": rng.integers(0, 2, n),
                         "channel": rng.choice(["Phone", "Web"], n), "zip_code": rng.choice(["Urban", "Rural"], n)})


def test_fixed_rule_maps_four_profiles():
    cov = _cov(4)
    cov["mens"], cov["womens"] = [1, 0, 1, 0], [0, 1, 1, 0]
    assert list(pl.fixed_rule_actions(cov)) == [1, 2, 0, 0]


def test_policy_functions_reject_assignment_and_outcomes():
    cov = _cov()
    for col in ("arm", "visit", "segment", "partition", "spend"):
        bad = cov.assign(**{col: 0})
        with pytest.raises(md.LeakageError):
            pl.fixed_rule_actions(bad)
        with pytest.raises(md.LeakageError):
            pl.main_policy_actions(bad, {}, {"policy": {"main": {"q": 1.0, "kappa": 0.0}, "tiebreak_key_template": "x{row_id}"}})


def test_gain_rule_ties_and_nonpositive():
    m = np.array([[0.1, 0.1, 0.1],    # zero gains -> no email
                  [0.1, 0.05, 0.08],  # negative -> no email
                  [0.1, 0.2, 0.2],    # tie M/W -> M
                  [0.1, 0.15, 0.3],   # W
                  [0.1, 0.12, 0.11]])  # M
    a, g = pl.best_gain_actions(m, 0.0)
    assert list(a) == [0, 0, 1, 2, 1]
    assert g[0] == 0 and g[3] == pytest.approx(0.2)
    a2, _ = pl.best_gain_actions(m, 0.05)  # cost removes small gains
    assert list(a2) == [0, 0, 1, 2, 0]


@pytest.mark.parametrize("q", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_capacity_limit_respects_quota_and_order(cfg, q):
    n = 101
    rng = np.random.default_rng(2)
    gains = rng.uniform(-0.05, 0.1, n)
    acts = np.where(gains > 0, 1, 0)
    ids = [f"r:{i}" for i in range(n)]
    out = pl.capacity_limit(acts, gains, ids, q, cfg["policy"]["tiebreak_key_template"])
    cap = int(np.floor(q * n))
    assert (out > 0).sum() == min(cap, (acts > 0).sum())
    assert not ((out > 0) & (gains <= 0)).any()  # no enforced contact with nonpositive gains
    if 0 < (out > 0).sum() < (acts > 0).sum():
        assert gains[out > 0].min() >= gains[(acts > 0) & (out == 0)].max()
    assert np.array_equal(out, pl.capacity_limit(acts, gains, ids, q, cfg["policy"]["tiebreak_key_template"]))


def test_capacity_count_exact():
    assert pl.capacity_count(0.25, 12802) == 3200 and pl.capacity_count(0.75, 12802) == 9601 and pl.capacity_count(0.0, 9) == 0


def test_hash_quota_and_cap_are_feature_independent(cfg):
    ids = [f"r:{i}" for i in range(200)]
    t = cfg["policy"]["baseline_key_template"]
    m = pl.hash_quota_actions(ids, 0.25, 1, t)
    w = pl.hash_quota_actions(ids, 0.25, 2, t)
    assert (m == 1).sum() == 50 and (w == 2).sum() == 50 and np.array_equal(m > 0, w > 0)
    assert (pl.hash_quota_actions(ids, 0.0, 1, t) == 0).all()
    rule = np.where(np.arange(200) % 2 == 0, 1, 2)
    capped = pl.hash_cap(rule, ids, 0.25, t)
    assert (capped > 0).sum() == 50 and np.all((capped == 0) | (capped == rule))


def _randomized(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    A = np.repeat([0, 1, 2], [n // 3, n // 3 + 7, n - 2 * (n // 3) - 7])
    rng.shuffle(A)
    Y = (rng.random(n) < np.array([0.1, 0.15, 0.18])[A]).astype(float)
    return A, Y


def test_constant_policy_value_equals_arm_mean():
    A, Y = _randomized()
    for a in (0, 1, 2):
        assert ev.ipw_value(np.full(len(A), a), A, Y) == pytest.approx(Y[A == a].mean(), abs=1e-15)
    ht = ev.ht_value_nominal(np.full(len(A), 1), A, Y)
    assert ht == pytest.approx(3 * (Y * (A == 1)).mean())  # nominal 1/3 differs in finite samples
    assert ht != pytest.approx(Y[A == 1].mean(), abs=1e-6)


def test_identical_policies_have_exact_zero_difference():
    A, Y = _randomized()
    acts = np.random.default_rng(1).integers(0, 3, len(A))
    d = ev.paired_difference(acts, acts.copy(), A, Y)
    assert d["estimate"] == 0 and d["se"] == 0 and d["status"] == "identical_policies"
    C = np.column_stack([ev.contributions(acts, A, Y)] * 2)
    B = ev.paired_bootstrap(C, A, 300, np.random.default_rng(2))
    assert np.array_equal(B[:, 0], B[:, 1])


def test_paired_se_uses_covariance_and_stratified_formula():
    A, Y = _randomized(seed=3)
    p, b = np.full(len(A), 1), np.where(np.arange(len(A)) % 2 == 0, 1, 0)
    d = ev.paired_difference(p, b, A, Y)
    dv = ev.contributions(p, A, Y) - ev.contributions(b, A, Y)
    oracle = np.sqrt(sum(dv[A == a].var(ddof=1) / (A == a).sum() for a in (0, 1, 2)))
    assert d["se"] == pytest.approx(oracle)
    indep = np.sqrt(ev.value_with_se(p, A, Y)["se"] ** 2 + ev.value_with_se(b, A, Y)["se"] ** 2)
    assert d["se"] < indep
    C = np.column_stack([ev.contributions(p, A, Y), ev.contributions(b, A, Y)])
    B = ev.paired_bootstrap(C, A, 4000, np.random.default_rng(4))
    assert (B[:, 0] - B[:, 1]).std(ddof=1) == pytest.approx(d["se"], rel=0.08)


def test_row_permutation_invariance_and_label_misalignment_detected():
    A, Y = _randomized(seed=5)
    acts = np.random.default_rng(6).integers(0, 3, len(A))
    perm = np.random.default_rng(7).permutation(len(A))
    assert ev.ipw_value(acts[perm], A[perm], Y[perm]) == pytest.approx(ev.ipw_value(acts, A, Y))
    relabeled = np.where(acts == 1, 2, np.where(acts == 2, 1, acts))  # remapped labels without remapping arms
    assert ev.ipw_value(relabeled, A, Y) != pytest.approx(ev.ipw_value(acts, A, Y))
    with pytest.raises(ValueError):
        ev.ipw_value(acts[:-1], A, Y)


def test_dr_identities():
    A, Y = _randomized(seed=8)
    n = len(A)
    acts = np.random.default_rng(9).integers(0, 3, n)
    perfect = np.zeros((n, 3))
    perfect[np.arange(n), A] = Y  # residuals vanish on observed actions
    psi = ev.dr_contributions(acts, A, Y, perfect)
    assert np.allclose(psi, perfect[np.arange(n), acts])
    const = np.full((n, 3), 0.3)  # badly wrong outcome model, correct allocation
    for a in (0, 1, 2):
        pol = np.full(n, a)
        assert ev.dr_contributions(pol, A, Y, const).mean() == pytest.approx(Y[A == a].mean(), abs=1e-12)


@pytest.mark.parametrize("lo,hi,cat", [(0.006, 0.02, "meaningful_gain"), (-0.03, -0.001, "worse"), (0.001, 0.004, "detectable_gain_below_margin"),
                                       (-0.01, 0.004, "excludes_margin"), (0.002, 0.02, "positive_margin_unresolved"), (-0.01, 0.02, "insufficient")])
def test_decision_categories(lo, hi, cat):
    assert ev.decision_category(lo, hi, 0.005) == cat


def test_constant_family_requires_all_bounds():
    diffs = {"const_0": {"estimate": 0.05, "se": 0.01}, "const_M": {"estimate": 0.03, "se": 0.01}, "const_W": {"estimate": 0.01, "se": 0.01}}
    r = ev.constant_family_bounds(diffs, 0.005)
    assert r["z"] == pytest.approx(2.128, abs=1e-3)
    assert not r["beats_constant_family"]
    diffs["const_W"]["estimate"] = 0.03
    assert ev.constant_family_bounds(diffs, 0.005)["beats_constant_family"]


def test_validation_selection_rules():
    assert ev.select_constant({0: 0.1, 1: 0.2, 2: 0.2 + 5e-7}, [0, 1, 2], 1e-6)["selected"] == 1
    A, Y = _randomized(seed=10)
    n = len(A)
    rule = np.full(n, 2)
    s = rule.copy()
    s[:5] = 1  # nearly identical but slightly different
    sel = ev.select_targeting({"fixed_rule": rule, "s_learner": s}, A, Y, ["fixed_rule", "s_learner", "t_learner"])
    assert sel["selected"] == "fixed_rule"  # within one paired SE -> simpler wins


def test_cluster_se_singletons_match_sandwich():
    A, Y = _randomized(seed=11)
    d = ev.contributions(np.full(len(A), 1), A, Y)
    r = ev.cluster_se_difference(d, A, np.arange(len(A)))
    assert r["ratio"] == pytest.approx(1.0)
    r2 = ev.cluster_se_difference(d, A, np.arange(len(A)) // 2)
    assert r2["n_clusters"] == len(A) // 2
