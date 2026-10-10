#!/usr/bin/env bash
# Assemble final deliverables in outputs/CampaignLab_Final and a publication-ready ZIP built from
# committed, tracked files only (git archive), then audit the ZIP for row-level/private content.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/outputs/CampaignLab_Final"
rm -rf "$OUT"
mkdir -p "$OUT"
cp -R "$ROOT/reports" "$OUT/reports"
mkdir -p "$OUT/docs"
for f in analysis_plan data_dictionary rights_and_assumptions implementation_log reproduction case_study interview_prep evidence_ledger resume_bullets; do
  cp "$ROOT/docs/$f.md" "$OUT/docs/"
done
cp "$ROOT/README.md" "$OUT/README_repository.md"
cp "$ROOT/docs/final_quality_audit.md" "$OUT/final_quality_audit.md"
cp "$ROOT/docs/deliverables_index.md" "$OUT/00_INDEX.md"
git -C "$ROOT" archive --format=zip --prefix=CampaignLab/ -o "$OUT/CampaignLab_publication_ready.zip" HEAD
"$ROOT/.venv/bin/python" "$ROOT/scripts/audit_public.py" --zip "$OUT/CampaignLab_publication_ready.zip"
( cd "$OUT" && find . -type f ! -name 'SHA256SUMS.txt' -print0 | sort -z | xargs -0 shasum -a 256 > SHA256SUMS.txt )
echo "deliverables in $OUT"
