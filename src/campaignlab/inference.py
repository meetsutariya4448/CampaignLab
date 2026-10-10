"""Experimental (ITT) inference for the three-arm design.

Every function takes an explicitly scoped sample. None of them selects policies or decides
which estimator is primary: the unadjusted difference in means is always the primary result.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import confint_proportions_2indep, proportion_confint

from .config import ARM_NAMES, ARM_SHORT

Z95 = float(stats.norm.ppf(0.975))  # 1.959964
UNITS = {
    "visit": "probability (risk difference); x100 = percentage points",
    "conversion": "probability (risk difference); x100 = percentage points",
    "spend": "USD gross spend per assigned customer (as recorded, 2008)",
    "spend_winsor_all": "USD per assigned customer, winsorized (sensitivity estimand)",
    "spend_winsor_positive": "USD per assigned customer, winsorized (sensitivity estimand)",
}


class RankDeficiencyError(ValueError):
    pass


# =========================================================================== core estimator

def mean_difference(y_t, y_c, level: float = 0.95) -> dict:
    """Difference in means with the conservative/large-sample SE sqrt(s_t^2/n_t + s_c^2/n_c) (n-1 variances).

    Degenerate inputs return an explicit status instead of dividing by zero.
    """
    y_t = np.asarray(y_t, dtype=float)
    y_c = np.asarray(y_c, dtype=float)
    n_t, n_c = len(y_t), len(y_c)
    out = {"n_treat": n_t, "n_control": n_c,
           "mean_treat": float(y_t.mean()) if n_t else np.nan,
           "mean_control": float(y_c.mean()) if n_c else np.nan}
    out["estimate"] = out["mean_treat"] - out["mean_control"]
    nan = {"se": np.nan, "z": np.nan, "p_value": np.nan, "ci_low": np.nan, "ci_high": np.nan}
    if n_t < 2 or n_c < 2:
        return {**out, **nan, "status": "insufficient_n"}
    var_t, var_c = float(y_t.var(ddof=1)), float(y_c.var(ddof=1))
    se = float(np.sqrt(var_t / n_t + var_c / n_c))
    out.update(var_treat=var_t, var_control=var_c)
    if se == 0.0:
        return {**out, **nan, "status": "degenerate_zero_variance"}
    z_crit = float(stats.norm.ppf(0.5 + level / 2))
    z = out["estimate"] / se
    return {**out, "se": se, "z": z, "p_value": float(2 * stats.norm.sf(abs(z))),
            "ci_low": out["estimate"] - z_crit * se, "ci_high": out["estimate"] + z_crit * se, "status": "ok"}


def holm(pvalues, alpha: float = 0.05) -> np.ndarray:
    """Holm step-down adjusted p-values (statsmodels method='holm', not its Holm-Sidak default)."""
    p = np.asarray(pvalues, dtype=float)
    if np.isnan(p).any():
        raise ValueError("Holm adjustment requires valid p-values for every family member")
    return multipletests(p, alpha=alpha, method="holm")[1]


def bonferroni_interval(estimate: float, se: float, family_size: int, alpha: float = 0.05) -> tuple[float, float, float]:
    """Two-sided simultaneous Bonferroni interval; returns (low, high, two-sided level)."""
    z = float(stats.norm.ppf(1 - alpha / (2 * family_size)))
    return estimate - z * se, estimate + z * se, 1 - alpha / family_size


def wilson_interval(events: int, n: int, level: float = 0.95) -> tuple[float, float]:
    lo, hi = proportion_confint(events, n, alpha=1 - level, method="wilson")
    return float(lo), float(hi)


def newcombe_interval(events_t: int, n_t: int, events_c: int, n_c: int, level: float = 0.95) -> tuple[float, float]:
    lo, hi = confint_proportions_2indep(events_t, n_t, events_c, n_c, method="newcomb", compare="diff", alpha=1 - level)
    return float(lo), float(hi)


# =========================================================================== tables

def arm_summary(df: pd.DataFrame, scope: str, outcomes=("visit", "conversion", "spend")) -> pd.DataFrame:
    rows = []
    for a in (0, 1, 2):
        sub = df[df["arm"] == a]
        n = len(sub)
        r = {"sample_scope": scope, "arm": ARM_NAMES[a], "n": n}
        for o in outcomes:
            y = sub[o].to_numpy(float)
            r[f"{o}_mean"] = float(y.mean())
            r[f"{o}_sd"] = float(y.std(ddof=1))
            if o in ("visit", "conversion"):
                k = int(y.sum())
                lo, hi = wilson_interval(k, n)
                r[f"{o}_events"], r[f"{o}_wilson_low"], r[f"{o}_wilson_high"] = k, lo, hi
            else:
                r["spend_positive_rows"] = int((y > 0).sum())
                r["spend_total"] = round(float(y.sum()), 2)
        rows.append(r)
    return pd.DataFrame(rows)


def contrast_rows(df: pd.DataFrame, outcome: str, contrasts, scope: str, dataset_sha: str, family: str) -> list[dict]:
    rows = []
    for t, c in contrasts:
        y = df[outcome].to_numpy(float)
        r = mean_difference(y[df["arm"].to_numpy() == t], y[df["arm"].to_numpy() == c])
        is_binary = outcome in ("visit", "conversion")
        rows.append({
            "dataset_sha256": dataset_sha, "sample_scope": scope, "N": int(len(df)), "outcome": outcome,
            "window": "two-week follow-up", "contrast": f"{ARM_SHORT[t]} - {ARM_SHORT[c]}",
            "contrast_label": f"{ARM_NAMES[t]} minus {ARM_NAMES[c]}", "family": family,
            "n_treat": r["n_treat"], "n_control": r["n_control"],
            "events_treat": int(y[df["arm"].to_numpy() == t].sum()) if is_binary else int((y[df["arm"].to_numpy() == t] > 0).sum()),
            "events_control": int(y[df["arm"].to_numpy() == c].sum()) if is_binary else int((y[df["arm"].to_numpy() == c] > 0).sum()),
            "events_definition": "outcome events" if is_binary else "rows with positive spend",
            "mean_treat": r["mean_treat"], "mean_control": r["mean_control"],
            "estimate": r["estimate"], "units": UNITS.get(outcome, outcome),
            "estimate_pp": 100 * r["estimate"] if is_binary else np.nan,
            "se": r["se"], "se_method": "sqrt(s_t^2/n_t + s_c^2/n_c), n-1 variances",
            "ci_low": r["ci_low"], "ci_high": r["ci_high"], "ci_method": "ordinary 95% normal (individual, not multiplicity-adjusted)",
            "ci_low_pp": 100 * r["ci_low"] if is_binary else np.nan, "ci_high_pp": 100 * r["ci_high"] if is_binary else np.nan,
            "z": r["z"], "p_raw": r["p_value"], "status": r["status"],
        })
    return rows


def effect_table(df: pd.DataFrame, cfg: dict, scope: str, dataset_sha: str) -> pd.DataFrame:
    """Primary (Holm, 2) and secondary (Holm, 4) families, plus exploratory W - M, for one scoped sample."""
    inf = cfg["inference"]
    alpha = inf["alpha"]
    code = {"Mens E-Mail": 1, "Womens E-Mail": 2}
    prim = []
    for outcome, arm in inf["primary_family"]["contrasts"]:
        prim += contrast_rows(df, outcome, [(code[arm], 0)], scope, dataset_sha, "primary")
    padj = holm([r["p_raw"] for r in prim], alpha)
    m = inf["simultaneous_interval"]["family_size"]
    for r, pa in zip(prim, padj):
        lo, hi, lvl = bonferroni_interval(r["estimate"], r["se"], m, alpha)
        r.update(p_adj=float(pa), adj_method="Holm step-down (statsmodels method='holm')", adj_family="primary: 2 visit contrasts",
                 simul_ci_low=lo, simul_ci_high=hi, simul_ci_low_pp=100 * lo, simul_ci_high_pp=100 * hi,
                 simul_ci_method=f"Bonferroni simultaneous two-sided {lvl:.1%} (family of {m})",
                 assumption_note="ITT under publisher-described randomization; one independent customer per row assumed")
    sec = []
    for outcome, arm in inf["secondary_family"]["contrasts"]:
        sec += contrast_rows(df, outcome, [(code[arm], 0)], scope, dataset_sha, "secondary")
    padj = holm([r["p_raw"] for r in sec], alpha)
    for r, pa in zip(sec, padj):
        r.update(p_adj=float(pa), adj_method="Holm step-down (transparency aid)", adj_family="secondary: 4 conversion/spend contrasts",
                 simul_ci_low=np.nan, simul_ci_high=np.nan, simul_ci_low_pp=np.nan, simul_ci_high_pp=np.nan,
                 simul_ci_method="not computed (secondary)",
                 assumption_note="Secondary; sparse purchases (zeros retained); gross spend is not margin or profit")
    expl = []
    for outcome in ("visit", "conversion", "spend"):
        expl += contrast_rows(df, outcome, [(2, 1)], scope, dataset_sha, "exploratory")
    for r in expl:
        r.update(p_adj=np.nan, adj_method="none (descriptive)", adj_family="exploratory W - M",
                 simul_ci_low=np.nan, simul_ci_high=np.nan, simul_ci_low_pp=np.nan, simul_ci_high_pp=np.nan,
                 simul_ci_method="not computed (exploratory)", assumption_note="Descriptive women's-vs-men's contrast; not a planned primary test")
    return pd.DataFrame(prim + sec + expl)


def allocation_table(arm: np.ndarray, scope: str) -> pd.DataFrame:
    n = len(arm)
    rows = []
    for a in (0, 1, 2):
        k = int((arm == a).sum())
        rows.append({"sample_scope": scope, "arm": ARM_NAMES[a], "n": k, "fraction": k / n, "nominal_fraction": 1 / 3,
                     "deviation_from_nominal_rows": k - n / 3, "deviation_from_nominal_pp": 100 * (k / n - 1 / 3)})
    return pd.DataFrame(rows)


# =========================================================================== balance

def balance_features(cov: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "recency": cov["recency"].astype(float),
        "history": cov["history"].astype(float),
        "log_history": np.log1p(cov["history"].astype(float)),
        "mens": cov["mens"].astype(float), "womens": cov["womens"].astype(float), "newbie": cov["newbie"].astype(float),
    })
    for lvl in ("Phone", "Web", "Multichannel"):
        out[f"channel_{lvl}"] = (cov["channel"] == lvl).astype(float)
    for lvl in ("Rural", "Urban", "Surburban"):
        out[f"zip_{lvl}"] = (cov["zip_code"] == lvl).astype(float)
    return out


def balance_table(cov: pd.DataFrame, arm: np.ndarray, scope: str) -> pd.DataFrame:
    """Pairwise SMD = (mean_a - mean_b) / sqrt((s_a^2 + s_b^2)/2) for all three arm pairs."""
    feats = balance_features(cov)
    rows = []
    for a, b in ((1, 0), (2, 0), (2, 1)):
        fa, fb = feats[arm == a], feats[arm == b]
        for col in feats.columns:
            ma, mb = float(fa[col].mean()), float(fb[col].mean())
            va, vb = float(fa[col].var(ddof=1)), float(fb[col].var(ddof=1))
            pooled = np.sqrt((va + vb) / 2)
            smd = (ma - mb) / pooled if pooled > 0 else np.nan
            rows.append({"sample_scope": scope, "comparison": f"{ARM_SHORT[a]} vs {ARM_SHORT[b]}", "feature": col,
                         "feature_type": "numeric" if col in ("recency", "history", "log_history") else "indicator/level share",
                         "mean_a": ma, "mean_b": mb, "sd_a": float(np.sqrt(va)), "sd_b": float(np.sqrt(vb)),
                         "raw_difference": ma - mb, "smd": smd, "abs_smd": abs(smd) if pooled > 0 else np.nan,
                         "status": "ok" if pooled > 0 else "invariant (pooled SD = 0); raw difference shown",
                         "in_model_basis": col not in ("history", "channel_Phone", "zip_Rural"),
                         "exceeds_0.1_reference": bool(pooled > 0 and abs(smd) > 0.1)})
    return pd.DataFrame(rows)


# =========================================================================== covariate adjustment

BASIS = ["recency", "log_history", "mens", "womens", "newbie", "channel_Web", "channel_Multichannel", "zip_Urban", "zip_Surburban"]


def raw_basis(cov: pd.DataFrame) -> pd.DataFrame:
    """Nine-column basis without scaling (used for OLS adjustment, centered by the caller)."""
    f = balance_features(cov)
    return f[BASIS]


def interacted_design(arm: np.ndarray, basis: pd.DataFrame, center=None) -> tuple[np.ndarray, list[str], np.ndarray]:
    center = basis.mean().to_numpy() if center is None else np.asarray(center)
    xc = basis.to_numpy(float) - center
    dm = (arm == 1).astype(float)[:, None]
    dw = (arm == 2).astype(float)[:, None]
    X = np.hstack([np.ones((len(arm), 1)), dm, dw, xc, dm * xc, dw * xc])
    names = (["const", "arm_M", "arm_W"] + [f"x_{c}" for c in basis.columns]
             + [f"M_x_{c}" for c in basis.columns] + [f"W_x_{c}" for c in basis.columns])
    return X, names, center


def check_design(X: np.ndarray) -> dict:
    rank = int(np.linalg.matrix_rank(X))
    if rank < X.shape[1]:
        raise RankDeficiencyError(f"design matrix rank {rank} < {X.shape[1]} columns")
    return {"rank": rank, "columns": int(X.shape[1]), "condition_number": float(np.linalg.cond(X))}


def ols_contrasts(y: np.ndarray, X: np.ndarray, cov_type: str, groups=None) -> dict:
    model = sm.OLS(np.asarray(y, float), X)
    if cov_type == "cluster":
        res = model.fit(cov_type="cluster", cov_kwds={"groups": groups}, use_t=False)
    else:
        res = model.fit(cov_type=cov_type, use_t=False)
    params, cov = np.asarray(res.params), np.asarray(res.cov_params())
    out = {}
    for label, L in (("M - 0", _vec(X.shape[1], {1: 1})), ("W - 0", _vec(X.shape[1], {2: 1})), ("W - M", _vec(X.shape[1], {2: 1, 1: -1}))):
        est = float(L @ params)
        se = float(np.sqrt(L @ cov @ L))
        z = est / se
        out[label] = {"estimate": est, "se": se, "ci_low": est - Z95 * se, "ci_high": est + Z95 * se,
                      "p_value": float(2 * stats.norm.sf(abs(z)))}
    return {"contrasts": out, "result": res}


def _vec(k: int, entries: dict) -> np.ndarray:
    v = np.zeros(k)
    for i, val in entries.items():
        v[i] = val
    return v


def unadjusted_ols(y, arm, cov_type="HC2", groups=None) -> dict:
    X = np.column_stack([np.ones(len(arm)), (arm == 1).astype(float), (arm == 2).astype(float)])
    return ols_contrasts(y, X, cov_type, groups)


def adjusted_table(df: pd.DataFrame, cfg: dict, scope: str, outcomes=("visit", "conversion", "spend")) -> tuple[pd.DataFrame, dict]:
    """Fixed fully interacted, centered OLS (Lin-style) with HC2 (primary adjustment) and HC3 (sensitivity)."""
    arm = df["arm"].to_numpy()
    basis = raw_basis(df)
    X, names, center = interacted_design(arm, basis)
    diag = check_design(X)
    diag.update({"sample_scope": scope, "n": int(len(df)), "centered_on": "analyzed-sample covariate means",
                 "center": dict(zip(basis.columns, map(float, center))), "columns": names})
    rows = []
    joint = {}
    for o in outcomes:
        y = df[o].to_numpy(float)
        unadj = {c: v for c, v in unadjusted_ols(y, arm, "HC2")["contrasts"].items()}
        for cov_type in (cfg["inference"]["ols_covariance"], cfg["inference"]["ols_covariance_sensitivity"]):
            fit = ols_contrasts(y, X, cov_type)
            for label, r in fit["contrasts"].items():
                rows.append({"sample_scope": scope, "N": int(len(df)), "outcome": o, "contrast": label,
                             "specification": "arm + centered 9-column basis + all arm x basis interactions (OLS)",
                             "covariance": cov_type, "role": "adjustment (primary adjustment)" if cov_type == "HC2" else "adjustment sensitivity",
                             "adj_estimate": r["estimate"], "adj_se": r["se"], "adj_ci_low": r["ci_low"], "adj_ci_high": r["ci_high"],
                             "adj_p": r["p_value"], "unadj_estimate": unadj[label]["estimate"], "unadj_se": unadj[label]["se"],
                             "se_ratio_adj_over_unadj": r["se"] / unadj[label]["se"],
                             "estimate_change": r["estimate"] - unadj[label]["estimate"]})
            if o == "visit":
                k = len(BASIS)
                R = np.zeros((2 * k, X.shape[1]))
                for i in range(2 * k):
                    R[i, 3 + k + i] = 1.0
                w = fit["result"].wald_test(R, scalar=True, use_f=False)
                joint[cov_type] = {"statistic": float(w.statistic), "df": 2 * k, "p_value": float(w.pvalue)}
    diag["joint_interaction_test_visit"] = joint
    return pd.DataFrame(rows), diag


def profile_cluster_table(df: pd.DataFrame, profile: np.ndarray, scope: str, outcomes=("visit", "conversion", "spend")) -> pd.DataFrame:
    """Hypothetical dependence sensitivity: cluster on identical seven-field pre-treatment profiles."""
    arm = df["arm"].to_numpy()
    rows = []
    for o in outcomes:
        y = df[o].to_numpy(float)
        base = unadjusted_ols(y, arm, "HC2")["contrasts"]
        cl = unadjusted_ols(y, arm, "cluster", groups=profile)["contrasts"]
        for label in ("M - 0", "W - 0"):
            rows.append({"sample_scope": scope, "outcome": o, "contrast": label, "estimate": base[label]["estimate"],
                         "se_row_independent": base[label]["se"], "se_profile_clustered": cl[label]["se"],
                         "se_ratio": cl[label]["se"] / base[label]["se"],
                         "ci_low_clustered": cl[label]["ci_low"], "ci_high_clustered": cl[label]["ci_high"],
                         "p_clustered": cl[label]["p_value"], "n_profiles": int(len(np.unique(profile))),
                         "note": "Profiles are identical pre-treatment field combinations, NOT verified customers"})
    return pd.DataFrame(rows)


# =========================================================================== resampling

def resample_counts(n: int, size: int, rng: np.random.Generator) -> np.ndarray:
    """Bootstrap multiplicity counts (size x n) from sampling n indices with replacement per replicate."""
    idx = rng.integers(0, n, size=(size, n))
    flat = (idx + (np.arange(size)[:, None] * n)).ravel()
    return np.bincount(flat, minlength=size * n).reshape(size, n)


def stratified_bootstrap_arm_means(y: np.ndarray, arm: np.ndarray, B: int, rng: np.random.Generator, batch: int = 250) -> dict:
    """Within-arm bootstrap (arm sizes fixed). Returns {arm: array of B resampled means}."""
    out = {}
    for a in (0, 1, 2):
        ya = np.asarray(y, float)[arm == a]
        n = len(ya)
        means = np.empty(B)
        for start in range(0, B, batch):
            b = min(batch, B - start)
            means[start:start + b] = resample_counts(n, b, rng) @ ya / n
        out[a] = means
    return out


def bootstrap_table(df: pd.DataFrame, outcome: str, B: int, rng: np.random.Generator, scope: str, batch: int = 250) -> pd.DataFrame:
    arm = df["arm"].to_numpy()
    y = df[outcome].to_numpy(float)
    means = stratified_bootstrap_arm_means(y, arm, B, rng, batch)
    rows = []
    for t, c in ((1, 0), (2, 0)):
        d = means[t] - means[c]
        analytic = mean_difference(y[arm == t], y[arm == c])
        lo, hi = np.percentile(d, [2.5, 97.5])
        rows.append({"sample_scope": scope, "outcome": outcome, "contrast": f"{ARM_SHORT[t]} - {ARM_SHORT[c]}",
                     "estimate": analytic["estimate"], "bootstrap_replicates": B,
                     "bootstrap_ci_low": float(lo), "bootstrap_ci_high": float(hi), "bootstrap_se": float(d.std(ddof=1)),
                     "analytic_ci_low": analytic["ci_low"], "analytic_ci_high": analytic["ci_high"], "analytic_se": analytic["se"],
                     "method": "within-arm stratified bootstrap, percentile 2.5/97.5; replicates are a numerical approximation, not extra customers"})
    return pd.DataFrame(rows)


def permutation_test_binary(y_t, y_c, draws: int, rng: np.random.Generator) -> dict:
    """Monte Carlo randomization test of the SHARP null (no unit-level effect) for a binary outcome.

    Assumes complete randomization conditional on the observed arm counts. Under that mechanism the
    number of treated events is hypergeometric, which is exactly equivalent to permuting labels.
    """
    y_t = np.asarray(y_t, dtype=np.int64)
    y_c = np.asarray(y_c, dtype=np.int64)
    n_t, n_c = len(y_t), len(y_c)
    K = int(y_t.sum() + y_c.sum())
    N = n_t + n_c
    obs = y_t.sum() / n_t - y_c.sum() / n_c
    k_t = rng.hypergeometric(K, N - K, n_t, size=draws) if 0 < K < N else np.full(draws, int(y_t.sum()))
    stat = k_t / n_t - (K - k_t) / n_c
    extreme = int(np.sum(np.abs(stat) >= abs(obs) - 1e-12))
    return {"observed_difference": float(obs), "draws": draws, "extreme": extreme, "p_value": (extreme + 1) / (draws + 1),
            "null": "sharp null of no effect for any unit", "mechanism": "assumed complete randomization conditional on arm counts"}


def permutation_test_mean_diff(y_t, y_c, draws: int, rng: np.random.Generator) -> dict:
    """Generic label-permutation version (reference implementation used to check the binary shortcut)."""
    y = np.concatenate([np.asarray(y_t, float), np.asarray(y_c, float)])
    n_t = len(y_t)
    obs = float(np.mean(y_t) - np.mean(y_c))
    extreme = 0
    for _ in range(draws):
        perm = rng.permutation(y)
        stat = perm[:n_t].mean() - perm[n_t:].mean()
        extreme += abs(stat) >= abs(obs) - 1e-12
    return {"observed_difference": obs, "draws": draws, "extreme": int(extreme), "p_value": (extreme + 1) / (draws + 1)}


# =========================================================================== heterogeneity

def subgroup_labels(df: pd.DataFrame, grouping: str) -> pd.Series:
    if grouping == "newbie":
        return df["newbie"].map({0: "newbie=0 (existing)", 1: "newbie=1 (new)"})
    if grouping == "purchase_profile":
        return (df["mens"].astype(str) + df["womens"].astype(str)).map({
            "10": "mens only", "01": "womens only", "11": "mens and womens", "00": "neither flag"})
    if grouping == "channel":
        return df["channel"].astype(str)
    raise ValueError(grouping)


def subgroup_table(df: pd.DataFrame, grouping: str, scope: str, min_rows: int, min_visits: int, optional: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    labels = subgroup_labels(df, grouping)
    arm = df["arm"].to_numpy()
    y = df["visit"].to_numpy(float)
    rows = []
    for lvl in sorted(labels.unique()):
        m = (labels == lvl).to_numpy()
        for t in (1, 2):
            r = mean_difference(y[m & (arm == t)], y[m & (arm == 0)])
            ev_t, ev_c = int(y[m & (arm == t)].sum()), int(y[m & (arm == 0)].sum())
            flagged = min(r["n_treat"], r["n_control"]) < min_rows or min(ev_t, ev_c) < min_visits
            rows.append({"sample_scope": scope, "grouping": grouping, "subgroup": lvl, "contrast": f"{ARM_SHORT[t]} - 0",
                         "n_subgroup": int(m.sum()), "n_treat": r["n_treat"], "n_control": r["n_control"],
                         "visits_treat": ev_t, "visits_control": ev_c, "rate_treat": r["mean_treat"], "rate_control": r["mean_control"],
                         "estimate": r["estimate"], "estimate_pp": 100 * r["estimate"], "se": r["se"],
                         "ci_low": r["ci_low"], "ci_high": r["ci_high"], "ci_low_pp": 100 * r["ci_low"], "ci_high_pp": 100 * r["ci_high"],
                         "p_raw_uncorrected": r["p_value"], "support_flag": bool(flagged),
                         "label": "exploratory (optional grouping)" if optional else "exploratory (prespecified grouping)"})
    sub = pd.DataFrame(rows)
    het = []
    for contrast, g in sub.groupby("contrast"):
        g = g[np.isfinite(g["se"]) & (g["se"] > 0)]
        w = 1 / g["se"] ** 2
        pooled = float((w * g["estimate"]).sum() / w.sum())
        Q = float((w * (g["estimate"] - pooled) ** 2).sum())
        dfree = len(g) - 1
        rec = {"sample_scope": scope, "grouping": grouping, "contrast": contrast, "levels": len(g), "Q_statistic": Q, "df": dfree,
               "p_value": float(stats.chi2.sf(Q, dfree)) if dfree > 0 else np.nan,
               "test": "Wald test of equal subgroup effects (independent subgroups); exploratory"}
        if len(g) == 2:
            a, b = g.iloc[1], g.iloc[0]
            diff = a["estimate"] - b["estimate"]
            se = float(np.sqrt(a["se"] ** 2 + b["se"] ** 2))
            rec.update(difference_label=f"[{a['subgroup']}] - [{b['subgroup']}]", difference=diff, difference_pp=100 * diff,
                       difference_se=se, difference_ci_low_pp=100 * (diff - Z95 * se), difference_ci_high_pp=100 * (diff + Z95 * se))
        het.append(rec)
    return sub, pd.DataFrame(het)


def winsorized(y: np.ndarray, threshold: float) -> np.ndarray:
    return np.minimum(np.asarray(y, float), threshold)
