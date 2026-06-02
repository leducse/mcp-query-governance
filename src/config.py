"""Central configuration for the local MVP.

Everything is environment-overridable so the same code path can be pointed at a
local SQLite file (default) or a local/remote PostgreSQL instance standing in
for the RDS PostgreSQL demo warehouse described in ``MVP_SPEC.md`` §2.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_DIR = DATA_DIR / "sample"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
CATALOG_DIR = PROJECT_ROOT / "catalog"
LOG_DIR = OUTPUTS_DIR / "logs"

DEFAULT_SEED = 1337


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw not in (None, "") else default


@dataclass(frozen=True)
class DetectionConfig:
    """Anomaly detection + hybrid hard-rule parameters (MVP_SPEC §6)."""

    # RCF-style anomaly score threshold. SageMaker RCF flags roughly at >= 3.0
    # (~3 sigma); the local IsolationForest detector is normalised to the same
    # z-score scale so the threshold semantics carry over.
    anomaly_threshold: float = field(
        default_factory=lambda: _env_float("ANOMALY_THRESHOLD", 3.0)
    )
    # Hybrid hard cap: queries in a single 15-minute window above this are
    # flagged regardless of the ML score (catches "obvious disasters").
    hard_cap_queries_per_window: int = field(
        default_factory=lambda: _env_int("HARD_CAP_QUERIES_PER_WINDOW", 50)
    )
    window_minutes: int = field(
        default_factory=lambda: _env_int("WINDOW_MINUTES", 15)
    )


@dataclass(frozen=True)
class SyntheticConfig:
    """Synthetic audit-log generation parameters (MVP_SPEC §6.2)."""

    n_normal_principals: int = field(
        default_factory=lambda: _env_int("N_NORMAL_PRINCIPALS", 10)
    )
    baseline_days: int = field(
        default_factory=lambda: _env_int("BASELINE_DAYS", 7)
    )
    scoring_hours: int = field(
        default_factory=lambda: _env_int("SCORING_HOURS", 24)
    )
    seed: int = field(default_factory=lambda: _env_int("SEED", DEFAULT_SEED))


@dataclass(frozen=True)
class Config:
    """Top-level runtime configuration."""

    # DB backend: "sqlite" (default, zero-setup) or "postgres" (RDS stand-in).
    db_backend: str = field(
        default_factory=lambda: os.environ.get("DB_BACKEND", "sqlite").lower()
    )
    # SQLAlchemy-free: sqlite path or a libpq DSN / DATABASE_URL for postgres.
    sqlite_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("SQLITE_PATH", str(DATA_DIR / "query_audit.db"))
        )
    )
    database_url: str = field(
        default_factory=lambda: os.environ.get("DATABASE_URL", "")
    )
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    synthetic: SyntheticConfig = field(default_factory=SyntheticConfig)
    # Detector backend: "local" (IsolationForest) or "sagemaker" (RCF stub).
    detector_backend: str = field(
        default_factory=lambda: os.environ.get("DETECTOR_BACKEND", "local").lower()
    )


def load_config() -> Config:
    return Config()


def ensure_dirs() -> None:
    for path in (DATA_DIR, SAMPLE_DIR, OUTPUTS_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)
