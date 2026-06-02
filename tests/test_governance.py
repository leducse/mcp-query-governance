"""Lightweight unit tests (stdlib unittest, no DB needed for most).

Covers MVP_SPEC §14: parameter validation, RLS SQL build, and a smoke test that
the detector flags injected abuse end to end on a small synthetic sample.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.config import Config, DetectionConfig, SyntheticConfig
from src.db import Database
from src.governed.catalog import QueryCatalog
from src.governed.executor import ExecutionError, QueryExecutor
from src.sentinel.scoring import score_audit_log
from src.synthetic.generator import generate_audit_log

CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog"


def _sqlite_config(path: Path) -> Config:
    return Config(db_backend="sqlite", sqlite_path=path)


class ParameterValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db = Database(_sqlite_config(Path(self.tmp.name) / "t.db"))
        db.reset()
        db.seed_pipeline([("tenant-a", "NA", 2025, 100.0), ("tenant-b", "NA", 2025, 50.0)])
        self.executor = QueryExecutor(db, QueryCatalog(CATALOG_DIR))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_required_param(self) -> None:
        with self.assertRaises(ExecutionError) as ctx:
            self.executor.execute("pipeline_summary", {}, "tenant-a", "u1")
        self.assertEqual(ctx.exception.code, "MISSING_PARAM")

    def test_invalid_enum(self) -> None:
        with self.assertRaises(ExecutionError) as ctx:
            self.executor.execute(
                "pipeline_summary", {"fiscal_year": 2025, "region_code": "ZZ"}, "tenant-a", "u1"
            )
        self.assertEqual(ctx.exception.code, "INVALID_PARAM")

    def test_unknown_query(self) -> None:
        with self.assertRaises(ExecutionError) as ctx:
            self.executor.execute("does_not_exist", {"fiscal_year": 2025}, "tenant-a", "u1")
        self.assertEqual(ctx.exception.code, "CATALOG_NOT_FOUND")

    def test_missing_tenant_blocks_rls(self) -> None:
        with self.assertRaises(ExecutionError) as ctx:
            self.executor.execute("pipeline_summary", {"fiscal_year": 2025}, None, "u1")
        self.assertEqual(ctx.exception.code, "UNAUTHORIZED")

    def test_rls_injected_and_scoped(self) -> None:
        result = self.executor.execute(
            "pipeline_summary", {"fiscal_year": 2025}, "tenant-a", "u1"
        )
        self.assertIn("tenant_id = 'tenant-a'", result.executed_sql)
        self.assertNotIn("tenant-b", result.executed_sql)
        # RLS must actually scope rows: only tenant-a's row is returned.
        self.assertEqual(result.row_count, 1)
        self.assertEqual(result.data[0]["arr"], 100.0)


class DetectorSmokeTest(unittest.TestCase):
    def test_injected_abusers_flagged(self) -> None:
        synthetic = SyntheticConfig(n_normal_principals=8, baseline_days=5, scoring_hours=24, seed=1337)
        audit = generate_audit_log(synthetic)
        result = score_audit_log(
            audit_df=audit.rows,
            baseline_end=audit.baseline_end,
            scoring_start=audit.scoring_start,
            scoring_end=audit.scoring_end,
            detection=DetectionConfig(),
            detector_backend="local",
            random_state=synthetic.seed,
        )
        flagged = {f.principal_id for f in result.flagged}
        for abuser in audit.abusers:
            self.assertIn(abuser.principal_id, flagged)


if __name__ == "__main__":
    unittest.main()
