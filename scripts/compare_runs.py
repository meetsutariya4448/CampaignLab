"""Compare two CampaignLab roots: deterministic artifact identity and numerical tolerances.

usage: python scripts/compare_runs.py <original-root> <rerun-root>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Timestamps and retrieval metadata legitimately change on every fresh run/download. The provenance
# manifest's own hash is excluded from the lock comparison because the manifest embeds retrieval
# time/headers; the manifest contents (bytes, SHA-256 of the data, URLs) are still compared.
TIMESTAMP_KEYS = {"created_utc", "completed_utc", "retrieved_utc", "retrieval", "runtime_seconds", "utc", "provenance_manifest_sha256"}


def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if k not in TIMESTAMP_KEYS}
    if isinstance(o, list):
        return [strip(v) for v in o]
    return o


def compare_csv(a: Path, b: Path):
    x, y = pd.read_csv(a), pd.read_csv(b)
    if list(x.columns) != list(y.columns) or x.shape != y.shape:
        return False, "shape/columns differ"
    num = x.select_dtypes("number").columns
    other = [c for c in x.columns if c not in num]
    if not x[other].astype(str).equals(y[other].astype(str)):
        return False, "non-numeric cells differ"
    xa, ya = x[num].to_numpy(float), y[num].to_numpy(float)
    ok = np.allclose(xa, ya, rtol=1e-8, atol=1e-10, equal_nan=True)
    return ok, f"max abs diff {np.nanmax(np.abs(xa - ya)) if xa.size else 0:.3g}"


def main(orig, rerun):
    orig, rerun = Path(orig), Path(rerun)
    rows = []
    for p in sorted((orig / "reports").rglob("*")):
        if p.is_dir() or p.name in ("publication_audit.json", "claims_audit.json"):
            continue
        rel = p.relative_to(orig)
        q = rerun / rel
        if not q.exists():
            rows.append((str(rel), "MISSING", ""))
            continue
        same = p.read_bytes() == q.read_bytes()
        if same:
            rows.append((str(rel), "identical", ""))
        elif p.suffix == ".csv":
            ok, note = compare_csv(p, q)
            rows.append((str(rel), "within tolerance" if ok else "DIFFERENT", note))
        elif p.suffix == ".json":
            ok = strip(json.loads(p.read_text())) == strip(json.loads(q.read_text()))
            rows.append((str(rel), "identical (ignoring timestamps)" if ok else "DIFFERENT", ""))
        else:
            rows.append((str(rel), "bytes differ", "binary/text rendering"))
    for name in ("lock_manifest.json", "split_manifest.json", "provenance_manifest.json", "selection.json", "frozen_thresholds.json"):
        a, b = orig / "artifacts/private" / name, rerun / "artifacts/private" / name
        if a.exists() and b.exists():
            same = strip(json.loads(a.read_text())) == strip(json.loads(b.read_text()))
            rows.append((f"artifacts/private/{name}", "identical (ignoring timestamps)" if same else "DIFFERENT", ""))
    for name in ("s_learner.json", "t_learner.json"):
        a, b = orig / "artifacts/private/models" / name, rerun / "artifacts/private/models" / name
        if a.exists() and b.exists():
            rows.append((f"artifacts/private/models/{name}", "identical" if a.read_bytes() == b.read_bytes() else "DIFFERENT", ""))
    a, b = orig / "artifacts/private/split_manifest.csv", rerun / "artifacts/private/split_manifest.csv"
    rows.append(("artifacts/private/split_manifest.csv", "identical" if a.read_bytes() == b.read_bytes() else "DIFFERENT", ""))
    df = pd.DataFrame(rows, columns=["artifact", "status", "note"])
    print(df.status.value_counts().to_string())
    bad = df[df.status.isin(["MISSING", "DIFFERENT"])]
    print(bad.to_string() if len(bad) else "no deterministic artifact differs")
    other = df[df.status == "bytes differ"]
    if len(other):
        print("non-identical renderings:\n" + other.to_string())
    out = Path(rerun).parent / "compare.csv"
    df.to_csv(out, index=False)
    sys.exit(1 if len(bad) else 0)


if __name__ == "__main__":
    main(*sys.argv[1:3])
