"""Reconcile numbers quoted in public narrative documents against the executed aggregate tables.

Extracts signed/unsigned decimals followed by 'pp', '%', or preceded by '$' (and CI pairs) and checks each
against the set of values in reports/tables (as-is, x100, rounded to the quoted precision). Unmatched numbers
are listed for manual review; exits non-zero if any remain unexplained.
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DOCS = ["README.md", "reports/executive_memo.md", "reports/technical_report.md", "docs/case_study.md", "docs/interview_prep.md",
        "docs/evidence_ledger.md", "docs/resume_bullets.md"]
ALLOW = {"97.5": "interval level of the Bonferroni simultaneous CI (method constant)",
         "$29.99": "illustrative history value in an interview example (observed minimum history; planning record)"}
NUM = re.compile(r"(?<![\w.])([+\-−]?\$?\d+\.\d+)\s*(pp|%)?")


def table_values():
    vals = set()
    for p in (ROOT / "reports" / "tables").rglob("*"):
        if p.suffix == ".csv":
            df = pd.read_csv(p)
            nums = df.select_dtypes("number").to_numpy().ravel()
        elif p.suffix == ".json":
            nums = []
            def walk(o):
                if isinstance(o, dict):
                    [walk(v) for v in o.values()]
                elif isinstance(o, list):
                    [walk(v) for v in o]
                elif isinstance(o, (int, float)) and not isinstance(o, bool):
                    nums.append(o)
            walk(json.loads(p.read_text()))
        else:
            continue
        for x in nums:
            if x == x:
                for v in (x, 100 * x, -x, -100 * x, x / 100):
                    vals.add(v)
    return vals


def matches(q: str, vals) -> bool:
    s = q.replace("−", "-").replace("$", "").replace("+", "")
    x = float(s)
    d = len(s.split(".")[1])
    tol = 0.5 * 10 ** (-d) + 1e-12
    return any(abs(v - x) <= tol for v in vals)


def main():
    vals = table_values()
    report = {}
    for doc in DOCS:
        p = ROOT / doc
        if not p.exists():
            continue
        text = p.read_text()
        unmatched = sorted({m.group(1) for m in NUM.finditer(text) if not matches(m.group(1), vals)})
        report[doc] = {"numbers_checked": len(NUM.findall(text)), "allowlisted": {u: ALLOW[u] for u in unmatched if u in ALLOW},
                       "unmatched": [u for u in unmatched if u not in ALLOW]}
    out = ROOT / "reports" / "claims_audit.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    for doc, r in report.items():
        print(f"{doc}: {r['numbers_checked']} numbers, unmatched: {r['unmatched']}")
    sys.exit(1 if any(r["unmatched"] for r in report.values()) else 0)


if __name__ == "__main__":
    main()
