"""Runnable entrypoint for the MCP Query Governance MVP demo.

End to end (local, no real AWS):
  1. Generate synthetic ``query_audit`` logs with injected abuse.
  2. Persist to the demo warehouse (SQLite by default; Postgres configurable).
  3. Run one governed Part 2 query (catalog -> param validation -> RLS -> SQL).
  4. Train + score the Part 1 Sentinel detector and flag principals.
  5. Emit notify-only alerts (stdout + log file) and write reports + a figure.

Run:  python -m src.main   (from the repo root, inside the .venv)
"""

from __future__ import annotations

import argparse

import numpy as np

from .config import CATALOG_DIR, LOG_DIR, OUTPUTS_DIR, SAMPLE_DIR, ensure_dirs, load_config
from .db import Database
from .governed.catalog import QueryCatalog
from .governed.executor import ExecutionError, QueryExecutor
from .report import write_figure, write_markdown_report, write_scoring_csv
from .sentinel.scoring import score_audit_log
from .synthetic.generator import generate_audit_log


def _seed_pipeline(db: Database) -> None:
    rng = np.random.RandomState(7)
    rows = []
    for tenant in ("tenant-a", "tenant-b"):
        for region in ("NA", "EMEA", "APAC"):
            for year in (2024, 2025):
                for _ in range(rng.randint(3, 8)):
                    rows.append((tenant, region, year, float(rng.randint(50_000, 900_000))))
    db.seed_pipeline(rows)


def _run_governed_demo(db: Database) -> None:
    catalog = QueryCatalog(CATALOG_DIR)
    executor = QueryExecutor(db, catalog)
    print("\n=== PART 2: GOVERNED MCP QUERY (catalog -> validation -> RLS) ===")
    print("Available catalog queries:", [q["query_id"] for q in catalog.list_queries()])
    try:
        result = executor.execute(
            query_id="pipeline_summary",
            parameters={"fiscal_year": 2025, "region_code": "NA"},
            tenant_id="tenant-a",
            principal_id="analyst-001",
        )
    except ExecutionError as exc:
        print(f"Governed query failed [{exc.code}]: {exc.message}")
        return
    print(f"correlation_id : {result.correlation_id}")
    print(f"executed_sql   : {result.executed_sql}")
    print(f"row_count      : {result.row_count} (truncated={result.truncated})")
    print(f"data           : {result.data}")

    print("\nValidation guardrail demo (server-side RLS is never optional):")
    try:
        executor.execute(
            query_id="pipeline_summary",
            parameters={"region_code": "NA"},  # missing required fiscal_year
            tenant_id="tenant-a",
            principal_id="analyst-001",
        )
    except ExecutionError as exc:
        print(f"  rejected as expected -> [{exc.code}] {exc.message}")


def _print_findings(result, abuser_ids: set[str]) -> None:
    print("\n=== PART 1: SENTINEL DETECTION RESULTS ===")
    print(
        f"Detector: {result.detector_name} | threshold={result.threshold} sigma | "
        f"hard_cap={result.hard_cap} queries/window"
    )
    print(f"Scored {len(result.findings)} principals; flagged {len(result.flagged)}.\n")
    for f in result.flagged:
        marker = "ABUSER" if f.principal_id in abuser_ids else "OTHER"
        print(
            f"[FLAGGED/{marker}] {f.principal_id}: score={f.max_anomaly_score:.2f} "
            f"hard_rule={f.hard_rule_triggered} peak_queries={f.peak_query_count} "
            f"peak_bytes={f.peak_sum_bytes_scanned:,}"
        )
        for c in f.top_features:
            print(
                f"    - {c.feature}: observed={c.observed:.1f} "
                f"baseline={c.baseline:.1f} ({c.pct_change:+.0f}% vs baseline)"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MCP Query Governance MVP demo")
    parser.add_argument("--seed", type=int, default=None, help="Override synthetic seed")
    parser.add_argument(
        "--skip-governed", action="store_true", help="Skip the Part 2 governed query demo"
    )
    args = parser.parse_args(argv)

    config = load_config()
    ensure_dirs()

    if args.seed is not None:
        import os

        os.environ["SEED"] = str(args.seed)
        config = load_config()

    print(f"Backend: db={config.db_backend} detector={config.detector_backend}")

    db = Database(config)
    db.reset()

    print("\n=== GENERATING SYNTHETIC QUERY AUDIT LOG ===")
    audit = generate_audit_log(config.synthetic)
    inserted = db.insert_audit_rows(audit.rows.to_dict("records"))
    print(
        f"Generated {inserted:,} audit rows for "
        f"{audit.rows['principal_id'].nunique()} principals "
        f"({audit.config.baseline_days}d baseline + {audit.config.scoring_hours}h scoring)."
    )

    # Commit a sample of the synthetic logs for the repo.
    sample = audit.rows.copy()
    sample["ts"] = sample["ts"].astype(str)
    sample.to_csv(SAMPLE_DIR / "query_audit_sample.csv", index=False)
    print(f"Wrote sample logs -> {SAMPLE_DIR / 'query_audit_sample.csv'}")

    _seed_pipeline(db)
    if not args.skip_governed:
        _run_governed_demo(db)

    audit_df = db.fetch_audit_df()
    result = score_audit_log(
        audit_df=audit_df,
        baseline_end=audit.baseline_end,
        scoring_start=audit.scoring_start,
        scoring_end=audit.scoring_end,
        detection=config.detection,
        detector_backend=config.detector_backend,
        random_state=config.synthetic.seed,
    )

    abuser_ids = {a.principal_id for a in audit.abusers}
    _print_findings(result, abuser_ids)

    from .sentinel.alerts import emit_alerts, print_alerts

    alerts = emit_alerts(
        result,
        log_path=LOG_DIR / "alerts.log",
        state_path=OUTPUTS_DIR / "enforcement_state.json",
    )
    print_alerts(alerts)

    csv_path = OUTPUTS_DIR / "scoring_report.csv"
    md_path = OUTPUTS_DIR / "scoring_report.md"
    fig_path = OUTPUTS_DIR / "figures" / "anomaly_scores.png"
    write_scoring_csv(result, csv_path)
    write_markdown_report(result, audit, md_path)
    write_figure(result, audit, fig_path)

    print("\n=== OUTPUTS ===")
    print(f"  {csv_path}")
    print(f"  {md_path}")
    print(f"  {fig_path}")
    print(f"  {LOG_DIR / 'alerts.log'}")
    print(f"  {OUTPUTS_DIR / 'enforcement_state.json'}")

    detected = {f.principal_id for f in result.flagged}
    missed = abuser_ids - detected
    if missed:
        print(f"\nWARNING: missed injected abusers: {sorted(missed)}")
        return 1
    print(f"\nSUCCESS: detected all injected abusers {sorted(abuser_ids)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
