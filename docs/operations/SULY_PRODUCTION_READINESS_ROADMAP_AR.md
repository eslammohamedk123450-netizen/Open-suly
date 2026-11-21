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
