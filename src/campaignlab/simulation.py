"""Known-truth SYNTHETIC validation of the estimators and the selection/evaluation pipeline.

Every number produced here comes from simulated data with known potential-outcome probabilities.
Nothing here is a Hillstrom observation or a historical finding.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import expit

from . import evaluation as ev
from . import governance as gov
from . import inference as inf
from . import models as md
from . import policy as pl
from .config import TABLES_DIR, rng_for

SCENARIOS = ["no_effect", "constant_effects", "sign_changing_heterogeneity", "misspecified_response", "broken_allocation"]
COV = ["row_id", "recency", "history", "mens", "womens", "newbie", "channel", "zip_code"]


def draw_X(rng: np.random.Generator, n: int) -> pd.DataFrame:
    """Synthetic pre-treatment covariates loosely shaped like the source fields (no row has mens=womens=0)."""
    prof = rng.choice(3, size=n, p=[0.45, 0.45, 0.10])  # mens only, womens only, both
    return pd.DataFrame({
        "row_id": [f"sim:{i}" for i in range(n)],
        "recency": rng.integers(1, 13, n),
        "history": np.round(np.clip(rng.lognormal(5.0, 0.9, n), 29.99, 3500), 2),
        "mens": (prof != 1).astype(int), "womens": (prof != 0).astype(int),
        "newbie": rng.integers(0, 2, n),
        "channel": rng.choice(["Phone", "Web", "Multichannel"], n, p=[0.44, 0.44, 0.12]),
        "zip_code": rng.choice(["Urban", "Surburban", "Rural"], n, p=[0.40, 0.45, 0.15]),
    })


def true_probs(scenario: str, X: pd.DataFrame) -> np.ndarray:
    """Known potential-response probabilities p_a(X) for a = 0, M, W (n x 3)."""
    lh = np.log1p(X["history"].to_numpy())
    rec = X["recency"].to_numpy()
    mens, womens, newbie = X["mens"].to_numpy(), X["womens"].to_numpy(), X["newbie"].to_numpy()
    web = (X["channel"] == "Web").to_numpy()
    base = expit(-2.3 + 0.18 * (lh - 5) - 0.05 * (rec - 6) + 0.25 * web)
    if scenario == "no_effect":
        return np.column_stack([base, base, base])
    if scenario in ("constant_effects", "broken_allocation"):
        return np.column_stack([base, np.clip(base + 0.07, 0, 1), np.clip(base + 0.045, 0, 1)])
    if scenario == "sign_changing_heterogeneity":
        pm = np.clip(base + 0.08 * mens - 0.03 * (1 - mens), 0, 1)
        pw = np.clip(base + 0.08 * womens - 0.03 * (1 - womens), 0, 1)
        return np.column_stack([base, pm, pw])
    if scenario == "misspecified_response":
        nl = expit(-2.3 + 0.6 * np.sin(rec) + 0.4 * (lh - 5) ** 2 * newbie - 0.3 * (lh - 5))
        pm = np.clip(nl + 0.06 * (rec <= 3) + 0.02, 0, 1)
        pw = np.clip(nl + 0.06 * (rec > 9) * womens + 0.01, 0, 1)
        return np.column_stack([nl, pm, pw])
    raise ValueError(scenario)


def assign(scenario: str, X: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """Complete randomization with nominal thirds; 'broken_allocation' makes M more likely at high history."""
    n = len(X)
    if scenario != "broken_allocation":
        A = np.repeat([0, 1, 2], [n // 3, n // 3, n - 2 * (n // 3)])
        rng.shuffle(A)
        return A
    hi = (np.log1p(X["history"].to_numpy()) > 5.3).astype(float)
    p = np.column_stack([1 / 3 - 0.12 * hi, 1 / 3 + 0.24 * hi, 1 / 3 - 0.12 * hi])
    u = rng.random(n)[:, None]
    return (u > np.cumsum(p, axis=1)).sum(axis=1)


def policy_value_truth(scenario: str, X: pd.DataFrame, actions: np.ndarray) -> float:
    p = true_probs(scenario, X)
    return float(p[np.arange(len(X)), actions].mean())


# =========================================================================== estimator validation

def estimator_validation(cfg: dict, reps: int, n: int, rng: np.random.Generator, truth_X: pd.DataFrame) -> pd.DataFrame:
    zc = stats.norm.ppf(0.975)
    rows = []
    for scen in SCENARIOS:
        P = true_probs(scen, truth_X)
        truth = {"ATE M-0": float((P[:, 1] - P[:, 0]).mean()), "ATE W-0": float((P[:, 2] - P[:, 0]).mean())}
        rule_truth = policy_value_truth(scen, truth_X, pl.fixed_rule_actions(truth_X[COV]))
        truth["IPW rule - constM"] = rule_truth - float(P[:, 1].mean())
        truth["DR(bad model) rule - constM"] = truth["IPW rule - constM"]
        truth["HT nominal rule - constM"] = truth["IPW rule - constM"]
        rec = {k: {"est": [], "se": [], "cover": [], "reject": []} for k in truth}
        holm_any = []
        for _ in range(reps):
            X = draw_X(rng, n)
            p = true_probs(scen, X)
            A = assign(scen, X, rng)
            Y = (rng.random(n) < p[np.arange(n), A]).astype(float)
            pvals = []
            for key, t in (("ATE M-0", 1), ("ATE W-0", 2)):
                r = inf.mean_difference(Y[A == t], Y[A == 0])
                _store(rec[key], r["estimate"], r["se"], truth[key], zc)
                pvals.append(r["p_value"])
            holm_any.append(bool((inf.holm(pvals) < 0.05).any()))
            rule = pl.fixed_rule_actions(X[COV])
            cm = np.full(n, 1)
            d = ev.paired_difference(rule, cm, A, Y)
            _store(rec["IPW rule - constM"], d["estimate"], d["se"], truth["IPW rule - constM"], zc)
            dr = ev.dr_paired_difference(rule, cm, A, Y, np.full((n, 3), 0.3))
            _store(rec["DR(bad model) rule - constM"], dr["estimate"], dr["se"], truth["DR(bad model) rule - constM"], zc)
            ht = ev.ht_paired_difference(rule, cm, A, Y)
            _store(rec["HT nominal rule - constM"], ht["estimate"], ht["se"], truth["HT nominal rule - constM"], zc)
        for key, r in rec.items():
            est, se, cover = np.array(r["est"]), np.array(r["se"]), np.array(r["cover"])
            cov_rate = float(cover.mean())
            row = {"scenario": scen, "estimand": key, "repetitions": reps, "n_per_rep": n, "true_value": truth[key],
                   "mean_estimate": float(est.mean()), "bias": float(est.mean() - truth[key]),
                   "bias_mc_se": float(est.std(ddof=1) / np.sqrt(reps)),
                   "bias_z": float((est.mean() - truth[key]) / (est.std(ddof=1) / np.sqrt(reps))), "empirical_sd": float(est.std(ddof=1)),
                   "mean_reported_se": float(se.mean()), "coverage_95": cov_rate, "coverage_mc_se": float(np.sqrt(cov_rate * (1 - cov_rate) / reps)),
                   "rejection_rate_two_sided_5pct": float(np.mean(r["reject"]))}
            lo, hi = cfg["simulation"]["coverage_diagnostic_range"]
            row["coverage_in_diagnostic_range"] = bool(lo <= cov_rate <= hi)
            row["bias_detected_abs_z_gt_3"] = bool(abs(row["bias_z"]) > 3)
            if scen != "broken_allocation":
                row["expected"] = "nominal behavior expected"
            elif key == "ATE W-0":
                row["expected"] = "allocation broken, but W and control are distorted equally: unbiased expected"
            else:
                row["expected"] = "bias expected (men's-arm assignment depends on history)"
            if key.startswith("ATE") and scen == "no_effect":
                row["primary_family_holm_fwer"] = float(np.mean(holm_any))
            rows.append(row)
    out = pd.DataFrame(rows)
    out.insert(0, "label", "SYNTHETIC known-truth simulation (not Hillstrom data)")
    return out


def _store(rec, est, se, truth, zc):
    rec["est"].append(est)
    rec["se"].append(se)
    rec["cover"].append(abs(est - truth) <= zc * se)
    rec["reject"].append(abs(est) > zc * se if se > 0 else False)


# =========================================================================== whole-pipeline validation

def pipeline_validation(cfg: dict, reps: int, n: int, rng: np.random.Generator, truth_X: pd.DataFrame) -> pd.DataFrame:
    """Refit the whole TRAIN->VALIDATION->TEST procedure on fresh synthetic data each repetition."""
    zc = stats.norm.ppf(0.975)
    rows = []
    for scen in ("no_effect", "sign_changing_heterogeneity"):
        P = true_probs(scen, truth_X)
        for r in range(reps):
            X = draw_X(rng, n)
            p = true_probs(scen, X)
            A = assign(scen, X, rng)
            Y = (rng.random(n) < p[np.arange(n), A]).astype(int)
            part = np.empty(n, dtype=object)
            for a in (0, 1, 2):
                idx = np.flatnonzero(A == a)
                idx = idx[rng.permutation(len(idx))]
                k1, k2 = (len(idx) * 60) // 100, (len(idx) * 80) // 100
                part[idx[:k1]], part[idx[k1:k2]], part[idx[k2:]] = "TRAIN", "VALIDATION", "TEST"
            tr, va, te = (part == "TRAIN"), (part == "VALIDATION"), (part == "TEST")
            Xtr, Xva, Xte = X[tr].reset_index(drop=True), X[va].reset_index(drop=True), X[te].reset_index(drop=True)
            folds = md.cv_folds(A[tr], 3, int(rng.integers(0, 2**31 - 1)))
            _, summ = md.cross_validate("s_learner", Xtr[COV], A[tr], Y[tr], cfg["models"]["C_grid"], folds, cfg)
            C = md.select_C(summ, cfg["models"]["tie_tolerance"])
            s = md.SLearner(cfg, C).fit(Xtr[COV], A[tr], Y[tr])
            cands_va = {"fixed_rule": pl.fixed_rule_actions(Xva[COV]), "s_learner": pl.best_gain_actions(s.predict_all(Xva[COV]), 0.0)[0]}
            consts = {a: ev.ipw_value(np.full(va.sum(), a), A[va], Y[va]) for a in (0, 1, 2)}
            cstar = ev.select_constant(consts, [0, 1, 2], 1e-6)["selected"]
            sel = ev.select_targeting(cands_va, A[va], Y[va], ["fixed_rule", "s_learner", "t_learner"])["selected"]
            act_te = pl.fixed_rule_actions(Xte[COV]) if sel == "fixed_rule" else pl.best_gain_actions(s.predict_all(Xte[COV]), 0.0)[0]
            d = ev.paired_difference(act_te, np.full(te.sum(), cstar), A[te], Y[te])
            # truth: superpopulation value of the SELECTED (fixed after selection) policy minus the selected constant
            act_truth = (pl.fixed_rule_actions(truth_X[COV]) if sel == "fixed_rule"
                         else pl.best_gain_actions(s.predict_all(truth_X[COV]), 0.0)[0])
            true_delta = float(P[np.arange(len(truth_X)), act_truth].mean() - P[:, cstar].mean())
            rows.append({"scenario": scen, "rep": r, "selected_policy": sel, "selected_constant": int(cstar), "C": C,
                         "estimate": d["estimate"], "se": d["se"], "true_delta_selected_policy": true_delta,
                         "covered": bool(abs(d["estimate"] - true_delta) <= zc * d["se"]) if d["se"] > 0 else d["estimate"] == true_delta,
                         "best_possible_delta": float(P.max(axis=1).mean() - P[:, 1:].mean(axis=0).max())})
    df = pd.DataFrame(rows)
    summary = df.groupby("scenario").agg(repetitions=("rep", "size"), share_selected_s_learner=("selected_policy", lambda s: float((s == "s_learner").mean())),
                                         mean_estimate=("estimate", "mean"), mean_true_delta=("true_delta_selected_policy", "mean"),
                                         coverage_95=("covered", "mean"), best_possible_delta=("best_possible_delta", "mean")).reset_index()
    summary["bias"] = summary["mean_estimate"] - summary["mean_true_delta"]
    summary["coverage_mc_se"] = np.sqrt(summary["coverage_95"] * (1 - summary["coverage_95"]) / summary["repetitions"])
    summary["n_per_rep"] = n
    summary.insert(0, "label", "SYNTHETIC whole-pipeline simulation (fixed-after-selection policy value; not Hillstrom data)")
    return summary


def run(cfg: dict) -> None:
    t0 = time.perf_counter()
    sim = cfg["simulation"]
    rng = rng_for(cfg, "simulation")
    truth_X = draw_X(rng, 400_000)
    est = estimator_validation(cfg, sim["repetitions"], sim["n_per_rep"], rng, truth_X)
    out = TABLES_DIR / "simulation"
    out.mkdir(parents=True, exist_ok=True)
    est.to_csv(out / "estimator_validation.csv", index=False, lineterminator="\n")
    pipe = pipeline_validation(cfg, sim["pipeline_repetitions"], 12000, rng, truth_X)
    pipe.to_csv(out / "pipeline_validation.csv", index=False, lineterminator="\n")
    gov.write_json(out / "simulation_meta.json", {
        "label": "SYNTHETIC", "truth_population_draws": 400000, "estimator_repetitions": sim["repetitions"], "n_per_rep": sim["n_per_rep"],
        "pipeline_repetitions_per_scenario": sim["pipeline_repetitions"], "pipeline_n_per_rep": 12000, "seed_stream": "simulation",
        "coverage_diagnostic_range": sim["coverage_diagnostic_range"],
        "truth_note": "Superpopulation truth averaged over 400,000 synthetic covariate draws; its Monte Carlo error is far below the per-rep SE.",
        "runtime_seconds": round(time.perf_counter() - t0, 1)})
