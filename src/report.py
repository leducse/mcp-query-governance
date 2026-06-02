"""Scoring report (CSV + Markdown) and a summary figure."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .sentinel.scoring import ScoringResult  # noqa: E402
from .synthetic.generator import GeneratedAudit  # noqa: E402


def write_scoring_csv(result: ScoringResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "principal_id",
        "window_start",
        "query_count",
        "sum_bytes_scanned",
        "max_bytes_scanned",
        "distinct_tables",
        "distinct_sql_hash",
        "shadow_ratio",
        "hour_of_day",
        "anomaly_score",
        "hard_rule_triggered",
        "flagged",
    ]
    df = result.scored_windows[cols].sort_values(
        ["flagged", "anomaly_score"], ascending=[False, False]
    )
    df.to_csv(path, index=False)


def write_markdown_report(
    result: ScoringResult,
    audit: GeneratedAudit,
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    abuser_ids = {a.principal_id for a in audit.abusers}
    lines: list[str] = []
    lines.append("# Sentinel Scoring Report\n")
    lines.append(
        "> Synthetic demo data. SageMaker Random Cut Forest is swapped for a "
        "local scikit-learn IsolationForest behind the same interface.\n"
    )
    lines.append("## Run configuration\n")
    lines.append(f"- Detector: `{result.detector_name}`")
    lines.append(f"- Anomaly threshold (sigma): `{result.threshold}`")
    lines.append(f"- Hard-cap rule: `query_count > {result.hard_cap}` per window")
    lines.append(f"- Baseline ends / scoring starts: `{audit.scoring_start.isoformat()}`\n")

    lines.append("## Injected abuse (ground truth)\n")
    lines.append("| principal_id | label | description |")
    lines.append("|---|---|---|")
    for a in audit.abusers:
        lines.append(f"| `{a.principal_id}` | {a.label} | {a.description} |")
    lines.append("")

    flagged = result.flagged
    detected = {f.principal_id for f in flagged}
    caught = abuser_ids & detected
    missed = abuser_ids - detected
    false_pos = detected - abuser_ids

    lines.append("## Detection summary\n")
    lines.append(f"- Principals scored: **{len(result.findings)}**")
    lines.append(f"- Flagged: **{len(flagged)}**")
    lines.append(
        f"- Injected abusers detected: **{len(caught)}/{len(abuser_ids)}** "
        f"({', '.join(sorted(caught)) or 'none'})"
    )
    lines.append(f"- Missed abusers: **{len(missed)}** ({', '.join(sorted(missed)) or 'none'})")
    lines.append(
        f"- False positives: **{len(false_pos)}** ({', '.join(sorted(false_pos)) or 'none'})\n"
    )

    lines.append("## Flagged principals\n")
    if not flagged:
        lines.append("_No principals flagged._\n")
    else:
        lines.append(
            "| principal_id | score | hard_rule | peak queries | peak bytes | top signals |"
        )
        lines.append("|---|---|---|---|---|---|")
        for f in flagged:
            signals = "; ".join(
                f"{c.feature} {c.pct_change:+.0f}%" for c in f.top_features
            )
            lines.append(
                f"| `{f.principal_id}` | {f.max_anomaly_score:.2f} | "
                f"{'yes' if f.hard_rule_triggered else 'no'} | {f.peak_query_count} | "
                f"{f.peak_sum_bytes_scanned:,} | {signals} |"
            )
        lines.append("")

    lines.append("## Top normal principals (highest non-flagged scores)\n")
    normal = [f for f in result.findings if not f.flagged][:5]
    lines.append("| principal_id | score | peak queries |")
    lines.append("|---|---|---|")
    for f in normal:
        lines.append(
            f"| `{f.principal_id}` | {f.max_anomaly_score:.2f} | {f.peak_query_count} |"
        )
    lines.append("")

    path.write_text("\n".join(lines))


def write_figure(result: ScoringResult, audit: GeneratedAudit, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    abuser_ids = {a.principal_id for a in audit.abusers}

    findings = sorted(result.findings, key=lambda f: f.max_anomaly_score)
    names = [f.principal_id for f in findings]
    scores = [f.max_anomaly_score for f in findings]
    colors = [
        "#d62728" if f.principal_id in abuser_ids
        else ("#ff7f0e" if f.flagged else "#1f77b4")
        for f in findings
    ]

    fig, ax = plt.subplots(figsize=(9, max(4, len(names) * 0.4)))
    ax.barh(names, scores, color=colors)
    ax.axvline(
        result.threshold,
        color="black",
        linestyle="--",
        linewidth=1,
        label=f"threshold ({result.threshold}sigma)",
    )
    ax.set_xlabel("Max RCF-style anomaly score (sigma)")
    ax.set_title("Per-principal anomaly score (red = injected abuser)")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
