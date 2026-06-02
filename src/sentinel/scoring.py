"""Batch scoring: train on baseline windows, score recent windows, explain.

Mirrors the MVP_SPEC §6.1 pipeline (feature aggregation -> RCF-style scoring ->
hybrid hard-rule -> flag) and the explainability requirement from
``ML_QUERY_MONITORING.md`` §5.3 (top contributing features per flag).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from ..config import DetectionConfig
from .detector import AnomalyDetector, build_detector
from .features import FEATURE_COLUMNS, build_window_features

# Features whose magnitude is the anomaly signal (used to explain "why flagged").
_EXPLAIN_FEATURES = [
    "query_count",
    "sum_bytes_scanned",
    "max_bytes_scanned",
    "distinct_tables",
    "shadow_ratio",
    "hour_of_day",
]


@dataclass
class FeatureContribution:
    feature: str
    observed: float
    baseline: float
    pct_change: float


@dataclass
class PrincipalFinding:
    principal_id: str
    flagged: bool
    state: str
    max_anomaly_score: float
    hard_rule_triggered: bool
    peak_window: datetime | None
    peak_query_count: int
    peak_sum_bytes_scanned: int
    top_features: list[FeatureContribution] = field(default_factory=list)


@dataclass
class ScoringResult:
    scored_windows: pd.DataFrame
    findings: list[PrincipalFinding]
    threshold: float
    hard_cap: int
    detector_name: str

    @property
    def flagged(self) -> list[PrincipalFinding]:
        return [f for f in self.findings if f.flagged]


def _baseline_stats(baseline_feat: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Per-principal median feature values used as the explanation baseline."""

    stats: dict[str, dict[str, float]] = {}
    for principal, grp in baseline_feat.groupby("principal_id"):
        stats[principal] = {
            col: float(grp[col].median()) for col in _EXPLAIN_FEATURES
        }
    return stats


def _explain(
    row: pd.Series,
    baseline: dict[str, float] | None,
) -> list[FeatureContribution]:
    contributions: list[FeatureContribution] = []
    for feature in _EXPLAIN_FEATURES:
        observed = float(row[feature])
        base = float(baseline[feature]) if baseline else 0.0
        denom = base if base != 0 else 1.0
        pct = (observed - base) / denom * 100.0
        contributions.append(
            FeatureContribution(
                feature=feature,
                observed=observed,
                baseline=base,
                pct_change=pct,
            )
        )
    contributions.sort(key=lambda c: abs(c.pct_change), reverse=True)
    return contributions[:3]


def score_audit_log(
    audit_df: pd.DataFrame,
    baseline_end: datetime,
    scoring_start: datetime,
    detection: DetectionConfig,
    scoring_end: datetime | None = None,
    detector: AnomalyDetector | None = None,
    detector_backend: str = "local",
    random_state: int = 1337,
) -> ScoringResult:
    feat = build_window_features(audit_df, detection.window_minutes)
    if feat.empty:
        raise ValueError("No audit data to score.")

    baseline_mask = feat["window_start"] < pd.Timestamp(baseline_end)
    scoring_mask = feat["window_start"] >= pd.Timestamp(scoring_start)
    if scoring_end is not None:
        scoring_mask &= feat["window_start"] < pd.Timestamp(scoring_end)
    baseline_feat = feat[baseline_mask].copy()
    scoring_feat = feat[scoring_mask].copy()

    if baseline_feat.empty or scoring_feat.empty:
        raise ValueError("Baseline or scoring window set is empty; check time ranges.")

    if detector is None:
        detector = build_detector(detector_backend, random_state=random_state)
    detector.fit(baseline_feat[FEATURE_COLUMNS].to_numpy())

    scores = detector.score(scoring_feat[FEATURE_COLUMNS].to_numpy())
    scoring_feat = scoring_feat.assign(anomaly_score=scores)
    scoring_feat["hard_rule_triggered"] = (
        scoring_feat["query_count"] > detection.hard_cap_queries_per_window
    )
    scoring_feat["flagged"] = (
        (scoring_feat["anomaly_score"] >= detection.anomaly_threshold)
        | scoring_feat["hard_rule_triggered"]
    )

    baseline_stats = _baseline_stats(baseline_feat)

    findings: list[PrincipalFinding] = []
    for principal, grp in scoring_feat.groupby("principal_id"):
        peak_idx = grp["anomaly_score"].idxmax()
        peak = grp.loc[peak_idx]
        any_flag = bool(grp["flagged"].any())
        hard_rule = bool(grp["hard_rule_triggered"].any())
        # Explain using the window that drove the flag (peak score).
        top = _explain(peak, baseline_stats.get(principal))
        findings.append(
            PrincipalFinding(
                principal_id=principal,
                flagged=any_flag,
                state="flagged" if any_flag else "normal",
                max_anomaly_score=float(grp["anomaly_score"].max()),
                hard_rule_triggered=hard_rule,
                peak_window=peak["window_start"].to_pydatetime(),
                peak_query_count=int(peak["query_count"]),
                peak_sum_bytes_scanned=int(peak["sum_bytes_scanned"]),
                top_features=top,
            )
        )

    findings.sort(key=lambda f: f.max_anomaly_score, reverse=True)

    return ScoringResult(
        scored_windows=scoring_feat.reset_index(drop=True),
        findings=findings,
        threshold=detection.anomaly_threshold,
        hard_cap=detection.hard_cap_queries_per_window,
        detector_name=type(detector).__name__,
    )
