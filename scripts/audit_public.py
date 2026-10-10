"""Audit every file that would be published (git-tracked + untracked-not-ignored) for row-level or private content.

Usage: python scripts/audit_public.py [--zip path/to/archive.zip]
Writes reports/publication_audit.json and exits non-zero on any failure.
"""
import argparse
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATHS = [r"^data/", r"^artifacts/private/", r"^artifacts/dev/", r"\.duckdb", r"\.pkl$", r"\.pickle$", r"\.joblib$", r"\.parquet$",
                   r"\.ipynb$", r"^\.venv/", r"__pycache__", r"Kevin_Hillstrom.*\.csv$", r"^outputs/"]
ROW_ID = re.compile(r"hillstrom-2008-v1:\d+")
RAW_HEADER = "recency,history_segment,history,mens,womens,zip_code,newbie,channel,segment,visit,conversion,spend"
ROW_COLUMNS = {"row_id", "split_key", "source_ordinal", "partition"}
MAX_TABLE_ROWS = 2000


def published_files():
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True)
    return sorted(set(out.stdout.split()))


DATA_LINE = re.compile(r"^\d+,[^,]*,\d+(\.\d+)?,[01],[01],")


def audit_text(name: str, text: str, problems: list):
    ids = set(ROW_ID.findall(text))
    if len(ids) > 3:
        problems.append(f"{name}: contains {len(ids)} distinct concrete row IDs")
    for line in text.splitlines():
        if ROW_ID.search(line) and re.search(r"\b(TRAIN|VALIDATION|TEST)\b", line):
            problems.append(f"{name}: row ID together with a partition label")
            break
    lines = text.splitlines()
    for i, line in enumerate(lines[:-1]):
        if line.strip() == RAW_HEADER and DATA_LINE.match(lines[i + 1].strip()):
            problems.append(f"{name}: raw CSV header followed by data rows")
            break
    if sum(bool(DATA_LINE.match(l)) for l in lines) > 20:
        problems.append(f"{name}: contains many raw-format data lines")
    if name.endswith(".csv"):
        lines = text.splitlines()
        header = set(lines[0].split(",")) if lines else set()
        if header & ROW_COLUMNS:
            problems.append(f"{name}: CSV has row-level column(s) {sorted(header & ROW_COLUMNS)}")
        if len(lines) - 1 > MAX_TABLE_ROWS:
            problems.append(f"{name}: {len(lines) - 1} rows exceeds the aggregate-table limit")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip")
    args = ap.parse_args()
    problems, checked = [], 0
    if args.zip:
        z = zipfile.ZipFile(args.zip)
        entries = [(n, lambda n=n: z.read(n)) for n in z.namelist() if not n.endswith("/")]
        names = [n.split("/", 1)[1] if "/" in n else n for n, _ in entries]
    else:
        names = published_files()
        entries = [(n, lambda n=n: (ROOT / n).read_bytes()) for n in names]
    for (name, read), rel in zip(entries, names):
        for pat in FORBIDDEN_PATHS:
            if re.search(pat, rel):
                problems.append(f"{rel}: forbidden path pattern {pat}")
        data = read()
        if len(data) > 5_000_000:
            problems.append(f"{rel}: unexpectedly large file ({len(data)} bytes)")
        if rel.endswith((".py", ".md", ".csv", ".json", ".sql", ".yaml", ".toml", ".txt", ".lock", ".svg", ".sh")) or "." not in Path(rel).name:
            audit_text(rel, data.decode("utf-8", errors="replace"), problems)
        checked += 1
    result = {"source": args.zip or "git working tree (tracked + untracked-not-ignored)", "files_checked": checked, "problems": problems,
              "passed": not problems,
              "checks": ["forbidden paths (raw data, databases, private artifacts, models, notebooks, env, outputs)", ">3 concrete row IDs or row ID with partition label",
                         "raw CSV header followed by data / raw-format data lines", "row-level CSV columns", f"tables over {MAX_TABLE_ROWS} rows", "files over 5 MB"]}
    if not args.zip:
        (ROOT / "reports" / "publication_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("files_checked", "passed")}), *problems, sep="\n")
    sys.exit(0 if not problems else 1)


if __name__ == "__main__":
    main()
