# SULY upstream engine inventory

**Snapshot date:** 2026-11-20  
**Target branch:** `main`  
**Purpose:** auditable intake register for the upstream projects considered for SULY. This is an inventory and routing decision, not a claim that these engines are installed, running, or approved for production.

## Intake rules

- SULY remains the control plane for identity, tenant ownership, durable tasks/DAG, worker leases, approvals, audit, usage, quotas, and billing.
- Engines are invoked through isolated runtimes and narrow adapters. No upstream engine receives Supabase service credentials, raw database access, or ambient user permissions.
- Select one backend per task/capability by policy. Do not run overlapping agents by default.
- Never copy or vendor upstream code until the exact commit's LICENSE/NOTICE, dependency licenses, provenance, and security model have been reviewed.
- GitHub metadata below is an initial discovery snapshot. The SPDX field is repository API metadata only; it is **not** a substitute for inspecting the exact pinned revision's LICENSE/NOTICE. `NOASSERTION` is a hard license-review blocker.
- Immutable source pins are now recorded in `services/api/app/services/engine_catalog.py` for Hermes (`2de9f51b8008a7d49a49221c184f2f11cbfc4af1`), OpenCode (`4cca18d80450a3dd6a9a4142028bde84ccb3116e`), and Browser Use (`ccbdb8095fbaf903c748880a600054a34c7b6191`). These are source identities only: they do not mean the runtimes are installed, adapted, sandboxed, or enabled.

## Repository inventory

| Upstream repository | Intended SULY role | GitHub default branch | Primary language | GitHub SPDX metadata | Last pushed (UTC) | Intake status |
|---|---|---:|---|---|---|---|
| [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | Primary general agent harness; planning, tool selection, skills, delegation | `main` | Python | MIT | 2026-11-20 | Existing source pin; runtime/API remains disabled pending sandbox and lifecycle work |
| [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | Specialist software-engineering agent | `main` | TypeScript | MIT | 2026-11-20 | Candidate; separate coding runtime |
| [anomalyco/opencode](https://github.com/anomalyco/opencode) | Alternative coding-agent backend | `dev` | TypeScript | MIT | 2026-11-20 | Candidate; compare with OpenHands/Aider; not simultaneous default |
| [Aider-AI/aider](https://github.com/Aider-AI/aider) | Lightweight repository editing backend | `main` | Python | Apache-2.0 | 2026-05-22 | Candidate; compare with OpenHands/OpenCode |
| [browser-use/browser-use](https://github.com/browser-use/browser-use) | Browser automation specialist | `main` | Python | MIT | 2026-11-20 | Candidate; isolated browser context required |
| [Skyvern-AI/skyvern](https://github.com/Skyvern-AI/skyvern) | Advanced browser workflow specialist | `main` | Python | AGPL-3.0 | 2026-11-19 | Legal/network-service review required before adoption |
| [bytedance/UI-TARS](https://github.com/bytedance/UI-TARS) | GUI/computer-use specialist | `main` | Python | Apache-2.0 | 2026-01-27 | Upstream repository reported archived; do not select for production without maintenance/security review |
| [OpenInterpreter/openinterpreter](https://github.com/OpenInterpreter/openinterpreter) | Controlled execution adapter | `main` | Rust | Apache-2.0 | 2026-11-20 | Sandbox-only candidate; host mode prohibited |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | Optional stateful workflow/graph runtime | `main` | Python | MIT | 2026-11-20 | Benchmark only; avoid duplicating SULY DAG/Hermes |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | Optional role-based multi-agent delegation | `main` | Python | MIT | 2026-11-20 | Candidate only for measured multi-agent use cases |
| [langgenius/dify](https://github.com/langgenius/dify) | Optional visual workflow/RAG service | `main` | Python | NOASSERTION | 2026-11-20 | License/edition boundary blocker; do not bundle pending exact-source review |
| [n8n-io/n8n](https://github.com/n8n-io/n8n) | External workflow automation service | `master` | TypeScript | NOASSERTION | 2026-11-20 | Commercial/embedding license review blocker; no bundling assumption |
| [openclaw/openclaw](https://github.com/openclaw/openclaw) | Messaging/channel connector layer | `main` | TypeScript | MIT | 2026-11-20 | Optional adapter; SULY retains identity, authorization, and task ledger |
| [FoundationAgents/OpenManus](https://github.com/FoundationAgents/OpenManus) | Research reference for multi-step agent execution | `main` | Python | MIT | 2026-11-02 | Benchmark unique capabilities; not a second primary agent |
| [HKUDS/nanobot](https://github.com/HKUDS/nanobot) | Lightweight agent runtime reference | `main` | Python | MIT | 2026-11-20 | Benchmark only; compare on constrained-resource workloads |
| [nearai/ironclaw](https://github.com/nearai/ironclaw) | Secure agent-runtime design/reference | `main` | Rust | Apache-2.0 | 2026-11-09 | Security architecture review/benchmark |
| [zeroclaw-labs/zeroclaw](https://github.com/zeroclaw-labs/zeroclaw) | Lightweight secure runtime reference | `master` | Rust | Apache-2.0 | 2026-11-20 | Benchmark only; do not create a competing primary runtime |
| [screenpipe/screenpipe](https://github.com/screenpipe/screenpipe) | Optional user-consented context capture | `main` | Rust | NOASSERTION | 2026-11-19 | Hold; exact license, consent, privacy, retention, and data-flow review required |

## Capability routing

| Capability | Preferred SULY route | Fallback/alternatives | Selection rule |
|---|---|---|---|
| General agent reasoning and tool orchestration | Hermes | OpenManus/Nanobot/IronClaw/ZeroClaw as evaluated references | Hermes remains primary unless benchmark evidence justifies a change |
| Coding and repository edits | Coding adapter | OpenHands, OpenCode, Aider | Choose one runtime per task based on task type, health, and resource budget |
| Browser automation | Browser adapter | Browser Use or Skyvern | Choose one backend per task; browser isolated per task |
| GUI/computer use | Computer-use adapter | UI-TARS | Block until maintained source and isolated desktop sandbox are verified |
| Multi-step durable execution | SULY task DAG + worker | LangGraph/CrewAI/OpenManus as optional specialists | SULY owns durable state; add another orchestrator only for a demonstrated gap |
| Visual workflows/RAG | Workflow adapter | Dify or n8n | Separate service; legal and edition review before use |
| Messaging channels | Channel adapter | OpenClaw | Channel identity never replaces SULY authentication |
| Local command execution | Sandbox execution adapter | Open Interpreter | Disposable non-root sandbox only; no host mode or secrets mounts |
| Ambient screen context | Not enabled | Screenpipe | Hold pending explicit consent and full privacy/license review |

## Mandatory security gates before enabling an engine

1. Pin immutable upstream commit and record source URL, commit SHA, release/tag, and update policy.
2. Read LICENSE, NOTICE, and relevant dependency licenses at that exact revision.
3. Run dependency and vulnerability review; inspect install/build scripts and network behavior.
4. Run as non-root in a dedicated runtime with task-only workspace, resource/time/output limits, and process cleanup.
5. No Docker socket, host filesystem mounts, host desktop, Supabase credentials, provider secrets, or inherited user tokens.
6. Default-deny network egress; allow only reviewed destinations needed by that engine.
7. Enforce SULY approval scopes, audit, quotas, and bounded delegation outside the engine.
8. Contract-test health, start, events, cancellation, lease loss, timeout, malformed/oversized output, retries, and cleanup.
9. Keep the engine disabled until all gates pass. A repository appearing in this inventory does not mean it is enabled.

## Next implementation sequence

1. Complete exact-commit LICENSE/NOTICE and security review for Hermes and the first coding/browser candidates.
2. Define the typed engine contract and registry in SULY, preserving existing worker/task behavior.
3. Add a mock engine adapter and contract tests before registering live upstream execution.
4. Finish Hermes run-ID/event/cancel lifecycle and sandbox review before exposing Hermes to user tasks.
5. Add coding and browser adapters one at a time; keep all other engines disabled until selected and verified.

## Snapshot limitations

This first pass records GitHub repository metadata (default branch, primary language, push timestamp, archived flag, and repository SPDX metadata) as observed on 2026-11-20. It does not yet certify exact-commit license text, dependency compatibility, runtime reproducibility, security posture, or operational readiness. Those are explicit audit tasks, not implied approvals.

## Hermes exact-source audit update (2026-11-20)

The current immutable Hermes source pin in `engines/hermes/compose.yaml` and `engines/hermes/README.md` is `2de9f51b8008a7d49a49221c184f2f11cbfc4af1`; the earlier `9f47677483d1b4de4d1a88d37b3b7ca18b18b215` was a valid older commit and has been superseded. The exact current revision's LICENSE is MIT. It includes the native Runs API for run creation, status polling, SSE events, stop requests, and idempotent admission. Upstream explicitly describes Hermes as a single-tenant personal agent and requires whole-process OS isolation for untrusted/shared production use. SULY will not expose one shared Hermes process as a multi-tenant security boundary. Per-tenant/task isolation, egress controls, resource limits, and full dependency/license review remain mandatory blockers.


## Initial runtime catalogue — 2026-11-20

- Added a typed SULY engine catalogue for Hermes, OpenCode, and Browser Use, each bound to an immutable upstream commit SHA and repository URL.
- Inspected the upstream LICENSE files at the selected revisions; all three report MIT. Preserve each upstream copyright/license notice if any source is later vendored. This is not yet a transitive dependency/SBOM audit.
- The catalogue registers capabilities with `enabled=false`, `requires_approval=true`, and no adapter. It does not install, launch, or expose any upstream process.
- Added tests for immutable provenance, duplicate IDs, and fail-closed defaults.
- OpenHands is not selected as the coding runtime from the current candidate snapshot: its repository README currently describes Agent Canvas/control-center functionality and multiple agent backends, so OpenCode is the clearer dedicated coding-agent candidate for the first integration.
- Next gates: verify exact upstream server/API entry points, audit dependency licenses and vulnerabilities, build task-scoped sandbox images, implement narrow adapters, and add cancellation/event/lease-loss contract tests before any runtime activation.


## Worker registry integration snapshot — 2026-11-20

- Hermes, OpenCode, and Browser Use are now loaded into the actual worker engine registry from the immutable engine catalogue.
- The existing Hermes adapter is retained and remains gated by worker enabled, Hermes enabled, isolation attestation, internal URL, and server API credential.
- OpenCode and Browser Use are registered but disabled with no adapter. Their native runtimes are not launched.
- Five agent roles are now built from the canonical role catalogue: general, coding, research, browser, workflow. A role is routable only when an enabled engine provides one of its requested capabilities.
- Added worker-level tests proving that configured Hermes is the only engine enabled by the current runtime builder and that all engines remain disabled when the worker flag is off.
- Commits: `c4f995fbb1fc`, `cbae5c145a54`, `4c592edc1b09`, `9db260180421`, `2cd2d33777ca`, `de8146717886`, `2f15ec98f5e5`.
- Tests have been authored but not confirmed by CI yet.
