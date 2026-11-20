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


## أول كتالوج محركات SULY — 2026-11-20

- أضيف `services/api/app/services/engine_catalog.py` لتسجيل Hermes وOpenCode وBrowser Use بهويات ومراجع upstream ثابتة (commit SHA) وقدرات منفصلة.
- تمت مراجعة ملفات LICENSE عند المراجع المثبتة؛ المشاريع الثلاثة تعلن MIT. ما زال فحص تراخيص الاعتماديات العابرة وSBOM مطلوبًا قبل التوزيع.
- جميع المحركات مسجلة معطلة افتراضيًا، وتتطلب موافقة، ولا يوجد Adapter مربوط بها في هذا التغيير؛ لم يتم تشغيل أي خدمة خارجية.
- أضيفت اختبارات لثبات المراجع ومنع التكرار والتأكد من الإغلاق الآمن افتراضيًا.
- Commits: `e28b4ec0a0d6`, `59e9d238dd1d`, `b178d64a2d8f`.
- لم يتم تشغيل الاختبارات في بيئة تنفيذ محلية بهذه الجلسة؛ يلزم انتظار CI.


## توصيل أدوار الوكلاء بكتالوج المحركات — 2026-11-20

- أضيف `agent_catalog.py` لربط أدوار SULY الثلاثة: الوكيل العام مع Hermes، وكيل البرمجة مع OpenCode، ووكيل المتصفح مع Browser Use.
- كل الأدوار معطلة افتراضيًا وتتطلب الموافقة؛ الاختبارات تؤكد رفض التوجيه قبل التفعيل.
- أضيفت اختبارات تغطي خريطة الأدوار وسلوك الرفض الآمن.
- Commits: `7bddc34a6fd7`, `d77e0e4b6129`, `e390e1fb8cfb`.
- لا توجد بعد عمليات تشغيل خارجية أو اتصالات فعلية بهذه المحركات؛ الربط الحالي هو خريطة قدرات داخلية فقط.


## قناة أحداث Hermes عبر SSE — 2026-11-20

- أضيف مستهلك اختياري لأحداث Hermes الأصلية عبر `GET /v1/runs/{run_id}/events`.
- تمر فقط أسماء الأحداث المسموح بها ورقم التسلسل والتوقيت؛ لا تمر معاينات الأدوات أو التفكير أو نصوص الرسائل أو المخرجات أو معاملات الأدوات.
- يظل فحص حالة التشغيل هو المرجع النهائي للنجاح والإلغاء، وتظل SSE قناة تقدم اختيارية لا تؤثر أعطالها على نتيجة المهمة.
- أضيفت اختبارات لتحليل SSE وربط الحدث بمعرف التشغيل ومنع تسريب المحتوى.
- Callback الأحداث غير مربوط بعد بمخزن أحداث دائم أو واجهة المستخدم؛ لذلك لم أعتبر البث للمستخدم مكتملاً.
- Commits: `0ac9476135a1`, `18555cf1f90a`, `1280ca0bd3be`, `a3070805ec25`.
undefined

## حالة التحقق بعد دمج كتالوج المحركات — 2026-11-20

- آخر HEAD قبل هذا التحديث التوثيقي: `09b334435e7ea9afff4b8e89f4def807a013e883`؛ حالة فحص Railway المسماة `strong-gentleness - suly-api` عادت `failure`.
- أداة GitHub المتاحة لم تعرض أي GitHub Actions workflow runs مرتبطة بهذا commit، ولا تتيح أدوات Railway المتصلة قراءة deployment logs؛ لذلك لم أحدد سبب الفشل ولم أعد تشغيل نشر تخميني.
- فحوصات Railway ليست دليلًا على نجاح اختبارات Python. الاختبارات الجديدة موجودة في المستودع، لكنها غير مؤكدة التنفيذ حتى تظهر نتيجة CI فعلية.
- تم تشديد كتالوج Hermes ليعلن فقط `agent.general` كقدرة SULY الموصولة حاليًا؛ قدرات التخطيط/المهارات/الذاكرة/البحث تظل غير قابلة للتوجيه المستقل حتى اكتمال تكاملاتها وصلاحياتها.
- Commit تحديث توضيح تفعيل الأدوار: `b5d8fb9583f3`.


## جلسة تطوير — 2026-11-20 (توصيل أحداث Hermes بالسجل الدائم)

- تم استكمال فجوة كانت موثقة سابقًا: SSE كان يُستهلك اختياريًا لكن callback لم يكن موصولًا بسجل SULY.
- أضيفت migration 20261120235000_engine_run_events.sql لإنشاء جدول أحداث metadata فقط، مع RLS لقراءة المالك، وكتابة service-role فقط، وRPC يتحقق من lease العامل وحالة سجل التشغيل قبل قبول الحدث.
- الأحداث المسموح بتخزينها هي أسماء محددة ورقم تسلسل وتوقيت فقط؛ لا تُخزن prompts أو reasoning أو tool arguments أو previews أو outputs.
- أضيف EngineRunStore.append_event بتحقق صارم من اسم الحدث والتسلسل والتوقيت، مع idempotency حسب upstream sequence وإرجاع false عند فقدان lease.
- تم توصيل callback من Hermes adapter إلى RPC، وأصبح GET /v1/tasks/{task_id} يعرض engine_events ضمن سجل المهمة بفلترة owner وحد أقصى 500 حدث.
- أضيفت اختبارات وحدة لـRPC/event validation، واختبار توصيل adapter، واختبار task detail owner-scoped.
- Commits: ad925cf0dc13 (migration)، dbf21874127d (store)، 92b3daeca1b3 و2bc7c7b7f037 (worker adapter)، b47b5b69e6c4 (API)، bf706c53abcf و9c1ba64e2843 وd7c92fe9ea6d و9b23db3b3d2d (tests).
- لم تُطبق migration على Supabase ولم يحدث deployment أو تشغيل Hermes. يجب تطبيق migration قبل نشر نسخة API التي تقرأ جدول الأحداث.
- الاختبارات أضيفت فقط حتى الآن؛ لا أعتبرها ناجحة قبل ظهور نتائج CI على HEAD الحالي. لم يتم تشغيل pytest محليًا من بيئة هذه الجلسة.

### الخطوة التالية
- مراجعة نتائج CI، ثم إضافة contract tests للـevent persistence/ownership، والتحقق من واجهة العميل لعرض أحداث التشغيل دون تسريب بيانات حساسة.
- بعد ذلك استكمال Hermes control endpoints التي يدعمها upstream (steer/approval/session/skills) واحدًا تلو الآخر بعد مراجعة API schema والربط مع موافقات SULY، ثم الانتقال إلى OpenCode runtime مع sandbox per-task.


## متابعة واجهة سجل أحداث المحركات — 2026-11-20

- أضيف النوع AgentEngineEvent إلى عميل Expo، وأصبحت استجابة task snapshot تتضمن engine_events.
- شاشة تفاصيل المهمة تعرض تحديثات التنفيذ بأسماء عربية ووقت الاستلام ورقم التسلسل فقط؛ لا تعرض أي payload خام من Hermes.
- أضيف شرح تعليمي عربي لمسار الحدث والـlease وRLS ومنع التكرار ومتطلبات النشر في docs/learning/ENGINE_RUN_EVENTS_AR.md.
- تحقق Platform CI وRepository baseline checks على commit 9b23db3b3d2d بنجاح؛ سجل API tests عدد 321 اختبارًا ناجحًا، كما نجح typecheck وExpo compatibility وweb export. كان هناك فشل سابق على commit أقدم بسبب fixture لم يتضمن جدول الأحداث، وتم إصلاحه قبل هذا النجاح.
- التغييرات اللاحقة الخاصة بالتوثيق وواجهة عرض الأحداث تنتظر نتائج CI على أحدث HEAD؛ لا تُنسب نتيجة 321 اختبارًا إلى commits أحدث قبل اكتمال فحوصاتها.
- لا تزال migration غير مطبقة، ولا يوجد WebSocket أو Hermes runtime حي أو worker منشور. واجهة التقدم تعتمد حاليًا على polling شاشة المهمة.


## جلسة تطوير — 2026-11-20 (التحكم في تشغيل Hermes من واجهة المهمة)

- أضيف العميل steer_agent_run لإرسال توجيه محدود إلى تشغيل Hermes موجود فقط عبر POST /v1/runs/{run_id}/steer؛ لا ينشئ تشغيلًا جديدًا ولا يقبل معرف تشغيل غير آمن.
- أضيف endpoint محمي POST /v1/tasks/{task_id}/engine-runs/{run_id}/steer. يتحقق من ملكية المستخدم للمهمة والمحرك، وحالة المهمة والتشغيل، ووجود lease صالح للخطوة، وإعدادات Hermes والعزل قبل الاتصال بالخدمة الخارجية.
- بعد قبول التوجيه، يحاول الخادم تسجيل حدث metadata باسم run.steered فقط عبر RPC يعيد التحقق من lease؛ لا يتم تخزين نص التوجيه.
- أضيفت اختبارات للـclient والـAPI: قبول التوجيه، رفض التشغيل المنتهي، ومنع الوصول لمهمة مستخدم آخر. أحدث تشغيل API CI على commit a7214c87: 329 passed, 2 warnings. نجاح API tests مؤكد؛ Client typecheck/export لنفس commit كان ما يزال قيد التنفيذ عند آخر فحص.
- شاشة تفاصيل المهمة أصبحت تعرض حقل توجيه وزرًا فقط عندما يكون Hermes run نشطًا. Platform CI على commit 6b09cdb4 نجح: API tests + TypeScript typecheck + Expo compatibility + Web export.
- أضيف تحديث توثيقي في HERMES_CAPABILITY_INTEGRATION_STATUS.md يوضح ما تم وما لا يزال مؤجلًا: موافقات Hermes الأصلية، clarify، sessions، skills، memory، وsubagents.
- فشل تشغيل SULY Free Test Worker المجدول في GitHub Actions عند خطوة التحقق من الأسرار المطلوبة (SUPABASE_URL وSUPABASE_SECRET_KEY)، قبل تثبيت المتطلبات أو تشغيل worker؛ لذلك لم تُعالج أي مهام ولم يحدث تنفيذ حي عبر هذا التشغيل. لم نضف أسرارًا أو نفعّل worker.
- لا تزال migration 20261120235000_engine_run_events.sql غير مطبقة، ولا يوجد deployment أو تشغيل Hermes حي. يجب تطبيق migration في disposable/staging أولًا قبل نشر API الذي يعتمد على الجدول.
- آخر HEAD بعد تحديث التوثيق: 12eb2b3754b1؛ فحوصات هذا التحديث تنتظر الاكتمال، ولا تُنسب نتائج commits السابقة إليه.


## تحقق نهائي للجلسة — 2026-11-20

- HEAD الذي تم التحقق منه قبل هذا التحديث: 7422195709611597414df4a6dc8a347d076ed983.
- Platform CI على هذا الـHEAD نجح بالكامل: 329 API tests passed، وTypeScript typecheck، وExpo dependency compatibility، وWeb export جميعها ناجحة. Repository baseline checks ناجحة أيضًا.
- التحذيران في API tests من Starlette/httpx واسم HTTP 422 deprecated؛ لم يؤثرا على نجاح الاختبارات.
- لا يوجد نشر أو تطبيق migrations أو تشغيل Hermes. فشل Free Test Worker المجدول كان قبل runtime بسبب عدم وجود أسرار Supabase المطلوبة، ولم يبدأ تنفيذ المهام.
- تحديث هذا السجل نفسه ينتج commit جديدًا، لذلك يجب إعادة التحقق من CI على HEAD النهائي بعده قبل اعتباره آخر checkpoint معتمد.


## دفعة تطوير — تكامل موافقات Hermes الدقيقة — 2026-11-20

- تمت مراجعة كود Hermes upstream المثبت عند commit 2de9f51b8008a7d49a49221c184f2f11cbfc4af1، وتأكدنا من endpoint الأصلي POST /v1/runs/{run_id}/approval ومن دعم request_id والاختيارات once/session/always/deny.
- نفذنا في SULY سياسة أضيق: يسمح فقط بـ once أو deny، ولا توجد موافقات session أو always أو resolve-all.
- أضيف resolve_agent_approval في Hermes bridge؛ يتحقق من هوية run وrequest في الاستجابة ومن أن resolved يساوي 1، ولا يمرر جسم الخطأ الخارجي.
- أضيف اختزال آمن لحدث approval.request: يحتفظ فقط بمعرف الطلب المعتم ASCII، ولا يحتفظ بالأمر أو الوصف أو نصوص النموذج.
- أضيفت أعمدة approval_request_id وapproval_choice إلى سجل الأحداث عبر migration جديدة، مع قيود تمنع البيانات غير المتوقعة. جعلنا القيود NOT VALID عند الإنشاء للتوافق مع أحداث الموافقات التاريخية القديمة، مع استمرار تطبيقها على الكتابات الجديدة.
- أضيف endpoint محمي لصاحب المهمة فقط، يطلب معرف الموافقة المسجل لنفس engine run، ويرفض المعرفات غير الموجودة أو التي تمت الإجابة عنها، ويتحقق من task/run/lease/config قبل استدعاء Hermes. بعد الاستجابة يسجل once/deny فقط.
- أضيفت أنواع وعميل التطبيق وشاشة تعرض بطاقة موافقة فيها زران: موافقة لمرة واحدة أو رفض. لا يظهر payload الخام ولا أي نص أمر حساس.
- أضيفت اختبارات لوحدة Hermes وEngineRunStore وAPI تشمل رفض session/always، والطلب غير المسجل، والطلب المجاب عنه، والعزل بين engine runs، والتحقق من رد Hermes.
- آخر CI مؤكد قبل هذه الدفعة: Platform CI وRepository baseline على commit 74311d9a نجحا (API tests + TypeScript + Expo compatibility + Web export). تغييرات موافقات Hermes الجديدة على commits 6daf7c1 إلى dd988dd9 قيد الفحص؛ لا ننسب نجاح الفحص السابق لها.
- Migration 20261121010000_engine_run_approval_metadata.sql غير مطبقة. يجب تطبيقها على قاعدة اختبار مؤقتة والتحقق من توقيع RPC الجديد قبل نشر API. لا يوجد Hermes runtime حي أو provider أو worker مفعّل.

## دفعة إضافية — موافقات مرئية وغير عمياء — 2026-11-20

- أضفنا endpoint لقراءة تفاصيل الموافقة من حالة Hermes الحالية، مع التحقق من أن run ما زال waiting_for_approval وأن request_id مطابق تمامًا.
- تفاصيل command وdescription تأتي من عرض Hermes المنقح، وتُعاد للمستخدم عند الطلب فقط. لا تحفظ قاعدة SULY نص الأمر أو الوصف؛ السجل الدائم يحتفظ بمعرف الطلب والقرار once/deny فقط.
- واجهة المهمة لم تعد تعرض أزرار الموافقة مباشرة: يجب الضغط على «عرض تفاصيل العملية» أولًا، ولا تظهر أزرار الموافقة/الرفض إلا بعد جلب التفاصيل بنجاح.
- أضيفت اختبارات تفاصيل الموافقة في Hermes client وAPI، تشمل ربط run/request، حالة الانتظار، ومنع إظهار تفاصيل طلب غير موجود أو تمت الإجابة عنه.
- Platform CI وRepository baseline على commit c79ee7f2 نجحا. Platform CI على commit 8762451a نجح: 355 API tests passed، TypeScript typecheck، Expo compatibility، وWeb export كلها ناجحة. التحذيران الموجودان في API tests من تبعيات Starlette/FastAPI ولا يمثلان فشلًا.
- بعد مراجعة migration الجديدة، شددنا شرط قاعدة البيانات ليرفض NULL صراحة في قرار الموافقة؛ commit 206e55df هو آخر HEAD، وCI الخاص به queued وقت التوثيق.
- لا تزال migrations غير مطبقة، ولا يوجد runtime حي أو worker أو provider مفعّل. لا نعلن نجاح CI للـHEAD الأحدث حتى تنتهي فحوصاته.

## دفعة مراجعة OpenCode وعزل المستأجرين — 2026-11-20

- راجعت المصدر المثبت OpenCode عند commit `4cca18d80450a3dd6a9a4142028bde84ccb3116e`، وتحققت من ترخيص MIT وحزمة `@opencode/server` 2.3.0.
- اتضح أن مصادقة OpenCode مبنية على كلمة مرور واحدة للخادم وsession cookie مشتقة منها بعمر 30 يومًا؛ ليست هوية SULY ولا صلاحيات مستخدم/مهمة مستقلة.
- راجعت Session handler وSessionLocation middleware وLocation middleware: session/location داخليان لخادم OpenCode ولا يثبتان ملكية SULY، كما أن اختيار directory من query/header لا يجوز تمريره من العميل كمسار مضيف.
- أضفت `docs/architecture/OPENCODE_INTEGRATION_AUDIT.md` وفيه متطلبات التشغيل الصحيح: حاوية مؤقتة لكل task attempt، سر مستقل لكل runtime، broker يتحقق من المالك والـlease، منع shared process/session store/PTY، egress default-deny، وإزالة الموارد عند الإلغاء وفقد lease.
- القرار: OpenCode يظل disabled بلا adapter ولا server مشترك. هذا تدقيق upstream وتصميم عزل، وليس إعلان دمج المحرك أو تشغيله.
- تم إصلاح migration `20261121010000_engine_run_approval_metadata.sql` بالكامل بعد اكتشاف أن نسخة سابقة كانت مبتورة ومكررة. النسخة الحالية تحتوي القيود كاملة، RPC الجديد، grants المقيدة لـservice_role، وقيود NOT VALID للتوافق مع السجلات التاريخية. لم يتم تطبيقها على أي قاعدة.
- شددنا عرض موافقات Hermes بإزالة Unicode control/format/bidi characters من command/description قبل عرضهما، مع اختبارات.
- CI: Platform CI وRepository baseline على commit `01e8e88b9e267b138bbfc0fbd24599be36294441` نجحا بالكامل: 364 API tests passed، TypeScript typecheck، Expo compatibility، Web export. Commit `b1666a9c` فشل بسبب fixture اختبار كتب newline/NUL كنص حرفي؛ تم إصلاح fixture في `01e8e88b` ثم نجح CI. أحدث HEAD عند كتابة هذا السطر هو `7232a4d886714bf70d10359dbef7f0726f6d9142` وفحوصاته queued؛ لا ننسب إليه نجاح commit السابق حتى تكتمل.
- لا worker أو Hermes/OpenCode runtime أو provider مفعّل، ولا migrations مطبقة، ولا deployment.


## دفعة تطوير إضافية — عزل هوية كل تشغيل OpenCode/Hermes — 2026-11-20

- راجعنا كود OpenCode المثبت عند revision 4cca18d80450a3dd6a9a4142028bde84ccb3116e. مصادقة OpenCode أصلًا server-wide وليست مصادقة SULY tenant؛ جلساته ومجلداته لا تمثل حد عزل بين مستخدمي SULY. لذلك لا يجوز تشغيل خادم مشترك أو تمرير مسار filesystem يختاره العميل.
- أضفنا تدقيقًا معماريًا في OPENCODE_INTEGRATION_AUDIT.md يحدد متطلبات runtime مؤقت لكل task attempt، وbroker يفحص المالك والـlease، وcredentials قصيرة العمر، وإغلاق العمليات وتنظيف المساحة بعد الإلغاء أو فقد lease.
- شددنا DockerSandboxCommandBuilder دون تشغيل Docker: أصبح يقبل engine_run_id اختياريًا، ويولّد اسم container وlabels على مستوى المحاولة، ويضبط PID/IPC/UTS namespaces على private ويمنع restart ويعطل container logs افتراضيًا.
- بقيت القيود السابقة كما هي: image digest ثابت، network none، root filesystem read-only، drop ALL capabilities، no-new-privileges، seccomp default، non-root، حدود CPU/RAM/PIDs/tmpfs، mount واحد لمساحة العمل، لا host mounts ولا Docker socket.
- أضفنا اختبارات لتمييز retries لنفس task بهويات تشغيل مستقلة والتحقق من private namespaces. هذا اختبار بناء command فقط؛ لا يثبت تشغيل container أو منع cross-tenant escape.
- CI: Repository baseline على commit 6289ed2e نجح، وPlatform CI كان قيد التشغيل عند آخر فحص. تغييرات الاختبارات والتوثيق اللاحقة على commits 1ab4cede وf4cb68bc تحتاج انتظار CI النهائي على أحدث HEAD.
- Hermes وOpenCode وBrowser Use والـworker ما زالت disabled افتراضيًا. لم يتم تشغيل Docker أو تطبيق migration أو نشر أي خدمة.


## دفعة تدقيق Browser Use — 2026-11-20

- راجعت Browser Use عند pin `ccbdb8095fbaf903c748880a600054a34c7b6191`، وتحققت من نسخة الحزمة 1.0.6 وترخيص MIT.
- اكتشفت أن MCP server يعرض `browser_exec` كـPython REPL مستمر ينفذ داخل process نفسه؛ يستطيع قراءة environment والملفات المحلية، بما فيها `BROWSER_USE_API_KEY` إذا كانت موجودة. لذلك لا يمكن مشاركة MCP server بين مهام أو مستخدمين.
- راجعت دعم local Chrome profile والاتصال بملف Chrome قائم، وأكدت ضرورة منع الوصول لملفات/ملفات تعريف المتصفح المضيف أو browser-harness daemon مشترك.
- upstream يوضح أن allowed_domains/prohibited_domains لا تحمي cloud browser؛ هذه القواعد تخص local Chromium فقط. لذلك لا يمكن اعتبارها SSRF/egress boundary.
- أضفت `docs/architecture/BROWSER_USE_INTEGRATION_AUDIT.md` وفيه عقد العزل المطلوب: MCP process/container لكل task attempt، egress proxy default-deny، فحص DNS/redirect/IPv4/IPv6، موافقة قبل side effects، وإنهاء process tree وإبطال credentials.
- Browser Use يظل disabled metadata فقط. لم يتم تشغيل browser أو MCP server أو استخدام API key، ولا توجد أي browser side effects.


## دفعة عقد Runtime لكل محاولة — 2026-11-20

- أضيف `runtime_broker_contract.py` بعقد RuntimeLease مربوط بـtask UUID + engine_run UUID + engine ID + runtime UUID، مع token مخفي عن repr ومدة صلاحية لا تتجاوز ساعة.
- أضيف TaskScopedRuntimeBroker لرفض إعادة استخدام نفس محاولة المهمة ونفس runtime ID، حتى بعد release داخل عمر العملية، مع context manager يحاول teardown دائمًا.
- شددت التحقق: HTTPS فقط، host DNS مطابق تمامًا لقائمة allowlist، رفض IP literals بما فيها metadata IP، ورفض credentials/query/fragment/path داخل base URL، وحد token 32–512 ASCII.
- أضيفت اختبارات للعزل بين المهام والمحاولات، endpoint allowlist، رفض HTTP وIP literal وsubdomain غير المطابق، انتهاء الصلاحية، تكرار المحاولة/runtime، invalid provider lease، وفشل teardown.
- العقد لا ينشئ containers ولا يشغّل OpenCode أو Browser Use. لا يوجد concrete provider أو network broker أو Docker runtime؛ المحركات ما زالت disabled.
- CI على commits السابقة: Platform CI وBaseline على `01e8e88b` نجحا (364 API tests + TypeScript + Expo compatibility + Web export). Baseline على commits `88927c93` و`3db6a8fd` نجح، لكن Platform CI لهما كان قيد التنفيذ عند آخر فحص. لا ننسب نجاح CI إلى HEAD الحالي قبل اكتماله.


## دفعة تدقيق إضافية — Hermes sessions وskills وtoolsets — 2026-11-20

- راجعنا endpoints الأصلية في Hermes pinned revision: GET /v1/skills وGET /v1/toolsets وعمليات /api/sessions.
- اكتشفنا أن skills وtoolsets محمية بـBearer auth، لكن skills list تشمل حتى disabled/editorial، وأن toolsets تعكس إعدادات عملية Hermes كاملة لا صلاحيات مستخدم SULY.
- Sessions API تعمل على قاعدة جلسات Hermes المحلية وملف profile، ولا تربط session ID بمالك SULY أو task أو RLS. وهي تعرض messages وfork وchat وlifecycle داخل profile واحد؛ لذلك لن نمررها مباشرة للعميل أو نستخدم Hermes profile مشتركًا.
- القرار: جلسات SULY ومحادثاته تظل المصدر الوحيد للسياق والملكية. لا نحفظ Hermes session IDs بين محاولات معمارية runtime المؤقت لكل task. Skill catalog مستقبلي يكون read-only، pinned ومراجع المصدر والرخصة، ولا يعني تفعيل الأدوات.
- أضيف التدقيق في HERMES_SESSIONS_SKILLS_AUDIT.md.
- أضيف runtime lease broker contract مع exact endpoint origin allowlist (scheme/host/port)، ربط lease بـtask/run/engine، صلاحية لا تتجاوز ساعة، ومنع إعادة استخدام runtime identity أو task attempt داخل العملية. أضيفت اختبارات unit تغطي origin/port، metadata/localhost، expiry، ownership mismatch، وإعادة الاستخدام والتنظيف.
- CI كشف فشلًا في اختبارات lease لأن وقت انتهاء الاختبار كان أبعد من حد الساعة؛ أصلحنا الاختبارات لتستخدم وقتًا حاليًا وصلاحية 30 دقيقة. فحص CI على commit 3936f442 queued وقت آخر فحص؛ لا نعلن نجاحًا قبل اكتمال API tests وclient typecheck/export على أحدث HEAD.
- لم يتم بناء provider فعلي أو تشغيل Docker أو Hermes أو Browser Use، ولم تُطبق أي migration أو deployment. كل المحركات تظل disabled.


## تشديد Runtime Lease Broker — 2026-11-20

- شددنا عقد endpoint الخاص بالـruntime: allowlist أصبحت origins كاملة بدل host فقط، ويجب أن تكون canonical HTTPS origins بلا credentials أو path أو query أو fragment، مع رفض localhost وIP literals/metadata IP.
- أضيف تحقق من exact origin match بدل suffix matching، حتى لا يقبل subdomain غير مقصود.
- أصبح broker يحتفظ بكائن الـlease نفسه، وليس معرف المحاولة فقط؛ لا يقبل release لكائن lease مستنسخ حتى لو كانت قيمه مساوية.
- عند اكتشاف runtime ID سبق إصداره، لا يحاول broker إيقافه مرة أخرى؛ لأن ذلك قد ينهي runtime ما زال مملوكًا لمهمة أخرى أو broker آخر. أما runtime جديد أُنشئ بالخطأ لمحاولة مكررة فيتم طلب release له.
- أضيفت اختبارات لرفض HTTP/IP origins، والـlease المزيف، وإعادة استخدام runtime identity.
- API tests على commit `7a805ed9a8d1` نجحت؛ Client jobs كانت قيد التنفيذ. أحدث commits الاختبارات `c3a0ad69` و`11c2bf29` تنتظر Platform CI، فلا نعلن نجاحها بعد.


## متابعة تدقيق runtime broker وHermes — 2026-11-20

- RuntimeLease أصبح يقبل exact HTTPS origin من allowlist الخادم فقط، ويرفض HTTP وIP literals وlocalhost والـpath/query/fragment وembedded credentials.
- تم التحقق من access token ليكون bounded وheader-safe ASCII، ومنع release لكائن lease مستنسخ حتى لو كانت قيمه متطابقة، ومنع teardown مرتين لمعرف runtime سبق إصداره.
- تمت إضافة اختبارات لتطابق origin الكامل (scheme/host/port)، رفض metadata IP وlocalhost، رفض HTTP، token validation، ownership mismatch، lease expiry، forged release، runtime ID reuse، وteardown.
- تم تدقيق Hermes sessions/skills/toolsets عند upstream pin الحالي؛ لا نستخدم Hermes session database المشتركة، ولا نعرض toolsets أو skills كصلاحيات SULY. جلسات SULY هي مصدر سياق المحادثة والملكية.
- Platform CI وRepository baseline على commit 7a805ed9 نجحا بالكامل: 381 API tests، TypeScript typecheck، Expo dependency compatibility، وWeb export.
- API tests على commit 11997350 نجحت: 388 passed, 2 warnings؛ client typecheck/export كانا قيد التنفيذ عند آخر فحص لهذا commit. أحدث تغييرات الاختبارات والوثائق بعده تنتظر Platform CI على أحدث HEAD.
- لا يوجد provider فعلي للـruntime broker ولا حاويات تعمل؛ OpenCode وBrowser Use وHermes ما زالت disabled. لا توجد migrations أو deployments تم تطبيقها في هذه الدفعة.


## تحسينات إضافية لموافقة Hermes — 2026-11-20
- تمت مراجعة مسار GET /v1/runs/{run_id} في نسخة Hermes المثبتة، وتأكدنا أن حالة waiting_for_approval تعيد كائن approval الذي بُني عبر helper التنقيح upstream؛ لا نستخدم SSE payload خامًا كبديل.
- أضيفت حماية no-store لاستجابة تفاصيل الموافقة، مع Vary: Authorization، واختبار يثبت عدم تخزين بيانات الأمر في cache.
- تم تصحيح مفاتيح حالة الموافقة في الواجهة لتكون مركبة من engine_run_id + request_id، منعًا لتصادم معرفات الطلب بين محاولات تشغيل مختلفة.
- API tests نجحت على commit 11c2bf29 بعد إصلاح اختبار إعادة استخدام runtime identity. التعديلات التالية الخاصة بمفاتيح الواجهة وno-store headers قيد CI على أحدث HEAD؛ لا نعلن نجاحًا قبل اكتمال أحدث API + typecheck + Expo compatibility + Web export.


## دفعة إضافية — تزامن runtime broker — 2026-11-20

- أضفت حجزًا ذريًا للمحاولة قبل إنشاء runtime لمنع سباق الاستدعاءات المتزامنة لنفس task/run/engine داخل worker process.
- أضفت منعًا لتكرار release المتزامن لنفس runtime، مع الاحتفاظ به محجوزًا إذا لم يؤكد provider عملية الإنهاء.
- أضفت اختبارات threads لتغطية السباق في acquire والازدواج في teardown.
- أثناء مراجعة CI اكتشفت أن تعديلًا سابقًا استهدف تعريف acquire داخل Protocol بدل class، ما أدى لفشل جمع الاختبارات. استعدت Protocol وTaskScopedRuntimeBroker كاملين في commit 772207dc، وسجلت السبب في وثيقة عقد broker.
- Repository baseline checks على commit 772207dc بدأت، وPlatform CI كان queued عند آخر فحص. لا أعتبر الإصلاح مجتازًا حتى تظهر نتيجة ناجحة على HEAD النهائي.
- لا يوجد provider حقيقي بعد، ولا يتم إنشاء حاويات أو تفعيل أي محرك. الحماية الحالية داخل process واحد فقط.


## دفعة Browser Use — سياسة URL/SSRF تمهيدية — 2026-11-20

- أضيف browser_network_policy.py كطبقة preflight لاختيار عناوين التصفح، مع allowlist لكل مهمة، ومنافذ محددة، ورفض userinfo وIP literals وlocalhost و.local و.internal وأي DNS answer غير public.
- أضيفت اختبارات تستخدم DNS resolver وهميًا؛ لا يوجد أي اتصال خارجي أثناء الاختبارات. تشمل exact host/subdomain، ports، private/mixed DNS answers، metadata IP، وURL malformed.
- راجعنا Browser Use MCP source عند pin ccbdb8095fbaf903c748880a600054a34c7b6191. MCP browser_exec يشغل Python داخل نفس process ويستطيع قراءة environment والملفات؛ لذلك لا يمكن تشغيله في API أو worker مشترك. لا يتم استخدام Browser Use Cloud أو أي API مدفوع.
- وثقنا ضرورة per-attempt browser process/profile وegress proxy يثبت DNS عند الاتصال ويعيد فحص redirects والـsubresources؛ BrowserNetworkPolicy مجرد preflight ولا يمنع DNS rebinding بمفرده.
- Platform CI على commit 772207dc نجح في API tests: **415 passed, 2 warnings**. Client typecheck/export كانا قيد التنفيذ عند آخر فحص؛ commit 852ddd1f أضاف تحديث التوثيق فقط وفحوصاته queued.
- لا يوجد Browser Use adapter أو runtime provider أو egress proxy فعلي، ولذلك المحرك ما زال disabled. لا توجد migrations أو deployments أو browser sessions حية.
