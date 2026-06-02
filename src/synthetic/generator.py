"""Deterministic synthetic ``query_audit`` generator with injected abuse.

Produces per-query rows for a population of normal principals plus a small set
of injected abusive principals (MVP_SPEC §6.2). The generator only fabricates
data; persistence and feature aggregation live elsewhere.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from ..config import SyntheticConfig

_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")

WAREHOUSE_TABLES = [
    "pipeline",
    "accounts",
    "opportunities",
    "regions",
    "fiscal_calendar",
    "products",
    "renewals",
    "usage_events",
    "support_tickets",
    "forecast_snapshots",
    "billing",
    "contracts",
]

GOVERNED_CLIENT = "governed-mcp"
SHADOW_CLIENT = "shadow-simulator"

GOVERNED_QUERY_IDS = ["pipeline_summary", "renewals_by_region", "account_health"]


@dataclass
class AbuseProfile:
    """Describes one injected abusive principal and why it should flag."""

    principal_id: str
    label: str
    description: str


@dataclass
class GeneratedAudit:
    rows: pd.DataFrame
    abusers: list[AbuseProfile]
    baseline_end: datetime
    scoring_start: datetime
    scoring_end: datetime
    config: SyntheticConfig = field(repr=False)


def _sql_hash(principal: str, table: str, variant: int) -> str:
    text = f"select * from {table} where principal='{principal}' v{variant}"
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _row_id(counter: int) -> str:
    return str(uuid.uuid5(_NAMESPACE, str(counter)))


class _RowBuilder:
    def __init__(self) -> None:
        self._counter = 0
        self._rows: list[dict] = []

    def add(
        self,
        ts: datetime,
        principal_id: str,
        client_id: str,
        table_name: str,
        bytes_scanned: int,
        row_count: int,
        duration_ms: int,
        status: str = "success",
        variant: int = 0,
    ) -> None:
        query_id = None
        if client_id == GOVERNED_CLIENT:
            query_id = GOVERNED_QUERY_IDS[variant % len(GOVERNED_QUERY_IDS)]
        self._rows.append(
            {
                "id": _row_id(self._counter),
                "ts": ts,
                "principal_id": principal_id,
                "client_id": client_id,
                "query_id": query_id,
                "sql_hash": _sql_hash(principal_id, table_name, variant),
                "table_name": table_name,
                "bytes_scanned": int(bytes_scanned),
                "row_count": int(row_count),
                "duration_ms": int(duration_ms),
                "status": status,
            }
        )
        self._counter += 1

    def frame(self) -> pd.DataFrame:
        df = pd.DataFrame(self._rows)
        df = df.sort_values("ts").reset_index(drop=True)
        # Store timestamps as ISO strings so they bind cleanly to SQLite/Postgres.
        df["ts"] = df["ts"].apply(lambda d: d.isoformat())
        return df


def _emit_normal_day(
    builder: _RowBuilder,
    rng: np.random.RandomState,
    principal: str,
    day_start: datetime,
) -> None:
    """One day of steady, low-volume, business-hours activity for a principal.

    Activity is emitted per 15-minute window (not per hour) so the baseline
    per-window distribution is tight and consistent: an active window holds a
    handful of light queries, which keeps benign bursts well below the abuse
    region.
    """

    for window_index in range(24 * 4):  # 96 fifteen-minute windows per day
        hour = window_index // 4
        # Interactive analysts work mostly business hours; rare off-hours noise.
        active_prob = 0.7 if 8 <= hour < 18 else 0.05
        if rng.rand() > active_prob:
            continue
        window_start = day_start + timedelta(minutes=15 * window_index)
        n_queries = int(rng.poisson(2) + 1)  # ~1-6 light queries per active window
        for _ in range(n_queries):
            offset = int(rng.randint(0, 15 * 60))
            ts = window_start + timedelta(seconds=offset)
            # 80% of legitimate traffic flows through the governed MCP path.
            client = GOVERNED_CLIENT if rng.rand() < 0.8 else SHADOW_CLIENT
            table = WAREHOUSE_TABLES[int(rng.randint(0, 5))]  # focused table set
            bytes_scanned = int(rng.lognormal(mean=14.0, sigma=0.5))  # ~1e6
            row_count = int(rng.randint(1, 500))
            duration_ms = int(rng.randint(40, 800))
            builder.add(
                ts=ts,
                principal_id=principal,
                client_id=client,
                table_name=table,
                bytes_scanned=bytes_scanned,
                row_count=row_count,
                duration_ms=duration_ms,
                variant=int(rng.randint(0, 3)),
            )


def _inject_volume_abuse(
    builder: _RowBuilder,
    rng: np.random.RandomState,
    principal: str,
    window_start: datetime,
    n_queries: int = 220,
) -> None:
    """Volume + cost spike: a shadow tool-loop scanning huge byte volumes."""

    for _ in range(n_queries):
        offset = int(rng.randint(0, 15 * 60))  # within a single 15-minute window
        ts = window_start + timedelta(seconds=offset)
        table = WAREHOUSE_TABLES[int(rng.randint(0, 3))]
        bytes_scanned = int(rng.lognormal(mean=20.0, sigma=0.4))  # ~5e8, full scans
        row_count = int(rng.randint(50_000, 500_000))
        duration_ms = int(rng.randint(3_000, 25_000))
        builder.add(
            ts=ts,
            principal_id=principal,
            client_id=SHADOW_CLIENT,
            table_name=table,
            bytes_scanned=bytes_scanned,
            row_count=row_count,
            duration_ms=duration_ms,
            variant=int(rng.randint(0, 8)),
        )


def _inject_fanout_abuse(
    builder: _RowBuilder,
    rng: np.random.RandomState,
    principal: str,
    window_start: datetime,
) -> None:
    """Schema-exploration burst: off-hours fan-out across many distinct tables.

    Volume stays under the hard cap on purpose so that only the ML detector
    catches it (demonstrates ML value beyond a static rule).
    """

    for i in range(40):
        offset = int(rng.randint(0, 15 * 60))
        ts = window_start + timedelta(seconds=offset)
        table = WAREHOUSE_TABLES[i % len(WAREHOUSE_TABLES)]  # touch all tables
        bytes_scanned = int(rng.lognormal(mean=15.0, sigma=0.5))
        row_count = int(rng.randint(1, 2_000))
        duration_ms = int(rng.randint(100, 1_500))
        builder.add(
            ts=ts,
            principal_id=principal,
            client_id=SHADOW_CLIENT,
            table_name=table,
            bytes_scanned=bytes_scanned,
            row_count=row_count,
            duration_ms=duration_ms,
            variant=int(rng.randint(0, 12)),
        )


def generate_audit_log(config: SyntheticConfig) -> GeneratedAudit:
    rng = np.random.RandomState(config.seed)

    now = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    scoring_end = now
    scoring_start = scoring_end - timedelta(hours=config.scoring_hours)
    baseline_end = scoring_start
    baseline_start = baseline_end - timedelta(days=config.baseline_days)

    builder = _RowBuilder()
    normal_principals = [f"analyst-{i:03d}" for i in range(1, config.n_normal_principals + 1)]

    # Baseline window: every principal behaves normally (this trains the model).
    total_days = config.baseline_days + (config.scoring_hours + 23) // 24
    for principal in normal_principals:
        day = baseline_start
        for _ in range(total_days + 1):
            _emit_normal_day(builder, rng, principal, day)
            day += timedelta(days=1)

    # Injected abusers behave normally during baseline, then spike in scoring.
    abuser_volume = "shadow-abuser-01"
    abuser_fanout = "shadow-abuser-02"
    for principal in (abuser_volume, abuser_fanout):
        day = baseline_start
        for _ in range(config.baseline_days):
            _emit_normal_day(builder, rng, principal, day)
            day += timedelta(days=1)

    # Volume/cost abuser: 220 queries in one off-hours 15-minute window.
    volume_window = scoring_start + timedelta(hours=2)
    _inject_volume_abuse(builder, rng, abuser_volume, volume_window)

    # Fan-out abuser: stays under the hard cap, only ML should catch it.
    fanout_window = scoring_start + timedelta(hours=3)
    _inject_fanout_abuse(builder, rng, abuser_fanout, fanout_window)

    abusers = [
        AbuseProfile(
            principal_id=abuser_volume,
            label="volume_cost_spike",
            description=(
                "220 shadow-client queries in one 15m window with ~5e8 bytes "
                "scanned each (tool-loop / full-table scans)."
            ),
        ),
        AbuseProfile(
            principal_id=abuser_fanout,
            label="offhours_fanout",
            description=(
                "Off-hours schema exploration across all tables, volume kept "
                "below the hard cap so only the ML detector flags it."
            ),
        ),
    ]

    return GeneratedAudit(
        rows=builder.frame(),
        abusers=abusers,
        baseline_end=baseline_end,
        scoring_start=scoring_start,
        scoring_end=scoring_end,
        config=config,
    )
