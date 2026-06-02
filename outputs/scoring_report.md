# Sentinel Scoring Report

> Synthetic demo data. SageMaker Random Cut Forest is swapped for a local scikit-learn IsolationForest behind the same interface.

## Run configuration

- Detector: `LocalIsolationForestDetector`
- Anomaly threshold (sigma): `3.0`
- Hard-cap rule: `query_count > 50` per window
- Baseline ends / scoring starts: `2026-05-31T00:00:00+00:00`

## Injected abuse (ground truth)

| principal_id | label | description |
|---|---|---|
| `shadow-abuser-01` | volume_cost_spike | 220 shadow-client queries in one 15m window with ~5e8 bytes scanned each (tool-loop / full-table scans). |
| `shadow-abuser-02` | offhours_fanout | Off-hours schema exploration across all tables, volume kept below the hard cap so only the ML detector flags it. |

## Detection summary

- Principals scored: **12**
- Flagged: **2**
- Injected abusers detected: **2/2** (shadow-abuser-01, shadow-abuser-02)
- Missed abusers: **0** (none)
- False positives: **0** (none)

## Flagged principals

| principal_id | score | hard_rule | peak queries | peak bytes | top signals |
|---|---|---|---|---|---|
| `shadow-abuser-02` | 4.31 | no | 40 | 131,721,529 | sum_bytes_scanned +3558%; query_count +1233%; distinct_tables +500% |
| `shadow-abuser-01` | 4.05 | yes | 220 | 112,697,449,866 | sum_bytes_scanned +3228068%; max_bytes_scanned +67430%; query_count +7233% |

## Top normal principals (highest non-flagged scores)

| principal_id | score | peak queries |
|---|---|---|
| `analyst-006` | 2.51 | 1 |
| `analyst-003` | 2.30 | 5 |
| `analyst-004` | 2.26 | 5 |
| `analyst-002` | 2.05 | 4 |
| `analyst-005` | 2.05 | 1 |
