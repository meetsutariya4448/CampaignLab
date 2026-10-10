# Reproduction guide and clean-rerun record

## Requirements

- macOS or Linux with Python ≥ 3.12. Tested with **CPython 3.14.3** on macOS 26.6.2, Apple M1 Pro, 32 GB RAM.
- Network access to the original publisher URL. The CSV is downloaded, never redistributed.
- About 1 GB of disk for the environment. Peak memory stays well under 1 GB; bootstrap work runs in batches of 250 replicates.

## Commands

```bash
git clone <this repository> CampaignLab && cd CampaignLab
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock        # exact tested versions
.venv/bin/pip install --no-deps -e .
.venv/bin/python -m campaignlab.run all           # acquire → validate → develop → fit → select → lock → evaluate → release → report
.venv/bin/python -m campaignlab.run simulate      # synthetic known-truth validation (~5.5 min)
.venv/bin/python -m campaignlab.run report        # re-render the report including the simulation section
.venv/bin/python -m pytest                        # all tests; private-data tests skip if the CSV is absent
.venv/bin/python scripts/audit_public.py          # publication audit (no row-level/private content)
.venv/bin/python scripts/audit_claims.py          # reconcile narrative numbers with tables
```

Individual stages run with `python -m campaignlab.run <stage>`. Out-of-order access is refused:

- `evaluate` without a verified lock fails.
- `release` before `evaluate` fails.
- `lock` after an evaluation exists fails.

**Expected artifact:** 3,964,977 bytes, SHA-256 `0e5893329d8b93cefecc571777672028290ab69865718020c78c7284f291aece`. A different hash stops the pipeline and quarantines the download for investigation. Never update the expected hash silently.

**Private outputs** (git-ignored):

- `data/raw/` holds the exact bytes, stored read-only.
- `data/processed/campaignlab.duckdb` is the database.
- `artifacts/private/` holds the provenance and split manifests, models (JSON parameters), selection, lock manifest, evaluation record, the outcome-access log, and stage timings.

## Clean rerun record (2026-10-09, executed)

`scripts/clean_rerun.sh <empty dir> /Library/Frameworks/Python.framework/Versions/3.14/bin/python3` did the following:

1. Cloned commit `76bebc8` into a fresh directory.
2. Created a new venv from `requirements.lock`.
3. Downloaded the publisher CSV again; its hash matched the pin.
4. Ran every stage, the simulation and the full test suite.
5. Compared all artifacts with the original working copy using `scripts/compare_runs.py`.

| Check | Result |
|---|---|
| Tests in the fresh clone | **85 passed** (31.8 s), including the private pinned-artifact test, the synthetic end-to-end lock/access test and the slow simulation tests |
| Report artifacts (all tables, figures PNG/SVG, memo, technical report) | 75 byte-identical; 1 table (`development/sql_arm_summary.csv`) within tolerance (max abs diff 2.8e−13, DuckDB parallel float aggregation); 0 different |
| Private manifests (split CSV, split, provenance, selection, thresholds, lock) and model JSONs | Identical, ignoring timestamps and retrieval metadata |
| Lock manifest | Same code, config, environment, split, model, selection, prediction and **66 TEST action checksums**. Only `created_utc` and the provenance-manifest hash differ, because that manifest records the new download's time and headers; its data hash matched |
| Decisions | Identical: C* = men's-for-all, π* = S-learner, TEST category "excludes δ" |
| Tolerance rule (plan §11) | Deterministic artifacts exact; floating estimates within 1e−10 absolute / 1e−8 relative |

**Runtime** (fresh clone, M1 Pro). Recorded by the run; nothing here is a performance claim.

| Stage | Time |
|---|---|
| Whole script, including venv creation and installs | 7 min 37 s |
| acquire (download) | 0.8 s |
| validate | 1.2 s |
| develop | 2.4 s |
| fit | 9.6 s |
| select | 0.2 s |
| lock | 1.2 s |
| evaluate | 3.3 s |
| release | 5.2 s |
| report | 5.9 s |
| simulate | 330.9 s |
| pytest | 31.8 s |

**Bootstrap precision.** Policy-interval endpoints moved by at most 0.047 pp between 5,000 and 10,000 replicates (target ≤ 0.1 pp). Spend intervals from two independent 5,000-replicate streams differed by at most $0.019 (`reports/tables/final/full_spend_bootstrap.csv`).

**Original-run integrity.** The original TEST evaluation used the lock with SHA-256 `59e7e741…`. That lock was created 2026-10-10T01:03:14Z (UTC); TEST outcomes were first read at 01:03:37Z; no locked module, config or environment lock has changed since (verified by recomputing hashes).
