# SULY AI --- V1 Launch Blueprint (Public Product)

**Version:** 1.0 • **Status:** Proposed implementation baseline\
**Purpose:** Turn the master architecture into a shippable first public
release with real, useful capabilities. V1 is not a toy chat prototype
and is not expected to implement every future capability.

## 1. V1 launch promise

SULY V1 is a multi-purpose AI workspace and task agent. Users can
converse, provide files, request research, create and analyze documents,
generate code and projects, use controlled browser/search tools, request
images and supported media, and track longer tasks from start to finish.

The product must be honest about which providers/tools are configured
and available. It must not display buttons that imply unavailable
capabilities.

## 2. V1 scope

### Must ship (P0)

-   Secure account/authentication, sessions, user preferences.
-   Chat interface with streaming where supported, attachments and
    history.
-   Projects/workspaces with scoped context and files.
-   Task creation, durable queue, worker, checkpoints, retry,
    cancellation, status timeline.
-   Central Agent: classify, plan, select capability, execute, observe,
    verify, replan within limits.
-   Model Gateway: provider/model registry, configuration, fallback,
    streaming, timeouts, error handling, budget enforcement.
-   Research/web search with source links, page reading, synthesis and
    source display.
-   File upload, extraction for supported formats, safe file preview,
    file generation and download.
-   Coding tasks in isolated sandbox: inspect workspace, create/edit
    files, run allowed commands/tests, report changes and test output.
-   Browser engine in isolated environment:
    open/search/navigate/read/extract, click/type only under
    permissions, screenshots and downloads as policy permits.
-   Image generation through configured provider(s), generated output
    stored as user artifacts.
-   Media capability entry points with provider capability checks; video
    creation enabled only if an operational video provider integration
    is available.
-   Data analysis for common CSV/XLSX data, calculations and charts with
    safe execution.
-   Skill/tool registry with schemas, validation, timeouts, permissions
    and audit.
-   Artifact center for outputs (documents, images, code bundles,
    analysis files).
-   Usage/credit ledger, cost budget and task limits.
-   Admin console: providers/models, tool/engine health, task/worker
    overview, basic usage, limits, feature flags.
-   Safety gates, confirmation UI, privacy controls, user data
    deletion/export path.
-   Arabic/English UI and RTL support.
-   Automated smoke, integration, security/RLS, task recovery and
    platform UI tests.

### P1 (ship only if core stable or clearly feature-flagged)

-   OAuth connectors to selected services (start with a small number and
    complete security review).
-   Reusable workflows/templates.
-   Project memory controls and retrieval.
-   Scheduled/recurring tasks.
-   Multi-agent specialist parallelism for bounded tasks.
-   Advanced computer-use/remote desktop if isolated runtime and
    permissions are ready.
-   Video generation integration if provider and costs/quotas are
    confirmed.

### Not required for first public launch

-   Dozens of simultaneous specialized agents.
-   Fully autonomous unsupervised operation across arbitrary
    accounts/sites.
-   Self-modifying production code or automatic deployment without
    review.
-   A custom foundation model.
-   Kubernetes or microservices by default.
-   Unlimited tasks or unlimited model credits.
-   Every external connector.
-   Advanced video editing/compositing suite. These are not refusals;
    they are roadmap items requiring verified infrastructure, providers,
    risk controls and demand.

## 3. User journeys

### Journey A --- Ask and discuss

User opens SULY → starts conversation → chooses model or Auto → sends
prompt → receives streamed response → continues conversation with
context → can convert discussion into a task/project.

### Journey B --- Research report

User requests investigation → Agent clarifies only if essential →
creates plan → search worker collects sources → pages are read and
relevance assessed → synthesis includes citations and uncertainties →
verifier checks source coverage → report delivered as chat and optional
document.

### Journey C --- File analysis and creation

User uploads supported file → API validates file size/type → storage
receives private object → extraction pipeline runs → task context
references extracted content → agent analyzes → creates requested output
→ artifact is saved with private access/download.

### Journey D --- Coding/build project

User describes desired app → agent generates plan and file tree → coding
sandbox is created from clean scoped workspace → agent writes code →
runs allowed checks → reads errors and attempts repair within budget →
verifier reviews expected behavior → changes and run results are
presented → user downloads project bundle or connects approved repo
integration.

### Journey E --- Browser-assisted work

User requests website research or a permitted action → policy checks →
isolated browser session → navigation/search/inspection → page data
treated as untrusted → agent summarizes or prepares action → high-risk
actions require preview and approval → task closes session and stores
permitted artifacts.

### Journey F --- Image/media

User requests image → modality/provider routing → generation request →
provider status/result → artifact stored → output shown. Video request →
confirm provider supports the required format/length and budget →
generate or clearly state unavailable; no fake completed state.

## 4. V1 user-facing modules

1.  **Home/Chat:** New conversation, suggested tasks, recent work,
    status of active tasks.
2.  **Agent task view:** goal, plan, progress, live activity, approvals,
    stop/retry/continue.
3.  **Projects:** project conversations, files, tasks, context,
    artifacts.
4.  **Files:** uploaded and generated files, metadata, preview,
    download, delete.
5.  **Model selection:** user preferences; Auto routing; provider/model
    availability.
6.  **Tools/Capabilities:** visible capabilities and availability---not
    fake toggles.
7.  **Usage:** credits/limits, current task estimated usage, completed
    ledger.
8.  **Settings:** account, language, theme, privacy, memory controls,
    connected integrations.
9.  **Admin:** provider keys, model routing, quotas, engines/workers,
    task inspection, feature flags, health.

## 5. V1 logical architecture

``` mermaid
flowchart TD
  USER[User] --> CLIENT[Expo Client: Android / iOS / Web]
  CLIENT --> API[FastAPI API]
  API --> AUTH[Auth Validation + Authorization]
  API --> CHAT[Conversation / Project]
  API --> TASKS[Task Manager]
  API --> GATEWAY[AI Gateway]
  API --> DB[(Supabase PostgreSQL)]
  API --> STORAGE[(Private Storage)]
  API --> EVENTS[Realtime Events]
  TASKS --> QUEUE[Durable Queue]
  QUEUE --> WORKERS[Python Worker Pool]
  WORKERS --> AGENT[Central Agent Runtime]
  AGENT --> PLANNER[Planner + Step Graph]
  AGENT --> ROUTER[Model Router]
  AGENT --> REGISTRY[Tool/Skill Registry]
  REGISTRY --> WEB[Research/Search]
  REGISTRY --> BROWSER[Browser Sandbox]
  REGISTRY --> CODE[Code Sandbox]
  REGISTRY --> FILES[File Engine]
  REGISTRY --> DATA[Data Analysis]
  REGISTRY --> IMAGE[Image Provider]
  REGISTRY --> VIDEO[Video Provider if enabled]
  AGENT --> VERIFY[Quality/Verifier]
  WORKERS --> DB
  WORKERS --> STORAGE
  WORKERS --> EVENTS
  API --> OBS[Monitoring]
  WORKERS --> OBS
```

## 6. V1 task flow

``` mermaid
flowchart TD
  A[User request] --> B[Validate identity, files, quota]
  B --> C[Create durable task + reserve budget]
  C --> D{Task complexity?}
  D -->|Simple| E[Direct model/tool execution]
  D -->|Complex| F[Planner generates steps/dependencies]
  F --> G[Policy checks + approval gates]
  G --> H[Queue and worker claim]
  E --> I[Execute]
  H --> I
  I --> J[Observe tool results]
  J --> K{Step successful?}
  K -->|Yes| L[Checkpoint + next step]
  K -->|Transient failure| M[Bounded retry]
  K -->|Needs new approach| N[Bounded replanning]
  M --> I
  N --> G
  L --> O{All steps done?}
  O -->|No| I
  O -->|Yes| P[Verify deliverables]
  P --> Q{Verification passed?}
  Q -->|No, fixable| N
  Q -->|Yes| R[Settle usage + publish artifacts]
  R --> S[Completed and user notified]
```

## 7. V1 task contract and reliability

A task record should contain: - task ID, owner ID, project/conversation
ID. - original request and normalized goal. - task type/capability. -
status and timestamps. - current plan version and active step. -
attempts, checkpoint, worker lease. - budget/usage reservation and
actual ledger entries. - approval state. - artifact references. - error
category and safe user-facing explanation.

Required behaviors: - Persist before enqueue. - Worker lease and
heartbeat. - Checkpoint step results. - Resume abandoned tasks after
worker failure. - Deduplicate events and external actions where
possible. - Retry transient errors only; don't loop on invalid input or
permission denial. - Preserve partial work and deliver partial result
when useful. - Cancellation should stop new actions and signal current
engine. - User sees accurate states; no stuck "working" indicator. -
Task and attempt budgets are enforced centrally.

## 8. Coding environment (non-negotiable safety)

-   Isolated container or sandbox per task/workspace, not the API server
    filesystem.
-   Non-root execution.
-   CPU, memory, wall-clock, disk, output and process limits.
-   No secrets injected into arbitrary model-generated code.
-   Network disabled by default; explicit approved network routes only.
-   Workspace mounts scoped to one task/project.
-   Commands allowlisted or policy-mediated; never unrestricted host
    shell.
-   Dependency installation restricted, logged and budgeted.
-   Clean up environment after task or preserve project workspace
    intentionally with lifecycle rules.
-   Test output and code diffs retained as artifacts.
-   Agent cannot deploy/publish/commit to user's external repo without
    explicit grant and confirmation.

## 9. Browser runtime

-   Use a supported browser automation framework and pinned compatible
    browser runtime (evaluate Playwright-based implementation as a
    baseline).
-   Browser worker isolated from API and other users.
-   Each task gets isolated context/profile; no cross-user cookies.
-   SSRF protection, download safety, file limits, domain policy.
-   Browser page content is untrusted; instructions on webpages cannot
    override system policy.
-   Log action/observation timeline; sensitive data redacted.
-   Require approval before high-risk form submissions, purchases,
    posting, deleting, or irreversible actions.
-   Browser engine reports capability and health; task fails safely when
    unavailable.

## 10. File and artifact support

### Initial input formats

-   PDF, TXT, Markdown, CSV, JSON, DOCX, XLSX, common image formats.
-   PPTX support can be added based on extraction and preview quality.
-   Validate MIME/type, file size, storage quotas, malware scanning
    strategy.
-   Extract text in a worker; never parse large/untrusted documents on
    API request.
-   OCR for image/scanned PDF only if an OCR provider/runtime is
    configured.

### Initial outputs

-   TXT/Markdown.
-   PDF/DOCX reports where generation libraries and fonts are
    configured.
-   CSV/XLSX tables.
-   ZIP project bundles.
-   PNG/JPEG/WebP images from configured image providers.
-   Code artifacts and charts.
-   Video artifact only with connected operational provider.

Artifacts are private, owner-scoped, signed download URLs with short
expiry where applicable. Metadata records type, size, task, version,
checksum, provider and creation time. Delete policy and retention are
clear.

## 11. Image/video provider strategy

-   Provider adapter interface; task orchestration does not depend on
    vendor-specific API.
-   Capability metadata: image generation/editing, video generation,
    resolution, duration, aspect ratios, supported input types, limits
    and cost.
-   Provider health and admin test.
-   Store generated assets privately.
-   Show actual provider, status, duration, limits and costs as
    appropriate.
-   Handle asynchronous polling/callbacks and timeouts.
-   Video generation is conditional: never present a nonfunctional
    button as a shipped feature.

## 12. Model gateway

-   Admin-configured provider and model catalog.
-   Capability tags: text, reasoning, tool calling, vision, image,
    audio/video as supported.
-   Auto model selection policy.
-   User-selectable model preferences within allowed catalog.
-   Fallback on provider outage/rate-limit only where policy allows.
-   Streaming adapter.
-   Timeouts, circuit breaker, concurrency limits, retries with backoff.
-   Cost and token accounting.
-   Secret rotation and redaction.
-   Model test playground for admin.
-   Never make model choice a hardcoded dependency inside each engine.

## 13. Initial API map

### Authentication/profile

-   `POST /api/v1/session/bootstrap`
-   `GET /api/v1/profile`
-   `PATCH /api/v1/profile/preferences`

### Chat

-   `POST /api/v1/conversations`
-   `GET /api/v1/conversations`
-   `GET /api/v1/conversations/{id}`
-   `POST /api/v1/conversations/{id}/messages`
-   `GET /api/v1/conversations/{id}/events` (stream/realtime approach
    selected during implementation)

### Projects

-   `POST /api/v1/projects`
-   `GET /api/v1/projects`
-   `GET /api/v1/projects/{id}`
-   `PATCH /api/v1/projects/{id}`
-   `POST /api/v1/projects/{id}/files`

### Tasks

-   `POST /api/v1/tasks`
-   `GET /api/v1/tasks/{id}`
-   `GET /api/v1/tasks/{id}/events`
-   `POST /api/v1/tasks/{id}/cancel`
-   `POST /api/v1/tasks/{id}/retry`
-   `POST /api/v1/tasks/{id}/continue`
-   `POST /api/v1/tasks/{id}/approvals/{approval_id}`

### Artifacts / usage / capabilities

-   `GET /api/v1/tasks/{id}/artifacts`
-   `GET /api/v1/artifacts/{id}`
-   `GET /api/v1/capabilities`
-   `GET /api/v1/models`
-   `GET /api/v1/usage`

These are illustrative routes; finalize OpenAPI contracts, auth,
idempotency, pagination, error formats and rate limits before
implementation.

## 14. Data tables (logical, not a final migration)

-   profiles, preferences.
-   conversations, messages, attachments.
-   projects, memberships, project_files.
-   tasks, task_attempts, plans, plan_steps, task_events, checkpoints,
    worker_leases.
-   artifacts, artifact_versions.
-   model_providers, models, user_model_preferences.
-   tools, skills, skill_versions, engine_health.
-   integrations, grants, secret references.
-   approvals.
-   usage_reservations, usage_ledger, credit_transactions.
-   memory_records.
-   feedback, quality_evaluations.
-   admin_settings, feature_flags, audit_events.

Each table requires ownership design, constraints, indexes, RLS and
migration tests before production.

## 15. Admin/operations requirements

Admin-only panel: - Provider configuration and connectivity tests. -
Model catalog and routing priorities/fallbacks. - Tool/engine enabled
state, health, versions. - Worker/queue health, queue depth, oldest
task, lease expiry. - Task inspection with safe logs and attempts. -
Per-task usage/cost and aggregate usage. - User quota/limits and feature
flags. - Error trends, task outcomes, latency. - Audit log and incident
controls. - Disable provider/engine quickly without code deploy. Admin
access requires strong authentication, least privilege, and audit trail.

## 16. V1 security and privacy checklist

-   Auth token validated server-side.
-   All endpoints authorize ownership.
-   RLS enabled and tested for every exposed table.
-   Service secrets only on backend/worker.
-   Private bucket and short-lived access.
-   Upload limits/type validation.
-   Safe extraction and parser isolation.
-   Sandbox isolation and resource quotas.
-   SSRF and redirect defenses.
-   Browser isolation and session cleanup.
-   OAuth scopes minimized, revoke flow tested.
-   Prompt-injection threat tests.
-   High-risk actions require preview/approval.
-   Rate limits and abuse protection.
-   Usage reservation/settlement atomic.
-   Sensitive logs redacted.
-   User data export/deletion flow tested.
-   Backup and restore test.
-   Dependency/license/security review.
-   Incident response contact/process documented.

## 17. V1 quality gates

### Product gate

-   User can chat and see streaming/progress.
-   Complex task plan is visible.
-   Research results have usable source links.
-   Files can be uploaded and outputs downloaded.
-   Coding tasks modify isolated workspace and run at least applicable
    checks.
-   Browser tasks can inspect pages and return evidence.
-   Images can be generated if configured.
-   Video capability is accurately gated.
-   Tasks survive app closure and worker restart test.
-   Stop/retry/continue works with truthful status.
-   Usage displayed accurately enough and no duplicate charges.
-   Arabic and English interface usable; RTL tested.
-   Android and web tested; iOS build path validated.

### Release gate

-   No critical/high unresolved security findings.
-   RLS tests pass.
-   API and task integration tests pass.
-   Worker recovery test passes.
-   Sandbox isolation test passes.
-   Rate/quota tests pass.
-   Crash/error telemetry available.
-   Backup/restore verified.
-   Terms/privacy and user-facing capability disclosures ready.
-   Rollback plan and release checklist approved.

## 18. Execution milestones (strict sequence)

### M0 --- Repository constitution

-   Create clean repository and protect against accidental secrets.
-   Commit these two architecture documents.
-   Create README, contribution/AI-agent rules, issue templates and
    decision record.
-   Configure CI skeleton, lint/type checks, test framework.
-   Owner confirms deployment target and provider credentials strategy.

**Exit:** documentation and repository governance reviewed; no code
feature work yet.

### M1 --- Platform skeleton

-   Expo TypeScript client shell, routes, design tokens, RTL/i18n.
-   FastAPI app, health endpoint, configuration, typed schemas.
-   Supabase connection through backend configuration, migrations
    pipeline.
-   Local development environment, `.env.example`, secret-free Git.
-   Basic CI for frontend/backend.

**Exit:** web and Android development builds run; API health; DB
migration and secure connection verified.

### M2 --- Auth, data and security

-   Auth flow, ownership and RLS.
-   Profile/preferences, project/conversation schema.
-   Storage policies.
-   Server authorization tests.
-   Admin bootstrap access safely configured.

**Exit:** cross-user data isolation proven by tests.

### M3 --- Chat and model gateway

-   Provider adapter(s) for initial selected models.
-   Model registry and admin configuration.
-   Chat, streaming, history, error states, model selection.
-   Usage instrumentation and request limits.

**Exit:** live chat reliable, provider outage behavior tested, secrets
remain server-side.

### M4 --- Durable tasks and Central Agent

-   Task schema, queue, workers, leases, events, checkpoints,
    cancellation.
-   Planner and structured plan.
-   Router, bounded execution, budgets, retry and replan.
-   Task timeline and progress UI.

**Exit:** long task continues after app closes; recovery after worker
restart demonstrated.

### M5 --- Research and browser

-   Search provider adapter.
-   Page reader/source collector.
-   Research engine, citation/source output.
-   Isolated browser worker.
-   SSRF/prompt injection and browser safety tests.

**Exit:** research report with verifiable source links; browser task
tested in isolated runtime.

### M6 --- Files and artifacts

-   Upload and extraction worker.
-   File context and project attachment handling.
-   Document/CSV generation and previews.
-   Artifact storage/download.
-   File parser security tests.

**Exit:** supported file types can be analyzed and output artifacts
delivered reliably.

### M7 --- Coding and data analysis

-   Isolated coding workspace.
-   File tree/read/edit/patch.
-   Controlled commands and tests.
-   Repair loop with limits.
-   CSV/XLSX analysis and chart outputs.

**Exit:** sample repositories/app tasks complete with reproducible test
evidence.

### M8 --- Image and media

-   Image provider integration.
-   Media job states and asynchronous result storage.
-   Video adapter only if a suitable provider is selected and
    credentials/cost limits exist.
-   Admin capability flags.

**Exit:** actual image creation delivered; media availability honest and
verified.

### M9 --- Integrations and workflows

-   Pick small set of high-value integrations.
-   OAuth security and permission scopes.
-   Workflow graph, retries, approvals and action logs.
-   Webhooks/trigger validation if included.

**Exit:** integrations/workflows pass permission, revocation, failure
and audit tests.

### M10 --- Memory, projects and quality

-   Project context retrieval.
-   Explicit memory types, controls and deletion.
-   Evaluation suite, verifier and task quality checks.
-   Feedback loop.

**Exit:** context retrieval is scoped, controllable and testable.

### M11 --- Admin, billing/credits, operational hardening

-   Admin control plane and health.
-   Atomic credit ledger/reservations/settlement.
-   Abuse limits, alerts, quotas.
-   Observability, backup/restore, incident runbooks.

**Exit:** financial/usage correctness and operational readiness tested.

### M12 --- Public release

-   End-to-end QA on Web/Android; iOS path verified.
-   Performance and load testing appropriate to initial capacity.
-   Security review, privacy/terms, store listing, release signing.
-   Rollout, monitoring, rollback.
-   Release notes and support process.

Do not skip milestones silently. If a dependency or provider is
unavailable, report blocker and propose a compatible path. Owner decides
changes that materially alter architecture, scope, spending or
permissions.

## 19. Acceptance test scenarios

1.  Basic chat succeeds; stream interruption recovers gracefully.
2.  User starts long research task, closes app, reopens and sees current
    status.
3.  Worker crash after checkpoint resumes without duplicating completed
    step.
4.  Provider outage routes to fallback or reports a clear failure.
5.  User cancels; no new tool action starts after cancellation
    acknowledged.
6.  Task budget exhausted; task pauses/terminates safely and partial
    result remains.
7.  Two users cannot read each other's conversations, files, projects,
    tasks or artifacts.
8.  Uploaded prompt-injection document cannot authorize external tool
    actions.
9.  Browser cannot access internal/private IPs through SSRF.
10. Coding sandbox cannot access host secrets or other user's workspace.
11. Duplicate task events do not duplicate UI output or billing.
12. Artifact download is private and expires where signed links are
    used.
13. High-risk external action shows a clear preview and requires
    approval.
14. Image provider returns a real artifact; provider failure isn't shown
    as success.
15. Unsupported video provider is shown as unavailable, not fake
    generation.
16. Usage reservation/settlement is atomic and retry-safe.
17. Admin disables a faulty engine and tasks fail over safely.
18. Arabic RTL, English LTR, narrow Android and web layouts work.

## 20. Launch experience and differentiation

SULY should feel like an agent workspace, not a collection of model
buttons: - The user speaks naturally; SULY decides when to answer, plan
or act. - Users can see the plan and progress without being buried in
technical logs. - Research deliverables include sources. - Coding
deliverables include files and test evidence. - Generated content is
organized in projects and artifact history. - Failures are recoverable
and explained, not hidden. - Users can choose model/control autonomy and
budget. - The product stays fast for simple requests and invests more
effort for complex tasks.

## 21. Public launch readiness checklist

-   [ ] Core chat and model gateway
-   [ ] Auth, RLS, ownership tests
-   [ ] Projects and conversation history
-   [ ] Durable agent tasks and worker recovery
-   [ ] Research with sources
-   [ ] File reading and output creation
-   [ ] Coding sandbox with tests
-   [ ] Browser engine isolated and secure
-   [ ] Image generation provider active
-   [ ] Video status accurately represented
-   [ ] Usage limits and ledger
-   [ ] Admin and health monitoring
-   [ ] Arabic/English UX
-   [ ] Web build deployed
-   [ ] Android release build and signing
-   [ ] iOS build/release path
-   [ ] Privacy/terms/support
-   [ ] Backups, restore, incident/rollback plan

## 22. Definition of a successful V1

SULY V1 is successful when a new user can complete a real, multi-step
task---research, file analysis, coding, browser-supported work, or
content creation---without manually orchestrating each tool, see
truthful progress, receive usable and verifiable outputs, and trust that
their data, permissions and spending are handled safely.

**Release mindset:** launch a powerful, bounded, honest product. Expand
capabilities based on real user tasks, reliability, cost and
feedback---not feature-count pressure.
