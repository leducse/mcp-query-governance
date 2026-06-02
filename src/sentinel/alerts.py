"""Notify-only enforcement (MVP_SPEC §6.3): log + simulated Slack/EventBridge.

No throttle, no auto-suspend. Each flagged principal moves to the ``flagged``
state and produces a structured alert that, in production, SNS would deliver to
Slack and EventBridge would route to an enforcement Lambda. Here those are
simulated: written to stdout and a log file, with state persisted to a local
JSON file standing in for the DynamoDB ``enforcement_state`` table.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .scoring import PrincipalFinding, ScoringResult

GOVERNED_MCP_DOC = "https://github.com/your-org/mcp-query-governance#governed-mcp"

logger = logging.getLogger("sentinel.alerts")


def _configure_logger(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    file_handler = logging.FileHandler(log_path, mode="w")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.propagate = False


def _build_alert(finding: PrincipalFinding, result: ScoringResult) -> dict[str, Any]:
    reasons = []
    if finding.hard_rule_triggered:
        reasons.append(f"hard_rule: query_count > {result.hard_cap}")
    if finding.max_anomaly_score >= result.threshold:
        reasons.append(
            f"ml_score {finding.max_anomaly_score:.2f} >= threshold {result.threshold:.2f}"
        )
    top_features = [
        {
            "feature": c.feature,
            "observed": round(c.observed, 2),
            "baseline": round(c.baseline, 2),
            "pct_change_vs_baseline": round(c.pct_change, 1),
        }
        for c in finding.top_features
    ]
    return {
        "schema": "sentinel.alert.v1",
        "detector": result.detector_name,
        "principal_id": finding.principal_id,
        "state_transition": f"normal -> {finding.state}",
        "enforcement": "notify_only",
        "anomaly_score": round(finding.max_anomaly_score, 3),
        "threshold": result.threshold,
        "trigger": reasons,
        "peak_window_utc": finding.peak_window.isoformat() if finding.peak_window else None,
        "peak_query_count": finding.peak_query_count,
        "peak_sum_bytes_scanned": finding.peak_sum_bytes_scanned,
        "top_features": top_features,
        "remediation": f"Use the governed MCP path: {GOVERNED_MCP_DOC}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _slack_text(alert: dict[str, Any]) -> str:
    feats = "; ".join(
        f"{f['feature']} {f['observed']} ({f['pct_change_vs_baseline']:+.0f}% vs baseline)"
        for f in alert["top_features"]
    )
    return (
        f":rotating_light: *Anomalous query behavior* for `{alert['principal_id']}`\n"
        f"> score *{alert['anomaly_score']}* (threshold {alert['threshold']}) - "
        f"enforcement: *{alert['enforcement']}*\n"
        f"> window {alert['peak_window_utc']} - "
        f"{alert['peak_query_count']} queries, "
        f"{alert['peak_sum_bytes_scanned']:,} bytes scanned\n"
        f"> top signals: {feats}\n"
        f"> {alert['remediation']}"
    )


def emit_alerts(
    result: ScoringResult,
    log_path: Path,
    state_path: Path,
) -> list[dict[str, Any]]:
    """Emit notify-only alerts for flagged principals; persist enforcement state."""

    _configure_logger(log_path)

    alerts: list[dict[str, Any]] = []
    enforcement_state: dict[str, Any] = {}

    for finding in result.findings:
        enforcement_state[finding.principal_id] = {
            "state": finding.state,
            "last_anomaly_score": round(finding.max_anomaly_score, 3),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if not finding.flagged:
            continue
        alert = _build_alert(finding, result)
        alerts.append(alert)
        logger.info("ALERT %s", json.dumps(alert))
        logger.info("SIMULATED_SLACK %s", _slack_text(alert))
        logger.info(
            "SIMULATED_EVENTBRIDGE %s",
            json.dumps(
                {
                    "source": "sentinel",
                    "detail-type": "AnomalousQueryBehavior",
                    "detail": alert,
                }
            ),
        )

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(enforcement_state, indent=2))

    return alerts


def print_alerts(alerts: list[dict[str, Any]]) -> None:
    if not alerts:
        print("\nNo principals flagged. (Notify-only enforcement: nothing to send.)")
        return
    print(f"\n=== NOTIFY-ONLY ALERTS ({len(alerts)} flagged principal(s)) ===")
    for alert in alerts:
        print("\n" + _slack_text(alert))
