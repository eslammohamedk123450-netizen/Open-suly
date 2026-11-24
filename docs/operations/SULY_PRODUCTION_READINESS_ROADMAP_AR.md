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
- [x] Shared Hermes task-context character budget (12k prompt-plus-context ceiling when the original prompt fits; long prompts preserved; Platform CI #1589 green)
- [x] cooperative stop + bounded terminal-state polling contract (mocked unit tests; remote process termination not live-verified)
- [ ] per-task/tenant disposable runtime isolation (host-isolated Docker bridge implementation added; real-Docker CI and deployment-host verification still required)
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
- [x] Read-only credits summary API + client history view (user-token/RLS, disabled by default)
- [x] Disposable PostgreSQL credit-ledger integration: grant/reserve/settle/release/expiry, concurrency, RLS
- [x] Capture OpenAI-compatible/Ollama token usage in chat metadata and display in client (no billing)
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
- [ ] user data export/delete and privacy policy (جزئي: تصدير JSON للمحادثات فقط عبر JWT المستخدم وRLS؛ لا يشمل projects/files/memories/credits ولا حذف الحساب)
- [ ] final production checklist and known limitations

## تعليم الكود
- SULY-owned source: Arabic comments at logical statements/branches, docstrings for classes/functions, type annotations, concise comments explaining purpose/why. Avoid comments on every syntactic token when they clutter code or risk changing generated/config/license files.
- Upstream files: preserve original source, headers, license, and avoid invasive Arabic comments that break maintainability. Provide separate Arabic learning guides explaining module purpose, key functions, flow, inputs/outputs, and integration points.
- Each added/modified file includes a short Arabic module guide where appropriate.
- Do not mark work complete based only on generated code; CI, tests, review, and runtime evidence are required.

## Current known blockers (2026-11-21)
- Supabase engine_runs and reconciliation migrations are committed but have not been applied to any live database; disposable PostgreSQL validation and explicit Staging approval are still required.
- Worker, Hermes, OpenCode and model providers remain disabled by default.
- Runtime task bridges require Docker Engine 28+ `inhibit_ipv4=true` on an internal bridge, with IPv6/ICC/masquerading disabled. The latest live Docker CI run on 2026-11-22 proved the host bridge has no IPv4 address, but also showed that this task network provides no host port binding; the prior claim that NAT-mode loopback publishing remained available was incorrect. The provisioner now returns 503 `runtime_gateway_unavailable` and cleans up rather than weakening isolation. A separate control-network gateway/sidecar must be implemented and tested before runtime acquire can work. The live probe verifies host-service, metadata-IP and external-egress denial without claiming gateway reachability. Production host-firewall policy, crash-time process-tree teardown, and task-aware SSRF/egress proxy enforcement remain separate gates.
- Runtime SQLite now enforces a unique `(task_id, engine_run_id)` index and rejects duplicate attempts before Docker allocation; concurrent registration races are protected by the database constraint. Existing duplicate rows fail startup closed and require operator reconciliation; this is not a substitute for full task-run admission idempotency.
- OpenCode result export now rejects unsafe POSIX/Windows archive paths and case-fold collisions, skips credential-oriented paths, and suppresses the exact per-runtime token plus known secret patterns. This is defense in depth, not a complete DLP system; no novel-secret detector or live cross-tenant runtime test is claimed.
- No production API/worker deployment or live model provider is configured.
- Latest CI on HEAD f3afbd9d098ed4ff7c80b1cd8141660c25c6930b exposed Worker syntax, Hermes toolset-default, and OpenCode test-double contract failures; commits 352800efe8400ae07d4373b41ec6406b5a173603 and fcea64cce7ff1c140542ca716686c14ed01dcf8a contain fixes. Their CI results must be confirmed before marking this repair complete.
- Credit ledger foundation/RPCs have disposable PostgreSQL integration coverage, but reserve/settle/release are not wired into OpenCode/Hermes task lifecycle. Pricing/token-to-credit conversion, usage metering, idempotent partial billing, and budget enforcement remain prerequisites before enabling user execution.

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


## Session checkpoint — 2026-11-20 (Sandbox policy foundation)

- أضيف `sandbox_policy.py` لبناء argv لـDocker دون تشغيله، مع صورة مثبتة بـSHA-256 digest فقط.
- السياسة تفرض network=none، root filesystem read-only، إسقاط كل Linux capabilities، no-new-privileges، حدود CPU/RAM/PIDs/ulimits، مستخدم غير root، وmount واحد لمساحة عمل خاصة ومملوكة لهوية worker.
- نرفض مسارات خارج workspace root والروابط الرمزية والصلاحيات المفتوحة وأسماء الصور mutable tags وأوامر غير صالحة.
- أضيفت اختبارات لقيود الموارد، الصور، المسارات، symlinks، صلاحيات المجلد، وعدم تمرير Docker socket.
- Commits: `2cec8a1e4151` (policy), `5fef4002f0ba` (initial tests), `1c3800fd8596` (type validation), `b5ac371b2b70` (private workspace), `336a11140915` (tests).
- هذه policy builder فقط؛ لا يوجد Docker runner أو image build أو container فعلي حتى الآن. كما أن network=none يعني أن أي coding agent لن يستطيع الوصول لمزود LLM قبل بناء egress proxy مقيد ومختبر.
- لا تفعيل للمحركات ولا mounts لملفات المستخدمين؛ لا يوجد Docker socket أو host networking.


## Session checkpoint — 2026-11-20 (Agent planning + late identity + sandbox hardening)

- أضيف `agent:` و`وكيل:` إلى planner لتكوين خطوة Hermes عامة فقط عندما تكون إعدادات Hermes مكتملة، والعزل مؤكد، والمحرك مفعّلًا. لا يتم إنشاء plan لوكيل غير متاح.
- تم تشديد `AgentManager` و`EngineRegistry` على أنواع metadata والـflags والـtimeouts والـadapters لمنع القيم غير المتوقعة.
- أضيفت migration `20261120220000_late_engine_run_identity.sql`: Hermes run الذي يفقد lease قبل حفظ run_id يبقى `stop_pending`، ويسمح بحفظ المعرف المتأخر دون استعادة صلاحية التنفيذ؛ يرجع attach false كي يوقف العامل التشغيل فورًا، ثم يتولى reconciler المحاولة.
- أصلحنا مسار Hermes عند فشل callback حفظ run_id: يعيد محاولة RPC مرة واحدة (idempotently)، ثم يرسل stop best-effort ولا يكمل التنفيذ.
- أصلحنا sandbox builder لتهيئة حدود الموارد قبل التحقق من ملكية workspace، وفرض `--pull=never` و`--memory-swap` مساويًا للذاكرة لمنع السحب التلقائي واستخدام swap.
- CI: Platform CI وBaseline على `d7fe1543a41a` نجحا. API tests على `3598544eed8d` نجحت؛ Platform CI وBaseline للـHEAD الأحدث كانا قيد التنفيذ وقت التوثيق.
- لا تزال كل migrations غير مطبقة. لا يوجد Docker runner أو image build أو egress proxy أو محرك coding/browser إضافي يعمل. sandbox policy builder لا يثبت العزل الفعلي.


## Session checkpoint — 2026-11-20 (Agent catalog and client integration)

- أضيف endpoint محمي بالمصادقة `GET /v1/agents` يعرض الأدوار والقدرات وحالة التوفر وأسماء المحركات فقط، دون أسرار أو مفاتيح.
- أضيفت اختبارات لوظائف الكتالوج ورفض الطلب غير المصادق.
- شاشة Agent تعرض أدوار الوكلاء وحالة كل دور.
- عميل التطبيق يستخدم `/auto-plan` في تحليل النص وHermes بدل إرسال خطة جاهزة من العميل؛ يرسل prefix صريحًا ويترك التحقق من القدرة والتفعيل والعزل للخادم.
- تم توحيد tool catalog ليعرض AI/Hermes/Task Engine متاحًا فقط عند تفعيل Worker، وHermes يتطلب isolation attestation وإعداداته كاملة.
- واجهة التطبيق تعطل إرسال المهمة إذا كان worker أو المحرك المطلوب غير متاح.
- Commits: `178c1be01802` (router), `2c8f7ad35966` (tests), `89957bf2fa5e` (auto-plan client), `477df523a12f` و`3050736ca0b1` (availability gates), `baf5bd807d83` و`288d2cd2130b` (client catalog/UI).
- CI على HEAD `e99f0e1349d4` قيد التنفيذ وقت التوثيق؛ لا يُسجل نجاح قبل اكتماله.
- لا يزال OpenHands/OpenCode/Aider/Browser Use غير مشغّل؛ لا يوجد Docker runner أو egress proxy. هذه المرحلة تبني catalog/route والحدود، وليست إعلان تشغيل المحركات.


## Session checkpoint — 2026-11-20 (Agent plan safety and readiness gates)

- أضيفت مصادقة وتحقق موحد لخطط المهام المرسلة من العميل: العمليات يجب أن تكون مسجلة في ToolRegistry، والمدخلات ضمن schema/الحجم المسموح، وعدد الخطوات ≤32، والمفاتيح فريدة، والاعتماديات موجودة وسابقة للخطوة، ولا يسمح بدورة أو حقل غير معروف.
- أضيفت اختبارات API ترفض العمليات غير المسجلة قبل أي اتصال بقاعدة البيانات.
- أصبح auto-plan يرفض إنشاء مهام إذا Worker معطل؛ ورفض general-agent إذا Hermes غير مفعّل أو العزل غير مؤكد أو الإعدادات ناقصة.
- كتالوج الأدوات وكتالوج الوكلاء وواجهة Agent تعكس حالة Worker والعزل الفعلية، ولا تعلن أداة/وكيلًا متاحًا عندما لا يستطيع الخادم تنفيذها.
- أضيفت متغيرات البيئة الموثقة للـWorker وHermes وEngine Reconciler، وجميعها false افتراضيًا.
- Commits ذات الصلة: `233c2ee36c44` (DAG validator)، `b857d2778a5f` (server plan validation)، `21c24b3fea03` (اختبار رفض shell.exec)، `a05feb5d1226` (API readiness tests)، `6bede601c606` (.env example).
- CI: على `a05feb5d1226` نجح API tests وClient typecheck/web export؛ Baseline checks على HEAD `6bede601c606` نجحت، وPlatform CI كان قيد التنفيذ وقت التوثيق.
- ما زال تشغيل محركات coding/browser upstream معطلاً لحين اكتمال Docker runner وegress proxy واختبارات عزل فعلية.


## Session checkpoint — 2026-11-20 (Orphan identity observability)

- تمت مراجعة Hermes upstream عند pin الحالي: POST Runs يدعم idempotency ledger/replay، لكن لا يوجد endpoint مستقل للبحث عن run عبر Idempotency-Key.
- لذلك لا نعيد POST لمجرد البحث، لأن ذلك قد ينشئ تشغيلًا جديدًا إذا لم يكن السجل موجودًا.
- أضيفت migration `20261120230000_monitor_missing_engine_identity.sql` لعدّ `stop_pending` التي لا تحمل upstream ID بعد عمر محدد، مع index وRPC service_role-only.
- أضيف `EngineRunStore.count_missing_upstream_identity` وتحذير error-level محدود التفاصيل داخل reconciler؛ لا نعلن توقف التشغيل ولا نغلق السجل دون تأكيد.
- Commits: `38be788521c6` (monitor migration/reconciler logging), `66a59f207655` (strict count store/tests), `6c1145aeacc2` (upstream idempotency audit note).
- فجوة معروفة: crash في النافذة بين استجابة Hermes وحفظ run_id قد يترك stop_pending بلا معرف؛ الحل الكامل يتطلب endpoint lookup upstream أو عقد admission مخصصًا. لا نستخدم إعادة POST غير آمنة.
- لا migrations مطبقة، وCI على HEAD `66a59f207655` كان queued وقت التوثيق.


## Follow-up — 2026-11-20 (Orphan alert quality)

- أضيف deduplication لتنبيه عدد السجلات التي تفتقد upstream ID؛ لا يعيد نفس الخطأ كل 30 ثانية ما دام العدد لم يتغير.
- أضيف اختبار يثبت عدم تكرار التنبيه عبر دورات reconciler متتالية.
- Commits: `cd3dc4858a64` (deduplication), `61dc3432b595` (test).
- Baseline على `cd3dc4858a64` نجح؛ CI للـHEAD الأحدث queued وقت التوثيق.

## تحديث حالة Hermes — 2026-11-20 (بعد دفعات run lifecycle والموافقات)

الحالة الموثقة الأحدث تتقدم على نقاط checkpoint التاريخية أعلاه عند التعارض:

### المرحلة B — Engine lifecycle (الحالة الحالية)
- [x] SULY-side run record لكل attempt مع lease guards
- [x] معالجة orphan run وstop_pending مع reconciler اختياري
- [x] idempotent run admission عبر Idempotency-Key وpersisted upstream run ID
- [x] status polling محدود وSSE metadata-only مع event persistence
- [x] cooperative stop مع انتظار terminal state محدود؛ لم يتم إثبات runtime حي
- [ ] disposable Postgres/Supabase integration tests وتطبيق migrations على staging

### المرحلة C — Hermes adapter (الحالة الحالية)
- [x] immutable upstream pin ومراجعة Runs API وMIT license
- [x] POST run وstatus polling وstop وsteer
- [x] SSE allowlist وتخزين metadata آمن مربوط بالـlease
- [x] exact-request approvals بقرار once أو deny فقط، دون session/always/resolve-all
- [x] واجهة task تعرض progress وأزرار الموافقة والرفض والتوجيه
- [ ] clarify وresolve-unknown، sessions، skills، memory، subagents
- [ ] runtime manager فعلي per-task isolation مع image digest وworkspace lifecycle
- [ ] CPU/memory/PID/disk limits داخل runtime فعلي واختبارها
- [ ] egress proxy default-deny مع allowlist واختبارات SSRF
- [ ] non-root/read-only/no-host-mount/no-Docker-socket داخل تشغيل فعلي
- [ ] end-to-end Hermes runtime + provider smoke test بعد الموافقة الصريحة

### تحقق CI لهذه الدفعة
- Commit 74311d9a: Platform CI وRepository baseline checks نجحا بالكامل (API tests، TypeScript، Expo compatibility، Web export).
- Commit 85abbbaa: Repository baseline checks نجح؛ API tests نجحت، وفحص Client كان قيد التنفيذ عند التسجيل.
- Commits التالية الخاصة بدمج واجهة الموافقات والتوثيق ما زالت تحت CI حتى اكتمال أحدث run.
- Migration 20261121010000_engine_run_approval_metadata.sql جديدة وغير مطبقة. يجب تشغيلها في قاعدة disposable/staging، مع التحقق من توقيع RPC الجديد وقيود البيانات قبل أي نشر.

### حدود الأمان والتشغيل
- Worker وHermes وprovider ما زالوا disabled افتراضيًا.
- لا توجد migrations مطبقة على Supabase production ولا أي deployment تم في هذه الدفعة.
- اختبارات HTTP mock لا تعادل اختبار Hermes container حقيقيًا؛ لا يتم وصف أي engine على أنه live أو production-ready.

## تحديث تكامل OpenCode — 2026-11-20

- [x] مراجعة upstream عند pin `4cca18d80450a3dd6a9a4142028bde84ccb3116e`، وتوثيق MIT ونسخة server package.
- [x] توثيق أن auth كلمة مرور خادم واحدة + cookie مشتقة منها، وليست SULY tenant auth.
- [x] توثيق حدود Session/Location middleware ورفض استخدام directory من العميل كمسار مضيف.
- [ ] runtime/container مؤقت لكل task attempt مع server secret منفصل.
- [ ] broker per-task يربط كل route بالـowner والـlease والـruntime.
- [ ] عزل filesystem/shell/PTY/MCP/plugins/credentials وقواعد البيانات بين المهام.
- [ ] egress proxy default-deny واختبارات SSRF.
- [ ] end-to-end isolation tests بين مهمتين قبل تفعيل المحرك.

ملف التدقيق: `docs/architecture/OPENCODE_INTEGRATION_AUDIT.md`. يظل OpenCode disabled؛ لا يوجد adapter أو server مشترك أو runtime حي.

## تصحيح migration ومراجعة CI — 2026-11-20

- أُعيد بناء `20261121010000_engine_run_approval_metadata.sql` بعد اكتشاف نسخة مبتورة/مكررة؛ النسخة الحالية مكتملة، لكن لم تُطبق على Supabase.
- تمت إزالة Unicode control/format/bidi characters من تفاصيل موافقات Hermes قبل العرض.
- Platform CI وRepository baseline على commit `01e8e88b9e267b138bbfc0fbd24599be36294441` نجحا: 364 API tests، TypeScript، Expo compatibility، Web export.
- أحدث HEAD وقت التحديث كان `21328dcb664e7ea02f87be6af7d4959c655faa33`؛ CI الخاص به يحتاج تحققًا منفصلًا بعد اكتماله.


## تحديث تكامل Browser Use — 2026-11-20

- [x] مراجعة upstream عند pin `ccbdb8095fbaf903c748880a600054a34c7b6191`، package 1.0.6، MIT.
- [x] مراجعة MCP Python REPL ومخاطر قراءة environment/files من process الخادم.
- [x] مراجعة local Chrome/profile attach ومخاطر browser-harness daemon المشترك.
- [x] إثبات أن allowed_domains/prohibited_domains لا تطبق على cloud browser؛ لا تعتبر حماية SSRF أو egress.
- [ ] MCP process/container منفصل لكل task attempt.
- [ ] browser profile وREPL وcredentials منفصلة، ومنع host Chrome وshared daemon.
- [ ] egress proxy default-deny مع فحص DNS/redirect/IPv4/IPv6 وmetadata/private ranges.
- [ ] task-scoped MCP broker مع owner/lease/runtime checks.
- [ ] approvals مرتبطة بالفعل المحدد قبل أي side effect.
- [ ] process-tree teardown وإبطال الأسرار واختبارات منع الوصول المتبادل.

ملف التدقيق: `docs/architecture/BROWSER_USE_INTEGRATION_AUDIT.md`. Browser Use ما زال disabled؛ لا يوجد MCP server أو browser runtime حي.


## تحديث عقد Runtime لكل محاولة — 2026-11-20

- [x] RuntimeLease يربط runtime/task/engine-run/engine IDs.
- [x] token مخفي عن repr ومحدود الطول، والـlease محدود بساعة كحد أقصى.
- [x] HTTPS + exact DNS host allowlist، ورفض IP literals وURL credentials/query/path.
- [x] منع تكرار task attempt أو runtime ID داخل broker process، ومحاولة teardown في context manager.
- [x] اختبارات العقد الأساسية.
- [ ] مزود runtime فعلي يخلق runtime جديدًا لكل محاولة ويحفظ uniqueness عبر restart.
- [ ] broker network/service حقيقي يربط task owner وlease وruntime identity في كل طلب.
- [ ] teardown مؤكد عبر process tree/container runtime حتى بعد worker crash/restart.
- [ ] اختبار DNS resolution/egress proxy وnetwork isolation في بيئة staging.
- [ ] OpenCode adapter وBrowser Use MCP broker بعد إثبات العزل.

هذا العقد لا يشغّل أي container أو process، ولا يجعل المحركات متاحة. تبقى جميع runtimes معطلة.


## تشديد عقد Runtime Lease — 2026-11-20

- [x] HTTPS canonical origin allowlist، exact match بلا subdomain suffix.
- [x] رفض IP literals وlocalhost وURL credentials/path/query/fragment.
- [x] ربط release بكائن lease الأصلي، لا بمجرد ID/قيم قابلة للاستنساخ.
- [x] منع teardown غير الآمن عند اكتشاف runtime ID مكرر سبق إصداره.
- [x] اختبارات للـorigin والـlease forgery وruntime reuse.
- [ ] إثبات uniqueness عبر workers/restarts بواسطة provider خارجي durable.
- [ ] تنفيذ teardown آمن عبر broker فعلي مع reconciliation للـorphan runtimes.
- [ ] تشغيل CI على آخر HEAD بعد اكتمال الاختبارات الحالية.


## Browser Use security gate update — 2026-11-20

- [x] Pin and review upstream Browser Use MCP implementation.
- [x] Document why a shared MCP/Python REPL is unsafe across tasks.
- [x] Add SULY URL preflight policy for canonical DNS allowlists, HTTP(S)-only URLs, no credentials, exact host matching, bounded ports, legacy/numeric IPv4 rejection, Unicode control rejection, and public DNS answer checks.
- [x] Platform CI on 782e08a4: 440 API tests, TypeScript typecheck, Expo compatibility, and Web export passed.
- [ ] Re-run complete CI on current HEAD after the subsequent oversized numeric/hex hostname tests.
- [ ] Implement a per-attempt isolated Browser Use runtime and MCP broker.
- [ ] Enforce DNS pinning and redirect-by-redirect URL checks at connection time through a default-deny egress proxy.
- [ ] Add browser side-effect approval and credential isolation tests.
- Browser Use remains disabled. No browser runtime has been started.

## OpenCode protocol readiness checkpoint — 2026-11-20

- [x] Review pinned server authentication, session, permission, and global event APIs.
- [x] Add pure session permission/event reducers with exact session binding and once/reject-only decisions.
- [ ] Implement a per-attempt process provisioner and unique OpenCode password.
- [ ] Add lease-guarded durable OpenCode session ID persistence.
- [ ] Implement the HTTPS Basic-auth client using the broker's exact-origin runtime lease.
- [ ] Add bounded assistant-message/output reducer and session-scoped permission UI.
- [ ] Run two-runtime isolation and end-to-end permission tests before enabling OpenCode.
- OpenCode remains disabled; protocol contract tests do not establish a usable live engine.

## Current CI checkpoint — 2026-11-20

- [x] API tests: 456 passed on commit 61c194f8.
- [x] Python compile, TypeScript typecheck, and Expo dependency compatibility on commit 61c194f8.
- [ ] Confirm Web export completion on the same commit before marking Platform CI green.

- [x] Platform CI على commit 61c194f8 اكتمل بنجاح: 456 API tests + TypeScript + Expo compatibility + Web export. Repository baseline نجح على نفس commit. Commits التوثيق اللاحقة لا تغير كود التطبيق.


## خطة الإغلاق الموحدة — ثمانية مسارات متوازية منطقيًا، 2026-11-20

> هذا سجل تنفيذ وتحقق، وليس إعلان اكتمال. لا يجوز اعتبار المسار منتهيًا بمجرد وجود interface أو mocked tests.

1. **إغلاق CI وإصلاح التحذيرات:** [x] Platform CI وRepository baseline نجحا على `db9e5ba6109f073f81f93694fff86b9d2c81bef8`؛ [ ] إزالة تحذيرات Starlette deprecated؛ [ ] تفعيل lint/type/security/dependency/migration checks إن لم تكن ضمن workflows.
2. **Runtime isolation:** [x] عقد RuntimeLease/Broker محلي؛ [ ] provider منفصل حقيقي مع OCI/container boundary، non-root، read-only FS، CPU/RAM/PID/disk/time limits؛ [ ] uniqueness durable وteardown بعد crash؛ [ ] اختبار cross-task isolation على staging.
3. **OpenCode:** [x] protocol reducers والصلاحيات once/reject وmetadata sanitization؛ [ ] provisioner + client + durable session binding + output reducer؛ [ ] end-to-end tests على runtime معزول.
4. **Browser Use:** [x] URL/DNS preflight؛ [ ] default-deny egress proxy يثبت DNS/IP عند الاتصال ويفحص redirects/subresources؛ [ ] per-task MCP/REPL/browser profile؛ [ ] credential isolation وside-effect approvals واختبارات عملية.
5. **Hermes:** [x] bridge/events/steering ومراجعات المصدر؛ [ ] إكمال sessions/skills مع tenant scoping؛ [ ] approvals lifecycle end-to-end؛ [ ] process isolation وresource/egress controls واختبارات runtime.
6. **Database/staging:** [x] migrations وRLS/RPC مكتوبة؛ [ ] تشغيل migration validation على disposable PostgreSQL؛ [ ] تطبيقها على Supabase staging بعد تصريح المستخدم فقط؛ [ ] cross-user/RLS/backup-restore drills؛ لا تغيير على production دون تصريح.
7. **Reliability/security/scale:** [x] اختبارات وحدات أساسية؛ [ ] integration/failure/retry/cancel/lease-race/idempotency/billing tests؛ [ ] rate limits/quotas/observability/alerts؛ [ ] load test موثق وSAST/dependency/container scans؛ [ ] threat review مستقل.
8. **Beta/production packaging:** [ ] build artifacts للمنصات المستهدفة؛ [ ] staging deploy + smoke tests؛ [ ] secrets manager + deployment/rollback/runbooks؛ [ ] privacy/data export/delete؛ [ ] قبول Beta؛ [ ] موافقة منفصلة قبل الإنتاج أو تفعيل أي worker/engine.

### حدود هذه الجلسة
- تم التحقق من Platform CI وRepository baseline على commit `db9e5ba6109f073f81f93694fff86b9d2c81bef8`: 456 API tests passed، Python compile، TypeScript، Expo compatibility، وWeb export كلها نجحت.
- أضيف تشديد OpenCode ضد محارف control/format/bidi في permission metadata واختباراته.
- لم يتم إنشاء provider أو proxy حقيقي، ولم يتم تشغيل محركات أو تطبيق migrations أو نشر خدمات. لا تتوفر في هذه الجلسة بيئة staging/OCI فعلية تثبت هذه الخصائص؛ إبقاء المحركات disabled هو القرار الآمن.
- لا يجوز إعلان 100% أو Beta/Production readiness حتى تُغلق جميع مربعات التحقق أعلاه مع أدلة تشغيلية على commit محدد.


## Session checkpoint — 2026-11-21 (Chat rate limits and worker safety)

- استعدنا TokenBucket implementation بعد أن كشف CI عن syntax corruption، وأصلحنا tests غير الصحيحة للسعة/الـburst، وأضفنا validation وpruning.
- تم تفعيل dependency rate limiting على chat write endpoints: `chat_respond`, `chat_conversations`, `chat_messages`; أضفنا integration tests للتحقق من 429 بعد limit وscope separation.
- SlidingWindowLimiter أصبح bounded من ناحية principal key count مع periodic idle pruning، fail-closed عند key-cap، ويدعم تحديث limits دون تصفير النافذة.
- أصلحنا OpenCode/runtime provisioner test fixtures التي لم تتوافق مع streamed JSON API وsession callback؛ runtime primitive CI نجح.
- أوقفنا schedule الـfree test worker (كل 5 دقائق). التشغيل أصبح workflow_dispatch فقط مع `enable_worker=false` افتراضيًا؛ لم يتم تشغيل worker.
- Platform CI #1005 على commit `38fdd402` اكتمل: **601 API tests passed, 5 warnings**؛ TypeScript typecheck، Expo compatibility، Web export نجحت. Repository baseline #1023 نجح.
- Repository baseline #1024 على commit `e0d9741d` نجح؛ Platform CI #1006 pending وقت checkpoint. OpenCode verification #166: runtime primitive tests نجحت؛ upstream Docker build/smoke pending.
- Rate limits المحلية لا تزال process-local؛ لا تُحسب IP/global limits أو distributed quota كمنجزة. المحركات/worker/deploy والمigrations ما زالت off/untouched.


### تحديث نتائج CI بعد checkpoint
- Platform CI #1006 على commit `e0d9741d` اكتمل بنجاح: API tests، TypeScript، Expo compatibility، وWeb export.
- Repository baseline checks #1024 على `e0d9741d` نجح. Baseline #1025 على commit `442ccd06` و#1026 على `45aacc23` نجحا أيضًا.
- OpenCode verification #166: Runtime primitives نجحت، upstream provenance/Bun install/server typecheck/Docker image build نجحت، وDocker smoke-test الأصلي كان قيد التنفيذ عند آخر قراءة.
- آخر HEAD وقت التحديث: `45aacc232cf720725c590c08aefdaf87ccaf8392`. التغييرات بعد #1006 هي توثيق فقط؛ Platform CI على commits الوثائق ما زال pending.
- Worker workflow لم يعد له schedule؛ لا يوجد worker execution في هذا التحديث.


## متابعة أمنية إضافية — 2026-11-21 (Bounded Runtime Gateway Requests)

- اكتشفنا في مراجعة provisioner أن endpoint إنشاء runtime كان يعتمد على Pydantic field limits بعد parse كامل للـJSON، وأن endpoint `/execute` كان يقرأ JSON مباشرة دون raw body cap؛ يمكن أن يستهلك oversized extra fields ذاكرة قبل field validation.
- جعلنا `ExecuteRequest` strict (رفض extra fields) وأضفنا 64 KiB streamed body cap قبل parsing لطلب تنفيذ task.
- جعلنا `CreateRuntime` و`FileSnapshot` strict، وأضافنا 6 MiB streamed cap لطلب إنشاء runtime؛ helper العام يقبل حدودًا حتى 8 MiB. التحقق من service token يسبق قراءة body.
- أضفنا tests للـoversized execute body، وoversized runtime creation body (لا يصل إلى Docker manager)، ورفض الحقول غير المتوقعة.
- CI API tests على commit `5aa8266b`: **601 passed, 5 warnings**. Platform CI #1014: API tests passed؛ TypeScript/Web export قيد التنفيذ. Repository baseline #1032 نجح.
- OpenCode verification #170: isolated runtime primitive tests نجحت؛ provenance/Bun install نجحا، upstream server typecheck كان قيد التنفيذ، Docker image build وsmoke test في الانتظار. لا تشغيل runtime أو agent حي خارج CI.
- Latest HEAD: `5aa8266b2fc5a375be60b63b4a3e8a5811e58d15`.


## OpenCode checkpoint — CI smoke closure and activation guard (2026-11-21)

- CI OpenCode verification #1014 / run `44879150324` on commit `5aa8266b2fc5a375be60b63b4a3e8a5811e58d15` is confirmed green: runtime primitive tests; upstream provenance; bridge tests; frozen Bun install; upstream server typecheck; Docker build; authenticated server `/api/info` smoke.
- Startup activation was tightened with `OPENCODE_ENABLED` default `false`. Runtime broker/provider are cleared and startup exits when disabled, even if provisioner URL/token/origins exist. Added a focused test; its CI is pending after this commit.
- **OpenCode code integration remains incomplete for users.** The transport includes prompt submit and interrupt primitives, but a verified owner/task/run/lease-bound user prompt route and task-worker executor wiring are not yet integrated. Do not call this complete or enable it until those pieces, DB staging tests, and runtime isolation are implemented.
- Do not deploy or apply migrations. No live runtime/worker/provider was activated.


## OpenCode worker integration update — 2026-11-21

- **Implemented in code (CI pending for latest commit):** `opencode.task.run` allow-listed worker tool with strict project/prompt/title input; explicit `engine.opencode.run` consent; lease-protected EngineRun ledger start/finish; server-side Workspace, Session and Lifecycle stores; result checkpoint returns IDs/status/count only and requires review; runtime broker/provider is constructed only when worker and OpenCode are explicitly enabled and provisioner config is complete.
- **User task entry:** authenticated `POST /v1/tasks/{task_id}/opencode-plan` queues a single coding step only for an owned queued task linked to a project. It does not launch execution itself.
- **Cancellation boundary:** executor watches the worker cancel/lease-loss event and calls task-attempt runtime release; it refuses to accept a late result after cancellation. Cancellation cleanup is covered by a focused unit test added in the latest commit, but its CI result has not been observed yet.
- **Tool approvals:** catalog includes the OpenCode operation, and reports availability false unless worker/runtime opt-in is configured. The approval scope cannot be self-granted through task input.
- **Current default:** `SULY_WORKER_ENABLED=false`, `OPENCODE_ENABLED=false`; no worker starts, no provisioner contact, no migrations, no deploy.
- **Remaining closure requirements:** confirm latest CI; inspect failing/pending runs and correct issues; verify runtime release semantics for cancellation against the provisioner contract; add/validate durable task/run recovery and event streaming behavior for OpenCode; confirm change-set review/apply lifecycle transitions and UI integration; run isolated staging integration tests after user approval. Until these checks, do not mark OpenCode integration complete or enable live execution.


## OpenCode frontend checkpoint — 2026-11-21

- The coding mode is now exposed in the project-linked task composer with explicit user consent and a server readiness gate. The client refuses to create an OpenCode task without a project context.
- Task details load the owner-scoped OpenCode change set, display bounded diff previews, allow apply/reject, and poll sanitized lifecycle events while the task is active.
- Platform CI #1049 at commit `b6f896dff319ad184eb36c020cb567e7b81b2aa1` is green: **608 API tests passed** (5 warnings); TypeScript, Expo compatibility, and Web export succeeded; repository baseline #1067 passed. Latest source commit is `b6f896d` (progress-doc-only commit after it does not change code).
- Upstream verification #177 is still running; isolated-runtime primitive tests and protocol/provenance/typecheck steps are green, Docker build and smoke are pending. Previous upstream verification #1014 is green.
- Do not enable or deploy. The remaining blockers are live Staging runtime/provisioner validation, DB migrations under explicit approval, real cancellation/release and orphan recovery integration, frontend acceptance on Android/web, and any usage/credits accounting for coding-engine execution.


## OpenCode core code integration — closure checkpoint (2026-11-21)

- **Core code integration is closed for the current scope.** The project-linked UI creates a dedicated OpenCode task; the API validates owner/task/project/runtime readiness; the allow-listed worker operation requires `engine.opencode.run`; the worker establishes an engine-run record and calls the original pinned OpenCode executor in a task-scoped runtime; output is bounded and contains review IDs/status; sanitized events are surfaced; users can inspect diffs and Apply/Reject with revision/CAS checks.
- CI evidence on code commit `7399ec775d25aa523ed0ba3a19d697d221e21e88`: Platform CI #1059 green (**609 API tests passed, 5 warnings**, API compile, TypeScript, Expo dependency compatibility, Web export); Repository baseline #1077 green.
- Upstream OpenCode verification #177 green on `1a84d30d`: runtime primitive/security tests, protocol bridge tests, provenance, frozen install, server typecheck, Docker image build and authenticated server smoke. Upstream code unchanged after that verification.
- New guide: `docs/operations/OPENCODE_TASK_FLOW_AR.md` explains route, worker flow, IDs, event feed, review/apply, defaults, and staging gates.
- **Do not mark Controlled Beta/production ready.** Live Staging integration is not run or approved. No migrations applied, worker or runtime activated, deployment, or paid service activation.
- Blocking pre-activation items: coding usage/credits metering and cost model (not implemented); approved disposable/staging migrations; provisioner runtime integration; end-to-end cancel/release/recovery and cross-user isolation tests; egress and resource-limit review; real Android/Web account acceptance. These are deployment readiness gates, not a reason to claim the code wiring itself is unfinished.


## Security checkpoint — 2026-11-21 (Fail-closed task-runtime egress)

- مراجعة `services/runtime-provisioner/app/docker_runtime.py` كشفت أن `RUNTIME_ALLOW_EGRESS=true` أو وسيط البناء `egress_allowed=True` كانا يحولان Docker bridge إلى `internal=False`، بينما لا توجد في المستودع بوابة egress task-aware أو آلية تثبت تطبيق host firewall allowlist. وجود تحذير في README وحده لا يفرض هذا الشرط تقنيًا.
- أُغلق هذا المسار: إعدادات egress المفعّلة تُرفض، والقيم غير المعروفة تُرفض، وفحص الإعداد يحدث قبل لمس Docker/workspace؛ فحص startup يمنع تشغيل الخدمة بإعداد egress غير آمن؛ وكل task network تُنشأ `internal=True` دائمًا.
- أضيفت اختبارات لقيم opt-in المختلفة، والقيم غير الصالحة، ورفض التشغيل قبل إنشاء أي Docker network/container. تم تحديث دليل التشغيل والضوابط الإلزامية.
- هذا hard gate فقط؛ لا ينفذ egress proxy ولا يثبت العزل على Docker host حقيقي. لا يتم تشغيل OpenCode أو Worker ولا نشر أو تطبيق migrations. يظل مسارا runtime isolation وBrowser Use egress مفتوحين حتى تنفيذ proxy واختبارات شبكة فعلية.
- يجب ربط حالة الاختبارات بنتيجة CI الفعلية للـcommit الذي يحمل هذا التغيير؛ لا تُعد هذه المراجعة إثبات تشغيل runtime.


## Session checkpoint — 2026-11-21 (CI repair and Hermes default-deny)

- Starting main HEAD: f3afbd9d098ed4ff7c80b1cd8141660c25c6930b; reviewed current roadmap, progress log, repository instructions, recent commits, relevant source/tests, and latest CI.
- Repository baseline run 44925526767 passed on the starting HEAD. Platform CI 44925526678 failed API compilation because worker_runtime.py contained a duplicate function declaration with an empty body; client typecheck, Expo compatibility and Web export passed.
- OpenCode upstream verification 44925526728 exposed: (a) Hermes runtime config unexpectedly exposed terminal/file platform toolsets despite the intended empty allowlist; (b) six OpenCode executor tests used a fake broker without the real release_attempt contract. The failing tests prevented later upstream build/smoke steps in that run.
- Fixes committed directly to main:
  - 352800efe8400ae07d4373b41ec6406b5a173603: remove duplicate Worker declaration; make OpenCode fake Broker implement release_attempt; assert cleanup is requested after reviewable change-set persistence.
  - fcea64cce7ff1c140542ca716686c14ed01dcf8a: set Hermes platform_toolsets.api_server to an empty list, matching the existing security test and runtime-provisioner README.
- No upstream source was edited; no revision/license changed.
- The CI evidence above predates the fixes. New CI must complete successfully before this checkpoint is treated as verified; no local pytest execution is claimed.
- Safety unchanged: no migration applied, no deployment, no live worker/agent/Hermes/OpenCode/provider, no paid service, no new secret.
- Next: verify all CI runs on the new HEAD, repair regressions, then implement the usage/credits gate for task execution without activating workers or engines.


## Session checkpoint — 2026-11-21 (Credit ledger idempotency NULL-safety)

- تم التحقق من `main` HEAD `3837c066878036283a96e394a02c0091370d1a0c` قبل التعديل ومراجعة roadmap وسجل التطوير وتعليمات المستودع وملفات الرصيد والاختبارات وCI.
- اكتشفنا مقارنة SQL غير آمنة في `release_engine_credits`: استخدام `metadata ->> 'reason' <> p_reason` لا يكتشف دائمًا القيمة المفقودة بسبب دلالات `NULL`. استُبدلت بـ`IS DISTINCT FROM`، وأضيف اختبار static يمنع رجوع المقارنات غير الآمنة.
- تم تحديث دليل دفتر الرصيد وسجل التقدم. لم نغيّر أي upstream source أو revision أو license.
- CI على HEAD السابق: Platform CI run `44930108723` وRepository baseline run `44930108558` نجحا؛ Engine runtime build run `44930107052` فشل، لكن GitHub connector لم يعرض jobs/logs لتحديد السبب. ظهر أيضًا فشل check خارجي `strong-gentleness - suly-api`; لم ننفذ deploy.
- لا pytest محلي في هذه الجلسة، ولا migration apply أو deploy أو تشغيل worker/agent/engine/provider. نتائج CI الجديدة مطلوبة بعد هذا commit.
- لم تتغير عناصر checklist: **51/120 (43%)**. تقدير Controlled Beta/Production Readiness يظل **نحو 20%** بطريقة milestone-weighted؛ وجود ledger code لا يعني billing integration أو staging validation.
- التالي: التحقق من CI الجديد، ثم اختبارات PostgreSQL disposable، وبعدها ربط cost/usage ledger بالـworker خلف gates مغلقة وبعد تحديد سياسة التكلفة.



### CI verification update — `1387b8960cd48056ea236485c749bab9d9712cb4`

- Platform CI run `44933680235` (#1374) succeeded: API compile, **757 API tests passed (5 warnings)**, client TypeScript typecheck, Expo dependency compatibility, and web export.
- Repository baseline run `44933680367` (#1392) succeeded.
- Engine runtime image build run `44933678909` (#44) failed, but the Actions API returned zero jobs and no logs were available. The cause remains unknown; no engine image build success is claimed.
- The combined commit status also reports an external `strong-gentleness - suly-api` failure. No Railway deployment or live service action was performed.
- These results are tied to commit `1387b8960cd48056ea236485c749bab9d9712cb4`; local pytest was not run.


## جلسة تطوير — 2026-11-22 (عرض الرصيد وسجل الحركات، دون تفعيل الفوترة)

- راجعنا HEAD والـroadmap وسجل التطوير وتعليمات AGENTS والملفات والـcommits والـActions قبل التغيير. بداية الجلسة: `69c129140ec0881a95b119499e11d6fbc493aee6`.
- أضيف API قراءة `GET /v1/credits`، يستخدم bearer الخاص بالمستخدم مع Supabase publishable client وRLS، ويعيد الحساب وحجوزات آخر 25 وسجل آخر 50 حركة. لا يعيد metadata أو معرفات المهام. الاستعلامات تضيف user_id filter مع حدود ثابتة.
- أُضيف `ENGINE_CREDITS_ENABLED=false` في إعدادات API و`.env.example`. عند تعطيله يرفض إنشاء DB client لدفتر الرصيد قبل أي query. endpoint قراءة فقط، ولا ينشئ account ولا يمنح/يخصم/يحجز رصيدًا.
- أُضيفت صفحة `/credits` في Expo ووصلة من الإعدادات؛ تعرض available/reserved والحجوزات والحركات، مع refresh، login-required، حالات empty/loading/error، وتوضيح أن الشراء والتشغيل غير مفعّلين.
- أضيفت 7 API tests لرفض unauthenticated، gate قبل DB client، ربط client بتوكن المستخدم، owner filtering، حدود النتائج، projection دون metadata، account-zero، أخطاء DB sanitized، وقيم account غير سليمة.
- لا pytest محلي؛ Platform CI للـAPI commit `2467140c` نجح (#1376 / run `44999253902`). Platform CI للـgate commit #1377 كان جاريًا، وللواجهة #1378 كان جاريًا وقت تسجيل هذا checkpoint. Repository baseline #1395 نجح، و#1396 كان جاريًا. Engine runtime build #217/#218 فشل دون jobs/logs، لذلك السبب مجهول. OpenCode upstream verification #316 كان جاريًا على commit أسبق.
- التحقق لا يثبت تطبيق migration أو RLS في قاعدة فعلية. Migration دفتر credits لم تُطبق؛ flag يظل false؛ لا deploy، ولا worker/engine/provider، ولا payment، ولا secrets.
- إعادة عد roadmap الحالية: **58/153 (38%)** checkbox قبل إضافة هذا العنصر؛ العنصر الجديد ما زال غير checked إلى أن يكتمل CI. نسبة Controlled Beta/Production Readiness تظل **نحو 20%** milestone-weighted؛ واجهة القراءة وحدها لا تُكمل usage metering أو billing أو staging/runtime gates.

### الخطوة التالية
1. تأكد من Platform CI على commit واجهة الرصيد؛ أصلح أي regression قبل اعتماد feature.
2. بعد ذلك أضف PostgreSQL disposable tests للـledger (concurrency/idempotency/NULL) إذا كانت CI environment تسمح، دون Supabase production.
3. اربط reserve/settle/release بدورة engine runs خلف cost policy server-side واضحة، approval وbudget gates، مع اختبار cancel/retry/recovery قبل أي تشغيل.


## تحقق CI — عرض credits (2026-11-22)

- Platform CI #1377/run `44999376502` على commit `129efc636c10` نجح: compile + **764 API tests passed (5 warnings)** + TypeScript + Expo compatibility + Web export.
- Platform CI #1378/run `44999424273` على commit `eee5d8a497fe` نجح بالمسارات نفسها؛ client typecheck وWeb export اكتملان.
- Repository baseline #1395/run `44999376560` و#1396/run `44999424191` نجحا.
- أحدث docs commit `dad1bbb8afc8`: Platform CI #1379 وRepository baseline #1397 ما زالان قيد التنفيذ وقت تحديث السجل.
- Engine runtime image builds #217/#218/#219 فشلت مع jobs فارغة في Actions API؛ لا توجد logs أو سبب معروف. OpenCode upstream verification #316 ما زالت قيد التنفيذ على commit أسبق.
- تم إعادة عد checklist: **59/154 (38%)**. Controlled Beta/Production Readiness لا تزال **نحو 20%**؛ API/UI read-only لا تثبت migrations/RLS على Postgres حقيقي ولا usage billing.


## تحقق PostgreSQL — ledger (2026-11-22)

- أُضيف workflow منفصل `Credit ledger PostgreSQL integration` يعمل على خدمة PostgreSQL 16 disposable في GitHub Actions، مع متغير يمنع reset خارج بيئة الاختبار.
- اختبار integration commit `d5a7d9d67f17` run #3 (`44999917678`) نجح بعد إصلاح fixtures: **5 passed**.
- التوسعة في commit `5a51b10a1c07` run #4 (`45000017619`) نجحت: **5 passed**؛ تشمل grants/idempotency، reserve/retry، settle/refund، release/expiry، insufficient/cross-user run، concurrency تمنع overdraw، وRLS على الحساب والحجز والledger مع رفض writes/RPC للـauthenticated.
- Platform CI #1385/run `45000017691` نجح: **764 passed, 5 skipped, 5 warnings**؛ TypeScript/Expo/Web export نجحت. Repository baseline #1403/run `45000017591` نجح.
- فشل أول run #1/#2 قبل الإصلاح في fixtures (engine ID mismatch وauth user FK). تم تشخيصها من logs وإصلاحها؛ لا نخفي المحاولات الفاشلة.
- إعادة عد checklist: **60/155 (39%)**. Production readiness milestone-weighted تظل **نحو 20%**؛ tests لا تعني تطبيق migrations على staging أو تفعيل credits في المحركات.


## Chat token telemetry — 2026-11-22

- AI Gateway now optionally normalizes OpenAI-compatible `prompt_tokens/completion_tokens` and Ollama `prompt_eval_count/eval_count` into input/output/total counts, bounded and validated; missing/invalid usage is omitted.
- Chat stores token counts in assistant message metadata only when the provider reports them; client shows the counts. No token estimation, monetary cost, credits charge, or usage ledger.
- Commit `5e41f6753be9` Platform CI #1387 failed only on client TypeScript due a malformed JSX time tag; API tests were green. Fix landed in `d033fd274bfc`; its Platform CI #1388 API job passed **770 tests** while client job was still running. UI total-count polish is commit `075a90ab1b2d`; CI #1389 was still in progress.
- Recount after adding this unchecked item: **60/156 (39%)**. Controlled Beta/Production readiness remains **~20%**; telemetry is not billing and no AI provider is enabled.


## تحقق Chat token telemetry — 2026-11-22

- Platform CI #1388/run `45000436704` على commit d033 و#1389/run `45000469647` على commit 075 نجحا؛ كل منهما **770 passed, 5 skipped, 5 warnings**. client typecheck، Expo compatibility، Web export green.
- فشل #1387 على commit 5e41 بسبب JSX tag syntax؛ API job كان green. أصلحنا markup/null metadata في d033، ثم أظهرت #1388/#1389 green.
- Platform CI #1390/run `45000536420` و#1391/run `45000583307` و#1392/run `45000602027` green. Repository baseline #1408/run `45000536405` و#1409/run `45000583353` و#1410/run `45000601971` green.
- إعادة عد checklist: **61/156 (39%)**. Readiness milestone-weighted remains **~20%**؛ provider usage counts لا تساوي cost ولا credits ولا تمنح صلاحية provider.


### Docs CI verification

- Platform CI #1390–#1392 وRepository baseline #1408–#1410 green؛ latest docs commit `144dedf820a2` checked.
- PostgreSQL credit integration #4: 5 passed. Engine runtime build #232 failed with empty jobs; diagnostic logs unavailable.


## Session checkpoint — 2026-11-22 (Owner-managed AI provider removal)

- The existing Vault migration already exposed a service-role-only `suly_ai_provider_config_clear` RPC, but the product had no owner API or UI action to remove the centrally stored key.
- Added an owner-verified, rate-limited DELETE route, a server-only RPC helper, sanitized failure handling, and a client confirmation flow.
- The response re-checks Vault and reports a server environment fallback as `source=environment`; deleting the Vault secret is not represented as disabling a provider when fallback credentials remain configured.
- This completes the in-product Vault removal path only. Provider/model smoke remains approval-gated; no provider, worker, or engine was activated. No migration was applied and no deployment occurred.
- Implementation commit: [`50c6d7449fab6cd98eca98c14583914985bf6925`](https://github.com/eslammohamedk123450-netizen/Open-suly/commit/50c6d7449fab6cd98eca98c14583914985bf6925). Tests were added for non-owner denial, secret non-disclosure, successful Vault removal, environment fallback, and safe RPC failure. Platform CI and repository baseline were queued at the last check; the engine build workflow failed without exposing jobs/logs. No green result is claimed until CI completes.


## تحديث تحقق الخصوصية — 2026-11-23

- تم تقليل صفحة قراءة الرسائل في `GET /v1/chat/export` إلى 25 سجلًا بدل 200 لتقليل الذاكرة المؤقتة لكل استعلام؛ صفحة المحادثات بقيت 200.
- أضيفت اختبارات تمنع تصدير رسالة مربوطة بمحادثة لا يملكها صاحب الطلب، وتتحقق من حدود الرسائل والمحادثات والصفحات.
- التنفيذ: [كود التصدير](https://github.com/eslammohamedk123450-netizen/Open-suly/commit/bfd9b63c52322ae97e5eafba649a805ec45f151d) و[اختبارات الخصوصية](https://github.com/eslammohamedk123450-netizen/Open-suly/commit/6ddc7a17e69748dfb79997c604a3471881f54fe1).
- حد `chat_export` الحالي محلي لكل عملية API، وليس موزعًا؛ global ingress rate limit ما زال blocker قبل اعتبار حماية الاستخراج ضد التوزيع/التوسع مكتملة.
- لا يتغير تقدير الجاهزية أو حالة بند export/delete الكامل: التصدير لا يزال للمحادثات فقط، ولا توجد وظيفة حذف حساب كاملة.
