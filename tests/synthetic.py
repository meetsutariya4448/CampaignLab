"""SYNTHETIC Hillstrom-format fixtures for tests. Never Hillstrom observations."""
from __future__ import annotations

import numpy as np

HEADER = ["recency", "history_segment", "history", "mens", "womens", "zip_code", "newbie", "channel", "segment", "visit", "conversion", "spend"]
SEGMENTS = ["No E-Mail", "Mens E-Mail", "Womens E-Mail"]
LABELS = ["1) $0 - $100", "2) $100 - $200", "3) $200 - $350", "4) $350 - $500", "5) $500 - $750", "6) $750 - $1,000", "7) $1,000 +"]
UPPER = [100, 200, 350, 500, 750, 1000]


def bucket_label(h: float) -> str:
    return LABELS[int(np.searchsorted(UPPER, h, side="left"))]


def make_rows(n: int = 600, seed: int = 0) -> list[list[str]]:
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        recency = int(rng.integers(1, 13))
        history = round(float(np.clip(rng.lognormal(5.0, 0.8), 29.99, 3000)), 2)
        mens, womens = int(rng.random() < 0.55), int(rng.random() < 0.55)
        zip_code = str(rng.choice(["Urban", "Surburban", "Rural"], p=[0.4, 0.45, 0.15]))
        newbie = int(rng.random() < 0.5)
        channel = str(rng.choice(["Phone", "Web", "Multichannel"], p=[0.44, 0.44, 0.12]))
        seg = int(rng.integers(0, 3))
        p = 0.10 + 0.06 * (seg == 1) * mens + 0.07 * (seg == 2) * womens + 0.02 * newbie
        visit = int(rng.random() < p)
        conversion = int(visit and rng.random() < 0.15)
        spend = round(float(rng.uniform(20, 400)), 2) if conversion else 0.0
        rows.append([str(recency), bucket_label(history), f"{history:.2f}", str(mens), str(womens), zip_code, str(newbie), channel,
                     SEGMENTS[seg], str(visit), str(conversion), "0" if spend == 0 else f"{spend:.2f}"])
    return rows


def to_bytes(rows, header=HEADER) -> bytes:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")
