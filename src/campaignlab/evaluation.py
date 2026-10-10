"""Off-policy value estimation for fixed (locked) action vectors on randomized observations.

The allocation weights are the evaluation sample's observed arm fractions n_E(a)/N_E. They are
NOT publisher-documented individual propensities. The nominal 1/3 design is a sensitivity.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .config import ARM_SHORT
from .inference import resample_counts

ARMS = (0, 1, 2)


def _check(actions, A, Y):
    actions, A, Y = np.asarray(actions), np.asarray(A), np.asarray(Y, dtype=np.float64)
    if not (len(actions) == len(A) == len(Y)):
        raise ValueError("actions, arms and outcomes must be aligned on the same rows")
    for a in ARMS:
        if not (A == a).any():
            raise ValueError(f"no evaluation support for arm {a}")
    return actions, A, Y


def contributions(actions, A, Y) -> np.ndarray:
    """1{pi(X_i) = A_i} * Y_i (the matched reward; zero when the recommended action was not assigned)."""
    actions, A, Y = _check(actions, A, Y)
    return (actions == A).astype(np.float64) * Y


def ipw_value(actions, A, Y) -> float:
    """Allocation-normalized IPW: sum over arms of mean_{A=a}[1{pi=a} Y]."""
    c = contributions(actions, A, Y)
    A = np.asarray(A)
    return float(sum(c[A == a].mean() for a in ARMS))


def ht_value_nominal(actions, A, Y, p: float = 1 / 3) -> float:
    """Horvitz-Thompson value with the publisher's nominal one-third assignment probability (sensitivity)."""
    return float(np.mean(contributions(actions, A, Y) / p))


def stratified_se(d, A, arm_weights=None) -> float:
    """sqrt( sum_a w_a^2 s^2(d|a) / n_a ), the conservative within-arm (stratified) SE."""
    d, A = np.asarray(d, float), np.asarray(A)
    w = arm_weights or {a: 1.0 for a in ARMS}
    return float(np.sqrt(sum(w[a] ** 2 * d[A == a].var(ddof=1) / (A == a).sum() for a in ARMS)))


def paired_difference(act_p, act_b, A, Y, level: float = 0.95) -> dict:
    """Delta(pi, b) on the same rows with the paired stratified SE (never independent-policy SEs)."""
    d = contributions(act_p, A, Y) - contributions(act_b, A, Y)
    A = np.asarray(A)
    est = float(sum(d[A == a].mean() for a in ARMS))
    if np.array_equal(np.asarray(act_p), np.asarray(act_b)):
        return {"estimate": 0.0, "se": 0.0, "ci_low": 0.0, "ci_high": 0.0, "z": np.nan, "p_value": np.nan, "status": "identical_policies"}
    se = stratified_se(d, A)
    if se == 0:
        return {"estimate": est, "se": 0.0, "ci_low": est, "ci_high": est, "z": np.nan, "p_value": np.nan, "status": "degenerate_zero_variance"}
    zc = float(stats.norm.ppf(0.5 + level / 2))
    z = est / se
    return {"estimate": est, "se": se, "ci_low": est - zc * se, "ci_high": est + zc * se, "z": z,
            "p_value": float(2 * stats.norm.sf(abs(z))), "status": "ok"}


def value_with_se(actions, A, Y, level: float = 0.95) -> dict:
    c = contributions(actions, A, Y)
    v = ipw_value(actions, A, Y)
    se = stratified_se(c, A)
    zc = float(stats.norm.ppf(0.5 + level / 2))
    return {"value": v, "se": se, "ci_low": v - zc * se, "ci_high": v + zc * se}


def ht_paired_difference(act_p, act_b, A, Y, p: float = 1 / 3, level: float = 0.95) -> dict:
    d = (contributions(act_p, A, Y) - contributions(act_b, A, Y)) / p
    est = float(d.mean())
    se = float(d.std(ddof=1) / np.sqrt(len(d))) if not np.array_equal(act_p, act_b) else 0.0
    zc = float(stats.norm.ppf(0.5 + level / 2))
    return {"estimate": est, "se": se, "ci_low": est - zc * se, "ci_high": est + zc * se}


def support_table(name: str, actions, A, Y, outcome: str) -> list[dict]:
    """Matched rows/events by arm: only rows with A = pi(X) contribute observed rewards."""
    actions, A, Y = _check(actions, A, Y)
    rows = []
    for a in ARMS:
        in_arm = A == a
        matched = in_arm & (actions == a)
        rows.append({"policy": name, "outcome": outcome, "arm": ARM_SHORT[a], "n_arm": int(in_arm.sum()),
                     "recommended_share_overall": float((actions == a).mean()), "matched_rows": int(matched.sum()),
                     "matched_events": int((Y[matched] > 0).sum()),
                     "matched_share_of_arm": float(matched.sum() / in_arm.sum())})
    return rows


# =========================================================================== doubly robust (sensitivity)

def dr_contributions(actions, A, Y, m_hat) -> np.ndarray:
    """psi_i = m(pi(X_i), X_i) + 1{A_i = pi(X_i)} / e(A_i) * [Y_i - m(A_i, X_i)], e(a) = n_E(a)/N_E.

    m_hat is a frozen TRAIN-fitted response model evaluated on the rows (never fitted on them).
    """
    actions, A, Y = _check(actions, A, Y)
    m_hat = np.asarray(m_hat, dtype=np.float64)
    N = len(A)
    e = np.array([(A == a).sum() / N for a in ARMS])
    idx = np.arange(N)
    return m_hat[idx, actions] + (actions == A) / e[A] * (Y - m_hat[idx, A])


def dr_arm_weights(A) -> dict:
    A = np.asarray(A)
    return {a: float((A == a).sum() / len(A)) for a in ARMS}


def dr_paired_difference(act_p, act_b, A, Y, m_hat, level: float = 0.95) -> dict:
    d = dr_contributions(act_p, A, Y, m_hat) - dr_contributions(act_b, A, Y, m_hat)
    est = float(d.mean())
    if np.array_equal(np.asarray(act_p), np.asarray(act_b)):
        return {"estimate": 0.0, "se": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    se = stratified_se(d, A, dr_arm_weights(A))
    zc = float(stats.norm.ppf(0.5 + level / 2))
    return {"estimate": est, "se": se, "ci_low": est - zc * se, "ci_high": est + zc * se}


# =========================================================================== bootstrap

def paired_bootstrap(C: np.ndarray, A, B: int, rng: np.random.Generator, arm_weights=None, batch: int = 250) -> np.ndarray:
    """Within-arm bootstrap of complete rows. C is (n x P) per-row contributions for P fixed policies.

    Every policy uses the same resampled rows in a replicate (paired); arm sizes are preserved;
    models and actions are fixed. Returns a (B x P) matrix of replicate values.
    """
    C = np.asarray(C, dtype=np.float64)
    A = np.asarray(A)
    w = arm_weights or {a: 1.0 for a in ARMS}
    out = np.zeros((B, C.shape[1]))
    for a in ARMS:
        Ca = C[A == a]
        n = len(Ca)
        for start in range(0, B, batch):
            b = min(batch, B - start)
            out[start:start + b] += w[a] * (resample_counts(n, b, rng) @ Ca) / n
    return out


def percentile_ci(x: np.ndarray, level: float = 0.95) -> tuple[float, float]:
    lo, hi = np.percentile(x, [50 * (1 - level), 100 - 50 * (1 - level)])
    return float(lo), float(hi)


# =========================================================================== profile-cluster sensitivity

def cluster_se_difference(d, A, clusters) -> dict:
    """Sandwich SE of sum_a mean_a(d) clustering on hypothetical pre-treatment profile groups.

    u_i = (d_i - mean_{A_i}(d)) / n_{A_i}; Var = sum_g (sum_{i in g} u_i)^2. The same formula with
    singleton clusters is reported for a like-for-like ratio. No small-sample correction.
    """
    d, A, clusters = np.asarray(d, float), np.asarray(A), np.asarray(clusters)
    u = np.zeros(len(d))
    for a in ARMS:
        m = A == a
        u[m] = (d[m] - d[m].mean()) / m.sum()
    _, inv = np.unique(clusters, return_inverse=True)
    sums = np.bincount(inv, weights=u)
    se_c = float(np.sqrt(np.sum(sums ** 2)))
    se_1 = float(np.sqrt(np.sum(u ** 2)))
    return {"se_clustered": se_c, "se_singleton": se_1, "ratio": se_c / se_1 if se_1 > 0 else np.nan,
            "n_clusters": int(len(sums))}


# =========================================================================== decision rules

DECISION_TEXT = {
    "meaningful_gain": "Meaningful gain versus the frozen comparator (CI lower bound > delta)",
    "worse": "Evidence the targeting policy is worse than the comparator (CI upper bound < 0)",
    "detectable_gain_below_margin": "Statistically detectable gain smaller than delta (0 < lower, upper < delta); practical requirement not met",
    "excludes_margin": "Evidence excludes a gain as large as delta (upper < delta); not proof of zero effect",
    "positive_margin_unresolved": "Positive difference but delta not established (lower in (0, delta]); insufficient evidence to justify personalization",
    "insufficient": "Insufficient evidence: the interval includes both zero and delta",
}


def decision_category(ci_low: float, ci_high: float, delta: float) -> str:
    if ci_low > delta:
        return "meaningful_gain"
    if ci_high < 0:
        return "worse"
    if ci_low > 0 and ci_high < delta:
        return "detectable_gain_below_margin"
    if ci_high < delta:
        return "excludes_margin"
    if ci_low > 0:
        return "positive_margin_unresolved"
    return "insufficient"


def constant_family_bounds(diffs: dict, delta: float, alpha: float = 0.05) -> dict:
    """One-sided Bonferroni lower bounds for Delta(pi*, c), c in {0, M, W} (approximate, large-sample)."""
    m = len(diffs)
    z = float(stats.norm.ppf(1 - alpha / m))
    bounds = {k: v["estimate"] - z * v["se"] for k, v in diffs.items()}
    return {"z": z, "family_size": m, "alpha": alpha, "lower_bounds": bounds,
            "beats_constant_family": all(b > 0 for b in bounds.values()),
            "worthwhile_gain_over_family": all(b > delta for b in bounds.values())}


# =========================================================================== validation selection

def select_constant(values: dict, tie_order, tol: float) -> dict:
    best = max(values.values())
    eligible = [a for a in tie_order if values[a] >= best - tol]
    return {"selected": int(eligible[0]), "values": {int(k): float(v) for k, v in values.items()},
            "rule": f"max VALIDATION IPW value; ties within {tol} prefer order {list(tie_order)}"}


def select_targeting(candidates: dict, A, Y, order) -> dict:
    """Best validation value; every candidate within one paired SE of it is eligible; pick the simplest."""
    values = {k: ipw_value(v, A, Y) for k, v in candidates.items()}
    best = max(values, key=lambda k: (values[k], -order.index(k)))
    log = []
    for name in order:
        if name not in candidates:
            continue
        pdiff = paired_difference(candidates[best], candidates[name], A, Y)
        gap = values[best] - values[name]
        eligible = name == best or gap <= pdiff["se"]
        log.append({"candidate": name, "validation_value": values[name], "gap_to_best": gap,
                    "paired_se_vs_best": pdiff["se"], "status": pdiff["status"], "eligible_within_one_se": bool(eligible)})
    selected = next(r["candidate"] for r in log if r["eligible_within_one_se"])
    return {"selected": selected, "best_by_value": best, "log": log,
            "rule": "within one paired SE of the best VALIDATION value; prefer fixed_rule, then s_learner, then t_learner"}
