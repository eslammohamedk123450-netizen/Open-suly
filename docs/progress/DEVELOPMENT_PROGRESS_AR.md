# سجل التطوير المستمر — SULY

آخر تحديث: 2026-11-20
الفرع: `main`
آخر نقطة راجعة قبل الجلسة: `c229a76698184ea78c7973de2bb6ff7a01db73ba`
Commit تحديث هذا السجل: يتم ربطه بعد إنشائه.

## هدف المرحلة الحالية
تثبيت تكامل Hermes native Runs API بأمان قبل تفعيل runtime؛ لا تشغيل حقيقي ولا نشر.

## ما تم في جلسة اليوم
- راجعنا خطة الجاهزية، HEAD، الملفات ذات الصلة، وCI.
- تم التأكد أن Compose وREADME يثبتان Hermes على revision واحد `2de9f51b8008a7d49a49221c184f2f11cbfc4af1`.
- CI قبل الجلسة كان ناجحًا (Platform CI + Repository baseline checks على `c229a766`).
- قيدنا معرف Hermes upstream `run_id` ليقبل ASCII letters/digits/underscore/hyphen فقط، لمنع slash/path manipulation والرموز غير المتوقعة.
- أضفنا رفضًا صريحًا لرد حالة Hermes إذا كان JSON ليس object أثناء انتظار الإلغاء.
- أضفنا tests لمعرفات upstream غير الآمنة (path traversal/slash/whitespace/Unicode/empty) ولرد حالة JSON غير صالح.
- حدّثنا checkboxes في roadmap بما تم تنفيذه فعليًا في client/pin/stop/status contract، ووضّحنا أن التحقق mock-only.

## الاختبارات
- API tests لCommit `7419a46d`: **نجاح** (GitHub Actions).
- Platform CI للCommit `7419a46d`: قيد التنفيذ عند آخر مراجعة.
- Baseline checks لCommit `e1516083`: قيد التنفيذ.
- Platform CI لCommit `e1516083`: queued عند آخر مراجعة.
- لا يوجد اختبار Runtime live: Hermes لم يُبنَ أو يُشغّل، ولا Provider/model configured.

## القدرات الحالية المثبتة بالكود
- واجهة API/Client scaffold والـauthenticated routes.
- Durable tasks/task steps، DAG planning، leases، heartbeat، checkpoints، cancellation.
- Approval-gated allowlist للعمليات.
- Engine registry وtyped adapters.
- سجل محاولات engines server-side وlease-guarded upstream run ID.
- Hermes bridge (disabled by default) native Runs admission، idempotency key، polling محدود، cooperative stop، output bounds، safe base URL and run ID validation.
- Tool catalog API تعرض scopes ومتطلبات الموافقة وschema bounds.
- Expo/React Native/Web client scaffold، لكن اكتمال الواجهات وتشغيل التطبيق end-to-end غير معتمد هنا.

## العقبات/القرارات المؤجلة
- مراجعة وتطبيق migrations في بيئة disposable/staging فقط بعد تصريح.
- Integration tests مع Postgres/Supabase disposable.
- Runtime manager لعزل task/container منفصل، CPU/memory/process/disk limits، no host mounts/socket، default-deny egress.
- SSE forwarding، reconciliation للأشغيل الخارجي orphaned بعد restart.
- Full upstream dependency/license audit؛ مراجعة Docker runtime behavior.
- لا يوجد deployment production API/worker ولا AI provider ولا live execution.
- استكمال rate limits/usage billing/quotas، monitoring، backups/restore، load tests، privacy export/delete، security scans.

## تقدير تقدم المشروع
**تقدير محافظ مؤقت: ~20% من هدف Controlled Beta/Production Readiness.**
طريقة التقدير: milestone-based وليس نسبة عدد الملفات؛ احتساب تقدم Core Control Plane وEngine Lifecycle وHermes adapter جزئيًا، مع اعتبار intake engines وscale/reliability وproduction package والاختبارات staging/runtime غير مكتملة. لا تُعتبر capability مكتملة دون اختبار/تشغيل مناسب. يعاد حساب النسبة عند كل checkpoint بناء على roadmap الحالية.

## التالي
1. استكمال انتظار CI على التغييرات الأخيرة ومراجعة أي failures.
2. دراسة worker lease/recovery behavior وتحديد أفضل خطوة تالية: SSE event handling أو orphan-run reconciliation.
3. تنفيذها مع tests وArabic learning note، ثم تحديث roadmap والسجل.


## جلسة تطوير مباشرة — 2026-11-20 (Configuration readiness endpoint)

- تم التحقق قبل التعديل من أحدث main HEAD: `c8c1572ce1d6b7adb2db53f958ceeeb88bd233c5`، وقراءة roadmap، وسجل التطوير، وملفات worker/Hermes، وCI.
- الحالة عند البدء: Repository baseline checks وPlatform CI على commit `c8c1572c` ناجحان.
- أضفنا endpoint جديد `GET /ready` في `services/api/app/main.py` لتمييز liveness (`/health`) عن readiness configuration-only.
- Endpoint يفحص فقط وجود `SUPABASE_URL` و`SUPABASE_PUBLISHABLE_KEY`؛ يعيد 503 إذا ناقصان، و200 إذا موجودان، ولا يعرض قيمهما.
- التوضيح مهم: endpoint لا ينفذ network/database probe، ولا يعتبر worker أو AI provider متطلبات readiness الأساسية. هو فحص إعدادات فقط.
- أضفنا اختبارات لحالة missing config وحالة config موجود مع التحقق من عدم تسريب placeholder key إلى response.
- Commit: `12f0aa5367fc8e7b00174ed77389fbcab905db94` — endpoint.
- Commit: `e341a1e6f869061d3107e03c5bb24331ddcc7147` — tests.
- CI للcommit `12f0aa5367fc`: Repository baseline checks ناجح؛ Platform CI كان in_progress وقت التسجيل.
- CI للcommit `e341a1e6`: Repository baseline checks وPlatform CI كانا in_progress وقت التسجيل.
- لم نشغل API محليًا لأن أدوات GitHub المتاحة هنا تسمح بالتعديل والتحقق من CI عن بعد، ولا توفر runtime محليًا؛ لم ندّع تشغيل pytest محليًا.
- لا توجد migrations جديدة، ولم نطبق أي migration على Supabase، ولم ننشر أو نشغّل worker أو Hermes أو provider.

### نقطة المتابعة التالية
- مراجعة نتائج CI النهائية للcommit `e341a1e6`، ثم معالجة أول نقطة أمان/موثوقية ذات أولوية في worker lifecycle أو engine reconciliation حسب الأدلة.


## جلسة تطوير — 2026-11-20 (Agent Foundation)

- تمت مراجعة HEAD والخطة وملفات worker وengine registry وHermes bridge والاختبارات.
- تحقق CI السابق على commit `bb6c101c1e73` من نجاح baseline checks؛ كما أظهر Platform CI نجاحًا على commit `12f0aa5367fc`. لم تُنسب هذه النتائج إلى التغييرات الجديدة.
- أضيف `services/api/app/services/agent_manager.py`: تعريف أدوار الوكلاء، التحقق من القدرات، ترتيب المحركات المفضلة، وعدم توجيه الوكيل إلا لمحرك مسجل ومفعّل.
- أضيف `services/api/tests/test_agent_manager.py` بخمسة اختبارات لوظائف التوجيه والفشل الآمن.
- Commits: `937bb987dc1d`, `e1d9d4b7bb31`.
- CI على HEAD الجديد كان queued/in progress وقت التوثيق؛ لا يوجد ادعاء بأن الاختبارات نجحت قبل اكتمال CI.
- لا يزال التنفيذ الحقيقي للمحركات غير متاح: لم يتم بناء/تشغيل runtime أو تفعيل Hermes أو أي provider، ولم تطبق migrations أو تنشر خدمات.
- الخطوة التالية: انتظار CI وإصلاح أي فشل، ثم إكمال ربط Agent Manager مع task planning/execution، ومعالجة orphan engine runs/reconciliation، وبعدها intake فعلي للمحركات بمراجعة المصدر والترخيص والأمن.


## جلسة تطوير — 2026-11-20 (مصالحة سجلات تشغيل المحركات اليتيمة)

- أضيفت migration احتياطية ذات دفعات محدودة لمصالحة engine_runs العالقة، بصلاحية service_role فقط وقفل SKIP LOCKED.
- أضيفت دالة عميل server-side مع validation لا تسمح بحجم دفعة خارج 1–500 أو استجابة RPC غير صحيحة.
- أضيفت اختبارات وحدة للحالات الصحيحة والخاطئة.
- Commits: `4b2631294ff6`, `fabebc485b09`, `c5fe327594ed`.
- CI على آخر commit كان queued وقت الفحص. لم تطبق migration ولم يتم تشغيل reconciler دوريًا.
- المصالحة الحالية تسوي حالة السجل في قاعدة البيانات فقط؛ لا تدّعي إيقاف Hermes أو أي process خارجي.


## جلسة تطوير — 2026-11-20 (Agent routing وUpstream intake)

- ربطنا Hermes path بمدير الوكلاء بدل توجيه مباشر للمحرك، وأضفنا كتالوج خمسة أدوار مع إبقاء coding/research/browser/workflow معطلة حتى توافر backends آمنة.
- اختبارات agent catalog وrouting أضيفت؛ CI اكتشف أن bool يمر كـint في batch size، وأصلحناه صراحة.
- Platform CI وRepository baseline checks على commit `7411adec258e` نجحا.
- أضيف ملف مراجعة upstream مع SHAs ثابتة وتقييمات الترخيص والعزل، بما فيها قيود Dify وn8n وAGPL في Skyvern وأرشفة UI-TARS.
- لم يتم تشغيل محركات OpenHands/OpenCode/Aider/Browser Use أو دمج source. OpenHands وBrowser Use لا يدخلان runtime قبل sandbox per-task.
- CI للتوثيق الأخير كان queued وقت التحديث.


## جلسة تطوير — 2026-11-20 (إيقاف المحركات الخارجية اليتيمة)

- عالجنا فجوة مهمة: انتهاء task lease لا يعني أن عملية Hermes الخارجية توقفت. أضيفت حالة `stop_pending` بدل إغلاق سجل تشغيل له upstream ID قبل محاولة الإيقاف.
- أضيفت RPCs لحجز طلبات الإيقاف بlease مستقل، وإتمامها بعد تأكيد الحالة النهائية، أو إعادة المحاولة مع backoff.
- أضيف Hermes stop client محدود الوقت، وEngineRunReconciler، وجدولة اختيارية في WorkerRuntime. بدء reconciler معطل افتراضيًا ويحتاج إعدادًا صريحًا وبيانات اتصال الخادم.
- اختبارات الوحدة تغطي store claims، stop confirmation، عدم اعتبار HTTP acceptance نجاحًا، فشل المحرك، وعدم تسريب تفاصيل الاستثناء.
- CI على commit `8080478aa8bb` نجح (API tests + client typecheck/web export). تغييرات لاحقة على stop guard وschedule لا تزال قيد CI.
- migration `20261120210000` غير مطبقة، ولا توجد عملية Hermes فعلية قيد التشغيل في بيئة اختبار. يلزم disposable PostgreSQL/Supabase للتحقق من SQL semantics قبل تفعيلها.


## جلسة تطوير — 2026-11-20 (أساس سياسة العزل)

- أضيف مولّد Docker argv بسياسة fail-closed: image digest ثابت، شبكة none، rootfs read-only، cap-drop ALL، no-new-privileges، non-root، حدود CPU/RAM/PIDs/ulimits، وmount واحد لمساحة خاصة.
- أضيف رفض symlinks والمسارات خارج الجذر والصلاحيات غير الخاصة وmutable image tags.
- الاختبارات تغطي حدود الموارد، هوية non-root، workspace permissions، mount restrictions وعدم تمرير Docker socket.
- لم يُنشأ Docker runner ولم يُبنَ image ولم تُشغّل حاوية؛ السياسة وحدها لا تثبت عزلًا فعليًا. نحتاج egress proxy آمن قبل السماح باتصال نماذج الذكاء الاصطناعي.


## جلسة تطوير — 2026-11-20 (Agent planning وlate run identity)

- أصبح planner يدعم طلبًا صريحًا `agent:` أو `وكيل:` لتوجيه المهمة إلى general-agent فقط بعد اكتمال إعداد Hermes وتأكيد العزل والتفعيل؛ وإلا يرفض الخطة.
- تم تشديد validation في AgentManager وEngineRegistry، واختبارات القيم والأنواع غير الصالحة.
- أضيفت معالجة سباق run_id: إذا فقد العامل lease قبل حفظ معرف Hermes، يبقى السجل stop_pending ويقبل المعرف المتأخر دون إعادة ملكية التنفيذ؛ ثم يُطلب الإيقاف وتتم المصالحة.
- Hermes bridge يعيد محاولة حفظ المعرف مرة واحدة، ثم يطلب الإيقاف عند فشل الحفظ.
- API tests على commit `3598544eed8d` نجحت؛ بقية CI قيد التنفيذ.
- Sandbox command builder صار يرفض سحب الصور وقت التشغيل ويمنع swap، لكن لا يوجد Docker runner فعلي ولا صورة محرك مبنية أو تشغيل حاويات.


## جلسة تطوير — 2026-11-20 (كتالوج الوكلاء وربط التطبيق)

- أضيف GET /v1/agents محمي بالمصادقة، ويعرض roles/capabilities/availability بدون أسرار.
- أضيفت شاشة تعرض أدوار الوكلاء وحالة التوفر.
- التطبيق أصبح يطلب auto-plan من الخادم لتحليل النص وHermes، بدل تمرير خطوات الخطة مباشرة من العميل؛ الخادم يتحقق من worker/engine/isolation.
- availability catalog صار يطابق حالة worker الفعلية؛ لا يعلن أدوات التنفيذ متاحة إذا worker معطل.
- CI على HEAD `e99f0e1349d4` كان قيد التنفيذ وقت التوثيق.
- لم يتم تشغيل أي محرك upstream إضافي أو بناء Docker image/runner.


## جلسة تطوير — 2026-11-20 (التحقق المركزي من خطط الوكلاء)

- أضيف validator موحد لخطط الوكلاء والـDAG: allow-list العمليات، حقول الإدخال، حدود الحجم وعدد الخطوات، مفاتيح فريدة، واعتماديات صحيحة مرتبة دون cycles.
- endpoint `/plan` لم يعد يقبل عمليات غير مسجلة مثل `shell.exec`؛ يتم الرفض قبل قاعدة البيانات.
- `auto-plan` لا ينشئ خطة إذا Worker معطل، وGeneral Agent يحتاج Worker + Hermes + عزل مؤكد + URL ومفتاح خادم.
- Tool catalog وواجهة Agent أصبحت تعكس حالة Worker الفعلية؛ لا يتم عرض محرك غير جاهز على أنه متاح.
- أضيفت متغيرات البيئة اللازمة مع تعطيل Worker/Hermes/Reconciler افتراضيًا.
- CI على `a05feb5d1226`: API tests وClient typecheck/web export نجحت؛ Baseline على HEAD `6bede601c606` نجح، وPlatform CI كان قيد التنفيذ.
- المسار لم يكتمل: لا يوجد تشغيل حي لـOpenHands/OpenCode/Aider/Browser Use، ولا Docker runner أو egress proxy، ولم تُطبق migrations.


## جلسة تطوير — 2026-11-20 (مراقبة التشغيل اليتيم)

- راجعنا Hermes idempotency ledger: إعادة POST بنفس المفتاح تعيد replay عند وجود السجل، لكن لا يوجد endpoint lookup مستقل بالمفتاح.
- تجنبنا إعادة POST للبحث حتى لا نبدأ run جديدًا بالخطأ.
- أضيفت migration وعدّاد server-only لمراقبة سجلات stop_pending التي لا تملك upstream ID، مع error log آمن في reconciler.
- فجوة crash بين رد Hermes وحفظ run_id موثقة بوضوح؛ لا نغلق السجل ولا ندعي إيقافه دون تأكيد.
- Commits: `38be788521c6`, `66a59f207655`, `6c1145aeacc2`.
- لم يتم تطبيق migration؛ CI على HEAD `66a59f207655` كان queued.


## متابعة — 2026-11-20 (تنبيه التشغيل اليتيم)

- أضفنا deduplication لتنبيه stop_pending بدون upstream ID، مع اختبار أن نفس العدد لا ينتج log متكررًا في كل دورة.
- Commits: `cd3dc4858a64`, `61dc3432b595`.
- Baseline على `cd3dc4858a64` نجح؛ CI للـHEAD الأحدث queued.


## تصحيح نطاق المنتج — 2026-11-20

- تأكيدًا لتصحيح صاحب المشروع: HIMS تابع لتطبيق قديم متوقف، وخارج نطاق SULY الجديد بالكامل.
- لا يجوز استخدام HIMS أو دمجه أو الحفاظ عليه كمتطلب أو بناء جداول/واجهات/API/صلاحيات/تكاملات تعتمد عليه.
- SULY منتج مستقل؛ المسموح بإعادة استخدامه من العمل السابق يقتصر على هوية SULY والعناصر البصرية المعتمدة فقط.
- تم توثيق هذا الاستثناء صراحةً في `README.md` و`SULY_MASTER_ARCHITECTURE.md` و`docs/architecture/OPEN_SOURCE_ENGINE_INTEGRATION.md`.
- Commits: `4e17c2ea32b9`, `a5eae8f7bf0c`, `7b9cfe708ab8`.
- لم يتم حذف أي جداول أو بيانات أو ملفات برمجيّة في هذه الخطوة؛ كانت التغييرات توثيقية لتثبيت نطاق المشروع دون المخاطرة بأجزاء أخرى.
- آخر فحص معروف قبل هذه التغييرات أظهر فشل حالة Railway على HEAD السابق `e9d88bc7183d`. يلزم تشخيص سجل البناء/النشر من Railway قبل نسبة الفشل إلى كود بعينه أو إعلان نجاح.


## تشديد تحقق مهلة Hermes — 2026-11-20

- عالجنا حالة تحقق حدودية في Hermes bridge: Python يعتبر `bool` نوعًا فرعيًا من `int`، ولذلك كانت القيمة `True` تمر سابقًا كمهلة ثانية واحدة.
- أصبح التحقق يرفض القيم المنطقية وغير الرقمية والمهل خارج النطاق 1–300 ثانية.
- أضيفت اختبارات للقيم `True` و`False` والصفر و301 والنص.
- Commits: `b3db61e15397`, `f1bf43fab49d`.
- الاختبارات لم تُشغّل محليًا في هذه الجلسة؛ ننتظر CI على commit الاختبارات قبل إعلان النجاح.
