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


## Checkpoint مباشر — API readiness configuration

- أضيف `GET /ready` لتمييز حالة إعداد Supabase عن endpoint liveness `/health`.
- الفحص configuration-only ويعيد 503 عند نقص URL أو publishable key، و200 عند وجودهما؛ لا يفحص الاتصال الفعلي أو صحة DB.
- اختبارات الحالة الناقصة والمكتملة وعدم تسريب key placeholder أضيفت.
- Commits: `12f0aa5367fc` endpoint، `e341a1e6f869` tests.
- CI runs الخاصة بهذه التغييرات كانت ما تزال قيد التنفيذ عند آخر تحقق.
- لا نشر أو اتصال حي بقاعدة البيانات، ولا تشغيل workers أو engines.


## Session checkpoint — 2026-11-20 (Agent foundation)

- أضيف `AgentDefinition` لتعريف دور الوكيل وقدراته والمحركات المفضلة، مع إبقاء `enabled=false` افتراضياً.
- أضيف `AgentManager` لتسجيل الأدوار واختيار المحركات المسجلة والمفعّلة فقط عبر `EngineRegistry`، مع ترتيب تفضيلات الوكيل دون تشغيل المحرك.
- التوجيه يرفض الوكيل المعطل أو القدرة غير المدعومة أو غياب أي محرك مؤهل؛ ولا يمنح صلاحيات ولا ينفذ عمليات.
- أضيفت اختبارات لحالة التوجيه الطبيعي، وتفضيل المحرك، واستبعاد المحركات المعطلة، ورفض الوكلاء/القدرات غير المعروفة، وفشل الإغلاق الآمن.
- Commits: `937bb987dc1d` (manager), `e1d9d4b7bb31` (tests).
- CI على HEAD `e1d9d4b7bb3128c0ab60754aaadf8a1b195880c9` كان queued عند كتابة هذا checkpoint؛ لا يُسجل نجاح قبل اكتماله.
- هذا أساس إدارة وتوجيه فقط، وليس وكيلًا يعمل أو محركًا مدمجًا/مفعّلًا. ما زالت مراجعة مصادر upstream وتثبيت إصداراتها وترخيصها وعزلها واختبار تشغيلها مطلوبة.


## Session checkpoint — 2026-11-20 (Orphan engine-run reconciliation)

- أضيفت migration `20261120190000_reconcile_orphan_engine_runs.sql` لإنشاء RPC محدودة الدفعة (1–500) تغلق سجلات المحركات التي بقيت running بينما الخطوة ملغاة/نهائية أو انتهى lease الخاص بها.
- تستخدم المصالحة `FOR UPDATE SKIP LOCKED` لتجنب تنازع أكثر من عامل مصالحة، وتخزن رموز أخطاء عامة فقط، وتقتصر صلاحية RPC على service_role.
- أضيف `EngineRunStore.reconcile_orphans` مع التحقق من حجم الدفعة والتحقق الصارم من استجابة RPC.
- أضيفت اختبارات لحجم الدفعة، والاستجابات الطبيعية/المغلفة، ورفض القيم غير الصالحة.
- Commits: `4b2631294ff6` (migration)، `fabebc485b09` (store)، `c5fe327594ed` (tests).
- CI على HEAD `c5fe327594ed6630c7e4b2406908f8721f3a983d` كان queued عند التوثيق؛ لم يتم ادعاء نجاحه.
- حد مهم: RPC تغلق سجل SULY فقط، ولا توقف العملية الخارجية بنفسها. ما زال يلزم reconciler آمن يسترجع معرف upstream ويطلب الإيقاف بعد التحقق من lease/runtime ownership. لم تُطبق migration على أي قاعدة بيانات.


## Session checkpoint — 2026-11-20 (Agent routing + upstream intake)

- ربطنا `hermes_agent_turn` فعليًا بـ`AgentManager`: أصبح الدور `general-agent` يختار محركًا مؤهلًا من registry بدل اختيار المحرك مباشرة. لا يحدث تشغيل إلا بعد approval والـlease، ويظل Hermes خاضعًا لإعداداته الحالية.
- أضفنا catalog للأدوار: general, coding, research, browser, workflow. كل الأدوار غير المتاحة تظل disabled؛ لا يتم اختراع محركات أو إظهارها كأنها تعمل.
- أضيفت اختبارات تثبت وجود الأدوار، الإعدادات المعطلة، واستخدام AgentManager في مسار Hermes.
- Commits: `cfb2b858b260` (integration), `72d596250734` (tests).
- CI على `72d59625` كشف خطأ validation: Python bool يقبل int؛ أُصلح بشرط رفض bool صراحة في `7411adec258e`. على commit `7411adec`: Repository baseline checks وPlatform CI كلاهما **success**.
- أضيف سجل استلام ومراجعة لمصادر الوكلاء مع immutable audit SHAs، وقرار الترخيص/العزل لكل مشروع: `docs/operations/UPSTREAM_AGENT_ENGINE_INTAKE_AR.md`.
- تمت مراجعة LICENSE الفعلي لـDify وn8n؛ Dify يقيّد multi-tenant دون موافقة مكتوبة، وn8n Sustainable Use License يقيّد الاستخدام التجاري/تقديم الخدمة للغير. لم يتم دمجهما.
- OpenHands مرشح أول للـcoding backend لكن توثيقه يحذر من host filesystem/shell/network access؛ لا تشغيل دون sandbox. Browser Use يتطلب عزل REPL وChrome profile وegress.
- CI لتغييرات التوثيق الأخيرة ما زال قيد الانتظار وقت checkpoint.
- لا يوجد build/run حي لمحرك upstream إضافي، ولا نسخ source أو تفعيل خدمة. لا migrations مطبقة.


## Session checkpoint — 2026-11-20 (External engine stop reconciliation)

- أضيفت migration `20261120210000_engine_stop_reconciliation.sql`: عند انتهاء lease أو إلغاء/إنهاء الخطوة، إذا كان هناك `upstream_run_id` لا يُغلق سجل المحرك مباشرة؛ يتحول إلى `stop_pending` حتى يتم إيقاف التشغيل الخارجي.
- أضيفت RPCs server-only لحجز تشغيلات الإيقاف بlease مستقل، وتأكيد الحالة النهائية، أو تحرير الحجز مع backoff عند الفشل.
- أضيف `stop_agent_run` في Hermes bridge: يتحقق من run ID، يرسل stop، ثم ينتظر حالة نهائية محدودة الوقت دون قراءة output. يبقى متاحًا لإيقاف التشغيلات المعروفة حتى عند تعطيل بدء تشغيل Hermes جديد، بشرط وجود credentials الخادم.
- أضيف `EngineRunReconciler` الذي يصالح السجلات المنتهية أولًا ثم يحجز ويوقف المحركات المدعومة، مع عدم تسجيل تفاصيل أخطاء خارجية.
- أضيفت إعدادات `ENGINE_RECONCILER_ENABLED=false` ومدة دورة افتراضية 30 ثانية. لا يبدأ reconciler إلا بإعداد صريح، ومع وجود Hermes URL/key. لا يتم تشغيله تلقائيًا في API.
- أضيفت اختبارات لحجز/تحقق/رفض claims، تأكيد إيقاف Hermes، backoff، فشل الإيقاف، وجدولة reconciler في WorkerRuntime.
- Commits الرئيسية: `cad84f16c623` (DB state), `fbd80bcd9b44` (store), `a0e4213cc7f8` (Hermes stop), `3c6c4076e90c` (reconciler), `b922f0a74ac4` (worker scheduling), `3c90a41f0abb` (tests).
- CI: على `8080478aa8bb` نجح Platform CI؛ إصلاح اختبار async sleep بعد فشل واحد سابق. Baseline checks لآخر commit `3c90a41f` كانت queued وقت التوثيق، وPlatform CI قيد التنفيذ.
- لا تزال migration غير مطبقة على أي DB. تفعيل `ENGINE_RECONCILER_ENABLED` قبل تطبيق migration واختبارها في بيئة disposable ممنوع.
- حد أمان: المحرك غير المدعوم لا يُعتبر متوقفًا؛ يتم تحرير claim مع backoff. يجب إضافة stopper خاص به قبل تسجيله كمدعوم.
