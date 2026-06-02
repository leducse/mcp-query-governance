"""Local stand-in for the executor Lambda (MVP_SPEC §5).

Validates parameters against the catalog, injects row-level security
server-side (never trusting the LLM to add the filter), executes the templated
SQL, writes a governed ``query_audit`` row, and returns data + executed SQL +
metadata. This is the "controlled execution plane" of Part 2, runnable locally.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..db import Database
from ..synthetic.generator import GOVERNED_CLIENT
from .catalog import CatalogEntry, QueryCatalog

# bytes_scanned proxy for governed queries (MVP_SPEC §4.1: row_count x constant).
_BYTES_PER_ROW_PROXY = 4096

_TOKEN_RE = re.compile(r":([a-zA-Z_][a-zA-Z0-9_]*)")


class ExecutionError(Exception):
    """Structured error mirroring the API error codes in MVP_SPEC §5.1."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ExecutionResult:
    correlation_id: str
    query_id: str
    version: str
    executed_sql: str
    row_count: int
    data: list[dict[str, Any]]
    truncated: bool
    duration_ms: int
    extras: dict[str, Any] = field(default_factory=dict)


def _validate_params(entry: CatalogEntry, params: dict[str, Any]) -> dict[str, Any]:
    validated: dict[str, Any] = {}
    for name, spec in entry.parameters.items():
        required = bool(spec.get("required", False))
        if name not in params or params[name] is None:
            if required:
                raise ExecutionError("MISSING_PARAM", f"Missing required parameter: {name}")
            continue
        value = params[name]
        ptype = spec.get("type", "string")
        if ptype == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ExecutionError("INVALID_PARAM", f"Parameter {name} must be an integer")
        elif ptype == "string":
            if not isinstance(value, str):
                raise ExecutionError("INVALID_PARAM", f"Parameter {name} must be a string")
        enum = spec.get("enum")
        if enum is not None and value not in enum:
            raise ExecutionError(
                "INVALID_PARAM", f"Parameter {name}={value!r} not in allowed values {enum}"
            )
        validated[name] = value
    return validated


def _build_rls_clause(entry: CatalogEntry, provided: dict[str, Any]) -> str:
    """Server-side RLS + any provided optional equality filters, as one clause."""

    parts = [f"AND {entry.rls_column} = :__tenant__"]
    for param_name, column in entry.optional_filters.items():
        if param_name in provided:
            parts.append(f"AND {column} = :{param_name}")
    return " ".join(parts)


def _literal(value: Any) -> str:
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


class QueryExecutor:
    def __init__(self, db: Database, catalog: QueryCatalog) -> None:
        self.db = db
        self.catalog = catalog

    def execute(
        self,
        query_id: str,
        parameters: dict[str, Any],
        tenant_id: str | None,
        principal_id: str,
        correlation_id: str | None = None,
    ) -> ExecutionResult:
        if not tenant_id:
            raise ExecutionError("UNAUTHORIZED", "Missing tenant_id (RLS cannot be enforced)")

        correlation_id = correlation_id or str(uuid.uuid4())
        entry = self.catalog.load(query_id)
        if entry is None:
            raise ExecutionError("CATALOG_NOT_FOUND", f"Unknown query_id: {query_id}")

        validated = _validate_params(entry, parameters)

        rls_clause = _build_rls_clause(entry, validated)
        sql_with_rls = entry.sql_template.replace("{{RLS}}", rls_clause)

        bind_values: dict[str, Any] = dict(validated)
        bind_values["__tenant__"] = tenant_id

        ordered: list[Any] = []
        placeholder = self.db._ph()

        def _sub(match: re.Match) -> str:
            token = match.group(1)
            ordered.append(bind_values[token])
            return placeholder

        parameterized_sql = _TOKEN_RE.sub(_sub, sql_with_rls)
        parameterized_sql = f"{parameterized_sql} LIMIT {entry.max_rows + 1}"

        # Transparency: executed SQL with literals substituted (post-RLS).
        display_ordered = list(ordered)
        display_iter = iter(display_ordered)
        executed_sql = _TOKEN_RE.sub(
            lambda m: _literal(bind_values[m.group(1)]), sql_with_rls
        )
        executed_sql = f"{executed_sql} LIMIT {entry.max_rows}"

        start = time.perf_counter()
        status = "success"
        try:
            cols, raw_rows = self.db.execute_select(parameterized_sql, ordered)
        except Exception as exc:  # surface DB errors as structured failures
            status = "failed"
            self._audit(entry, principal_id, executed_sql, 0, 0, start, status)
            raise ExecutionError("EXECUTION_FAILED", str(exc)) from exc
        duration_ms = int((time.perf_counter() - start) * 1000)

        truncated = len(raw_rows) > entry.max_rows
        rows = raw_rows[: entry.max_rows]
        data = [dict(zip(cols, r)) for r in rows]
        row_count = len(data)

        self._audit(entry, principal_id, executed_sql, row_count, duration_ms, start, status)

        return ExecutionResult(
            correlation_id=correlation_id,
            query_id=entry.query_id,
            version=entry.version,
            executed_sql=executed_sql,
            row_count=row_count,
            data=data,
            truncated=truncated,
            duration_ms=duration_ms,
            extras={"client_id": GOVERNED_CLIENT, "tenant_id": tenant_id},
        )

    def _audit(
        self,
        entry: CatalogEntry,
        principal_id: str,
        executed_sql: str,
        row_count: int,
        duration_ms: int,
        start: float,
        status: str,
    ) -> None:
        table_match = re.search(r"FROM\s+([a-zA-Z_][a-zA-Z0-9_]*)", entry.sql_template)
        table_name = table_match.group(1) if table_match else "unknown"
        row = {
            "id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "principal_id": principal_id,
            "client_id": GOVERNED_CLIENT,
            "query_id": entry.query_id,
            "sql_hash": hashlib.md5(executed_sql.encode("utf-8")).hexdigest(),
            "table_name": table_name,
            "bytes_scanned": row_count * _BYTES_PER_ROW_PROXY,
            "row_count": row_count,
            "duration_ms": duration_ms,
            "status": status,
        }
        self.db.insert_audit_rows([row])
