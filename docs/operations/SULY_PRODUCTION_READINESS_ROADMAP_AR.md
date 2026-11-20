# SULY Production Readiness & Integration Roadmap — Arabic

## الهدف
تجهيز SULY تدريجيًا ليكون مشروعًا قابلًا للنشر (Frontend + API + Workers + database + engine runtimes)، مع الاحتفاظ بمصادر المحركات الأصلية وإصداراتها وتراخيصها، وعدم ادعاء الجاهزية قبل التحقق.

## قواعد تنفيذ ثابتة
- كل تعديل على فرع main فقط؛ لا branches ولا PRs.
- لا تفعّل أي AI provider أو Worker أو Hermes runtime افتراضيًا.
- لا تنشر خدمات أو تطبق migrations على Supabase دون تصريح صريح.
- لا تخزن secrets أو مفاتيح أو prompts/output حساسة في repo أو engine ledger.
- لكل upstream: pin immutable commit، حفظ LICENSE/NOTICE، provenance، مراجعة dependencies، tests، adapter، sandbox.
- نسخ المصدر الأصلي لا يعني نسخًا عشوائيًا: الالتزام بالترخيص وبنية التشغيل upstream، مع فصل الخدمة عندما يلزم.
- لا تعتمد على shared process كحد أمني لعدة tenants.

## مراحل العمل (حالة وتحقق)
### المرحلة A — Core control plane
- [x] API scaffold، authenticated routes، RLS owner scope
- [x] durable tasks + task steps
- [x] DAG planning RPC
- [x] worker leases / heartbeat / checkpoints / cancellation
- [x] tool allowlist + persisted approval controls
- [x] Engine Registry + typed adapter contract
- [x] Engine Run ledger (migration committed; not yet applied live)
- [ ] apply/review DB migrations in a controlled environment
- [ ] integration tests against disposable Postgres/Supabase project

### المرحلة B — Engine lifecycle
- [x] SULY-side run record per attempt
- [x] close stale run when task-step lease transition is observed (trigger migration committed; not applied)
- [ ] reconciliation job for orphan runs if a trigger event is missed or deployment interrupted
- [ ] idempotent run admission, lease-expiry races and retry invariants tests
- [ ] external runtime run IDs, status polling, event streaming and cancellation contract
- [x] verify terminal state before task completion in bridge contract (mocked tests; live runtime not verified)

### المرحلة C — Hermes adapter
- [x] upstream exact-source audit (MIT revision recorded; full transitive license audit still pending)
- [x] documented native Runs API and stop semantics
- [x] update pin consistently in Compose + docs (verified same immutable SHA `2de9f51b8008a7d49a49221c184f2f11cbfc4af1`)
- [x] integration client: POST run, idempotency key, lease-guarded persisted external ID (mocked unit tests; no live runtime)
- [ ] status polling and bounded SSE parsing
- [x] cooperative stop + bounded terminal-state polling contract (mocked unit tests; remote process termination not live-verified)
- [ ] per-task/tenant disposable runtime isolation
- [ ] CPU, memory, process, disk, timeout bounds
- [ ] default-deny egress / approved proxy
- [ ] no host mounts, docker socket, inherited credentials, non-root
- [ ] provider configuration & model smoke test only after explicit user approval
- [ ] sandbox threat review before enabling API server

### المرحلة D — Engine source intake
Priority order, one backend per capability by policy:
1. Hermes general agent (isolated runtime)
2. OpenCode / Aider / OpenHands coding engines (compare capability, choose—not all simultaneously)
3. Browser Use / Skyvern browser automation (select by task; isolated browser profile)
4. UI-TARS computer-use research only (archive status/maintenance and license/runtime check)
5. LangGraph / CrewAI optional orchestration adapters only if existing SULY DAG/Hermes does not satisfy
6. Dify workflow/RAG optional isolated service; licensing edition boundaries review
7. Open Interpreter execution adapter only in disposable sandbox, never host mode
8. n8n workflow integration subject to license/commercial terms
9. OpenClaw connector/channel adapter only after security and license review
10. Nanobot, IronClaw, ZeroClaw, OpenManus: evaluate/benchmark; do not duplicate core agent without clear reason
11. Screenpipe deferred pending consent, privacy, retention, and license review

For every engine:
- exact commit pin
- license + notices + transitive dependency inventory
- runtime language/version compatibility
- build reproducibility
- adapter contract and allowlisted capabilities
- auth/tenant isolation
- resource limits and egress controls
- unit, integration, failure, cancellation, abuse tests
- operational runbook and rollback
- status remains "not enabled" until all gates pass

### المرحلة E — Scale & reliability
- [ ] API stateless deployment + health/readiness distinction
- [ ] shared durable queue and bounded worker concurrency
- [ ] pool limits for Postgres and connection lifecycle
- [ ] idempotency for user requests, task admissions, billing and tool actions
- [ ] rate limits by user/IP/capability
- [ ] quota/usage ledger exactness and partial billing
- [ ] Redis only where needed; document failure behavior
- [ ] structured logs with redaction, metrics, traces, alerting
- [ ] object storage quotas, signed URLs, retention
- [ ] backups and restore drill
- [ ] horizontal scaling tests, queue backpressure, overload response
- [ ] load tests with explicit hardware/service assumptions and published observed results

### المرحلة F — Production package
- [ ] .env.example only (no actual secrets)
- [ ] Dockerfiles with non-root, pinned base images and minimal build
- [ ] compose profiles for API/worker/database/engines; default profiles safe/off
- [ ] deployment instructions for frontend, API, worker, DB migrations, secrets
- [ ] CI: lint, typecheck, tests, security/dependency scan, migration validation, build
- [ ] smoke tests after deployment
- [ ] disaster recovery, rollback, incident runbook
- [ ] user data export/delete and privacy policy
- [ ] final production checklist and known limitations

## تعليم الكود
- SULY-owned source: Arabic comments at logical statements/branches, docstrings for classes/functions, type annotations, concise comments explaining purpose/why. Avoid comments on every syntactic token when they clutter code or risk changing generated/config/license files.
- Upstream files: preserve original source, headers, license, and avoid invasive Arabic comments that break maintainability. Provide separate Arabic learning guides explaining module purpose, key functions, flow, inputs/outputs, and integration points.
- Each added/modified file includes a short Arabic module guide where appropriate.
- Do not mark work complete based only on generated code; CI, tests, review, and runtime evidence are required.

## Current known blockers (2026-11-20)
- Supabase engine_runs migration and reconciliation migration committed, not applied to live DB.
- Worker and Hermes are disabled by default.
- Hermes Compose source pin must be aligned with audited immutable revision.
- Compose is development scaffold only; no production sandbox or egress limits yet.
- No production API/worker deployment; no model provider configured.
- CI for latest commits must be observed to completion; pending runs are not passing evidence.

## Definition of ready for controlled beta
- all schema migrations reviewed and applied to staging only
- API and frontend deployed to staging
- workers queue and recover safely
- engine runtimes isolated and disabled unless explicitly configured
- authentication/RLS verified by tests and manual cross-user tests
- cancellation/retry/billing/idempotency tests pass
- backup/restore and monitoring verified
- no critical/high unresolved security findings
- load test report describes achieved throughput, latency, error rate, resource use and bottlenecks
- production secrets stored in platform secret manager, never repository


## Session checkpoint — 2026-11-20 (Hermes bridge input/status hardening)

- Verified `main` head before work: `c229a76698184ea78c7973de2bb6ff7a01db73ba`.
- Confirmed Repository baseline checks and Platform CI both succeeded for that HEAD.
- Verified Hermes Compose and README use the same immutable upstream revision `2de9f51b8008a7d49a49221c184f2f11cbfc4af1`.
- Hardened upstream `run_id` validation to accept only safe ASCII letters, digits, underscores, and hyphens; rejects slash/path traversal, spaces, Unicode and empty IDs before persisting or polling.
- Hardened cancellation-poll status parsing to reject non-object JSON responses with a controlled HermesAgentError.
- Added parameterized tests for invalid upstream IDs and malformed status payloads. CI pending until runs for the resulting commit finish.
- Safety boundary unchanged: Hermes runtime and provider remain disabled; no DB migrations applied or deployments performed.
- Next: verify CI; then implement bounded SSE event handling or orphan-run reconciliation (choose after reviewing worker lease/recovery design). Sandbox manager remains prerequisite for any activation.
