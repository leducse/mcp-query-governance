# MCP Query Governance Platform

**Status:** MVP implemented (local, runnable). Spec: [`MVP_SPEC.md`](MVP_SPEC.md).

Portfolio case study: detect abusive programmatic database querying (Part 1
**Sentinel**) and provide a governed MCP + API path with cataloged queries and
RLS (Part 2). The design is AWS-native, but the whole demo **runs locally with
no real AWS account** — SQLite stands in for the RDS demo warehouse and a local
scikit-learn `IsolationForest` stands in for SageMaker Random Cut Forest.

> **SageMaker RCF swap:** SageMaker Random Cut Forest is not available locally,
> so the detector runs scikit-learn `IsolationForest` behind a
> SageMaker-swappable interface (`AnomalyDetector`). The production class
> `SageMakerRandomCutForestDetector` shares the same interface; switching is a
> one-line config change (`DETECTOR_BACKEND=sagemaker`). The local detector is
> normalised to a sigma scale so the `ANOMALY_THRESHOLD=3.0` (~3σ) default
> carries the same meaning as RCF. See `src/sentinel/detector.py`.

## Quickstart

```bash
cd mcp-query-governance
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Generate synthetic logs, run the governed query, train+score the detector,
# emit notify-only alerts, and write reports + a figure.
python -m src.main
```

Expected outcome: the run flags **both injected abusers**
(`shadow-abuser-01`, `shadow-abuser-02`) with **zero false positives**, prints
explainable alerts, and exits `0`.

Run the tests:

```bash
python -m unittest discover -s tests
```

## What the entrypoint does

1. Generates synthetic `query_audit` logs (10 normal principals + 2 injected
   abusers) and writes them to the demo warehouse + `data/sample/`.
2. **Part 2 (Governed MCP):** runs one cataloged query
   (`pipeline_summary`) through param validation + server-side RLS injection,
   printing the executed SQL and data, and demonstrates a rejected call.
3. **Part 1 (Sentinel):** aggregates per-principal/15-minute features, trains
   the detector on the baseline window, scores the recent window, and applies a
   hybrid ML + hard-cap rule.
4. Emits **notify-only** alerts (stdout + `outputs/logs/alerts.log`) with
   simulated Slack/EventBridge payloads, and persists `flagged` state to
   `outputs/enforcement_state.json` (DynamoDB stand-in). No throttle/suspend.
5. Writes `outputs/scoring_report.{csv,md}` and
   `outputs/figures/anomaly_scores.png`.

## Detection results (synthetic demo)

| principal | score (σ) | trigger | why |
|---|---|---|---|
| `shadow-abuser-01` | ~4.0 | ML **and** hard-rule | 220 queries / 15m, ~1e11 bytes scanned |
| `shadow-abuser-02` | ~4.3 | **ML only** (under hard cap) | off-hours fan-out across all tables |
| all `analyst-*` | < 2.6 | — | below the 3.0σ threshold |

`shadow-abuser-02` is the key result: it stays under the hard cap, so only the
ML detector catches it — demonstrating ML value beyond static rules.

## MVP scope: implemented vs deferred

| Area | This repo (local MVP) | Deferred to AWS build (documented) |
|---|---|---|
| Demo warehouse | SQLite (configurable to Postgres) | RDS PostgreSQL via CDK |
| Anomaly model | `IsolationForest` (RCF-swappable interface) | SageMaker RCF batch transform |
| Feature pipeline | pandas aggregation per principal/window | Lambda `feature_agg` + EventBridge schedule |
| Enforcement | notify-only: log + simulated Slack/EventBridge + state JSON | SNS + DynamoDB + EventBridge |
| Governed path | local catalog dir + Python executor (validation, RLS, audit) | S3 catalog + API Gateway + Lambda + Cognito |
| MCP server (stdio) | not built; executor is callable directly | MCP `list_queries` / `run_query` tools |
| Infra (CDK) | not built | single CDK stack (`MVP_SPEC.md` §8) |

## Configuration

All env-overridable (see `src/config.py`). Defaults run with zero setup.

| Variable | Default | Meaning |
|---|---|---|
| `DB_BACKEND` | `sqlite` | `sqlite` or `postgres` (RDS stand-in) |
| `DATABASE_URL` | _(unset)_ | libpq DSN when `DB_BACKEND=postgres` |
| `DETECTOR_BACKEND` | `local` | `local` (IsolationForest) or `sagemaker` (stub) |
| `ANOMALY_THRESHOLD` | `3.0` | flag at score ≥ this many σ |
| `HARD_CAP_QUERIES_PER_WINDOW` | `50` | hybrid hard-rule cap |
| `SEED` | `1337` | deterministic synthetic seed |

To use Postgres: uncomment `psycopg2-binary` in `requirements.txt`, then
`DB_BACKEND=postgres DATABASE_URL=postgresql://... python -m src.main`.

## Documents

| File | Purpose |
|------|---------|
| [`MVP_SPEC.md`](MVP_SPEC.md) | **Built from this** — AWS MVP scope, architecture, CDK outline, demo script |
| [`REQUIREMENTS.md`](REQUIREMENTS.md) | Full product requirements (production target) |
| [`RESEARCH.md`](RESEARCH.md) | Synth literature review + service positioning |
| [`ML_QUERY_MONITORING.md`](ML_QUERY_MONITORING.md) | ML / SageMaker RCF deep dive |
| [`BLIND_SPOTS.md`](BLIND_SPOTS.md) | Skeptical review — risks and AWS realities |

## Disclaimer

This MVP uses a **demo database and synthetic workloads**, not real customer or
warehouse data, and does not connect to live cloud services. See the production
evolution in [`MVP_SPEC.md`](MVP_SPEC.md) §11.
