import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from campaignlab import governance as gov  # noqa: E402
from campaignlab.config import load_config  # noqa: E402


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture(autouse=True)
def isolated_governance(tmp_path, monkeypatch):
    """Keep unit tests from touching the real private state, access log, lock or evaluation record."""
    priv = tmp_path / "private"
    priv.mkdir()
    monkeypatch.setattr(gov, "STATE_PATH", priv / "state.json")
    monkeypatch.setattr(gov, "ACCESS_LOG_PATH", priv / "access.jsonl")
    monkeypatch.setattr(gov, "LOCK_PATH", priv / "lock.json")
    monkeypatch.setattr(gov, "EVAL_RECORD_PATH", priv / "eval.json")
    return priv


@pytest.fixture
def toy_frame():
    """Small synthetic randomized frame with covariates, arm and binary outcome."""
    rng = np.random.default_rng(11)
    n = 900
    df = pd.DataFrame({
        "row_id": [f"syn:{i}" for i in range(n)],
        "recency": rng.integers(1, 13, n),
        "history": np.round(rng.lognormal(5, 0.7, n) + 30, 2),
        "mens": rng.integers(0, 2, n), "womens": rng.integers(0, 2, n), "newbie": rng.integers(0, 2, n),
        "channel": rng.choice(["Phone", "Web", "Multichannel"], n), "zip_code": rng.choice(["Urban", "Surburban", "Rural"], n),
    })
    df["arm"] = np.tile([0, 1, 2], n // 3)
    p = 0.15 + 0.08 * (df["arm"] == 1) * df["mens"] + 0.08 * (df["arm"] == 2) * df["womens"]
    df["visit"] = (rng.random(n) < p).astype(int)
    df["conversion"] = ((df["visit"] == 1) & (rng.random(n) < 0.2)).astype(int)
    df["spend"] = np.where(df["conversion"] == 1, np.round(rng.uniform(10, 300, n), 2), 0.0)
    return df


PRIVATE = Path(__file__).resolve().parents[1] / "data" / "raw"


def private_data_available() -> bool:
    return any(PRIVATE.glob("*.csv"))
