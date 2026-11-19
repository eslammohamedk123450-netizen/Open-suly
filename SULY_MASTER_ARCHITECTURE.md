# SULY AI --- Master Architecture & Engineering Constitution

**Version:** 1.0 • **Status:** Foundation reference • **Product:** SULY
AI\
**Vision:** More Than AI. Your Intelligent Partner.

> This document is the architectural north star for SULY. It defines the
> product vision, capabilities, system boundaries, technology choices,
> data flows, execution lifecycle, security, quality, and scaling
> principles. It does not authorize uncontrolled scope expansion or
> blind copying of third-party repositories.

## 0. Product mandate

SULY is an AI Agent platform that accepts user goals, clarifies
ambiguity when necessary, plans work, selects models and tools, executes
real actions in controlled environments, observes outcomes, recovers
from failures, verifies deliverables, and returns usable results.

SULY is not a thin chat UI around a model API. Chat is the primary
interaction surface; the product's value is its persistent task
execution and integrated capabilities.

**Target experience:** A user can ask SULY to research, reason, discuss,
create documents, analyze files, create images (through connected image
models), prepare video-generation requests or generate video where a
supported provider is connected, browse websites, write and modify code,
build projects, use integrations, and carry out multi-step work with
progress and deliverables.

### Product principles

1.  User goal first: the plan is adapted to the requested outcome, not a
    fixed workflow.
2.  One coherent platform: central orchestration, common tool contracts,
    common task state, common permissions.
3.  Capability depth over agent count: engines are actual working
    systems, not prompt personas.
4.  Persistent execution: tasks survive app closure, refresh,
    disconnect, and worker restart where infrastructure supports it.
5.  Truthful status: distinguish planned, running, blocked, failed,
    partial, and completed.
6.  Verifiable outputs: test or inspect deliverables before presenting
    them as complete.
7.  User control: confirmation gates for sensitive, irreversible,
    external, financial, or destructive actions.
8.  Cost-aware intelligence: choose model/tool based on quality
    requirement, latency, budget, availability, and policy.
9.  Secure by default: least privilege, isolation, server-side secrets,
    explicit grants, auditability.
10. Build for evolution: replace engines/providers without rewriting the
    entire product.

## 1. Product capabilities map

### 1.1 Conversation and task UX

-   Chat-first experience with text streaming and structured activity
    timeline.
-   Normal chat, deep task/agent mode, and project-scoped work.
-   Conversation/project context, attachments, task references,
    artifacts and history.
-   Task plan display with editable/approved steps where appropriate.
-   Progress events: queued, planning, tool selected, executing, waiting
    for approval, retrying, verifying, completed, partial, failed,
    cancelled.
-   Stop, pause/resume (when supported), retry, continue, and task
    feedback.
-   User-facing summaries, sources, tool activity transparency, and
    output previews.
-   Arabic-first RTL, English support, localization architecture.

### 1.2 Intelligence layer

-   Central Agent / Orchestrator.
-   Intent and task classification.
-   Context assembly with token-aware trimming and retrieval.
-   Planner that produces structured task plans (steps, dependencies,
    required capabilities, expected artifacts, risk).
-   Model Router / AI Gateway: provider abstraction, model catalog,
    routing policies, fallback, retries, streaming, rate-limit handling.
-   Agent runtime: bounded loops, tool-call budget, time budget,
    token/cost budget, max depth and iteration limits.
-   Critic / verifier: check requirements and output quality, detect
    missing work and unsupported claims.
-   Re-planning: revise plan based on observation, failure, new user
    input, or changing environment.
-   Memory retrieval: conversation, project, preference and task memory
    with user controls and privacy boundaries.
-   Specialist agents as role configurations backed by shared runtime;
    avoid duplicating orchestration logic.

### 1.3 Execution engines (capability modules)

All engines expose a standard contract and report progress,
observations, artifacts, cost, and errors.

  ---------------------------------------------------------------------------
  Engine                  Launch-grade baseline       Advanced evolution
  ----------------------- --------------------------- -----------------------
  Research/Web            search providers,           query expansion,
                          fetch/open pages, source    iterative
                          collection, synthesis,      investigation, source
                          citations                   triangulation, deep
                                                      research

  Browser                 isolated browser sessions,  persistent workflows,
                          navigation, click/type,     complex authenticated
                          screenshots, extraction,    flows, resilient
                          downloads under policy      selectors, browser
                                                      fleets

  Coding                  repo/file inspection,       multi-file refactor,
                          patching, command execution autonomous repair
                          in sandbox, tests, error    loops, longer tasks,
                          analysis, review            repo-level planning

  Files/Docs              read supported formats,     batch processing,
                          extract/transform, generate templates, semantic
                          DOCX/PDF/XLSX/CSV/MD/TXT    search, advanced
                          and previews                conversion

  Data/Analysis           safe tabular processing,    larger datasets,
                          Python sandbox, charts,     repeatable analysis
                          calculations                jobs, specialized
                                                      runtimes

  Image                   prompt construction,        multi-image workflows,
                          provider routing, generated image understanding,
                          image retrieval, editing    editing pipelines
                          where provider supports     

  Video                   provider adapter,           longer generation,
                          prompt/script/storyboard,   scene workflow, editing
                          generation/status polling,  and compositing
                          storage and output delivery integrations
                          when providers support      
                          video                       

  Workflow                graph of actions,           reusable templates,
                          conditions, retries,        trigger/event
                          approval checkpoints,       automation, external
                          schedules when enabled      workflow integrations

  Computer-use            controlled desktop/GUI      remote desktop pools,
                          environment, visual         advanced recovery and
                          observation and action      multi-app workflows
                          execution where available   

  Integrations            OAuth/API adapters, scoped  connector marketplace,
                          permissions, secrets stored event/webhook
                          server-side                 integrations,
                                                      user-defined tools
  ---------------------------------------------------------------------------

Capability must be feature-gated by provider, environment, permission,
budget, and availability. The UI must not claim video or desktop actions
are available if no usable provider/worker is configured.

### 1.4 Skills and tools

-   Skill Registry: discoverable skills with metadata, version, schemas,
    permission requirements, engine/provider dependencies, risk class
    and tests.
-   Skill packages are instructions + validated tool bindings + optional
    code; they are not arbitrary unrestricted scripts.
-   Tool Registry: schemas, input validation, auth scope, timeout, retry
    policy, rate limits, idempotency, audit events.
-   Tool invocation follows an allowlist and permission policy.
-   Tool results are treated as untrusted data. Prompt injection in
    webpages/files must not override system policy.
-   Skills can be installed, disabled, updated, tested, and
    version-pinned; user/admin controls required.

## 2. Reference inspiration (not copy-paste architecture)

Use the 18 reference projects as capability research sources. Their
implementation, license, security, maintenance and dependency status
must be checked individually before reuse.

  -----------------------------------------------------------------------
  Reference                           Capability inspiration
  ----------------------------------- -----------------------------------
  OpenManus                           general autonomous agent/task
                                      execution

  Hermes Agent                        persistent agent workflows and tool
                                      use

  OpenHands                           coding agent, repository and
                                      environment execution

  OpenClaw                            agent/tool integration patterns

  OpenCode                            coding workflows and developer
                                      interaction

  Browser Use                         browser agent interaction

  LangGraph                           explicit graph/stateful
                                      orchestration

  Dify                                application/workflow orchestration
                                      and visual configuration

  UI-TARS                             visual UI understanding /
                                      computer-use research

  CrewAI                              specialist coordination patterns

  Open Interpreter                    controlled execution and computer
                                      interaction concepts

  Screenpipe                          context capture/search patterns;
                                      privacy review required

  Nanobot                             lightweight agent architecture
                                      patterns

  IronClaw                            safety and tool-use design
                                      inspiration

  ZeroClaw                            modular runtime/agent patterns

  Aider                               code editing and repository
                                      workflow patterns

  n8n                                 workflow graph and integrations

  Skyvern                             browser automation patterns
  -----------------------------------------------------------------------

Do not treat this table as an endorsement, security audit, license
clearance, or a mandate to incorporate all code. Create an architecture
decision record for any dependency or copied code.

## 3. Approved technology direction

### Client

-   Expo + React Native + TypeScript.
-   Expo Router for cross-platform navigation.
-   React Native Web for shared UI where practical.
-   Targets: Android, iOS, Web.
-   Platform-specific components are allowed where web/native behavior
    differs.
-   Design system: Midnight Gold Luxury; dark foundation, restrained
    gold accent, Arabic RTL/Tajawal support and English/Inter,
    accessibility and responsive layouts.
-   Chat-first UI with projects/tasks/artifacts; not a dashboard-first
    experience.

### Backend

-   Python + FastAPI as SULY's backend/API and agent orchestration
    service.
-   Pydantic schemas for validation and typed contracts.
-   Async I/O for API/provider calls; bounded concurrency.
-   Modular monolith initially, with clean module boundaries. Split into
    services only when measurable load, security or operational needs
    justify it.
-   Background worker processes for long-running, blocking, browser,
    coding and media jobs; never rely on a single HTTP request for long
    task execution.

### Data and managed infrastructure

-   Supabase PostgreSQL as managed database initially.
-   Supabase Auth for authentication.
-   Supabase Storage for user assets and task artifacts.
-   Realtime for task status/events when appropriate.
-   Row Level Security for user-owned records; explicit server-side
    authorization.
-   Queue/outbox/durable job pattern. Select an appropriate queue
    implementation; start with a Postgres-backed queue if suitable and
    migrate to a dedicated broker if volume or reliability demands.
-   Keep business logic and repository/data access behind SULY service
    interfaces to reduce lock-in. Moving database/Auth later is a
    migration project, not a magic toggle.

### Hosting

-   Vercel (or a suitable static/managed web host) for web frontend,
    depending on Expo web output and deployment needs.
-   API and persistent workers on a container-capable host/VPS/cloud
    service.
-   GitHub for version control, issue tracking, CI, release history.
-   EAS Build/Submit or other appropriate build pipeline for mobile
    packages and store release.
-   GitHub Pages only for static content, documentation or static
    export---not persistent API, workers, browser sessions or database.

### AI provider layer

-   Unified provider adapters; never hardcode one model vendor
    throughout the system.
-   Support provider/model configuration, capabilities, context size,
    modalities, latency estimates, pricing metadata (where available),
    availability, rate limits and tool support.
-   Route tasks by capability and policy. Users/admins may choose
    preferred models, but server validates allowed provider/model.
-   Secrets stored only in server-side secret manager/environment. No
    provider secret in client app or Git.
-   Optional user BYOK should be encrypted and handled server-side with
    careful scope, consent and deletion controls.

## 4. System architecture

``` mermaid
flowchart TD
  U[User] --> APP[Expo App: Android / iOS / Web]
  APP -->|HTTPS / Auth token / stream| API[FastAPI API Gateway]
  API --> AUTH[Auth & Policy]
  API --> CHAT[Chat / Project Service]
  API --> TASK[Task Service]
  API --> AI[AI Gateway / Model Router]
  API --> DB[(Supabase PostgreSQL)]
  API --> STORE[(Supabase Storage)]
  API --> RT[Realtime / Task Events]
  TASK --> Q[Durable Queue / Outbox]
  Q --> W[Worker Pool]
  W --> ORCH[Agent Orchestrator]
  ORCH --> PLAN[Planner / Task Graph]
  ORCH --> ROUTER[Model Router]
  ORCH --> REG[Tool & Skill Registry]
  ORCH --> RESEARCH[Research Engine]
  ORCH --> BROWSER[Browser Engine]
  ORCH --> CODE[Code Sandbox Engine]
  ORCH --> FILES[Files & Docs Engine]
  ORCH --> DATA[Analysis Engine]
  ORCH --> MEDIA[Image / Video Provider Engine]
  ORCH --> WORKFLOW[Workflow Engine]
  ORCH --> VERIFY[Verifier / Critic]
  W --> DB
  W --> STORE
  W --> RT
  API --> OBS[Logs / Metrics / Traces]
  W --> OBS
```

## 5. Request and execution lifecycle

``` mermaid
sequenceDiagram
  participant User
  participant App
  participant API
  participant Agent
  participant Queue
  participant Worker
  participant Tools
  participant DB
  User->>App: Goal / prompt / attachments
  App->>API: Authenticated request
  API->>DB: Save user request + task
  API->>Queue: Enqueue task
  API-->>App: task_id + initial state
  App->>API: Subscribe/poll task events
  Queue->>Worker: Claim task (lease)
  Worker->>Agent: Context + policy + budget
  Agent->>Agent: Plan / select engine / split steps
  Agent->>Tools: Execute validated action
  Tools-->>Agent: Observation / result / artifact
  Agent->>Agent: Verify, retry, or re-plan
  Agent->>DB: Save checkpoint and event
  DB-->>App: Realtime progress
  Agent->>Worker: Final verified result
  Worker->>DB: Completed/partial/failed + artifact refs
  App-->>User: Summary, citations, downloadable artifacts
```

### Task state machine

`created → queued → planning → running → waiting_approval → running → verifying → completed`

Additional states: `retrying`, `paused`, `partial`, `failed`,
`cancel_requested`, `cancelled`, `expired`.

State transitions must be validated on the server. Terminal tasks cannot
silently be rerun. Retry is a new attempt or a controlled continuation
with clear attempt identity.

### Durable execution requirements

-   Task and plan saved before execution.
-   Worker claims task with lease/heartbeat.
-   Checkpoint after each meaningful step.
-   Idempotency key for provider/tool operations when supported.
-   Retry policy with exponential backoff, jitter, max attempts, and
    retryable-error classification.
-   Recover abandoned leases after worker crash.
-   Cancellation is cooperative; tool/worker cancellation behavior
    documented.
-   Timeout and resource limits for each tool.
-   Task ledger records model/tool costs and usage.
-   User-facing partial results preserved on failure.
-   Duplicate event delivery tolerated; clients de-duplicate by
    event/task sequence.
-   Avoid exactly-once claims where infrastructure only guarantees
    at-least-once; use idempotency and deduplication.

## 6. Orchestrator design

Central orchestrator owns the task lifecycle and coordination;
specialist engines do not independently create competing task state.

### Planning schema (conceptual)

A plan contains: - task goal and normalized requirements; -
assumptions/questions; - ordered or DAG steps; - dependency edges; -
selected engine/tool capability; - inputs and expected outputs; - risk
and approval requirements; - estimated budget/time; - retry/verification
strategy.

### Planning rules

-   Small requests may use direct execution without elaborate plan.
-   Complex tasks use a plan/DAG.
-   Parallelize only independent steps.
-   Prefer the least risky and least costly tool that can satisfy the
    task.
-   Ask user only for essential missing information.
-   If plan changes materially, surface a progress update.
-   Limit autonomous loops and re-planning.
-   Maintain task budget and deadline.
-   No agent may bypass shared permissions, cost controls, task ledger,
    or sandbox policy.

### Model routing

Route based on task class, required modality, reasoning/quality,
context, tools, latency, cost, provider health and user selection. Model
router supports: - primary/fallback lists; - provider timeouts and
circuit breakers; - retry only on appropriate errors; - streaming where
supported; - model capability registry; - budget-aware routing; - model
availability health checks; - admin test/validation; - usage and cost
reporting. Never promise identical model behavior across providers.

## 7. Engine contract

Each engine should follow a common interface conceptually:

-   `engine_id`, version, capabilities, availability, health.
-   `validate_input(schema)`.
-   `execute(context, inputs, permissions, budget, cancellation)`.
-   progress events.
-   structured observations.
-   artifact references.
-   usage/cost estimates and actual usage.
-   warnings and error classification.
-   `verify(output, requirements)` where applicable.
-   cleanup/session release.

Engines run with explicit tool access, not unrestricted access to all
platform resources.

## 8. API and realtime boundaries

Use versioned API routes (`/api/v1/...`) and typed request/response
schemas. Avoid leaking internal worker/engine schemas directly to mobile
clients.

API categories: - Authentication/session bootstrap. -
Conversations/messages/streaming. - Projects and project context. -
Tasks: create, get, list, cancel, retry/continue, approve/reject
action. - Artifacts: list, metadata, secure download. - Skills/tools:
capability catalog and status. - Models: safe catalog, preferences. -
Usage/credits/ledger. - Integrations: connection status and OAuth
flow. - Admin: providers, engines, worker health, policy, feature flags.

Realtime events: `task.created`, `task.plan.updated`,
`task.step.started`, `task.step.progress`, `task.tool.started`,
`task.tool.completed`, `task.tool.failed`, `task.approval.required`,
`task.artifact.created`, `task.retry`, `task.verification`,
`task.completed`, `task.partial`, `task.failed`, `task.cancelled`.

Every event has task ID, event ID/sequence, timestamp, safe payload and
schema version. No secrets in event payloads.

## 9. Data domains

Design tables/domains with migrations and explicit ownership: -
users/profiles/preferences. - sessions and auth provider references
(managed Auth where possible). - conversations, messages, message
attachments. - projects, project membership, project context. - tasks,
task attempts, plans, steps, dependency edges. - task events,
checkpoints, worker leases. - tool/skill registry and versions. -
provider/model catalog and health. - user/provider preferences. -
integrations, encrypted credentials reference and scopes. - artifacts
and artifact versions. - usage ledger, credit transactions,
reservations, settlement. - approvals and permission grants. - feedback,
quality checks. - audit/security events. - admin settings/feature
flags. - memory records with type, scope, source, confidence, retention,
visibility and user controls.

### Database principles

-   Every user-owned row has user/project ownership.
-   RLS policies on all client-accessible tables; default deny.
-   Worker/service role never exposed to clients.
-   Database migrations tracked in repository and reviewed.
-   Atomic credit reservation/settlement; no double charge.
-   Use foreign keys, indexes, constraints and transaction boundaries.
-   Avoid storing full sensitive tool/browser content unless needed and
    retention is defined.
-   Soft-delete/retention policies are explicit; sensitive deletion must
    cover derivatives where feasible.

## 10. Security and safety architecture

### Trust boundaries

-   Client is untrusted.
-   External websites, files, model output and tool output are
    untrusted.
-   Provider keys and service credentials are secret.
-   Workers and sandboxes are separate security boundaries.
-   Agent-generated actions require policy validation.

### Controls

-   Authentication and server-side authorization on every request.
-   RLS with least privilege.
-   Secret management, rotation, redaction.
-   Secure OAuth with minimum scopes, state validation and revocation.
-   Sandbox code execution: non-root, isolated filesystem, no host
    secrets, CPU/RAM/time limits, network deny-by-default or controlled
    egress, disposable environment, output size limits.
-   Browser isolation: per-task or per-session isolated context,
    download controls, credential handling, domain policy, prevent
    cross-user session leakage.
-   SSRF protection: block internal/private IP ranges and unsafe
    schemes, validate redirects and DNS resolution for server-side
    fetch/browser tools.
-   Prompt-injection defenses: treat retrieved text as data; tool
    allowlists; separate instructions from content; approval for
    sensitive actions.
-   Rate limits, abuse detection, quotas, bot and credential abuse
    protection.
-   Content and action safety policy.
-   Audit events for approvals, integrations, external actions,
    privileged changes.
-   Backups, restore tests, incident procedures.
-   No destructive/external action without appropriate user
    confirmation.

### Risk tiers

-   Low: read-only search, summaries, calculations.
-   Medium: file creation, code changes in sandbox, draft messages.
-   High: authenticated account actions, publishing, sending, deleting,
    spending, irreversible changes. High-risk actions require explicit
    confirmation and clear preview. Risk policy can be tightened by
    user/admin.

## 11. Cost, credits, and resource governance

-   Usage ledger is authoritative.
-   Reserve estimated usage before task; settle actual usage after;
    release unused reservation.
-   Record model/provider, tokens, tool usage, duration, retries, and
    cost where known.
-   Prevent concurrent double-spending with atomic DB operations.
-   Per-user, per-task, per-provider, and global limits.
-   Budget passed into orchestrator and every worker/tool.
-   Stop or ask for confirmation when budget limit reached.
-   Admin-configurable model routing, provider fallback and pricing
    estimates.
-   Credits must never be charged twice because of retries or duplicate
    events.
-   Separate internal estimated cost from customer billing and disclose
    uncertainty.
-   Reward/free usage must be abuse-resistant and financially bounded.

## 12. Observability and quality

-   Structured logs with correlation/task/attempt/step IDs.
-   Metrics: task success rate, partial rate, retry rate, latency, queue
    wait, worker saturation, provider errors, cost/task, cancellation,
    tool failure.
-   Trace request → plan → step → tool → provider → artifact.
-   Redact secrets and sensitive content from logs.
-   Admin health view for queue, workers, providers, engines and errors.
-   User feedback and evaluation sets.
-   Tests: unit, API, integration, RLS, security, sandbox, provider
    contract, task end-to-end, mobile/web, load, recovery.
-   Quality checks evaluate requirements coverage, factual support,
    artifact validity, code test result and tool-result consistency.
-   Track product outcomes, not only model benchmark scores.

## 13. Scaling strategy

### Stage A --- modular platform

-   One backend deployment with modular services.
-   Managed PostgreSQL/Auth/Storage.
-   One queue mechanism.
-   One worker host with multiple bounded worker processes.
-   Provider adapters.
-   Strict task limits.

### Stage B --- workload separation

-   Separate browser workers, coding workers, media workers and research
    workers.
-   Independent concurrency and queue limits.
-   Dedicated sandbox/containers.
-   Metrics-driven autoscaling where host supports it.

### Stage C --- distributed execution

-   Multiple worker nodes.
-   Dedicated queue/broker if justified.
-   Artifact storage lifecycle policies.
-   Provider circuit breakers.
-   Regional deployment only if demand, latency or compliance warrants
    it.

**Scale trigger:** Do not split services or buy infrastructure because
it sounds impressive. Split based on observed bottlenecks, failure
isolation, security boundary, cost or operational need.

## 14. Repository layout proposal

``` text
suly/
├── apps/
│   ├── client/                 # Expo app: web + Android + iOS
│   └── admin/                  # Admin UI (may share app or be separate)
├── backend/
│   ├── api/                    # FastAPI routes, middleware, auth
│   ├── core/                   # orchestrator, planner, router, policies
│   ├── domains/                # chat, projects, tasks, usage, artifacts
│   ├── engines/                # research, browser, coding, files, data, media
│   ├── tools/                  # validated tool implementations
│   ├── skills/                 # skill registry/packages
│   ├── providers/               # model and media adapters
│   ├── workers/                 # durable worker entrypoints
│   ├── schemas/                 # shared server schemas
│   └── tests/
├── infra/
│   ├── docker/                  # Dockerfiles and compose for local/dev
│   ├── deployment/               # hosting manifests/config templates
│   └── monitoring/
├── supabase/
│   ├── migrations/
│   ├── policies/
│   └── seed/
├── packages/
│   ├── shared-contracts/         # API/event schema definitions
│   └── design-system/
├── docs/
│   ├── MASTER_ARCHITECTURE.md
│   ├── V1_LAUNCH_BLUEPRINT.md
│   ├── decisions/
│   ├── security/
│   └── operations/
├── scripts/
├── .env.example
├── .gitignore
└── README.md
```

Adjust this structure only through an architecture decision record. Do
not create all directories empty just to imitate this diagram; create
modules as implementation begins.

## 15. Delivery discipline / AI coding-agent rules

1.  Read the master architecture and launch blueprint before editing.
2.  Work on the production/main branch unless owner explicitly requests
    another branch.
3.  Never create branches without explicit owner permission.
4.  Never replace the whole project to fix a localized issue.
5.  Inspect existing files and tests before editing.
6.  Implement one bounded milestone at a time.
7.  Before changes: report intended files, plan, risk and tests.
8.  After changes: run available checks and report actual outcomes; do
    not claim tests passed if not run.
9.  Keep migrations backward-compatible where possible; provide
    rollback/backup steps for risky migrations.
10. Do not commit secrets, tokens, user data or private keys.
11. Do not invent environment variables or pretend a provider is
    configured.
12. If an external integration cannot be tested, state it.
13. Keep docs, schemas, API contracts and tests synchronized.
14. Ask owner before irreversible, billing, publication, credential, or
    security policy decisions.
15. No scope expansion without updating the blueprint and obtaining
    owner approval.
16. Every milestone ends with a concise report: changed, tested, not
    tested, risks, next milestone.
17. No fake placeholders for core launch capabilities. A capability is
    either functional, clearly unavailable, or explicitly marked in
    development.
18. Do not add dependencies without checking license, maintenance,
    security, size and platform compatibility.

## 16. Definition of done (platform-wide)

A feature is done only when: - acceptance criteria are explicit and
met; - API and authorization are implemented; - UI reflects real
states; - error/loading/empty states exist; - tests are added and pass
where runnable; - security and privacy review is performed; - usage/cost
impact is understood; - docs are updated; - failure and retry behavior
are considered; - deployment and rollback implications are documented.

## 17. Product north-star metrics

-   Task success with verified deliverables.
-   User-perceived helpfulness and repeat use.
-   Task completion rate without manual rescue.
-   Median and P95 time-to-first-useful-progress.
-   Recovery rate after transient failure.
-   Cost per successful task and cost per user.
-   Source quality for research.
-   Code task verification rate.
-   Safety/permission incident rate.
-   Artifact delivery success.
-   Retention and paid conversion; monitor without manipulative dark
    patterns.

## 18. Architecture decision record (ADR) template

For material decisions: - Title/date/status. - Context and problem. -
Options considered. - Decision. - Consequences/tradeoffs. -
Security/cost/maintenance implications. - Migration/reversal plan. -
Owner approval.

## 19. North-star statement

**SULY should transform a user's goal into a verified outcome---not
merely transform a prompt into text.** Build the platform as a
trustworthy, persistent, cost-aware, extensible agent system that can
research, create, code, operate tools and coordinate workflows under
user control.
