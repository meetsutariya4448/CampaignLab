"""T6 end-to-end access and lock controls, run on a SYNTHETIC dataset in an isolated project root."""
import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
import yaml

from campaignlab import data as dt
from campaignlab import governance as gov
from synthetic import make_rows, to_bytes

REPO = Path(__file__).resolve().parents[1]


def _run(root: Path, stage: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "CAMPAIGNLAB_ROOT": str(root), "PYTHONPATH": str(root / "src")}
    return subprocess.run([sys.executable, "-m", "campaignlab.run", stage], cwd=root, env=env, capture_output=True, text=True, timeout=600)


@pytest.fixture(scope="module")
def synthetic_project(tmp_path_factory):
    root = tmp_path_factory.mktemp("campaignlab_synthetic")
    shutil.copytree(REPO / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
    shutil.copytree(REPO / "sql", root / "sql")
    (root / "config").mkdir()
    cfg = yaml.safe_load((REPO / "config" / "analysis.yaml").read_text())
    n = 3000
    raw = to_bytes(make_rows(n, seed=21))
    cfg["dataset"]["raw_path"] = "data/raw/synthetic.csv"
    (root / "data" / "raw").mkdir(parents=True)
    (root / cfg["dataset"]["raw_path"]).write_bytes(raw)
    cfg["dataset"].update(expected_sha256=gov.sha256_bytes(raw), expected_bytes=len(raw), expected_rows=n, id="synthetic-v1")
    text = dt.parse_source(raw, cfg)
    typed, _ = dt.type_and_validate(text, cfg)
    q = dt.global_quality(typed)
    cfg["dataset"]["expected_quality"] = {k: q[k] for k in cfg["dataset"]["expected_quality"]}
    split = dt.assign_split(typed["row_id"], typed["arm"], cfg)
    counts = dt.split_counts(split)
    names = {0: "No E-Mail", 1: "Mens E-Mail", 2: "Womens E-Mail"}
    cfg["split"]["expected_by_arm"] = {names[a]: {k: int(v) for k, v in r.items()} for a, r in counts.iterrows()}
    cfg["split"]["expected_totals"] = {k: int(v) for k, v in counts.sum().items()}
    cfg["inference"].update(bootstrap_development_replicates=200, bootstrap_final_replicates=200, permutation_draws=199)
    cfg["evaluation"].update(bootstrap_replicates=200, stability_extra_replicates=200)
    cfg["development_diagnostics"]["stability_resplits"] = 2
    (root / "config" / "analysis.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    return root, cfg


def _ok(proc):
    assert proc.returncode == 0, proc.stderr[-3000:]


def test_pipeline_access_order_and_lock(synthetic_project):
    root, cfg = synthetic_project
    for stage in ("acquire", "validate", "develop", "fit", "select"):
        _ok(_run(root, stage))

    # development outputs contain only TRAIN+VALIDATION rows
    dev = pd.read_csv(root / "reports/tables/development/arm_summary.csv")
    exp = cfg["split"]["expected_totals"]
    assert dev["n"].sum() == exp["TRAIN"] + exp["VALIDATION"]
    assert not (root / "reports/tables/final").exists()

    # evaluation before a lock and release before evaluation are refused
    r = _run(root, "evaluate")
    assert r.returncode != 0 and "AccessError" in r.stderr
    r = _run(root, "release")
    assert r.returncode != 0 and "AccessError" in r.stderr

    _ok(_run(root, "lock"))
    lock = json.loads((root / "artifacts/private/lock_manifest.json").read_text())
    assert lock["test_rows"]["n"] == exp["TEST"]
    log = [json.loads(l) for l in (root / "artifacts/private/outcome_access_log.jsonl").read_text().splitlines()]
    assert all(e["scope"] not in ("test", "full") for e in log)  # no TEST/full outcome read before the lock

    # tampering with the frozen config after the lock is detected
    cfg_path = root / "config/analysis.yaml"
    original = cfg_path.read_text()
    cfg_path.write_text(original.replace("practical_margin_delta: 0.005", "practical_margin_delta: 0.001"))
    r = _run(root, "evaluate")
    assert r.returncode != 0 and "lock verification failed" in r.stderr
    cfg_path.write_text(original)

    # changing TEST outcomes cannot change locked predictions/actions: verification still passes
    con = duckdb.connect(str(root / cfg["dataset"]["database_path"]))
    con.execute("UPDATE outcomes SET visit = 1 - visit WHERE row_id IN (SELECT row_id FROM split WHERE partition = 'TEST') AND conversion = 0")
    con.close()
    _ok(_run(root, "evaluate"))
    log = [json.loads(l) for l in (root / "artifacts/private/outcome_access_log.jsonl").read_text().splitlines()]
    first_test = next(i for i, e in enumerate(log) if e["scope"] == "test")
    state = json.loads((root / "artifacts/private/state.json").read_text())
    assert "lock_verified" in state and all(e["scope"] != "full" for e in log[:first_test])

    # constant-policy identity on the evaluated TEST rows
    vals = pd.read_csv(root / "reports/tables/final/policy_values.csv").set_index("policy")
    con = duckdb.connect(str(root / cfg["dataset"]["database_path"]), read_only=True)
    means = dict(con.execute("SELECT s.arm, avg(o.visit) FROM outcomes o JOIN split s USING (row_id) WHERE s.partition='TEST' GROUP BY s.arm").fetchall())
    con.close()
    for a, name in ((0, "const_0"), (1, "const_M"), (2, "const_W")):
        assert vals.loc[name, "ipw_value"] == pytest.approx(means[a], abs=1e-12)
    comp = pd.read_csv(root / "reports/tables/final/policy_comparisons.csv")
    assert {"const_0", "const_M", "const_W"} <= set(comp.loc[comp.role.str.startswith("pi*") | comp.role.str.startswith("primary"), "baseline"])

    # a new lock after unblinding is refused; release now works
    r = _run(root, "lock")
    assert r.returncode != 0 and "already recorded" in r.stderr
    _ok(_run(root, "release"))
    full = pd.read_csv(root / "reports/tables/final/full_arm_summary.csv")
    assert full["n"].sum() == cfg["dataset"]["expected_rows"]
    grid = pd.read_csv(root / "reports/tables/final/capacity_cost_grid.csv")
    assert (grid["contacts"] <= grid["cap_floor_qN"]).all()
    assert set(grid["q"]) == set(cfg["policy"]["q_grid"]) and set(grid["kappa"]) == set(cfg["policy"]["kappa_grid"])
