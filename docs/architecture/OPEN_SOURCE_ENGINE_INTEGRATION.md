# SULY Open-Source Engine Integration Architecture

Status: approved integration direction; implementation is incremental and capability-gated.
Target branch: `main` only.
Last reviewed: 2026-11-20.

## Objective

Reuse complete, upstream-maintained systems where they provide a distinct capability. Each upstream engine belongs in its own isolated runtime/package and is exposed to SULY through a narrow adapter. Do not flatten unrelated repositories into the FastAPI API process, copy code without provenance, or replace SULY's user-facing product and security boundaries.

"Integrate the full system" means preserve the upstream engine's meaningful runtime, tools, and lifecycle in its own bounded component, not merely imitate a few features. It does not mean enabling every privileged capability by default.

## Non-negotiable SULY control plane

SULY remains authoritative for:
- User identity, sessions, tenant ownership, RLS, and API authentication.
- Durable task records, DAG planning, dependencies, worker leases/heartbeat, retries, cancellation, checkpoints, idempotency, and final task status.
- Persisted user approvals, tool scopes, audit events, usage accounting, quotas, and billing.
- Provider configuration and secret storage.
- User-facing conversations, files, projects, settings, and product UI.

An upstream engine never receives Supabase service credentials, raw database access, user-supplied identity claims, or authority to grant itself permissions. Task input is untrusted. Trusted identity and approved scopes are injected by SULY's server-side adapter.

## Runtime topology

```text
Expo Web / Android / iOS
        |
        v
SULY FastAPI API + Auth + RLS boundary
        |
        v
SULY durable task/DAG + approvals + audit + usage
        |
        v
SULY worker claims step / owns lease
        |
        +--> Hermes agent runtime (primary general-purpose agent harness)
        |       +--> SULY tool/approval adapter
        |       +--> specialist engine adapters
        |
        +--> Coding runtime: OpenHands / OpenCode / Aider (one selected per job)
        |
        +--> Browser runtime: Browser Use / Skyvern (one selected per job)
        |
        +--> Computer-use runtime: UI-TARS (separately sandboxed)
        |
        +--> Workflow runtime: n8n / Dify (workflow products, not agent brains)
        |
        v
Bounded JSON result -> SULY validates lease -> checkpoint -> audit/usage
```

Hermes is the primary agent harness for planning, tool selection, skills, memory/session recall, and delegation. It does not replace SULY's durable task state machine or worker lease protocol. SULY must be able to cancel an engine run and reject its result after lease loss.

## Repository disposition and correct subsystem

| Upstream project | SULY subsystem | Integration decision |
|---|---|---|
| NousResearch/Hermes-Agent | Core agent runtime | Primary general agent harness; isolated service/runtime, pinned upstream revision |
| OpenManus | General agent experiments | Do not run as a second primary brain; evaluate unique tools/algorithms and port/adapt only non-duplicative components |
| OpenClaw | Channel/gateway adapters | Optional messaging/channel connector layer; never own SULY identity, approvals, or task ledger |
| OpenHands | Software engineering | Full isolated coding-agent runtime, invoked for coding tasks |
| OpenCode | Software engineering | Alternative coding runtime behind the same SULY coding adapter; do not run simultaneously by default |
| Aider | Software engineering | Alternative repository-editing engine; selectable backend, not a second always-on agent |
| Browser Use | Browser automation | Browser specialist runtime with per-task isolated browser context |
| Skyvern | Browser workflow automation | Alternative/advanced browser workflow backend; AGPL-3.0 compatibility review required before code incorporation or network deployment |
| LangGraph | Stateful graph orchestration | Optional specialist workflow runtime only if Hermes + SULY DAG do not cover a measured use case; avoid duplicate orchestration |
| Dify | Visual AI app/workflow and RAG subsystem | Optional isolated workflow/RAG service; review modified Apache license and edition boundaries |
| CrewAI | Multi-agent team runtime | Optional delegated team backend for tasks that benefit from role-based crews; not default for every task |
| UI-TARS | Computer-use / GUI agent | Isolated computer-use specialist; no host desktop access or unrestricted credentials |
| Open Interpreter | Controlled local/computer execution | Optional execution adapter only inside disposable sandbox; disable host mode |
| Screenpipe | Context capture / screen activity | Hold: privacy, consent, retention, data-flow, and commercial license review required; no integration yet |
| Nanobot | Lightweight agent runtime | Benchmark/compatibility reference; avoid duplicating Hermes unless it wins a measured constrained-device use case |
| IronClaw | Secure agent runtime | Security design/reference and possible isolated specialist after upstream audit and compatibility review |
| ZeroClaw | Lightweight secure agent runtime | Benchmark/reference or optional constrained runtime; no parallel primary runtime |
| n8n | Workflow automation | Separate workflow service/adapter; license is not OSI-style permissive, commercial/embedding terms must be reviewed before bundling |
| OpenClaw / Open Interpreter / UI-TARS | Privileged execution boundary | Must remain separately sandboxed and require explicit scopes; no ambient host access |

## Integration phases

### A. Foundation and contracts
- Create an upstream inventory with repository URL, exact pinned tag/commit, license, transitive dependency summary, supported runtime, security model, and update policy.
- Define a common SULY engine contract: capability declaration, health, start, cancel, bounded event stream, result schema, resource limits, and provenance.
- Define a SULY adapter contract for trusted user/task context and approved scopes.
- Keep the existing deterministic worker and registry operational when engines are disabled.

### B. Primary agent
- Vendor no arbitrary snapshot. Pin Hermes upstream release/commit and retain required LICENSE/NOTICE files.
- Run Hermes in a separate process/container with a dedicated non-root identity and ephemeral workspace.
- Disable local-host terminal, arbitrary filesystem, browser, cron, gateway, and messaging features initially.
- Expose only SULY-approved tool adapters; secrets are never placed in prompts or workspace.
- Use mocked model/provider tests until a provider is explicitly configured. Do not claim real autonomous generation while AI_PROVIDER is disabled.

### C. Specialist engines
- Add coding, browser, computer-use, and workflow runtimes independently, each behind an adapter and isolated execution environment.
- Select one backend per capability/job based on explicit policy and health; do not start every engine for every task.
- Preserve upstream licenses and attribution. Pin dependencies and lockfiles.
- Do not expose arbitrary shell, filesystem, browser, desktop, or network access without a dedicated approval scope and sandbox verification.

### D. Verification and operations
- Unit/contract tests for each adapter, permission denial, cancellation, lease loss, timeout, oversized output, malformed JSON, and retry behavior.
- Integration tests using mock models and fake tools; live model tests only after provider selection.
- Security review and dependency/license scan before each upstream engine is enabled.
- Resource budgets, concurrency limits, process cleanup, telemetry redaction, and health checks.
- A capability is not "integrated" until its runtime starts in the intended sandbox and passes its contract/security tests.

## Licensing and supply-chain gates

- MIT/Apache/BSD components may be considered subject to their notices, dependencies, and compatibility.
- AGPL components (including Skyvern) require a deliberate network-service and distribution compliance review before adoption.
- n8n Sustainable Use License is not treated as a permissive open-source license; no bundling/resale/embedding assumption.
- Dify's repository license and edition-specific components must be checked at the exact pinned revision.
- Screenpipe remains excluded until its exact current license and commercial-use terms are confirmed.
- Never infer a license from a directory, package name, or third-party comparison page. Read the upstream LICENSE at the pinned commit.
- Do not copy a whole repository into SULY merely to claim integration. Prefer isolated upstream runtime deployments or cleanly separated vendored components with provenance.

## Current truth / non-claims

At the time this document is added:
- SULY has durable task/DAG, worker lease/heartbeat, retry/cancellation/checkpoint, tool registry, persisted approval/audit infrastructure.
- Only deterministic `text.analyze` is registered for task execution.
- The worker is opt-in and not deployed as an always-on service.
- No model provider is selected; `AI_PROVIDER=disabled`.
- No upstream engine listed above is yet claimed as running inside SULY.
- This document establishes architecture and integration gates; it is not evidence that engines have already been installed or that autonomous tasks work.

## Completion report requirements

Every integration batch must list:
1. Upstream repositories and exact pinned revisions.
2. License/NOTICE files and any excluded components.
3. Runtime boundaries and enabled capabilities.
4. Files changed and adapters implemented.
5. Tests run with exact results, including security/cancellation cases.
6. What is genuinely operational versus still disabled or blocked.
