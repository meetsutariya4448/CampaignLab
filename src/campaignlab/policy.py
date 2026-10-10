"""Policy action rules. Action codes: 0 = no email, 1 = Mens E-Mail (M), 2 = Womens E-Mail (W).

Action functions receive only pre-treatment covariates, row IDs, frozen model predictions and the
frozen q/kappa parameters. They never receive the observed arm or any outcome.
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np
import pandas as pd

from .governance import hash_strings
from .models import assert_covariates_only


def capacity_count(q: float, n: int) -> int:
    """floor(q * n) computed exactly (q is a decimal grid value)."""
    return int(Fraction(str(q)) * n // 1)


def constant_actions(n: int, action: int) -> np.ndarray:
    return np.full(n, int(action), dtype=np.int8)


def fixed_rule_actions(cov: pd.DataFrame) -> np.ndarray:
    """Frozen historical-purchase rule: M if mens only, W if womens only, otherwise no email.

    mens/womens record prior merchandise purchases, not customer gender.
    """
    assert_covariates_only(cov)
    mens, womens = cov["mens"].to_numpy(), cov["womens"].to_numpy()
    out = np.zeros(len(cov), dtype=np.int8)
    out[(mens == 1) & (womens == 0)] = 1
    out[(mens == 0) & (womens == 1)] = 2
    return out


def best_gain_actions(m_hat: np.ndarray, kappa: float) -> tuple[np.ndarray, np.ndarray]:
    """g(a,X) = m(a,X) - m(0,X) - kappa. Largest strictly positive gain wins, else no email.

    Exact ties: no email first (a zero gain is not positive), then M before W.
    """
    m_hat = np.asarray(m_hat, dtype=np.float64)
    g_m = m_hat[:, 1] - m_hat[:, 0] - kappa
    g_w = m_hat[:, 2] - m_hat[:, 0] - kappa
    best = np.where(g_w > g_m, 2, 1).astype(np.int8)
    best_gain = np.maximum(g_m, g_w)
    actions = np.where(best_gain > 0, best, 0).astype(np.int8)
    return actions, np.where(actions > 0, best_gain, 0.0)


def _rank_keys(row_ids, template: str) -> np.ndarray:
    return np.asarray(hash_strings([template.format(row_id=r) for r in row_ids]), dtype="U64")


def capacity_limit(actions: np.ndarray, gains: np.ndarray, row_ids, q: float, tiebreak_template: str) -> np.ndarray:
    """Contact at most floor(qN) rows with positive gain, by gain descending then ascending ID hash."""
    actions = np.asarray(actions).copy()
    cap = capacity_count(q, len(actions))
    contacted = np.flatnonzero(actions > 0)
    if len(contacted) <= cap:
        return actions
    keys = _rank_keys(np.asarray(row_ids, dtype=object)[contacted], tiebreak_template)
    order = np.lexsort((keys, -np.asarray(gains)[contacted]))
    actions[contacted[order[cap:]]] = 0
    return actions


def hash_quota_actions(row_ids, q: float, action: int, baseline_template: str) -> np.ndarray:
    """Feature-independent quota baseline: the first floor(qN) rows by baseline hash get `action`."""
    n = len(row_ids)
    cap = capacity_count(q, n)
    keys = _rank_keys(row_ids, baseline_template)
    out = np.zeros(n, dtype=np.int8)
    out[np.argsort(keys, kind="stable")[:cap]] = action
    return out


def hash_cap(actions: np.ndarray, row_ids, q: float, baseline_template: str) -> np.ndarray:
    """Cap a fixed (non-scored) policy at floor(qN) contacts, keeping contacted rows in baseline-hash order."""
    actions = np.asarray(actions).copy()
    cap = capacity_count(q, len(actions))
    contacted = np.flatnonzero(actions > 0)
    if len(contacted) <= cap:
        return actions
    keys = _rank_keys(np.asarray(row_ids, dtype=object)[contacted], baseline_template)
    actions[contacted[np.argsort(keys, kind="stable")[cap:]]] = 0
    return actions


# =========================================================================== policy sets

def main_policy_actions(cov: pd.DataFrame, predictions: dict[str, np.ndarray], cfg: dict) -> dict[str, np.ndarray]:
    """All q=1, kappa=0 policies: three constants, fixed rule and each available learner."""
    assert_covariates_only(cov)
    n = len(cov)
    out = {"const_0": constant_actions(n, 0), "const_M": constant_actions(n, 1), "const_W": constant_actions(n, 2),
           "fixed_rule": fixed_rule_actions(cov)}
    kappa = cfg["policy"]["main"]["kappa"]
    for name, m_hat in predictions.items():
        acts, gains = best_gain_actions(m_hat, kappa)
        out[name] = capacity_limit(acts, gains, cov["row_id"], cfg["policy"]["main"]["q"], cfg["policy"]["tiebreak_key_template"])
    return out


def scenario_policy_actions(cov: pd.DataFrame, predictions: dict[str, np.ndarray], cfg: dict) -> dict[str, np.ndarray]:
    """Frozen capacity/cost grid. Keys: '<policy>|q=<q>|kappa=<kappa>' (baselines do not depend on kappa)."""
    assert_covariates_only(cov)
    pol = cfg["policy"]
    row_ids = cov["row_id"]
    rule = fixed_rule_actions(cov)
    out = {}
    for q in pol["q_grid"]:
        out[f"const_0|q={q}|kappa=any"] = constant_actions(len(cov), 0)
        out[f"quota_M|q={q}|kappa=any"] = hash_quota_actions(row_ids, q, 1, pol["baseline_key_template"])
        out[f"quota_W|q={q}|kappa=any"] = hash_quota_actions(row_ids, q, 2, pol["baseline_key_template"])
        out[f"fixed_rule|q={q}|kappa=any"] = hash_cap(rule, row_ids, q, pol["baseline_key_template"])
        for name, m_hat in predictions.items():
            for kappa in pol["kappa_grid"]:
                acts, gains = best_gain_actions(m_hat, kappa)
                out[f"{name}|q={q}|kappa={kappa}"] = capacity_limit(acts, gains, row_ids, q, pol["tiebreak_key_template"])
    return out
