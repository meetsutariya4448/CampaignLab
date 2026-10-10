"""Frozen configuration access and project paths."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(os.environ.get("CAMPAIGNLAB_ROOT", Path(__file__).resolve().parents[2]))
CONFIG_PATH = ROOT / "config" / "analysis.yaml"

PRIVATE_DIR = ROOT / "artifacts" / "private"
TABLES_DIR = ROOT / "reports" / "tables"
FIGURES_DIR = ROOT / "reports" / "figures"
SQL_DIR = ROOT / "sql"


def load_config(path: Path | None = None) -> dict:
    with open(path or CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def rng_for(cfg: dict, purpose: str) -> np.random.Generator:
    """Purpose-specific RNG stream derived from the primary seed (never reused across purposes)."""
    streams = cfg["seeds"]["streams"]
    if purpose not in streams:
        raise KeyError(f"unknown RNG purpose {purpose!r}; declare it in config seeds.streams")
    seq = np.random.SeedSequence(cfg["seeds"]["primary"], spawn_key=(int(streams[purpose]),))
    return np.random.default_rng(seq)


def seed_int_for(cfg: dict, purpose: str) -> int:
    """Integer seed for APIs (e.g. scikit-learn) that take an int, derived from the same stream."""
    streams = cfg["seeds"]["streams"]
    seq = np.random.SeedSequence(cfg["seeds"]["primary"], spawn_key=(int(streams[purpose]),))
    return int(seq.generate_state(1, dtype=np.uint32)[0])


ARM_NAMES = {0: "No E-Mail", 1: "Mens E-Mail", 2: "Womens E-Mail"}
ARM_SHORT = {0: "0", 1: "M", 2: "W"}
ARM_CODES = {v: k for k, v in ARM_NAMES.items()}
