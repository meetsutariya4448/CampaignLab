"""Response models for visit: TRAIN-fitted feature basis, interacted logistic S-learner and T-learner.

Fitted models are stored as plain JSON parameters (no pickles) and predictions are recomputed from
those parameters, so a model's identity is the hash of its parameters.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

from . import governance as gov

FORBIDDEN_FEATURE_COLUMNS = {"arm", "segment", "visit", "conversion", "spend", "spend_cents", "partition", "split_key"}
INDICATORS = ["mens", "womens", "newbie", "channel_Web", "channel_Multichannel", "zip_Urban", "zip_Surburban"]


class LeakageError(ValueError):
    """A covariate frame carried assignment, outcome or split information into a feature/policy function."""


class UnknownCategoryError(ValueError):
    pass


def assert_covariates_only(cov: pd.DataFrame) -> None:
    bad = FORBIDDEN_FEATURE_COLUMNS & set(cov.columns)
    if bad:
        raise LeakageError(f"covariate frame contains non-feature columns {sorted(bad)}")


# =========================================================================== feature basis

class FeatureBasis:
    """Nine-column basis. Continuous columns standardized with statistics from the fit rows only.

    encoding='log_history' is the frozen main basis. encoding='coarse_segment' replaces
    log(1+history) by six history_segment indicators (development-only encoding diagnostic).
    """

    def __init__(self, cfg: dict, encoding: str = "log_history"):
        f = cfg["features"]
        self.channel_levels = list(f["channel_levels"])
        self.zip_levels = list(f["zip_levels"])
        self.history_levels = list(cfg["dataset"]["allowed"]["history_segment"])
        self.encoding = encoding
        self.stats: dict | None = None
        self.n_fit = 0

    @property
    def columns(self) -> list[str]:
        hist = ["log_history"] if self.encoding == "log_history" else [f"hseg_{i}" for i in range(2, 8)]
        return ["recency"] + hist + ["mens", "womens", "newbie", "channel_Web", "channel_Multichannel", "zip_Urban", "zip_Surburban"]

    def _raw(self, cov: pd.DataFrame) -> pd.DataFrame:
        assert_covariates_only(cov)
        unknown_ch = set(cov["channel"].unique()) - set(self.channel_levels)
        unknown_zip = set(cov["zip_code"].unique()) - set(self.zip_levels)
        if unknown_ch or unknown_zip:
            raise UnknownCategoryError(f"unknown categories: channel={unknown_ch}, zip_code={unknown_zip}")
        out = pd.DataFrame({"recency": cov["recency"].astype(float).to_numpy()})
        if self.encoding == "log_history":
            out["log_history"] = np.log1p(cov["history"].astype(float).to_numpy())
        else:
            seg = cov["history_segment"].to_numpy()
            if set(seg) - set(self.history_levels):
                raise UnknownCategoryError("unknown history_segment label")
            for i, lvl in enumerate(self.history_levels[1:], start=2):
                out[f"hseg_{i}"] = (seg == lvl).astype(float)
        for c in ("mens", "womens", "newbie"):
            out[c] = cov[c].astype(float).to_numpy()
        out["channel_Web"] = (cov["channel"] == "Web").astype(float).to_numpy()
        out["channel_Multichannel"] = (cov["channel"] == "Multichannel").astype(float).to_numpy()
        out["zip_Urban"] = (cov["zip_code"] == "Urban").astype(float).to_numpy()
        out["zip_Surburban"] = (cov["zip_code"] == "Surburban").astype(float).to_numpy()
        return out[self.columns]

    def fit(self, cov: pd.DataFrame) -> "FeatureBasis":
        raw = self._raw(cov)
        scaled = [c for c in ("recency", "log_history") if c in raw.columns]
        self.stats = {c: {"mean": float(raw[c].mean()), "sd": float(raw[c].std(ddof=0))} for c in scaled}
        self.n_fit = int(len(raw))
        return self

    def transform(self, cov: pd.DataFrame) -> np.ndarray:
        if self.stats is None:
            raise RuntimeError("FeatureBasis must be fitted on training rows before transform")
        raw = self._raw(cov)
        for c, s in self.stats.items():
            raw[c] = (raw[c] - s["mean"]) / s["sd"]
        return raw.to_numpy(dtype=np.float64)

    def to_dict(self) -> dict:
        return {"encoding": self.encoding, "columns": self.columns, "stats": self.stats, "n_fit": self.n_fit}

    @classmethod
    def from_dict(cls, cfg: dict, d: dict) -> "FeatureBasis":
        b = cls(cfg, d["encoding"])
        b.stats, b.n_fit = d["stats"], d["n_fit"]
        return b


# =========================================================================== logistic fitting

def fit_logistic(X: np.ndarray, y: np.ndarray, C: float, cfg: dict) -> dict:
    m = cfg["models"]
    lr = LogisticRegression(C=float(C), l1_ratio=0.0, solver="lbfgs", tol=float(m["tol"]), max_iter=int(m["max_iter"]))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        lr.fit(np.asarray(X, dtype=np.float64), np.asarray(y, dtype=np.int64))
    n_iter = int(np.max(lr.n_iter_))
    conv_warn = any(issubclass(w.category, ConvergenceWarning) for w in caught)
    return {"coef": lr.coef_.ravel().astype(float).tolist(), "intercept": float(lr.intercept_[0]), "n_iter": n_iter,
            "converged": bool(n_iter < int(m["max_iter"]) and not conv_warn), "n_rows": int(len(y)), "events": int(np.sum(y))}


def predict_logistic(params: dict, X: np.ndarray) -> np.ndarray:
    return expit(X @ np.asarray(params["coef"]) + params["intercept"])


def s_design(Z: np.ndarray, action: np.ndarray) -> np.ndarray:
    """[basis, 1{a=M}, 1{a=W}, 1{a=M} x basis, 1{a=W} x basis] — the arm x feature interactions are required."""
    dm = (np.asarray(action) == 1).astype(np.float64)[:, None]
    dw = (np.asarray(action) == 2).astype(np.float64)[:, None]
    return np.hstack([Z, dm, dw, dm * Z, dw * Z])


def s_design_main_effects(Z: np.ndarray, action: np.ndarray) -> np.ndarray:
    """Instructional ablation only: arm main effects without interactions (preserves arm ordering)."""
    dm = (np.asarray(action) == 1).astype(np.float64)[:, None]
    dw = (np.asarray(action) == 2).astype(np.float64)[:, None]
    return np.hstack([Z, dm, dw])


class SLearner:
    kind = "s_learner"

    def __init__(self, cfg: dict, C: float, encoding: str = "log_history", interactions: bool = True):
        self.cfg, self.C, self.encoding, self.interactions = cfg, float(C), encoding, interactions
        self.basis: FeatureBasis | None = None
        self.params: dict | None = None

    def _design(self, Z, action):
        return s_design(Z, action) if self.interactions else s_design_main_effects(Z, action)

    def fit(self, cov: pd.DataFrame, arm: np.ndarray, y: np.ndarray) -> "SLearner":
        self.basis = FeatureBasis(self.cfg, self.encoding).fit(cov)
        Z = self.basis.transform(cov)
        self.params = fit_logistic(self._design(Z, arm), y, self.C, self.cfg)
        return self

    @property
    def converged(self) -> bool:
        return bool(self.params["converged"])

    def predict_observed(self, cov: pd.DataFrame, arm: np.ndarray) -> np.ndarray:
        return predict_logistic(self.params, self._design(self.basis.transform(cov), arm))

    def predict_all(self, cov: pd.DataFrame) -> np.ndarray:
        """m(a, X) for a = 0, M, W on the same rows. Uses covariates only."""
        Z = self.basis.transform(cov)
        n = len(Z)
        return np.column_stack([predict_logistic(self.params, self._design(Z, np.full(n, a))) for a in (0, 1, 2)])

    def to_dict(self) -> dict:
        names = self.basis.columns
        design_cols = names + ["arm_M", "arm_W"] + ([f"M_x_{c}" for c in names] + [f"W_x_{c}" for c in names] if self.interactions else [])
        return {"kind": self.kind, "C": self.C, "interactions": self.interactions, "basis": self.basis.to_dict(),
                "design_columns": design_cols, "params": self.params,
                "solver": "lbfgs, L2 (l1_ratio=0), float64", "tol": self.cfg["models"]["tol"], "max_iter": self.cfg["models"]["max_iter"]}

    @classmethod
    def from_dict(cls, cfg: dict, d: dict) -> "SLearner":
        m = cls(cfg, d["C"], d["basis"]["encoding"], d["interactions"])
        m.basis, m.params = FeatureBasis.from_dict(cfg, d["basis"]), d["params"]
        return m


class TLearner:
    kind = "t_learner"

    def __init__(self, cfg: dict, C: float):
        self.cfg, self.C = cfg, float(C)
        self.basis: FeatureBasis | None = None
        self.params: dict[int, dict] = {}

    def fit(self, cov: pd.DataFrame, arm: np.ndarray, y: np.ndarray) -> "TLearner":
        arm = np.asarray(arm)
        y = np.asarray(y)
        self.basis = FeatureBasis(self.cfg).fit(cov)  # common scaling from all training rows of the fit
        Z = self.basis.transform(cov)
        for a in (0, 1, 2):
            m = arm == a
            if m.sum() == 0:
                raise ValueError(f"no training rows for arm {a}")
            self.params[a] = fit_logistic(Z[m], y[m], self.C, self.cfg)
        return self

    @property
    def converged(self) -> bool:
        return all(p["converged"] for p in self.params.values())

    def predict_observed(self, cov: pd.DataFrame, arm: np.ndarray) -> np.ndarray:
        all_ = self.predict_all(cov)
        return all_[np.arange(len(all_)), np.asarray(arm)]

    def predict_all(self, cov: pd.DataFrame) -> np.ndarray:
        Z = self.basis.transform(cov)
        return np.column_stack([predict_logistic(self.params[a], Z) for a in (0, 1, 2)])

    def to_dict(self) -> dict:
        return {"kind": self.kind, "C": self.C, "basis": self.basis.to_dict(), "design_columns": self.basis.columns,
                "params": {str(a): p for a, p in self.params.items()},
                "solver": "lbfgs, L2 (l1_ratio=0), float64", "tol": self.cfg["models"]["tol"], "max_iter": self.cfg["models"]["max_iter"]}

    @classmethod
    def from_dict(cls, cfg: dict, d: dict) -> "TLearner":
        m = cls(cfg, d["C"])
        m.basis = FeatureBasis.from_dict(cfg, d["basis"])
        m.params = {int(a): p for a, p in d["params"].items()}
        return m


def model_from_dict(cfg: dict, d: dict):
    return SLearner.from_dict(cfg, d) if d["kind"] == "s_learner" else TLearner.from_dict(cfg, d)


def model_identity(d: dict) -> str:
    return gov.sha256_json(d)


LEARNERS = {"s_learner": SLearner, "t_learner": TLearner}


# =========================================================================== CV and selection

def cv_folds(arm: np.ndarray, n_folds: int, seed: int, groups=None) -> np.ndarray:
    """Fold index per row: arm-stratified (optionally profile-grouped for the dependence diagnostic)."""
    fold = np.full(len(arm), -1)
    if groups is None:
        splitter = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed).split(np.zeros(len(arm)), arm)
    else:
        splitter = StratifiedGroupKFold(n_splits=n_folds, shuffle=True, random_state=seed).split(np.zeros(len(arm)), arm, groups)
    for k, (_, test_idx) in enumerate(splitter):
        fold[test_idx] = k
    return fold


def cross_validate(kind: str, cov: pd.DataFrame, arm: np.ndarray, y: np.ndarray, C_grid, folds: np.ndarray, cfg: dict,
                   **learner_kwargs) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fold-local fitting (basis + model refit inside each training fold). Held-out log loss per fold."""
    rows = []
    for C in C_grid:
        for k in sorted(np.unique(folds)):
            tr, te = folds != k, folds == k
            model = LEARNERS[kind](cfg, C, **learner_kwargs).fit(cov[tr].reset_index(drop=True), arm[tr], y[tr])
            p = model.predict_observed(cov[te].reset_index(drop=True), arm[te])
            rows.append({"learner": kind, "C": float(C), "fold": int(k), "n_train_fold": int(tr.sum()), "n_heldout": int(te.sum()),
                         "logloss": float(log_loss(y[te], p, labels=[0, 1])), "brier": float(brier_score_loss(y[te], p)),
                         "converged": model.converged})
    per_fold = pd.DataFrame(rows)
    summary = per_fold.groupby("C", as_index=False).agg(mean_logloss=("logloss", "mean"), sd_logloss=("logloss", "std"),
                                                         mean_brier=("brier", "mean"), all_converged=("converged", "all"))
    summary.insert(0, "learner", kind)
    return per_fold, summary


def select_C(summary: pd.DataFrame, tie_tol: float) -> float:
    """Lowest mean CV log loss; values within tie_tol of the minimum prefer the smaller C."""
    best = summary["mean_logloss"].min()
    eligible = summary[summary["mean_logloss"] <= best + tie_tol]
    return float(eligible["C"].min())


def t_learner_gate(cov: pd.DataFrame, arm: np.ndarray, y: np.ndarray, cfg: dict) -> dict:
    g = cfg["models"]["t_learner_gate"]
    basis = FeatureBasis(cfg).fit(cov)._raw(cov)
    checks = []
    for a in (0, 1, 2):
        m = arm == a
        v, nv = int(y[m].sum()), int((1 - y[m]).sum())
        checks.append({"check": f"arm {a} visits >= {g['min_visits_per_arm']}", "value": v, "passed": v >= g["min_visits_per_arm"]})
        checks.append({"check": f"arm {a} non-visits >= {g['min_nonvisits_per_arm']}", "value": nv, "passed": nv >= g["min_nonvisits_per_arm"]})
        for col in INDICATORS:
            for level in (0.0, 1.0):
                lm = m & (basis[col].to_numpy() == level)
                lv, lnv = int(y[lm].sum()), int((1 - y[lm]).sum())
                ok = lv >= g["min_level_visits"] and lnv >= g["min_level_nonvisits"]
                checks.append({"check": f"arm {a} {col}={int(level)} visits/non-visits >= {g['min_level_visits']}/{g['min_level_nonvisits']}",
                               "value": f"{lv}/{lnv}", "passed": ok})
    return {"support_passed": all(c["passed"] for c in checks), "checks": checks}


# =========================================================================== diagnostics

def response_diagnostics(model, cov: pd.DataFrame, arm: np.ndarray, y: np.ndarray, scope: str) -> tuple[dict, pd.DataFrame]:
    """Log loss, Brier, arm-level calibration and decile reliability. These assess response prediction, not uplift."""
    p = model.predict_observed(cov, arm)
    summary = {"learner": model.kind, "C": model.C, "sample_scope": scope, "n": int(len(y)),
               "logloss": float(log_loss(y, p, labels=[0, 1])), "brier": float(brier_score_loss(y, p)),
               "mean_predicted": float(p.mean()), "observed_rate": float(np.mean(y))}
    rows = []
    for a in (0, 1, 2):
        m = arm == a
        rows.append({"learner": model.kind, "sample_scope": scope, "bin": f"arm {a}", "n": int(m.sum()),
                     "mean_predicted": float(p[m].mean()), "observed_rate": float(y[m].mean())})
    edges = np.quantile(p, np.linspace(0, 1, 11))
    bins = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, 9)
    for b in range(10):
        m = bins == b
        if m.any():
            rows.append({"learner": model.kind, "sample_scope": scope, "bin": f"decile {b + 1}", "n": int(m.sum()),
                         "mean_predicted": float(p[m].mean()), "observed_rate": float(y[m].mean())})
    return summary, pd.DataFrame(rows)


def coefficient_table(d: dict) -> pd.DataFrame:
    if d["kind"] == "s_learner":
        return pd.DataFrame({"learner": d["kind"], "model": "pooled", "term": ["intercept"] + d["design_columns"],
                             "coefficient": [d["params"]["intercept"]] + d["params"]["coef"]})
    frames = []
    for a, p in d["params"].items():
        frames.append(pd.DataFrame({"learner": d["kind"], "model": f"arm {a}", "term": ["intercept"] + d["design_columns"],
                                    "coefficient": [p["intercept"]] + p["coef"]}))
    return pd.concat(frames, ignore_index=True)
