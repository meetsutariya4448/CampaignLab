#!/usr/bin/env bash
# Clean local rerun: fresh clone of the committed repository, fresh venv from requirements.lock,
# fresh download of the publisher CSV, every pipeline stage, simulation and tests; then compare
# all artifacts with the original working copy.
#   usage: scripts/clean_rerun.sh <empty-target-dir> [python-interpreter]
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$1"
PY="${2:-python3}"
mkdir -p "$DEST"
[ -z "$(ls -A "$DEST")" ] || { echo "target directory must be empty"; exit 1; }
START=$(date +%s)
git clone --quiet "$SRC" "$DEST/CampaignLab"
cd "$DEST/CampaignLab"
"$PY" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.lock
.venv/bin/pip install --quiet --no-deps -e .
T0=$(date +%s)
.venv/bin/python -m campaignlab.run all
.venv/bin/python -m campaignlab.run simulate
.venv/bin/python -m campaignlab.run report
T1=$(date +%s)
.venv/bin/python -m pytest -q -p no:cacheprovider | tee "$DEST/pytest.txt"
T2=$(date +%s)
.venv/bin/python scripts/compare_runs.py "$SRC" "$DEST/CampaignLab" | tee "$DEST/compare.txt"
echo "{\"setup_seconds\": $((T0-START)), \"pipeline_seconds\": $((T1-T0)), \"tests_seconds\": $((T2-T1))}" | tee "$DEST/timing.json"
