# Research Brief: MCP Data Access Governance (Synth corpus)

> Literature review via Synth MCP (arXiv/OpenAlex). Supports
> [`REQUIREMENTS.md`](REQUIREMENTS.md) and a future **managed service offering**.
> Last updated: June 2026.

---

## Executive summary

Recent MCP security research (2025–2026) overwhelmingly focuses on **malicious servers,
tool poisoning, and data exfiltration**. Your problem—**legitimate shadow MCPs using real
credentials, flooding the warehouse, and returning plausible-but-wrong SQL**—is adjacent
but **under-served in academia**. That gap is a strong **commercial differentiation**
for a “Data Platform Control Plane for AI Agents” service.

The literature **validates demand** (attack surface expanding, defenses weak) and
**validates building blocks** (enterprise MCP gateway, private registry, rate limits,
anomaly detection, scoped auth). Almost no paper connects **DB workload telemetry +
ML anomaly detection + progressive enforcement** with a **catalog-governed query MCP**
as one product.

---

## Theme 1: MCP is now a standard attack surface

| Finding | Sources |
|---------|---------|
| MCP standardizes LLM ↔ tools/data; adoption is rapid; **security lags** | [A Survey of AI Agent Protocols — Yingxuan Yang et al. (2025)](https://arxiv.org/abs/2504.16736) |
| Industry-leading LLMs can be coerced via MCP into **code execution, RCE, credential theft** | [MCP Safety Audit — Brandon Radosevich et al. (2025)](https://arxiv.org/abs/2504.03767) |
| **17 attack types**, 4 surfaces; protections succeed **&lt;30%** on average | [MCPSecBench — Yixuan Yang et al. (2025)](https://arxiv.org/abs/2508.13220) |
| Malicious servers are **cheap to mass-produce** and **hard for scanners to catch** | [When MCP Servers Attack — Weibo Zhao et al. (2025)](https://arxiv.org/abs/2509.24272) |
| **12,230 tools / 1,360 servers** analyzed; systemic **privacy toolchain** risks | [Parasites in the Toolchain — Zhao, Shuli et al. (2025)](https://arxiv.org/abs/2509.06572) |

**Implication for your offering:** Enterprises will pay for **measurable risk reduction**
and **auditability**, not just “another MCP server.” Lead with empirical benchmarks
(MCPSecBench-style) applied to *your* gateway + catalog design.

---

## Theme 2: Governance controls the literature recommends (overlap with your Part 2)

[Securing the Model Context Protocol (MCP): Risks, Controls, and Governance — Herman Errico et al. (2025)](https://arxiv.org/abs/2511.20920) proposes controls that map closely to your governed path:

- Per-user auth with **scoped authorization**
- **Provenance tracking** across agent workflows
- Containerized sandboxing + I/O checks
- **Inline policy enforcement**, DLP, **anomaly detection**
- **Centralized governance** via **private registries or gateway layers**
- End-to-end audit

[MCP Guardian — Sonu Kumar et al. (2025)](https://arxiv.org/abs/2504.12757) adds operational patterns you already planned:

- Authentication, **rate-limiting**, logging, tracing, **WAF**
- Defense-in-depth with **minimal overhead** (empirically tested)

[Simplified and Secure MCP Gateways for Enterprise AI Integration — Ivo Brett (2025)](https://arxiv.org/abs/2504.19997) targets **enterprise self-hosted** integrations:

- Reference architecture, threat model, **intrusion detection**, secure tunneling
- Explicitly **not** public/community server focus

**Implication:** Your Lambda + API Gateway + S3 catalog + RLS is a **credible “enterprise MCP gateway + private tool registry”** story. Differentiate on **data-platform outcomes** (query cost, correctness, RLS), not generic MCP hosting.

---

## Theme 3: Tool poisoning vs. your “missing parameters” problem

[MCPTox — Zhiqiang Wang et al. (2025)](https://arxiv.org/abs/2508.14925): malicious instructions in **tool metadata**; high ASR on capable models (instruction-following works *against* safety).

[Model Context Protocol Threat Modeling… — Charoes Huang et al. (2026)](https://arxiv.org/abs/2603.22489): **tool poisoning** is top STRIDE/DREAD risk; recommends static metadata analysis, **behavioral anomaly detection**, user transparency.

**Distinction for your service:**

| Literature focus | Your customer pain |
|------------------|-------------------|
| Adversarial / malicious MCP | **Benign** MCP + user creds |
| Steal secrets, exfiltrate | **Overload DB**, wrong filters |
| Poison tool descriptions | **LLM omits WHERE** on real tools |

**Innovation:** **Query Contract Registry**—tools expose only `query_id` + validated parameters, not free SQL. This is “tool poisoning defense” inverted: *replace* open-ended tool definitions with **signed, versioned contracts** (your S3 catalog).

---

## Theme 4: Agent protocols and verification (accuracy layer)

[A Survey of AI Agent Protocols — Yang et al. (2025)](https://arxiv.org/abs/2504.16736): calls for protocols with better **security, scalability, latency**—MCP is one of several; no single winner.

[A Survey of Safety and Trustworthiness of LLMs… — Xiaowei Huang et al. (2023)](https://arxiv.org/abs/2305.11391): emphasizes **runtime monitoring** and **verification** across the LLM lifecycle.

[Building A Secure Agentic AI Application Leveraging A2A Protocol — Idan Habler et al. (2025)](https://arxiv.org/abs/2504.16902): **A2A + MCP synergy** for secure interoperability; MAESTRO threat modeling.

**Implication:** Optional **v2 verifier** (re-execute aggregates, row-count bounds) aligns with V&amp;V literature. v1 **transparency** (return executed SQL) is the minimum viable “accuracy” control papers support without a full verifier agent.

---

## Theme 5: Anomaly detection and cloud ML (Part 1 evidence)

Direct papers on **warehouse query-volume anomaly + MCP** were sparse in this corpus. Adjacent support:

- [A Survey on LLM Security and Privacy… — Yifan Yao et al. (2023)](https://arxiv.org/abs/2312.02003): LLMs used for **security tasks** including anomaly-style problems; also **user-level attacks**.
- [How to integrate cloud service, data analytic and ML… — Upakar Bhatta (2024)](https://arxiv.org/abs/2405.11601): **ML on cloud telemetry** for threat detection (network-focused, not SQL-specific).
- [Efficient Dynamic Clustering — Binbin Gu et al. (2022)](https://arxiv.org/abs/2203.00812): streaming **anomaly detection** via ML on evolving workloads (methodology parallel, different domain).

Errico et al. explicitly list **inline anomaly detection** as a control—not tied to SageMaker or warehouse audit logs, but **validates the control class**.

**Implication:** Part 1 is **novel in published MCP work** → strong IP/narrative for managed service. Position SageMaker as implementation detail; sell **“behavioral firewall for agentic DB access.”**

---

## Theme 6: Defense-in-depth and frameworks (how to package the sale)

[Adapting cybersecurity frameworks to manage frontier AI risks — Shaun Ee et al. (2024)](https://arxiv.org/abs/2408.07933): **NIST AI RMF + lifecycle + threat-based (ATT&amp;CK/ATLAS)** for frontier AI.

Errico et al.: existing frameworks (**NIST AI RMF, ISO/IEC 42001**) **do not yet cover MCP in detail**.

**Implication:** Offer **“MCP + Data Access Annex”** mapping:

- NIST AI RMF functions → your controls
- MITRE ATLAS-style TTPs for agentic data access
- Evidence pack from CloudWatch/S3 audit exports for auditors

---

## Gaps and opportunities (business seeds)

| Gap in literature | Your service opportunity |
|-------------------|-------------------------|
| Malicious MCP focus; little on **authorized abuse / capacity** | **Workload governance**: throttle, cost attribution, FinOps for agent queries |
| Weak enterprise controls (&lt;30% mitigation) | **Managed gateway + private registry** as productized control plane |
| No unified **DB telemetry → enforcement → governed MCP** loop | **Closed-loop platform**: detect shadow path, migrate to catalog path |
| Tool metadata attacks | **Query contracts** instead of open SQL tools |
| Accuracy = jailbreak/hallucination discourse | **Parameter validation + executed SQL disclosure + optional verifier** |
| Academic gateways (Guardian, Brett) lack **RLS + semantic catalog** | **“Governed analytics MCP”** for data platform buyers |
| Scanners (MCPSafetyScanner) pre-deployment | **Continuous audit** + **runtime policy** on approved servers only |

---

## Recommended service offering (draft)

### Positioning

**Decision Layer: Agentic Data Access Control** (working title)

*We secure and scale LLM-to-warehouse access for enterprises adopting AI coding tools and MCP—not by blocking AI, but by replacing shadow database credentials with a governed control plane.*

### Product modules (maps to REQUIREMENTS.md)

| Module | Buyer value | Research anchor |
|--------|-------------|-----------------|
| **Sentinel** (Part 1) | Stop warehouse meltdown; fair-use enforcement | Errico anomaly detection; dynamic workload ML |
| **Governed MCP** (Part 2) | Approved path with RLS + catalog | Private registry + gateway papers |
| **Contract Studio** | Data team owns metrics/SQL templates in S3 | MCPTox → invert to signed contracts |
| **Evidence Hub** | Audit exports for security/compliance | NIST RMF mapping (Ee et al.) |

### Delivery tiers

1. **Assess** — 2–4 week engagement: MCP/DB audit log review, shadow MCP inventory, threat model (STRIDE), MCPSecBench-style gap report.
2. **Build** — Deploy governed MCP MVP + catalog workflow + logging.
3. **Operate** — Managed Sentinel (SageMaker pipelines), on-call for enforcement false positives, catalog change management.

### Innovative differentiators (vs. papers + point tools)

1. **Dual-path strategy** — Detect *and* redirect (most papers pick one).
2. **Progressive enforcement** — Educate → throttle → suspend (vs. binary block).
3. **Correctness by construction** — Parameterized contracts, not “hope the LLM writes good SQL.”
4. **Data-platform buyer** — FinOps + DBA + security joint KPIs, not AppSec-only.
5. **AWS-native reference architecture** — SageMaker, Lambda, API Gateway, Cognito, EventBridge (implementation credibility for AWS-heavy buyers).

---

## Key papers (quick bibliography)

| Paper | Why read it |
|-------|-------------|
| [Securing the Model Context Protocol (MCP) — Errico et al. (2025)](https://arxiv.org/abs/2511.20920) | Closest governance control checklist to your design |
| [MCPSecBench — Yang et al. (2025)](https://arxiv.org/abs/2508.13220) | Market proof that defenses fail today |
| [MCP Safety Audit — Radosevich et al. (2025)](https://arxiv.org/abs/2504.03767) | Pre-deploy audit tooling pattern |
| [When MCP Servers Attack — Zhao et al. (2025)](https://arxiv.org/abs/2509.24272) | Taxonomy for sales conversations |
| [Parasites in the Toolchain — Zhao, Shuli et al. (2025)](https://arxiv.org/abs/2509.06572) | Scale of ecosystem risk |
| [MCP Guardian — Kumar et al. (2025)](https://arxiv.org/abs/2504.12757) | Gateway feature parity benchmark |
| [Simplified and Secure MCP Gateways — Brett (2025)](https://arxiv.org/abs/2504.19997) | Enterprise self-hosted positioning |
| [A Survey of AI Agent Protocols — Yang et al. (2025)](https://arxiv.org/abs/2504.16736) | Broader protocol landscape |

---

## Suggested updates to REQUIREMENTS.md (after review)

- Add **FinOps metrics** (scan bytes, cost per principal, agent vs human ratio).
- Add **private MCP registry** requirement (allowlist server versions; Errico).
- Add **pre-deployment MCP audit** optional module (MCPSafetyScanner-class).
- Add **compliance mapping** appendix (NIST AI RMF / ISO 42001).
- Clarify **benign abuse** as primary threat model, not only malicious servers.

---

*Synth searches run: MCP security/governance, agent protocols, text-to-SQL security surveys, DB anomaly (sparse), targeted OpenAlex MCP papers.*
