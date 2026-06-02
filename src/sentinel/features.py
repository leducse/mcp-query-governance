"""Aggregate raw ``query_audit`` rows into per-principal/per-window features.

Each feature vector summarises one ``(principal_id, time_window)`` pair, matching
the schema described in ``ML_QUERY_MONITORING.md`` §3. Features are intentionally
explainable so alerts can name the contributing signal.
"""

from __future__ import annotations

import pandas as pd

from ..synthetic.generator import GOVERNED_CLIENT

# Numeric features fed to the anomaly detector. Order is stable so explanations
# can map model inputs back to human-readable names. ``hour_of_day`` is computed
# and reported for explainability but kept OUT of the model: a raw 0-23 hour is
# a poor IsolationForest input (midnight reads as a numeric extreme), which
# would flag benign off-hours windows. Off-hours abuse is still caught via its
# volume/bytes/fan-out signature.
FEATURE_COLUMNS: list[str] = [
    "query_count",          # query volume
    "sum_bytes_scanned",    # total bytes scanned (cost)
    "max_bytes_scanned",    # heaviest single query
    "distinct_tables",      # table fan-out
    "distinct_sql_hash",    # repetition / exploration breadth
]

# Explainability-only signals (reported, not fed to the detector). hour_of_day
# and shadow_ratio are both noisy as raw model inputs at 15-minute granularity
# (a single off-hours or all-shadow query would otherwise dominate), so they are
# surfaced as context in alerts instead of driving the score.
EXPLAIN_ONLY_COLUMNS: list[str] = ["hour_of_day", "shadow_ratio"]


def build_window_features(df: pd.DataFrame, window_minutes: int) -> pd.DataFrame:
    """Return a tidy frame of feature vectors indexed by principal + window."""

    if df.empty:
        return pd.DataFrame(
            columns=[
                "principal_id",
                "window_start",
                *FEATURE_COLUMNS,
                *EXPLAIN_ONLY_COLUMNS,
            ]
        )

    work = df.copy()
    work["ts"] = pd.to_datetime(work["ts"], utc=True)
    work["window_start"] = work["ts"].dt.floor(f"{window_minutes}min")
    work["is_shadow"] = (work["client_id"] != GOVERNED_CLIENT).astype(int)
    work["is_failed"] = (work["status"] != "success").astype(int)

    grouped = work.groupby(["principal_id", "window_start"], sort=True)
    feat = grouped.agg(
        query_count=("id", "size"),
        sum_bytes_scanned=("bytes_scanned", "sum"),
        max_bytes_scanned=("bytes_scanned", "max"),
        distinct_tables=("table_name", "nunique"),
        distinct_sql_hash=("sql_hash", "nunique"),
        shadow_queries=("is_shadow", "sum"),
        failed_queries=("is_failed", "sum"),
    ).reset_index()

    feat["shadow_ratio"] = feat["shadow_queries"] / feat["query_count"]
    feat["failed_ratio"] = feat["failed_queries"] / feat["query_count"]
    feat["hour_of_day"] = feat["window_start"].dt.hour

    ordered = [
        "principal_id",
        "window_start",
        *FEATURE_COLUMNS,
        *EXPLAIN_ONLY_COLUMNS,
        "failed_ratio",
    ]
    return feat[ordered]
