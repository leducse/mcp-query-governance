"""Database access layer for the demo warehouse + ``query_audit`` table.

Defaults to local SQLite (zero setup) but is configurable to a PostgreSQL
instance that stands in for the RDS PostgreSQL warehouse in ``MVP_SPEC.md`` §2.
The two backends share one schema and one set of helpers so the AWS swap is a
config change, not a code rewrite.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Sequence

import pandas as pd

from .config import Config

QUERY_AUDIT_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS query_audit (
    id            TEXT PRIMARY KEY,
    ts            TEXT NOT NULL,
    principal_id  TEXT NOT NULL,
    client_id     TEXT NOT NULL,
    query_id      TEXT,
    sql_hash      TEXT NOT NULL,
    table_name    TEXT NOT NULL,
    bytes_scanned INTEGER NOT NULL,
    row_count     INTEGER NOT NULL,
    duration_ms   INTEGER NOT NULL,
    status        TEXT NOT NULL
);
"""

QUERY_AUDIT_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS query_audit (
    id            UUID PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL,
    principal_id  TEXT NOT NULL,
    client_id     TEXT NOT NULL,
    query_id      TEXT,
    sql_hash      TEXT NOT NULL,
    table_name    TEXT NOT NULL,
    bytes_scanned BIGINT NOT NULL,
    row_count     INTEGER NOT NULL,
    duration_ms   INTEGER NOT NULL,
    status        TEXT NOT NULL
);
"""

# Minimal seed warehouse table used by the Part 2 governed executor (RLS demo).
PIPELINE_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS pipeline (
    tenant_id    TEXT NOT NULL,
    region_code  TEXT NOT NULL,
    fiscal_year  INTEGER NOT NULL,
    arr          REAL NOT NULL
);
"""

PIPELINE_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS pipeline (
    tenant_id    TEXT NOT NULL,
    region_code  TEXT NOT NULL,
    fiscal_year  INTEGER NOT NULL,
    arr          NUMERIC NOT NULL
);
"""

AUDIT_COLUMNS = (
    "id",
    "ts",
    "principal_id",
    "client_id",
    "query_id",
    "sql_hash",
    "table_name",
    "bytes_scanned",
    "row_count",
    "duration_ms",
    "status",
)


class Database:
    """Thin wrapper exposing the small surface this MVP needs.

    The paramstyle differs between backends (``?`` for sqlite, ``%s`` for
    psycopg2); :meth:`_ph` hides that so callers write backend-agnostic SQL.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.backend = config.db_backend
        if self.backend not in ("sqlite", "postgres"):
            raise ValueError(f"Unsupported DB_BACKEND: {self.backend!r}")

    def _connect(self) -> Any:
        if self.backend == "sqlite":
            self.config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.config.sqlite_path)
            conn.row_factory = sqlite3.Row
            return conn
        try:
            import psycopg2  # type: ignore
            import psycopg2.extras  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "DB_BACKEND=postgres requires psycopg2-binary "
                "(uncomment it in requirements.txt)."
            ) from exc
        dsn = self.config.database_url
        if not dsn:
            raise RuntimeError("DB_BACKEND=postgres requires DATABASE_URL to be set.")
        return psycopg2.connect(dsn)

    @contextmanager
    def connect(self) -> Iterator[Any]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ph(self) -> str:
        return "?" if self.backend == "sqlite" else "%s"

    def init_schema(self) -> None:
        with self.connect() as conn:
            cur = conn.cursor()
            if self.backend == "sqlite":
                cur.execute(QUERY_AUDIT_DDL_SQLITE)
                cur.execute(PIPELINE_DDL_SQLITE)
            else:
                cur.execute(QUERY_AUDIT_DDL_POSTGRES)
                cur.execute(PIPELINE_DDL_POSTGRES)

    def reset(self) -> None:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute("DROP TABLE IF EXISTS query_audit")
            cur.execute("DROP TABLE IF EXISTS pipeline")
        self.init_schema()

    def insert_audit_rows(self, rows: Sequence[dict[str, Any]]) -> int:
        if not rows:
            return 0
        ph = self._ph()
        placeholders = ", ".join([ph] * len(AUDIT_COLUMNS))
        sql = (
            f"INSERT INTO query_audit ({', '.join(AUDIT_COLUMNS)}) "
            f"VALUES ({placeholders})"
        )
        payload = [tuple(r[c] for c in AUDIT_COLUMNS) for r in rows]
        with self.connect() as conn:
            cur = conn.cursor()
            cur.executemany(sql, payload)
        return len(payload)

    def seed_pipeline(self, rows: Iterable[Sequence[Any]]) -> None:
        ph = self._ph()
        sql = (
            "INSERT INTO pipeline (tenant_id, region_code, fiscal_year, arr) "
            f"VALUES ({ph}, {ph}, {ph}, {ph})"
        )
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM pipeline")
            cur.executemany(sql, list(rows))

    def fetch_audit_df(self) -> pd.DataFrame:
        with self.connect() as conn:
            df = pd.read_sql_query(
                "SELECT * FROM query_audit ORDER BY ts", conn
            )
        if not df.empty:
            df["ts"] = pd.to_datetime(df["ts"], utc=True, format="ISO8601")
        return df

    def execute_select(self, sql: str, params: Sequence[Any]) -> tuple[list[str], list[tuple]]:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, tuple(params))
            cols = [d[0] for d in cur.description]
            data = [tuple(row) for row in cur.fetchall()]
        return cols, data
