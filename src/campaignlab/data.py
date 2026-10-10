"""Acquisition, typed contract validation, row identity, logical tables and the frozen split.

Order of operations: hash the exact bytes before parsing; assign source-ordinal row IDs
before any sorting; never deduplicate; separate covariates / assignment / outcomes.
"""
from __future__ import annotations

import csv
import io
import os
import re
import stat
import urllib.request
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import governance as gov
from .config import ARM_CODES, PRIVATE_DIR, ROOT, SQL_DIR

PROVENANCE_PATH = PRIVATE_DIR / "provenance_manifest.json"
SPLIT_MANIFEST_CSV = PRIVATE_DIR / "split_manifest.csv"
SPLIT_MANIFEST_JSON = PRIVATE_DIR / "split_manifest.json"

PRETREATMENT_RAW = ["recency", "history", "mens", "womens", "newbie", "channel", "zip_code"]
OUTCOME_COLUMNS = ["visit", "conversion", "spend"]
BINARY_COLUMNS = ["mens", "womens", "newbie", "visit", "conversion"]
_AMOUNT_RE = re.compile(r"^(\d+)(?:\.(\d+))?$")
_INT_RE = re.compile(r"^-?\d+$")

# Right-closed reconstruction of the publisher's history buckets (upper bounds in cents).
_BUCKET_UPPER_CENTS = [10000, 20000, 35000, 50000, 75000, 100000]


class ContractError(ValueError):
    """Hard data-contract failure; analysis must stop and the artifact be investigated."""


# =========================================================================== acquisition

def raw_path(cfg: dict) -> Path:
    return ROOT / cfg["dataset"]["raw_path"]


def acquire(cfg: dict, *, timeout: int = 120) -> dict:
    """Download the exact publisher bytes once, verify size/SHA-256 before parsing, store read-only."""
    ds = cfg["dataset"]
    path = raw_path(cfg)
    if path.exists():
        digest = gov.sha256_file(path)
        if digest != ds["expected_sha256"]:
            raise ContractError(f"existing raw file hash {digest} != expected {ds['expected_sha256']}")
        if PROVENANCE_PATH.exists():
            return gov.read_json(PROVENANCE_PATH)
        return _write_provenance(cfg, path, digest, retrieval=None)

    req = urllib.request.Request(ds["source_url"], headers={"User-Agent": "CampaignLab/1.0 (reproducible research download)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # certificate checks untouched; HTTP source
        body = resp.read()
        retrieval = {
            "retrieved_utc": gov.utc_now(),
            "http_status": resp.status,
            "final_url": resp.geturl(),
            "headers": {k: resp.headers.get(k) for k in ("Content-Length", "Content-Type", "ETag", "Last-Modified")},
        }
    digest = gov.sha256_bytes(body)
    if len(body) != ds["expected_bytes"] or digest != ds["expected_sha256"]:
        quarantine = path.with_suffix(".unexpected")
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        quarantine.write_bytes(body)
        raise ContractError(
            f"downloaded artifact differs from the pinned one (bytes={len(body)}, sha256={digest}); "
            f"saved to {quarantine} for investigation. Do not update the expected hash silently."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as fh:
        fh.write(body)
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # immutable local copy
    return _write_provenance(cfg, path, digest, retrieval)


def _write_provenance(cfg: dict, path: Path, digest: str, retrieval: dict | None) -> dict:
    ds = cfg["dataset"]
    data = path.read_bytes()
    manifest = {
        "dataset_id": ds["id"],
        "source_url": ds["source_url"],
        "article_url": ds["article_url"],
        "local_path": str(path.relative_to(ROOT)),
        "bytes": len(data),
        "sha256": digest,
        "expected_sha256": ds["expected_sha256"],
        "sha256_matches": digest == ds["expected_sha256"],
        "crlf_count": data.count(b"\r\n"),
        "encoding": ds["encoding"],
        "parser": "python csv.reader over utf-8-sig decoded text; all fields read as text, typed afterwards",
        "original_order_preserved": True,
        "row_id_scheme": f"{ds['id']}:<zero-based source row ordinal>",
        "retrieval": retrieval,
        "rights": "No explicit redistribution license found; raw bytes kept private (see docs/rights_and_assumptions.md)",
        "note": "A hash detects change relative to the pinned copy; it is not a publisher signature.",
    }
    gov.write_json(PROVENANCE_PATH, manifest)
    return manifest


def read_verified_bytes(cfg: dict) -> bytes:
    data = raw_path(cfg).read_bytes()
    digest = gov.sha256_bytes(data)
    if digest != cfg["dataset"]["expected_sha256"]:
        raise ContractError(f"raw artifact hash mismatch: {digest}")
    return data


# =========================================================================== parsing / contract

def parse_source(data: bytes, cfg: dict) -> pd.DataFrame:
    """Parse bytes to an all-text frame with row IDs assigned in original order (before any sort)."""
    text = data.decode(cfg["dataset"]["encoding"])
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader)
    expected = cfg["dataset"]["expected_columns"]
    if header != expected:
        raise ContractError(f"header mismatch: {header} != {expected}")
    rows = list(reader)
    bad_width = [i for i, r in enumerate(rows) if len(r) != len(header)]
    if bad_width:
        raise ContractError(f"{len(bad_width)} rows have the wrong number of fields (first ordinal {bad_width[0]})")
    df = pd.DataFrame(rows, columns=header, dtype=object)
    n = len(df)
    df.insert(0, "source_ordinal", np.arange(n, dtype=np.int64))
    df.insert(0, "row_id", [f"{cfg['dataset']['id']}:{i}" for i in range(n)])
    return df


def _amount_to_cents(values: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Exact decimal-string → integer cents. Returns (cents, valid_mask)."""
    cents = np.zeros(len(values), dtype=np.int64)
    valid = np.zeros(len(values), dtype=bool)
    for i, s in enumerate(values.to_numpy()):
        m = _AMOUNT_RE.match(s) if isinstance(s, str) else None
        if not m:
            continue
        whole, frac = m.group(1), m.group(2) or ""
        if len(frac) > 2:
            continue  # more than two decimal places violates the DECIMAL(10,2) contract
        cents[i] = int(whole) * 100 + int(frac.ljust(2, "0"))
        valid[i] = True
    return cents, valid


def type_and_validate(text: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Python-side typed contract. Returns the typed frame and {check_name: failure_count}."""
    allowed = cfg["dataset"]["allowed"]
    checks: dict[str, int] = {}
    n = len(text)
    checks["row_count"] = int(n != cfg["dataset"]["expected_rows"])
    src_cols = cfg["dataset"]["expected_columns"]
    checks["blank_fields"] = int(sum((text[c].astype(str).str.strip() == "").sum() for c in src_cols))

    out = pd.DataFrame({"row_id": text["row_id"], "source_ordinal": text["source_ordinal"]})

    rec_ok = text["recency"].map(lambda s: bool(_INT_RE.match(s))).to_numpy()
    rec = np.where(rec_ok, pd.to_numeric(text["recency"].where(rec_ok, "0")).to_numpy(), 0)
    checks["recency_integer_in_range"] = int((~rec_ok | (rec < allowed["recency_min"]) | (rec > allowed["recency_max"])).sum())
    out["recency"] = rec.astype(np.int16)

    for col in ("history", "spend"):
        cents, ok = _amount_to_cents(text[col])
        checks[f"{col}_decimal_format"] = int((~ok).sum())
        checks[f"{col}_nonnegative_finite"] = int((~ok).sum())  # regex admits only finite nonnegative values
        out[col] = cents / 100.0
        out[f"{col}_cents"] = cents

    for col in BINARY_COLUMNS:
        ok = text[col].isin(["0", "1"]).to_numpy()
        checks[f"binary_{col}"] = int((~ok).sum())
        out[col] = np.where(ok, text[col].map({"0": 0, "1": 1}).fillna(0), 0).astype(np.int8)

    for col in ("zip_code", "channel", "segment", "history_segment"):
        checks[f"allowed_{col}"] = int((~text[col].isin(allowed[col])).sum())
        out[col] = text[col].astype(str)

    out["arm"] = out["segment"].map(ARM_CODES).fillna(-1).astype(np.int8)
    checks["conversion_without_visit"] = int(((out["conversion"] == 1) & (out["visit"] == 0)).sum())
    checks["positive_spend_without_conversion"] = int(((out["spend_cents"] > 0) & (out["conversion"] == 0)).sum())
    checks["conversion_without_positive_spend"] = int(((out["conversion"] == 1) & (out["spend_cents"] <= 0)).sum())
    checks["row_id_unique"] = int(n - out["row_id"].nunique())
    return out, checks


def assert_contract(checks: dict) -> None:
    failed = {k: v for k, v in checks.items() if v != 0}
    if failed:
        raise ContractError(f"hard contract checks failed: {failed}")


# =========================================================================== quality diagnostics

def right_closed_bucket(history_cents: np.ndarray) -> np.ndarray:
    """1..7 bucket index under a simple right-closed reconstruction of the publisher labels."""
    return np.searchsorted(np.array(_BUCKET_UPPER_CENTS), history_cents, side="left") + 1


def history_bucket_disagreements(typed: pd.DataFrame) -> pd.DataFrame:
    src = typed["history_segment"].str.slice(0, 1).astype(int).to_numpy()
    recon = right_closed_bucket(typed["history_cents"].to_numpy())
    mask = src != recon
    d = pd.DataFrame({
        "rounded_history": typed.loc[mask, "history"].round(0).astype(int).astype(str),
        "source_bucket": typed.loc[mask, "history_segment"],
        "right_closed_bucket": recon[mask],
    })
    return d.groupby(["rounded_history", "source_bucket", "right_closed_bucket"]).size().rename("row_count").reset_index()


def profile_ids(cov: pd.DataFrame) -> np.ndarray:
    """Integer code per identical seven-field pre-treatment profile (hypothetical dependence groups only)."""
    keys = cov[PRETREATMENT_RAW].astype(str).agg("|".join, axis=1)
    return pd.factorize(keys, sort=True)[0].astype(np.int64)


def matching_summary(typed: pd.DataFrame) -> dict:
    full_cols = ["recency", "history_segment", "history_cents", "mens", "womens", "zip_code", "newbie", "channel", "segment", "visit", "conversion", "spend_cents"]
    g = typed.groupby(full_cols, sort=False).size()
    multi = g[g > 1]
    p = typed.groupby(PRETREATMENT_RAW, sort=False).size()
    return {
        "full_row_match_groups": int(len(multi)),
        "full_row_match_excess": int((multi - 1).sum()),
        "full_row_match_rows_involved": int(multi.sum()),
        "largest_full_row_group": int(g.max()),
        "distinct_pretreatment_profiles": int(len(p)),
        "pretreatment_profile_excess": int((p - 1).sum()),
        "largest_profile_group": int(p.max()),
    }


def global_quality(typed: pd.DataFrame) -> dict:
    """Global (not arm-by-outcome) quality facts, all already inspected during planning."""
    q = {
        "rows": int(len(typed)),
        "arm_counts": {seg: int(c) for seg, c in typed["segment"].value_counts().sort_index().items()},
        "global_visits": int(typed["visit"].sum()),
        "global_conversions": int(typed["conversion"].sum()),
        "positive_spend_rows": int((typed["spend_cents"] > 0).sum()),
        "history_bucket_boundary_disagreements": int(history_bucket_disagreements(typed)["row_count"].sum()),
    }
    q.update(matching_summary(typed))
    return q


# =========================================================================== split

def split_keys(row_ids, template: str) -> np.ndarray:
    return gov.hash_strings([template.format(row_id=r) for r in row_ids])


def assign_split(row_ids, arms, cfg: dict) -> pd.DataFrame:
    """Frozen arm-stratified split. Only row IDs (and arm for stratification) enter; no outcome or covariate."""
    sp = cfg["split"]
    df = pd.DataFrame({"row_id": np.asarray(row_ids, dtype=object), "arm": np.asarray(arms)})
    df["split_key"] = split_keys(df["row_id"], sp["key_template"])
    df["partition"] = ""
    for _, idx in df.groupby("arm", sort=True).groups.items():
        g = df.loc[idx].sort_values(["split_key", "row_id"], kind="mergesort")
        n = len(g)
        n_train = (n * sp["train_percent"]) // 100
        n_val = (n * sp["validation_percent"]) // 100
        labels = np.array(["TRAIN"] * n_train + ["VALIDATION"] * n_val + ["TEST"] * (n - n_train - n_val), dtype=object)
        df.loc[g.index, "partition"] = labels
    return df


def split_counts(split: pd.DataFrame) -> pd.DataFrame:
    return split.groupby(["arm", "partition"]).size().unstack(fill_value=0)[["TRAIN", "VALIDATION", "TEST"]]


def check_split(split: pd.DataFrame, cfg: dict) -> dict:
    exp = cfg["split"]
    totals = split["partition"].value_counts().to_dict()
    by_arm = {}
    inv = {v: k for k, v in ARM_CODES.items()}
    for arm, row in split_counts(split).iterrows():
        by_arm[inv[int(arm)]] = {k: int(v) for k, v in row.items()}
    sets = {p: set(split.loc[split["partition"] == p, "row_id"]) for p in ("TRAIN", "VALIDATION", "TEST")}
    result = {
        "totals": {k: int(totals.get(k, 0)) for k in ("TRAIN", "VALIDATION", "TEST")},
        "by_arm": by_arm,
        "disjoint": all(not (sets[a] & sets[b]) for a, b in (("TRAIN", "VALIDATION"), ("TRAIN", "TEST"), ("VALIDATION", "TEST"))),
        "complete": len(sets["TRAIN"] | sets["VALIDATION"] | sets["TEST"]) == len(split) == split["row_id"].nunique(),
    }
    result["matches_expected"] = (result["totals"] == exp["expected_totals"] and result["by_arm"] == exp["expected_by_arm"]
                                  and result["disjoint"] and result["complete"])
    if not result["matches_expected"]:
        raise ContractError(f"split does not reconcile with the frozen plan: {result}")
    return result


def write_split_manifest(split: pd.DataFrame, cfg: dict, data_sha: str) -> dict:
    SPLIT_MANIFEST_CSV.parent.mkdir(parents=True, exist_ok=True)
    out = split.sort_values("row_id", key=lambda s: s.str.split(":").str[1].astype(int))[["row_id", "arm", "partition", "split_key"]]
    out.to_csv(SPLIT_MANIFEST_CSV, index=False, lineterminator="\n")
    meta = {
        "algorithm": "within-arm ascending SHA-256 of key_template, row_id tie-break; floor(60%) TRAIN, floor(20%) VALIDATION, remainder TEST (integer arithmetic)",
        "key_template": cfg["split"]["key_template"],
        "version": "split/v1",
        "seed_component": "2027 (embedded in the key template)",
        "dataset_sha256": data_sha,
        "manifest_csv_sha256": gov.sha256_file(SPLIT_MANIFEST_CSV),
        "membership_checksum": gov.vector_checksum(split["row_id"], split["partition"]),
        "check": check_split(split, cfg),
        "inputs_used": ["row_id", "arm (stratification only)"],
    }
    gov.write_json(SPLIT_MANIFEST_JSON, meta)
    return meta


# =========================================================================== DuckDB

def db_path(cfg: dict) -> Path:
    return ROOT / cfg["dataset"]["database_path"]


def run_sql_file(con: duckdb.DuckDBPyConnection, name: str) -> None:
    sql = (SQL_DIR / name).read_text(encoding="utf-8")
    con.execute(sql)


def build_database(cfg: dict, text: pd.DataFrame, split: pd.DataFrame) -> dict:
    """Create the private DuckDB database with typed tables, logical views and SQL contract checks."""
    path = db_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con = duckdb.connect(str(path))
    try:
        raw_text = text.copy()
        con.register("raw_text_df", raw_text)
        con.execute("CREATE TABLE raw_text AS SELECT * FROM raw_text_df")
        con.unregister("raw_text_df")
        split_df = split[["row_id", "arm", "partition", "split_key"]].copy()
        con.register("split_df", split_df)
        con.execute("CREATE TABLE split AS SELECT row_id, CAST(arm AS TINYINT) AS arm, partition, split_key FROM split_df")
        con.unregister("split_df")
        con.execute(f"SET VARIABLE expected_rows = {int(cfg['dataset']['expected_rows'])}")
        allowed = cfg["dataset"]["allowed"]
        for var, key in (("allowed_zip", "zip_code"), ("allowed_channel", "channel"), ("allowed_segment", "segment"),
                         ("allowed_history_segment", "history_segment")):
            con.execute(f"SET VARIABLE {var} = ?::VARCHAR[]", [list(allowed[key])])
        run_sql_file(con, "01_validate.sql")
        sql_checks = dict(con.execute("SELECT check_name, failures FROM contract_checks ORDER BY check_name").fetchall())
        sql_quality = {k: v for k, v in con.execute("SELECT metric, value FROM quality_summary").fetchall()}
    finally:
        con.close()
    return {"sql_checks": {k: int(v) for k, v in sql_checks.items()}, "sql_quality": {k: int(v) for k, v in sql_quality.items()}}


class Store:
    """Read-only access to the private database with scope-guarded outcome loading."""

    FREE_SCOPES = {"train": ("TRAIN",), "validation": ("VALIDATION",), "development": ("TRAIN", "VALIDATION")}

    def __init__(self, cfg: dict, stage: str):
        self.cfg = cfg
        self.stage = stage
        self.path = db_path(cfg)
        if not self.path.exists():
            raise FileNotFoundError(f"{self.path} missing; run the validate stage")

    def _query(self, sql: str, params=None) -> pd.DataFrame:
        con = duckdb.connect(str(self.path), read_only=True)
        try:
            return con.execute(sql, params or []).df()
        finally:
            con.close()

    def covariates(self) -> pd.DataFrame:
        """Pre-treatment covariates for all rows (no arm, outcome or split columns)."""
        return self._query(
            "SELECT row_id, source_ordinal, recency, CAST(history AS DOUBLE) AS history, mens, womens, newbie, channel, zip_code "
            "FROM covariates ORDER BY source_ordinal")

    def descriptive(self) -> pd.DataFrame:
        return self._query("SELECT d.row_id, d.history_segment FROM descriptive d JOIN covariates c USING (row_id) ORDER BY c.source_ordinal")

    def assignment(self) -> pd.DataFrame:
        """Assigned arm and split partition for all rows (assignment is not an outcome)."""
        return self._query(
            "SELECT a.row_id, a.segment, a.arm, s.partition FROM assignment a JOIN split s USING (row_id) "
            "JOIN covariates c USING (row_id) ORDER BY c.source_ordinal")

    def outcomes(self, scope: str, token=None) -> pd.DataFrame:
        if scope in self.FREE_SCOPES:
            parts = self.FREE_SCOPES[scope]
        elif scope == "test":
            gov.check_test_token(token)
            parts = ("TEST",)
        elif scope == "full":
            gov.check_release_token(token)
            parts = ("TRAIN", "VALIDATION", "TEST")
        else:
            raise gov.AccessError(f"unknown outcome scope {scope!r}")
        placeholders = ",".join(["?"] * len(parts))
        df = self._query(
            "SELECT o.row_id, s.arm, s.partition, o.visit, o.conversion, CAST(o.spend AS DOUBLE) AS spend, o.spend_cents "
            f"FROM outcomes o JOIN split s USING (row_id) JOIN covariates c USING (row_id) WHERE s.partition IN ({placeholders}) "
            "ORDER BY c.source_ordinal", list(parts))
        gov.log_access(scope, self.stage, len(df))
        return df

    def frame(self, scope: str, token=None) -> pd.DataFrame:
        """Covariates + assignment + outcomes for one permitted scope, one row per row_id."""
        y = self.outcomes(scope, token)
        cov = self.covariates()
        a = self.assignment()[["row_id", "segment"]]
        df = y.merge(cov, on="row_id", how="left", validate="one_to_one").merge(a, on="row_id", how="left", validate="one_to_one")
        if len(df) != len(y):
            raise ContractError("join multiplied rows")
        return df.sort_values("source_ordinal", kind="mergesort").reset_index(drop=True)

    def sql(self, name: str, token=None) -> pd.DataFrame:
        """Run a summary SQL file. Development SQL is filtered to TRAIN+VALIDATION by its view;
        the final full-sample SQL requires the release token."""
        if name.startswith("03"):
            gov.check_release_token(token)
        elif not name.startswith("02"):
            raise gov.AccessError(f"{name} is not an analysis summary query")
        con = duckdb.connect(str(self.path), read_only=True)
        try:
            df = con.execute((SQL_DIR / name).read_text(encoding="utf-8")).df()
        finally:
            con.close()
        gov.log_access(f"sql:{name}", self.stage, int(df["n_rows"].sum()) if "n_rows" in df else len(df))
        return df
