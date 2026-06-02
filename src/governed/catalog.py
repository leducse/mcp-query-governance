"""Local stand-in for the S3 query catalog (MVP_SPEC §4.2, §5.2).

A directory of versioned JSON query definitions plus an ``index.json``. In
production this is an S3 bucket with versioning + an approval workflow; the
loader interface is identical so the swap is storage-only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CatalogEntry:
    query_id: str
    version: str
    description: str
    parameters: dict[str, dict[str, Any]]
    sql_template: str
    rls_column: str
    optional_filters: dict[str, str]
    max_rows: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CatalogEntry":
        return cls(
            query_id=data["query_id"],
            version=data.get("version", "0.0.0"),
            description=data.get("description", ""),
            parameters=data.get("parameters", {}),
            sql_template=data["sql_template"],
            rls_column=data.get("rls_column", "tenant_id"),
            optional_filters=data.get("optional_filters", {}),
            max_rows=int(data.get("max_rows", 500)),
        )


class QueryCatalog:
    def __init__(self, catalog_dir: Path) -> None:
        self.catalog_dir = catalog_dir

    def list_queries(self) -> list[dict[str, str]]:
        index_path = self.catalog_dir / "index.json"
        if not index_path.exists():
            return []
        index = json.loads(index_path.read_text())
        return index.get("queries", [])

    def load(self, query_id: str) -> CatalogEntry | None:
        path = self.catalog_dir / f"{query_id}.json"
        if not path.exists():
            return None
        return CatalogEntry.from_dict(json.loads(path.read_text()))
