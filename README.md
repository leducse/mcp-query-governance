# MCP Query Governance Platform

**Status:** MVP spec ready — see [`MVP_SPEC.md`](MVP_SPEC.md) to build.

Portfolio case study: detect abusive programmatic database querying (Part 1
**Sentinel**) and provide a governed MCP + API path with cataloged queries and
RLS (Part 2).

## Documents

| File | Purpose |
|------|---------|
| [`MVP_SPEC.md`](MVP_SPEC.md) | **Build this** — AWS MVP scope, architecture, CDK outline, demo script |
| [`REQUIREMENTS.md`](REQUIREMENTS.md) | Full product requirements (production target) |
| [`RESEARCH.md`](RESEARCH.md) | Synth literature review + service positioning |
| [`ML_QUERY_MONITORING.md`](ML_QUERY_MONITORING.md) | ML / SageMaker RCF deep dive |
| [`BLIND_SPOTS.md`](BLIND_SPOTS.md) | Skeptical review — risks and AWS realities |

## MVP at a glance

- **AWS:** RDS PostgreSQL, Lambda, API Gateway, Cognito, S3, DynamoDB, EventBridge, SageMaker RCF (batch), SNS, CDK
- **Governed path:** S3 query catalog → API → Lambda (RLS) → audit log
- **Sentinel:** 15m feature aggregates → RCF anomaly score → **notify only** (no auto-suspend in MVP)
- **Demo:** synthetic shadow abuse script + local MCP server

## Disclaimer

MVP uses a **demo database and synthetic workloads**, not real customer or
warehouse data. See production evolution in `MVP_SPEC.md` §11.
