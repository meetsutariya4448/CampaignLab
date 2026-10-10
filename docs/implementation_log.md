# Implementation log

Chronological record of milestones, artifacts, checks, deviations and remaining work. Times are local (America, 2026-10-09). Results quoted here are copied from executed artifacts in `reports/tables/`.

## M0 — Plan freeze (complete)

- Read blueprint README and documents 01–12; verified every blueprint file against `blueprint_quality_audit.json` hashes (all matched).
- Wrote `config/analysis.yaml`, `docs/analysis_plan.md` (SAP v1.0, with disclosure of prior inspection and freeze-time interpretation clarifications), `docs/data_dictionary.md`, `docs/rights_and_assumptions.md`.
- Git commit `60d32e3` records the freeze **before** any arm-by-outcome summary, split-level outcome table, model fit or policy selection.

## M1 — Environment and acquisition (complete)

- Python 3.12 (blueprint proposal) is not installed; CPython **3.14.3** used (deviation logged in SAP §13). Isolated `.venv`; exact versions in `requirements.lock` (numpy 2.5.3, pandas 3.0.6, scipy 1.18.1, statsmodels 0.15.0, scikit-learn 1.9.1, duckdb 1.5.6, matplotlib 3.11.2, seaborn 0.13.2, PyYAML 6.0.3, pytest 9.1.1).
- Acquired the original publisher CSV over the original HTTP URL (HTTP 200). **3,964,977 bytes; SHA-256 `0e5893329d8b93cefecc571777672028290ab69865718020c78c7284f291aece` (matches the pin)**; 64,001 CRLF line endings. Stored read-only in ignored `data/raw/`; private provenance manifest in `artifacts/private/`.
- **Relocation:** the project was first created under `~/Documents/Codex/2026-10-09/.../CampaignLab`; at the user's instruction it was copied with `rsync -a` (history preserved, `60d32e3` intact) to `~/Desktop/CampaignLab`, the venv was recreated there with identical pinned versions, no absolute paths needed changing (all paths derive from the package location), and the Phase 1 checks were re-run successfully from the new location. Final deliverables live in `outputs/CampaignLab_Final/` inside the project (git-ignored copies).

## M2 — Validation, split and SQL (complete)

- Python typed contract and DuckDB SQL contract (`sql/01_validate.sql`) both report **zero hard-check failures** (25 named checks).
- Quality facts reproduce the planning record exactly: arms 21,306 / 21,307 / 21,387; 9,394 visits; 578 conversions; 578 positive-spend rows; 1,072 full-row matching groups, 6,562 excess rows (7,634 rows involved, largest group 31); 56,209 distinct pre-treatment profiles (7,791 excess, largest 83); 5 history-bucket boundary cases (rounded 100 ×2, 200 ×2, 500 ×1). All retained.
- SQL and Python agree on all global counts, total history cents and split totals.
- Split executed exactly as frozen: **TRAIN 38,399 / VALIDATION 12,799 / TEST 12,802** (by arm 12,783/4,261/4,262; 12,784/4,261/4,262; 12,832/4,277/4,278); disjoint and complete; private manifest with membership checksum.
- Logical tables `covariates`, `descriptive`, `assignment`, `outcomes`, `split`; development view `dev_outcomes` excludes TEST.
- Code-level access control: development stages can load TRAIN/VALIDATION outcomes only; TEST needs a verified-lock token; full sample needs an evaluation-complete record; each outcome load is logged.
- Tests at this point: `test_data.py` 28 passed (incl. private pinned-artifact test), `test_inference.py` 19, `test_models.py` + `test_policy.py` 35, `test_pipeline.py` 1 (synthetic end-to-end access/lock test) — 83 passed.

## Remaining work

M3–M9 (below as they complete).
