"""Known-truth SYNTHETIC checks (slow): unbiasedness/coverage under valid randomization, and failure detection when broken."""
import numpy as np
import pytest

from campaignlab import evaluation as ev
from campaignlab import inference as inf
from campaignlab import policy as pl
from campaignlab import simulation as sim

pytestmark = pytest.mark.slow


def _run(scen, reps, n, rng, truth_X):
    P = sim.true_probs(scen, truth_X)
    t_ate = float((P[:, 1] - P[:, 0]).mean())
    t_rule = sim.policy_value_truth(scen, truth_X, pl.fixed_rule_actions(truth_X[sim.COV])) - float(P[:, 1].mean())
    ate, cover, rule, dr = [], [], [], []
    for _ in range(reps):
        X = sim.draw_X(rng, n)
        p = sim.true_probs(scen, X)
        A = sim.assign(scen, X, rng)
        Y = (rng.random(n) < p[np.arange(n), A]).astype(float)
        r = inf.mean_difference(Y[A == 1], Y[A == 0])
        ate.append(r["estimate"])
        cover.append(r["ci_low"] <= t_ate <= r["ci_high"])
        acts = pl.fixed_rule_actions(X[sim.COV])
        rule.append(ev.paired_difference(acts, np.full(n, 1), A, Y)["estimate"])
        dr.append(ev.dr_paired_difference(acts, np.full(n, 1), A, Y, np.full((n, 3), 0.3))["estimate"])
    return t_ate, np.array(ate), np.mean(cover), t_rule, np.array(rule), np.array(dr)


def test_valid_randomization_is_unbiased_and_covers():
    rng = np.random.default_rng(123)
    truth_X = sim.draw_X(rng, 200_000)
    t_ate, ate, cov, t_rule, rule, dr = _run("sign_changing_heterogeneity", 300, 3000, rng, truth_X)
    mcse = ate.std(ddof=1) / np.sqrt(len(ate))
    assert abs(ate.mean() - t_ate) < 4 * mcse
    assert 0.90 <= cov <= 0.99
    assert abs(rule.mean() - t_rule) < 4 * rule.std(ddof=1) / np.sqrt(len(rule))
    assert abs(dr.mean() - t_rule) < 4 * dr.std(ddof=1) / np.sqrt(len(dr))  # bad outcome model, correct allocation


def test_broken_allocation_is_detected():
    rng = np.random.default_rng(321)
    truth_X = sim.draw_X(rng, 200_000)
    t_ate, ate, cov, *_ = _run("broken_allocation", 300, 3000, rng, truth_X)
    assert abs(ate.mean() - t_ate) > 4 * ate.std(ddof=1) / np.sqrt(len(ate))
