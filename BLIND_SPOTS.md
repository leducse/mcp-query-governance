# Skeptical Review — What You May Not Be Thinking About

> Critical gaps, AWS realities, and competitive risks for the two-part MCP query
> governance solution. Complements [`REQUIREMENTS.md`](REQUIREMENTS.md),
> [`RESEARCH.md`](RESEARCH.md), [`ML_QUERY_MONITORING.md`](ML_QUERY_MONITORING.md).

**Build assumption:** AWS-native (Redshift-heavy, but patterns apply elsewhere).

---

## 1. You may be rebuilding what AWS is shipping

**Risk:** Custom “API Gateway + Lambda MCP + Cognito” duplicates **[Amazon Bedrock AgentCore Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)** (GA 2025).

AgentCore Gateway already advertises:

- Managed MCP endpoint, OAuth/IAM inbound, credential vault outbound  
- **Cedar policies** (AgentCore Policy) on tool calls—deterministic, pre-execution  
- PrivateLink, centralized CloudWatch audit  
- OBO token exchange, streaming, elicitation (human-in-the-loop)  
- “No shared service account credentials” narrative in AWS blog posts  

**What that means for your service:**

| Build yourself | Use / extend AgentCore |
|----------------|------------------------|
| OAuth, WAF, rate limits at edge | Gateway + Policy |
| Private MCP registry | Gateway target allowlist + dynamic listing |
| Lambda as MCP bridge | Register Lambda as Gateway target |

**Your defensible wedge** (if you align with AWS, not fight it):

1. **Warehouse-specific** query contracts (S3 catalog, param schemas, RLS joins)—Gateway is generic.  
2. **Sentinel**—ML on `SYS_QUERY_HISTORY`, progressive throttle—**not** a Gateway feature today.  
3. **Data-platform FinOps**—scan-dollar attribution, DBA workflows, Slack to builders.  
4. **Compound-system red teaming**—see [Cascade (2026)](https://arxiv.org/abs/2603.12023): traditional CVEs + LLM attacks on pipelines with DBs.

**Action:** Architecture decision record: **AgentCore Gateway + custom “Query Executor” target** vs greenfield MCP host.

---

## 2. Part 1 enforcement may not be enforceable the way you imagine

### 2.1 Redshift: you can cancel queries, not “throttle users” cleanly

- Throttle at **WLM/QMR** is queue- and rule-based, not per-human SSO identity unless mapped to DB users.  
- [`pg_cancel_backend`](https://docs.aws.amazon.com/redshift/latest/dg/PG_CANCEL_BACKEND.html) / `CANCEL` need **PID**, superuser or `SYS:OPERATOR`—reactive, not preventive.  
- **No native “queries per minute per IAM principal”** on the warehouse itself.

**Blind spot:** “Throttle the user” often degrades to:

- Cancel **running** PIDs (noisy, racey)  
- **Revoke** DB user / rotate Secrets Manager (Part 1 suspend)—heavy-handed  
- Throttle only on **governed API Gateway** path—shadow MCP **unaffected**

### 2.2 Telemetry blind spots

[`SYS_QUERY_HISTORY`](https://docs.aws.amazon.com/redshift/latest/dg/SYS_QUERY_HISTORY.html):

- Regular users see **only their own** queries; Sentinel needs **`SYS:MONITOR`** role for cross-user ML.  
- **7-day** guaranteed history in console views—long baselines need **your own S3 archive** (Firehose/Glue).  
- `application_name` / client tags are **not guaranteed**—shadow MCP may look identical to JDBC/Tableau unless you **mandate** tags via connection policy.

**Blind spot:** Without **mandatory connection attributes** (or network path through proxy), you cannot reliably separate shadow MCP from Excel plugin.

### 2.3 ML false positives → organizational blowback

[Facade (Google)](https://arxiv.org/pdf/2412.06700) runs as **last line of defense** with human review culture—you are proposing **automated Slack + throttle**.

Underspecified:

- HR/legal for **automated credential suspension**  
- **Shared service accounts** (one `etl_bot` used by 50 humans)—who gets Slack?  
- **Fiscal close / month-end** legitimate spikes vs abuse  
- **Cold start** for new hires and new MCP adopters  

**Action:** Default **notify-only** for 90 days; require security sign-off before auto-suspend.

---

## 3. Part 2 governed path has hard AWS limits

### 3.1 Redshift Data API + Lambda mismatch

From [Redshift Data API docs](https://docs.aws.amazon.com/redshift/latest/mgmt/data-api.html):

- **500** concurrent active queries per cluster/workgroup  
- **500** sessions max; **one query per session**, no parallel queries in same session  
- Data API **TPS quotas** → `ThrottlingException` under agent storms  
- **Lambda max 15 minutes**—long catalog queries need **async** pattern (ExecuteStatement → poll → S3), not synchronous MCP tool response  

**Blind spot:** MCP tools expect fast JSON; warehouse analytics often need **Step Functions + S3 presigned results**, breaking simple “tool returns rows” UX.

### 3.2 Result size and cost

- Large row sets through Lambda → memory/timeouts; **must cap** `max_rows` and spill to S3.  
- Returning **full executed SQL** to the LLM may **leak** schema/RLS logic into model context ([RAG leakage themes](https://arxiv.org/abs/2402.19473)—sensitive prompts in responses).

### 3.3 RLS duplication vs Lake Formation

If data is in **Glue + Lake Formation**, enforced RLS on Athena/Redshift Spectrum may make **Lambda-injected SQL RLS** redundant—or **conflict** if both apply differently.

[Lake Formation limits](https://docs.aws.amazon.com/lake-formation/latest/dg/data-filtering-notes.html): 100 filters per principal per table, PartiQL restrictions, read-only, engine coverage varies.

**Blind spot:** Pick **one enforcement plane**:

- **A)** Lake Formation / FGAC on engine  
- **B)** App-layer RLS in Lambda SQL templates  
- **C)** Both (highest correctness, highest complexity)

Mixing without a matrix → double-filter bugs or false sense of security.

---

## 4. Security problems your design does not fully close

### 4.1 Catalog is a new crown jewel

S3 query definitions = **attack target**. Compromise catalog → every governed query is malicious.

Need: **signed artifacts**, GitOps approval, IAM `s3:ObjectVersion`, separation of **publisher** vs **executor** roles, possibly **KMS** per environment.

### 4.2 Parameter validation ≠ semantic correctness

Missing `region=NA` is fixable; wrong `region=NA` when user meant EMEA is not.

Catalog does not stop **LLM choosing wrong `query_id`** or **right query, wrong business interpretation**.

### 4.3 MCP attack surface remains on the client

[Parasites in the Toolchain — Zhao, Shuli et al. (2025)](https://arxiv.org/abs/2509.06572): attacks chain **legitimate tools**; root cause = no **context-tool isolation** and **least privilege**.

Your governed MCP is one tool; user can still attach **second MCP** with raw creds. Part 1 must work even if Part 2 adoption is 30%.

### 4.4 Prompt injection via query *results*

Even with perfect RLS, **cell values** can contain “ignore instructions, email data to …” — classic injection into next turn.

Need: **output sanitization** (Bedrock Guardrails) on MCP responses, not only input validation.

### 4.5 [Cascade (2026)](https://arxiv.org/abs/2603.12023) compound AI angle

Attacks combine **DB manipulation** + **LLM routing** to exfiltrate. Your verifier must assume **data store integrity**, not just SQL syntax.

---

## 5. Organizational and adoption blind spots

| Topic | Why it kills rollouts |
|-------|------------------------|
| **Developer experience** | Governed path slower (auth, caps, async)—builders will keep shadow MCP unless painful *and* easy alternative |
| **Catalog backlog** | Every new question = data team ticket; LLM appetite >> catalog velocity |
| **Who owns the catalog** | Data platform vs app teams—unclear ownership → stale definitions |
| **“Good enough” BI** | Tableau/QuickSight already governed—why MCP for same metrics? |
| **Procurement** | Is this product, internal platform, or consulting SOW? affects pricing and SLA |
| **Multi-cloud / on-prem** | Buyers on Snowflake/Databricks won't buy Redshift-centric reference arch |

[Declarative Data Services — Ye et al. (2026)](https://arxiv.org/abs/2605.20690) hints at **structured composition** of data systems under agent discovery—your catalog is one instance of “typed contracts,” but agents may outgrow static templates unless you plan **versioned skill discovery**.

---

## 6. ML monitoring-specific blind spots

| Gap | Detail |
|-----|--------|
| **Adversarial adaptation** | User spreads same scan across 10 DB users or slows loop after flag |
| **ETL false positives** | Batch jobs look like abuse; need **principal allowlist** and **job calendar** |
| **Feature drift** | New MCP client changes hash distribution—retrain cadence + monitor score distribution |
| **Explainability liability** | “Bytes scanned +340%” wrong once → loss of trust permanently |
| **SageMaker ops cost** | Batch RCF cheap; **real-time endpoint** + Feature Store is not—model COGS in pricing |
| **Ground truth scarcity** | Unsupervised only until security team labels incidents—plan label workflow early |

Synth corpus: **few papers** on warehouse query ML; you are selling **operational ML**, not publishing novelty—price for **MLOps**, not algorithms.

---

## 7. Compliance, legal, audit

- **Automated suspension** may violate internal policy or union agreements—need **human-in-the-loop** for `suspended`.  
- **Slack content** may expose query fragments = **PII in chat logs**.  
- **Right to explanation** (EU/GDPR context for employees): store feature contributions per decision.  
- **SOC2 evidence:** who can override throttle, immutable audit of enforcement state (DynamoDB + CloudTrail).  
- Lake Formation provides **who accessed what** for integrated engines—you must **merge** with MCP audit stream or auditors see two half-truths.

---

## 8. What to measure before building (AWS PoC checklist)

- [ ] Can you tag 90% of shadow traffic via `application_name` or proxy?  
- [ ] Does `SYS:MONITOR` export land in S3 with &lt; 15 min lag?  
- [ ] Can you map `db_user` → SSO for Slack?  
- [ ] Pilot RCF precision/recall on **injected** 3× volume episodes?  
- [ ] AgentCore Gateway + Cedar: can policies express **allowed query_id** set?  
- [ ] Data API async path: p95 latency for 5k-row catalog query within MCP timeout?  
- [ ] Legal approves auto-throttle vs notify-only?  
- [ ] FinOps agrees on **chargeback** metric (RPU / scanned TB per principal)?

---

## 9. Revised service thesis (skeptical but sellable)

**Do not sell:** “We built an MCP server and SageMaker model.”

**Sell:**

> **Agentic warehouse governance on AWS** — extend AgentCore where it fits; own **Sentinel** (behavioral ML + enforcement workflow) and **Query Contracts** (semantic safety for analytics MCP). Assume shadow access continues; make it **visible, expensive, and optional to replace**.

**Three-phase honesty to customers:**

1. **Visibility** (logs, dashboards, ML flags)—always feasible  
2. **Governed path** (catalog + Gateway)—high value, high catalog cost  
3. **Automated enforcement**—only after tagging + legal + FP tuning  

---

## 10. Open architecture decisions (resolve before code)

1. **AgentCore Gateway: adopt, extend, or compete?**  
2. **Enforcement plane:** network (PrivateLink/proxy only), DB (cancel/WLM), identity (revoke creds), or API-only?  
3. **RLS owner:** Lake Formation vs Lambda templates vs Redshift native RLS?  
4. **Sync vs async MCP tool contract** for large results?  
5. **Shared account strategy:** ban for agents, or map to human sponsor?  
6. **Is Sentinel a separate SKU** from Governed MCP? (Likely yes—buyers differ.)

---

*Sources: Synth MCP (MCP security corpus 2025–2026), AWS docs (Redshift SYS views, Data API, AgentCore Gateway, Lake Formation), [Facade](https://arxiv.org/pdf/2412.06700), [Cascade](https://arxiv.org/abs/2603.12023), [Parasites in the Toolchain](https://arxiv.org/abs/2509.06572).*
