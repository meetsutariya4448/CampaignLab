"""Hashing, run state, outcome-access logging and lock/release tokens.

These controls make the information-access sequence auditable. They are workflow
discipline for a public dataset, not cryptographic secrecy.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

import numpy as np

from .config import CONFIG_PATH, PRIVATE_DIR, ROOT, SQL_DIR

STATE_PATH = PRIVATE_DIR / "state.json"
ACCESS_LOG_PATH = PRIVATE_DIR / "outcome_access_log.jsonl"
LOCK_PATH = PRIVATE_DIR / "lock_manifest.json"
EVAL_RECORD_PATH = PRIVATE_DIR / "evaluation_complete.json"

# Modules whose content determines actions, estimates or access control. reporting.py and
# simulation.py only render or test, so a wording fix there does not invalidate the lock.
LOCKED_MODULES = ["config.py", "data.py", "evaluation.py", "governance.py", "inference.py", "models.py", "policy.py", "run.py"]
KEY_PACKAGES = ["numpy", "pandas", "scipy", "statsmodels", "scikit-learn", "duckdb", "matplotlib", "seaborn", "PyYAML", "pytest"]


class AccessError(PermissionError):
    """Raised when a stage requests outcomes outside its permitted scope."""


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_json_default)


def sha256_json(obj) -> str:
    return sha256_bytes(canonical_json(obj).encode("utf-8"))


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not JSON serializable: {type(o)}")


def write_json(path: Path, obj, indent: int = 2) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=indent, sort_keys=True, default=_json_default) + "\n"
    path.write_text(text, encoding="utf-8")
    return sha256_bytes(text.encode("utf-8"))


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def hash_strings(values) -> np.ndarray:
    """Hex SHA-256 for each string (vectorized helper used by the split and policy tie-breaks)."""
    return np.array([hashlib.sha256(v.encode("utf-8")).hexdigest() for v in values], dtype=object)


def vector_checksum(row_ids, values) -> str:
    """Order-independent checksum of an aligned (row_id, value) vector."""
    pairs = sorted(zip(map(str, row_ids), map(_canonical_scalar, values)))
    h = hashlib.sha256()
    for rid, val in pairs:
        h.update(f"{rid}\t{val}\n".encode("utf-8"))
    return h.hexdigest()


def _canonical_scalar(v) -> str:
    if isinstance(v, (float, np.floating)):
        return float(v).hex()
    return str(int(v)) if isinstance(v, (int, np.integer, bool, np.bool_)) else str(v)


# --------------------------------------------------------------------------- state / logs

def load_state() -> dict:
    return read_json(STATE_PATH) if STATE_PATH.exists() else {}


def mark_stage(stage: str, **info) -> None:
    state = load_state()
    state[stage] = {"completed_utc": utc_now(), **info}
    write_json(STATE_PATH, state)


def require_stage(stage: str) -> dict:
    state = load_state()
    if stage not in state:
        raise AccessError(f"stage {stage!r} has not completed; run it first")
    return state[stage]


def log_access(scope: str, stage: str, n_rows: int) -> None:
    ACCESS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ACCESS_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"utc": utc_now(), "scope": scope, "stage": stage, "rows": int(n_rows)}) + "\n")


# --------------------------------------------------------------------------- hashes / environment

def code_hashes() -> dict:
    src = ROOT / "src" / "campaignlab"
    out = {f"src/campaignlab/{m}": sha256_file(src / m) for m in LOCKED_MODULES}
    for p in sorted(SQL_DIR.glob("*.sql")):
        out[f"sql/{p.name}"] = sha256_file(p)
    return out


def environment_record() -> dict:
    versions = {}
    for pkg in KEY_PACKAGES:
        try:
            versions[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            versions[pkg] = None
    lock = ROOT / "requirements.lock"
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": versions,
        "requirements_lock_sha256": sha256_file(lock) if lock.exists() else None,
    }


def config_hash() -> str:
    return sha256_file(CONFIG_PATH)


# --------------------------------------------------------------------------- tokens

@dataclass(frozen=True)
class TestAccessToken:
    """Issued only after the lock manifest has been re-verified against recomputed actions."""

    __test__ = False  # not a pytest test class
    lock_sha256: str


@dataclass(frozen=True)
class FullReleaseToken:
    """Issued only after the locked TEST evaluation has completed and been recorded."""

    evaluation_record_sha256: str


def check_test_token(token) -> None:
    if not isinstance(token, TestAccessToken):
        raise AccessError("TEST outcomes require a TestAccessToken from a verified lock")
    if not LOCK_PATH.exists():
        raise AccessError("no lock manifest exists; TEST outcomes are unavailable")
    if sha256_file(LOCK_PATH) != token.lock_sha256:
        raise AccessError("lock manifest changed after the token was issued")
    verified = load_state().get("lock_verified", {})
    if verified.get("lock_sha256") != token.lock_sha256:
        raise AccessError("lock manifest has not been verified in this state")


def check_release_token(token) -> None:
    if not isinstance(token, FullReleaseToken):
        raise AccessError("full-sample outcomes require a FullReleaseToken after TEST evaluation")
    if not EVAL_RECORD_PATH.exists() or sha256_file(EVAL_RECORD_PATH) != token.evaluation_record_sha256:
        raise AccessError("evaluation-complete record missing or changed")


def issue_release_token() -> FullReleaseToken:
    if not EVAL_RECORD_PATH.exists():
        raise AccessError("TEST evaluation has not completed; full-sample release is blocked")
    record = read_json(EVAL_RECORD_PATH)
    if record.get("lock_sha256") != (sha256_file(LOCK_PATH) if LOCK_PATH.exists() else None):
        raise AccessError("evaluation record does not match the current lock manifest")
    return FullReleaseToken(sha256_file(EVAL_RECORD_PATH))
