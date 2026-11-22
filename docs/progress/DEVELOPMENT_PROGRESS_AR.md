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
1. تأكيد نتائج CI على أحدث commit بعد إصلاح أخطاء syntax وعقد runtime؛ لا تُسجل نجاحًا قبل اكتمال الـruns.
2. بعد CI أخضر، استكمال usage/credits metering للمهام والمحركات مع idempotency ومنع التنفيذ عند نفاد الرصيد، دون تفعيل أي محرك.
3. مراجعة lease/recovery وعمليات Apply/Reject واختبارات cross-user على قاعدة disposable قبل أي طلب Staging.


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


## دفعة إضافية — إحكام أحداث موافقات Hermes — 2026-11-20

- أصبحت أحداث approval.request وapproval.responded تُرفض بالكامل إذا كان request_id ناقصًا أو غير صالح، بدل تمرير event ناقص إلى RPC.
- أحداث approval.responded لا تمر إلا إذا كان القرار once أو deny؛ session وalways وأي قيمة غير متوقعة لا تدخل سجل الأحداث.
- أضيفت اختبارات للقيم الناقصة، ومحارف التحكم، والقرارات الدائمة/غير المدعومة، والتأكد من بقاء السجل metadata-only.
- GitHub Platform CI على commit 06c46b4d: اختبارات API نجحت، 427 passed و2 warnings. فحص Client typecheck/Expo compatibility/Web export كان ما زال جاريًا وقت التحقق.
- ملاحظة: run سابق على commit 17889cf7 فشل بسبب اختبارات قديمة كانت تتوقع الاحتفاظ بحدث approval ناقص؛ تم تحديث الاختبارات لتتوافق مع fail-closed behavior، ثم نجح API CI على 06c46b4d.
- لا توجد موافقات Hermes حية أو runtime مفعّل؛ هذه اختبارات وحدات/API mock.


## تشديد أخير لسياسات التصفح والموافقات — 2026-11-20

- BrowserNetworkPolicy يرفض الآن أيضًا صيغ IPv4 القديمة مثل 127.1 والأعداد الصحيحة/hex التي قد تتجاوز فحص IP التقليدي، كما تم تصحيح التعامل مع المنفذ الصريح 0 حتى لا يُعامل كمنفذ HTTPS افتراضي.
- Hermes SSE أصبح يسقط حدث approval.responded بالكامل إذا كان request_id أو choice غير صالح؛ لا يسمح بحدث جزئي قد يُفسر كطلب معلق. تم تحديث الاختبارات لتتوافق مع fail-closed behavior.
- مسارات عرض تفاصيل الموافقة وحلها تتحقق من lease ما زال حيًا قبل إظهار command أو إرسال القرار؛ تم إضافة no-store headers لرد تفاصيل الموافقة.
- API tests على commit 06c46b4d نجحت: **427 passed, 2 warnings**. TypeScript typecheck وExpo compatibility نجحا، وكان Web export قيد التنفيذ عند آخر فحص. تغييرات المنفذ 0 واختباره على HEAD a858ea69 تنتظر CI.
- ما زال Browser Use مجرد policy helper بلا egress proxy أو runtime provider، وOpenCode بلا adapter/runtime. لا توجد محركات مفعلة أو migrations مطبقة أو deployment حي.


## تحقق إضافي — اكتمال Platform CI على دفعة موافقات Hermes — 2026-11-20

- Commit 06c46b4d: Platform CI اكتمل بنجاح بالكامل؛ API tests: 427 passed، وClient typecheck + Expo dependency compatibility + Web export نجحت.
- بعد ذلك أضيفت مراجعات SSRF preflight للمتصفح: رفض صيغ IPv4 الرقمية المختصرة/العشرية/hex، ثم رفض محارف Unicode control/format/bidi في URL.
- BrowserNetworkPolicy لا ينفذ طلبات ولا يمثل egress proxy؛ هو preflight فقط، ويظل Browser Use disabled إلى أن يوجد proxy فعلي يفرض DNS/IP pinning على كل redirect وsubresource.
- أحدث commits التي تحمل تغييرات URL الأخيرة لها Platform CI قيد التشغيل عند تحديث هذا السجل؛ لا ننسب نجاح 06c46b4d إلى هذه التغييرات اللاحقة.


## دفعة Browser SSRF preflight — 2026-11-20

- أضفنا `browser_network_policy.py` كسياسة تحقق مسبق مستقلة قبل أي اتصال متصفح مستقبلي.
- تتحقق من allowlist دقيقة للمضيف والمنفذ، وتسمح بالـsubdomains فقط عند تفعيل صريح، وترفض userinfo وURL المشوهة وscheme غير HTTP/HTTPS والمنافذ غير المسموحة.
- تحظر IP literals وlocalhost و.local و.internal، وتستخدم socket.inet_aton لرفض صيغ IPv4 القديمة مثل 127.1 والعنوان الصحيح كعدد صحيح أو hex.
- تحل DNS مسبقًا وترفض الإجابة الفارغة أو غير الصالحة أو أي عنوان غير global؛ وترفض خليط العناوين العامة والخاصة بدل اختيار العام فقط.
- أضفنا اختبارات للـDNS وIPv4/IPv6 وnumeric IPv4 aliases والمنافذ والـallowlist.
- هذا preflight لا يثبت أمان الاتصال الفعلي: يلزم egress proxy يكرر الفحص لكل redirect/subresource ويثبت IP المحلول عند الاتصال لمنع DNS rebinding. لم يتم ربطه بمتصفح حي، وBrowser Use ما زال disabled.
- API tests نجحت على commit a858ea69، وPlatform CI كان ما يزال ينفذ Client typecheck/Web export وقت التحديث. أحدث تحديث توثيقي ينتظر CI على HEAD الجديد.


## نتيجة تحقق لاحقة — 2026-11-20

- بعد إضافة اختبارات صيغ IPv4 القديمة ومحارف Unicode/Bidi والمنفذ صفر، نجح API CI على commit `82671ffd`: **432 passed, 2 warnings**. فحص Client typecheck/export كان ما زال قيد التنفيذ عند آخر قراءة. تحديث التوثيق اللاحق لا يغير كود الاختبارات.


## تحديث اختبار Browser Network Policy — 2026-11-20

- أضيف تحقق صارم لقائمة المضيفين نفسها: أسماء DNS lowercase ASCII canonical فقط، ورفض wildcard/labels غير صالحة/trailing dot/localhost/.local/.internal وعناوين IP المباشرة أو الرقمية القديمة.
- اختبارات URL تشمل صيغ IPv4 المختصرة والعددية وhex، وUnicode control/bidi، بالإضافة إلى DNS الخاص أو المختلط.
- Platform CI على commit 84fc162c: API tests نجحت، 440 passed و2 warnings. فحص TypeScript/Expo/Web export كان ما زال جاريًا وقت التحقق.
- تغييرات التوثيق بعد ذلك على HEAD 782e08a4 لم تُتحقق بعد في Platform CI؛ لا نخلط نجاح 84fc162c بنتيجة HEAD الأحدث.


## تحديث Browser Use ونتائج CI — 2026-11-20

- تم تدقيق سياسة URL قبل تشغيل Browser Use، ثم تشديد canonical DNS allowlist ورفض IP literals وlegacy IPv4 وnumeric-only host forms، مع فحص Unicode controls/bidi والـports وDNS answers الخاصة.
- تمت إضافة اختبارات لعناوين مثل 127.1 وinteger IPv4 وhex IPv4، وoversized numeric/hex، والـzero port، وأسماء DNS غير canonical.
- Platform CI على commit 782e08a4 نجح بالكامل: 440 API tests passed، وTypeScript typecheck، وExpo dependency compatibility، وWeb export جميعها نجحت.
- Repository baseline على commit 782e08a4 نجح أيضًا.
- تعديلات إضافية بعد هذا التحقق على browser_network_policy.py واختباراته (commits b70ea81f وa4b584dc) قيد CI؛ لا ننسب إليها نتيجة 440 حتى يكتمل CI على أحدث HEAD.
- Browser Use لا يزال disabled؛ لا يوجد browser process أو MCP server أو egress proxy فعلي، ولا يُعد preflight وحده حماية SSRF كاملة.

## دفعة OpenCode protocol contract — 2026-11-20

- أضفت opencode_contract.py كطبقة pure لتضييق بروتوكول OpenCode قبل بناء أي اتصال فعلي.
- جلسة OpenCode المستقبلية تبدأ بقاعدة صلاحيات عامة ask لكل action/resource.
- طلبات الصلاحية ترتبط بمعرف الجلسة المحدد، وتُختزل إلى request ID + action + resources فقط؛ لا يتم تمرير message أو metadata أو save rules أو source payload.
- الردود المسموحة مرة واحدة فقط أو رفض؛ لا يوجد مسار لـalways.
- أحداث OpenCode تُختزل إلى lifecycle وpermission metadata المسموحة فقط، مع رفض session mismatch، وعدم تمرير reasoning أو text deltas أو tool input/output.
- أضيفت اختبارات حدود البروتوكول، بما فيها malformed/unhashable decisions وtimestamps الكبيرة.
- لا يوجد OpenCode HTTP client أو runtime provisioner أو session persistence حتى الآن؛ المحرك يظل disabled.

## نتيجة اختبارات OpenCode contract وBrowser URL — 2026-11-20

- أحدث Platform CI على commit 61c194f8: **456 API tests passed**، وPython compile نجح.
- Client TypeScript typecheck نجح، وExpo dependency compatibility نجح؛ Web export كان لا يزال قيد التنفيذ وقت تسجيل هذا التحديث.
- Repository baseline على commit 61c194f8 نجح.
- لا ننسب اكتمال Platform CI حتى يكتمل Web export.

- تحديث نهائي: Platform CI على commit 61c194f8 اكتمل بنجاح؛ 456 API tests passed، TypeScript typecheck، Expo compatibility، وWeb export كلها نجحت. Repository baseline نجح أيضًا. هذه النتيجة تخص commit 61c194f8، بينما commits التوثيق اللاحقة لم تغير كود التطبيق.


## تحقق أمني وCI — 2026-11-20 (OpenCode permission metadata)

- تم تشديد `opencode_contract.py`: أسماء الإجراءات تقبل ASCII محددًا فقط، وتُرفض محارف Unicode من فئات control/format/surrogate في أسماء الموارد، بما فيها محارف اتجاه النص المخفية.
- أضيفت اختبارات ترفض محارف bidi والمسافات غير المسموحة في action، وترفض bidi في resource.
- Platform CI على commit `db9e5ba6109f073f81f93694fff86b9d2c81bef8` اكتمل بنجاح: 456 اختبار API، وPython compile، وTypeScript typecheck، وExpo dependency compatibility، وWeb export.
- Repository baseline checks على نفس commit نجحت.
- ظهرت محاولات CI سابقة فاشلة على commits وسيطة أثناء تعديل نص الاختبارات؛ تم تصحيح الاختبارات، والمرجع النهائي المعتمد هنا هو نجاح CI على db9e5ba.
- التحذيران في API tests ما زالا متعلقين بواجهات Starlette deprecated، ولا يمثلان فشلًا. يلزم تنظيفهما في دفعة مستقلة مع الحفاظ على توافق الإصدارات.
- هذا التعديل لا يضيف OpenCode runtime ولا يفعّله؛ يظل المحرك disabled حتى اكتمال provisioner والعزل واختبارات الاتصال الفعلية.


## جلسة استكمال — 2026-11-21 (Rate limits + CI repairs + worker safety)

### مراجعة البداية
- HEAD الذي بدأنا منه: `8f53808a9c98955455da19cb39dc40f44091d306`.
- Repository baseline كان ناجحًا، لكن Platform CI وOpenCode runtime verification كانا يفشلان.
- فحصنا logs الفشل بدل تكرار تطوير جديد: ظهرت syntax corruption في rate limiter، اختبارين في RuntimeBroker لم يواكبا callback جديدًا، وfixture SSE/streaming كانت تحتوي escaping غير صالح/واجهة FakeClient قديمة.

### ما تم تعديله
- استعدنا `services/api/app/core/ratelimit.py` كتطبيق TokenBucket صحيح: حدود capacity/refill/time، حساب انتظار، pruning فعلي، وقفل آمن مع fail-closed key cap.
- صححنا tests القديمة التي كانت تتوقع السماح بعد استنفاد burst، وصححنا concurrency test ليستهلك السعة كاملة، وأضفنا حالات key-cap pruning، policies غير الصالحة، والساعة التي ترجع للخلف.
- ربطنا `services/api/app/routers/chat.py` بمحددات المعدل الفعلية على POST chat respond / conversation creation / message creation؛ قبل ذلك كانت dependency موجودة لكن غير مستخدمة في router.
- أضفنا اختبارات تثبت أن POST الكتابة في نطاق conversations/messages تُرفض بـ429 عند استنفاد حد المستخدم، مع scope isolation.
- أصلحنا `SlidingWindowLimiter` لحدود عدد principal keys، pruning للـidle keys، fail-closed عند امتلاء السعة، وتهيئة limit جديدة دون مسح أحداث النافذة. أضفنا tests لهذه الحدود.
- حدّثنا fixtures لـRuntimeBroker لتقبل `on_session_created` وتتحقق من تمرير callback، وأصلحنا SSE test bytes string، وأضفنا fake streamed JSON response إلى اختبار provisioner الذي كان يستخدم واجهة HTTP قديمة.
- أوقفنا schedule الـFree Test Worker كل 5 دقائق؛ أصبح workflow يدويًا فقط مع boolean opt-in default=false. لم يتم تشغيل worker ولا معالجة مهام حية.

### التحقق
- Platform CI #1005 على commit `38fdd4025b9c483bfbf97825d526b7811134d9d`: **601 API tests passed, 5 warnings**؛ TypeScript typecheck، Expo dependency compatibility، Web export: نجاح كامل.
- Repository baseline #1023 على نفس commit: نجاح.
- Platform CI #1003 على `d901c6f407eb45deddc244376c93f6ac41b61de6`: نجاح كامل.
- OpenCode runtime primitive tests على verification run #166 (commit `d901c6f4`): نجاح. Upstream provenance check وBun install وserver typecheck نجحت؛ Docker build + smoke-test كانا قيد التنفيذ عند آخر فحص.
- Repository baseline #1024 على commit `e0d9741d` (worker workflow safety change): نجاح. Platform CI #1006 قيد التنفيذ.
- لا يوجد live deployment، لا migrations مطبقة، لا API/worker/engine مفعّل، ولا provider/model configuration.

### القدرات بعد هذه الجلسة
- Rate limit scopes الثلاثة لكتابة المحادثات أصبحت enforced في API dependency؛ الواجهة تبقى 429 عند الاستنفاد.
- الـlimiters المحلية ترفض fail-closed عند key capacity بدل السماح بتوسع memory غير محدود.
- Free worker لا يعمل تلقائيًا؛ يحتاج manual workflow dispatch وتفعيل opt-in صريح.

### ما لم يكتمل / التالي
- انتظر Platform CI #1006 على HEAD `e0d9741d`، واستكمل OpenCode upstream Docker build/smoke run #166 إن انتهى.
- Rate limiting لا يزال per-process وليس distributed، ولا توجد ingress-level IP/global throttling.
- متابعة worker/RLS/engine idempotency وruntime recovery/teardown، egress isolation، disposable DB integration tests، privacy/scale/production packaging.
- تقدير المشروع لا يتغير من checkpoint السابق: **~20% من Controlled Beta readiness (مؤقت)**؛ هذا تقدير milestone-weighted محافظ، وليس نسبة من عدد الملفات. هذه الدفعة تقوي API safety/tests، ولا تغلق staging/runtime/production milestones.


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


## جلسة متابعة — 2026-11-21 (OpenCode upstream smoke verified + explicit disable switch)

- بدأنا من main HEAD `5b48f1315ec66ef2df2e9b68c681ee04db56ce2c` بعد مراجعة roadmap، development log، ملفات OpenCode/runtime، وGitHub Actions.
- تحققت نتائج CI المرتبطة بـOpenCode verification #1014 (run ID `44879150324`) على commit `5aa8266b2fc5a375be60b63b4a3e8a5811e58d15`: job isolated runtime primitives وjob pinned upstream/server workspace كلاهما **success**. في job upstream نجح provenance verification، bridge/protocol tests، Bun frozen install، upstream server typecheck، Docker build، وauthenticated `GET /api/info` smoke test داخل CI. هذه الاختبارات لم تنشئ runtime لخدمة حقيقية ولا تفعّل المحرك في SULY.
- اكتشفنا أن runtime broker كان يتفعّل تلقائيًا إذا توفرت إعدادات provisioner الثلاثة. أضفنا إعداد `OPENCODE_ENABLED=false` افتراضيًا، وجعلنا startup يضبط broker/provider على `None` ويخرج مبكرًا عندما flag غير فعال؛ وجود credentials/URL لا يكفي وحده.
- أضفنا test `services/api/tests/test_opencode_runtime_config.py` للتحقق أن الإعدادات المكتملة لا تفعّل broker عند flag=false.
- هذا تعديل دفاعي: لا يضيف تشغيل prompts أو workers أو user-facing engine start route، ولا يجعل OpenCode متاحًا. التطبيق ما زال يحتاج wiring آمن لمهام المستخدم، runtime provider durable، integration/staging tests، review approvals وworkspace apply.
- لا يمكننا الادعاء أن الاختبار الجديد نفذ محليًا في هذه الجلسة؛ ينتظر CI بعد commit.
- التقدير لم يتغير: اكتمال OpenCode **بنية/كود تجريبي فقط وليس end-user engine**. لا تشغيل live أو deploy أو migration.


## جلسة تنفيذ — 2026-11-21 (Worker-to-OpenCode wiring)

- راجعنا main وملفات task worker/tool registry، planner validation، OpenCode task executor، session/lifecycle stores، runtime provisioner، migrations، وCI قبل التعديل.
- أضفنا operation allow-listed باسم `opencode.task.run` إلى Worker Tool Registry. المدخلات المقبولة محددة فقط: `project_id`, `prompt`, `title`; يحتاج grant صريح `engine.opencode.run`؛ يدعم cancel-aware handler؛ ولا يستطيع task input منح صلاحية لنفسه.
- أضفنا handler worker ينشئ EngineRun عبر lease-protected RPC، يتحقق من project UUID والـprompt، يبني Workspace/Sessions/Lifecycle stores server-side، ويستدعي OpenCode Task Executor. لا يخرج للـtask checkpoint إلا summary محدود (run/session/change-set IDs/status/count) ولا يرجع محتوى الملفات أو tokens في worker output.
- أضفنا إعداد opt-in لبناء HTTPS Runtime Provider/Broker داخل worker process فقط عند `SULY_WORKER_ENABLED=true` و`OPENCODE_ENABLED=true` مع اكتمال URL/token/origin allowlist. لا توجد مفاتيح أو credentials committed، وما زالت القيم الافتراضية false. API process وworker process لا يشغلان runtime افتراضيًا.
- أضفنا API `POST /v1/tasks/{task_id}/opencode-plan` لإنشاء خطوة واحدة فقط لمهمة مملوكة للمستخدم ومربوطة بمشروع؛ لا يفعّل تشغيلًا أو يطبق migrations. يستخدم `plan_task` RPC الحالي ويستند إلى task.request.
- أضفنا Cancel Event monitor في OpenCode executor: عند فقد worker lease أو إلغاء التعاون، يتم طلب release للـruntime attempt حتى لا يستمر تشغيل طويل خارج ملكية lease؛ guard يمنع اعتبار نتيجة متأخرة مكتملة عند cancel event.
- حدّثنا tool approval catalog ليعرض OpenCode availability فقط عندما worker والمحرك وruntime provisioning config opt-in مكتمل. أضفنا/عدّلنا اختبارات planner, worker disabled gate, endpoint owner/project checks, tool catalog, registry, وcancel cleanup.
- CI: Platform CI #1036 على commit `9ea8b25c` **success** (API tests + Client Typecheck/Web Export). أحدث CI #1037 على commit `bee29171` ما زال قيد التنفيذ وقت هذا التحديث؛ Repository baseline #1055 قيد التنفيذ؛ OpenCode upstream verification #176 pending. commits `bee29171` لا تزال تنتظر CI.
- هذه wiring ليست تفعيل live execution: لا Worker بدأ، لا Runtime provisioner اتصل، لا Hermes/OpenCode agent live، لا DB migrations/deploy. الإطلاق الحقيقي يحتاج isolated staging، تطبيق migrations يدويًا بعد موافقة، ومراجعة عملية runtime release/interrupt وworker cancellation/recovery.
- **المرحلة الحالية:** الكود أصبح يربط task plan -> worker operation -> OpenCode executor -> runtime lease -> lifecycle/session -> reviewable change set. باقي إغلاق الاعتمادية/المراجعة/التطبيق على Staging وواجهة العميل End-to-End والتحقق من نتائج CI الأخيرة، وليس فقط إنشاء wiring.


## جلسة متابعة — 2026-11-21 (UI task submission, event timeline and review/apply)

- ربطنا واجهة الوكيل بوضع OpenCode: اختيار engine، موافقة `engine.opencode.run`، يتحقق من project context قبل إنشاء task، ويستخدم endpoint `opencode-plan` الخاص.
- Task detail يعرض change-set المقدم، preview لكل ملف diff (بحد 8KB للعرض لكل ملف)، ويتيح رفض أو تطبيق التغييرات عبر endpoint owner-protected مع CAS workspace revision.
- أضفنا عرض الأحداث sanitized الخاصة بـOpenCode من `opencode_task_events` وتحديثها كل 2.5 ثانية أثناء المهمة، باستخدام run ID محفوظ في output step.
- أضفنا اختبار handler happy-path لربط engine run، OpenCode executor، summary output، وfinish RPC، واختبار cancel event لإثبات محاولة release runtime. تم اختبارها في Platform CI.
- **CI verified على main HEAD `b6f896dff319ad184eb36c020cb567e7b81b2aa1`: Platform CI #1049 نجح — API tests **608 passed, 5 warnings**، Client typecheck + Expo compatibility + Web export نجح. Repository baseline #1067 نجح. `OPENCODE_ENABLED` و`WORKER_ENABLED` افتراضيًا false.
- OpenCode upstream verification #177: runtime primitive tests نجحت؛ bridge/protocol tests وupstream provenance وBun frozen install وserver typecheck نجحت؛ Docker image build وsmoke test ما زالا قيد التنفيذ وقت هذا التوثيق. Verification #1014 السابقة مكتملة بنجاح، لكن #177 أحدث run يحتاج إغلاق.
- لا Live runtime، لا worker، لا migration/deploy. لم يتم اختبار integration end-to-end مع provisioner أو قاعدة Staging؛ هذا يظل شرطًا مهمًا قبل إعلان التكامل closed.


## إغلاق تكامل OpenCode على مستوى الكود — 2026-11-21

- آخر code checkpoint: `7399ec775d25aa523ed0ba3a19d697d221e21e88` (موجود على main). أُضيف دليل تدفق التشغيل `docs/operations/OPENCODE_TASK_FLOW_AR.md` بعده.
- **تم إغلاق مسار التكامل البرمجي الأساسي:** task linked to project -> `opencode-plan` -> allow-listed worker operation -> explicit approval -> engine-run ledger -> OpenCode executor/runtime lease -> lifecycle events -> result/change set -> task UI diff review -> CAS apply/reject.
- UI يدعم وضع OpenCode داخل مشروع، readiness/config gate، موافقة `engine.opencode.run`، event timeline، مراجعة diff مع توسيع full diff، وتطبيق/رفض المجموعة.
- **Platform CI #1059 على commit `7399ec77`: success.** API compilation/tests **609 passed, 5 warnings**؛ TypeScript typecheck، Expo dependency compatibility، وWeb export جميعها success. Repository baseline #1077 على commit ذاته success.
- **OpenCode upstream verification #177: success.** isolated runtime primitives + bridge/protocol/provenance + frozen upstream install + upstream server typecheck + Docker build + authenticated server smoke test نجحوا. هذا run على commit `1a84d30d`؛ engine/upstream files لم تتغير بعدها.
- كان هناك CI failures خلال تطوير UI/endpoint، وتم إصلاحها؛ checkpoint #1059 و#1077 أعطيا نتائج green. لا نُخفي المحاولات الفاشلة السابقة، لكنها لا تمثل HEAD بعد الإصلاح.
- **إغلاق نطاق الكود الأساسي: مكتمل.** لا يزال Staging/Live integration غير مختبر: worker وOpenCode افتراضيًا disabled؛ لا اتصال حقيقي بالProvisioner، لا migrations/deploy، لا live runtime. كذلك usage/credits metering للمهام البرمجية غير موجود حتى الآن ويجب أن يسبق أي تشغيل مدفوع/مفتوح.
- لا نعتبر ذلك إطلاق Beta أو Production. القرار المتبقي: Staging provisioning/migrations وcredits model ومراجعة egress/limits/cancel/teardown/recovery وAndroid/Web acceptance بعد موافقة صريحة.


## جلسة إصلاح CI وتشديد إعداد Hermes — 2026-11-21

### مراجعة البداية
- تمت مراجعة main من جديد قبل التعديل؛ HEAD عند بدء الجلسة: f3afbd9d098ed4ff7c80b1cd8141660c25c6930b.
- تمت مراجعة AGENTS.md والـroadmap وسجل التطوير وملفات Worker/Hermes/OpenCode/Runtime Provisioner وآخر 12 commit وGitHub Actions.
- Repository baseline checks run 44925526767 على HEAD السابق اكتمل بنجاح.
- Platform CI run 44925526678 فشل في Compile API بسبب IndentationError في worker_runtime.py:356؛ واجهة العميل اجتازت TypeScript وExpo compatibility وWeb export.
- OpenCode upstream verification run 44925526728 كشف ثلاثة أسباب مستقلة:
  1. اختبار runtime provisioner توقع platform_toolsets.api_server فارغًا، لكن إعداد Hermes كان يفعّل terminal وfile، خلافًا لتعليق الكود ودليل التشغيل. هذا انحراف أمني فعلي وليس اختبارًا يجب تجاوزه.
  2. ستة اختبارات OpenCode executor استخدمت fake Broker لا يطبق release_attempt الموجود بالفعل في عقد TaskScopedRuntimeBroker.
  3. فشل الاختبارات منع خطوات بناء/تشغيل OpenCode upstream اللاحقة في ذلك run؛ لا تُعد هذه الخطوات ناجحة.

### التغييرات المنفذة
- حُذف تعريف الدالة المكرر والفارغ _hermes_project_workspace_files في services/api/app/worker_runtime.py، مع الإبقاء على تنفيذها الأصلي مرة واحدة.
- أُعيد إعداد Hermes task profile إلى platform_toolsets.api_server: [] في services/runtime-provisioner/app/docker_runtime.py. بذلك يتطابق التنفيذ مع default-deny المقصود ومع README واختبار runtime الموجودين؛ لم نخفّض الاختبار أو نسمح بأدوات terminal/file.
- استُكمل fake Broker في services/api/tests/test_opencode_task_executor.py بعقد release_attempt، وأضيف assertion يثبت طلب تحرير runtime بعد حفظ change set القابلة للمراجعة.
- لم يتم تعديل أي ملف upstream أو تغيير revision أو ترخيص.

### Commits
- 352800efe8400ae07d4373b41ec6406b5a173603 — إصلاح syntax في Worker واستكمال عقد release في OpenCode test double.
- fcea64cce7ff1c140542ca716686c14ed01dcf8a — تعطيل platform toolsets في Hermes runtime profile افتراضيًا.

### الاختبارات وCI
- لا يوجد ادعاء بتشغيل pytest محليًا؛ التعديل تم عبر GitHub، والتحقق التنفيذي المطلوب هو CI.
- نتائج CI المذكورة أعلاه تخص HEAD السابق قبل الإصلاح.
- نتائج CI الخاصة بالـcommits الجديدة لم تُؤكد بعد عند كتابة هذا السجل؛ يجب فحص Platform CI وRuntime Provisioner/OpenCode verification وRepository baseline على أحدث HEAD، وعدم اعتبار أي run queued أو skipped نجاحًا.
- اختبار runtime الموجود بالفعل يثبت أن api_server فارغ؛ واختبارات OpenCode الآن تستخدم واجهة release المطابقة للعقد الحقيقي.

### القدرات الحالية وحدودها
- Core API وtask planning/worker contracts وowner-scoped project/task data وengine-run lifecycle موجودة في الكود، مع migrations ملتزمة بالمستودع فقط.
- تكامل OpenCode البرمجي الأساسي وواجهة task/review/apply موجودان؛ لا يعني ذلك تشغيل محرك فعلي للمستخدم.
- Hermes adapter وcatalog/skills/memory/session/tool-approval wiring موجودة جزئيًا في مسار SULY؛ لكن runtime لا يزال غير مفعّل، وأدوات upstream platform مغلقة افتراضيًا.
- Runtime Provisioner يحتوي على قيود container/network/body/identity، لكن لا توجد حتى الآن بوابة egress task-aware مثبتة أو تحقق عزل على Docker host/Staging حقيقي.
- Worker وHermes وOpenCode وموفرو النماذج تظل disabled افتراضيًا.

### المرحلة والقرارات المؤجلة
- المرحلة A: أساس control plane مكتوب؛ مراجعة/تطبيق migrations واختبارات Postgres/Supabase disposable ما زالت مطلوبة.
- المرحلة B: مسارات lifecycle/reconciliation مكتوبة جزئيًا؛ إثبات lease races وrecovery وexternal teardown على Staging غير مكتمل.
- المرحلة C: Hermes adapter متصل بالكود؛ العزل والتشغيل الآمن والـegress واختبار model/runtime غير مكتملة.
- المرحلة D: OpenCode code path موجود؛ التكامل الحي مع provisioner وcredits metering والقبول الفعلي على Android/Web لم تُثبت.
- المرحلتان E/F (reliability/scale/production package) ما زالتا مفتوحتين.
- لا migrations على قاعدة الإنتاج أو Staging، لا deploy، لا workers/agents/runtimes حية، لا خدمات مدفوعة، ولا secrets جديدة.
- قرار مؤجل: بناء egress proxy task-aware مع DNS pinning وredirect enforcement وhost firewall attestation؛ إبقاء الشبكة الداخلية بلا egress هو الخيار الآمن حاليًا.
- قرار مؤجل: تصميم usage/credits ledger وpartial billing/idempotency قبل أي تفعيل لمحركات قد تستهلك موارد أو تكلفة.

### تقدير التقدم
- لقطة roadmap عند بداية الجلسة: 51/120 بند checklist مكتملًا (نحو 43% من عناصر القائمة). هذه نسبة عدّ checkbox فقط، وليست نسبة جاهزية المنتج؛ البنود غير متساوية في الوزن وبعض المكتمل منها كود دون إثبات تشغيل.
- يظل تقدير Controlled Beta/Production Readiness المحافظ نحو 20% وفق المنهج milestone-weighted الموثق في هذا الملف؛ لا نرفعه قبل إغلاق Staging وDB وruntime/security وcredits وdeployment gates.
- لا يغيّر إصلاح CI وحده تقدير الجاهزية.

### نقطة متابعة الجلسة القادمة
1. افحص أحدث main HEAD وكل CI runs المرتبطة به؛ تأكد من نجاح compile وAPI tests وprovisioner tests وOpenCode upstream build/smoke وclient web export.
2. أصلح أي regression جديد بأصغر تغيير آمن، ثم حدّث هذا السجل بنتائج CI الفعلية.
3. بعد CI أخضر، ابدأ تصميم/اختبارات usage وcredits للمهام، مع منع أي تشغيل عند غياب grant/رصيد صالح، دون تشغيل worker أو engine حي.


## جلسة متابعة — 2026-11-21 (إغلاق ثغرة NULL في idempotency لدفتر الرصيد)

### مراجعة البداية
- تم جلب مرجع `main` مباشرة قبل التعديل؛ HEAD عند البداية: `3837c066878036283a96e394a02c0091370d1a0c`، وتأكدنا أن مرجع الفرع يشير إلى commit نفسه.
- راجعنا `AGENTS.md`، والـroadmap، وسجل التطوير، ودليل دفتر الرصيد، وملفات migration/adapter/tests، وآخر commits وحالة Actions.
- لقطة roadmap الحالية: **51/120** بند checklist مكتمل (43%)؛ هذه نسبة عدّ عناصر وليست نسبة جاهزية المنتج.
- على HEAD السابق: Platform CI run `44930108723` نجح، وRepository baseline run `44930108558` نجح. Engine runtime image build run `44930107052` فشل؛ واجهة GitHub أعادت صفر jobs ولم توفر logs عبر الاتصال الحالي، لذلك لم ننسب سببًا تخمينيًا للفشل. كما أظهر combined status فشل check خارجي باسم `strong-gentleness - suly-api`؛ لم نبدأ deploy أو نتصل ببنية Railway.

### المشكلة والإصلاح
- أثناء مراجعة `release_engine_credits` وجدنا أن فحص إعادة استخدام idempotency key كان يقارن `metadata ->> 'reason'` باستخدام `<>`.
- إذا كانت قيمة `reason` في سجل قديم مفقودة، تعيد المقارنة SQL قيمة `NULL`، وشرط `IF` لا يدخل فرع التعارض؛ بذلك يمكن قبول إعادة طلب غير مطابقة بدل رفضها.
- استبدلنا المقارنة بـ`IS DISTINCT FROM`، لتتعامل مع `NULL` كاختلاف صريح، وبذلك تتسق مع فحوص grant وsettle التي شُددت في commit السابق.
- أضفنا اختبار migration static يمنع عودة مقارنات metadata غير الآمنة، وحدّثنا دليل الرصيد بشرح السلوك.

### الملفات
- `supabase/migrations/20261121250000_credit_ledger_foundation.sql`
- `services/api/tests/test_sql_migration_static.py`
- `docs/operations/ENGINE_CREDITS_LEDGER_AR.md`
- `docs/progress/DEVELOPMENT_PROGRESS_AR.md`
- `docs/operations/SULY_PRODUCTION_READINESS_ROADMAP_AR.md`

### التحقق والحدود
- لم نشغّل pytest محليًا في هذه الجلسة؛ لا ندّعي نتيجة اختبار محلي.
- نجاح Platform CI وRepository baseline المذكور أعلاه يخص HEAD السابق فقط. يجب فحص runs الجديدة الناتجة عن هذا commit قبل اعتماد الإصلاح.
- فشل Engine runtime build السابق لم يُشخّص؛ سبب الفشل غير متاح من jobs/logs في الاتصال الحالي.
- لم تُطبق أي migration على Supabase، ولم يتم نشر أو تشغيل worker أو agent أو Hermes أو OpenCode أو أي provider، ولم تُفعّل خدمة مدفوعة أو secret.

### الحالة والقرار المؤجل
- دفتر الرصيد أصبح يملك أساسًا خادميًا موحدًا للمنح والحجز والتسوية والتحرير وانتهاء الحجز، مع RLS وRPC مقيدة؛ لكنه **غير مربوط بعد** بمسارات تشغيل OpenCode/Hermes، ولا توجد سياسة أسعار أو تحويل usage إلى credits أو واجهة رصيد.
- تبقى المراحل A/B/C/D غير مثبتة على Staging، وتبقى E/F (التكلفة والاعتمادية والتوسع والتغليف والنشر) مفتوحة. لا نرفع تقدير Controlled Beta/Production Readiness عن **نحو 20%**؛ النسبة milestone-weighted محافظة، بينما 51/120 هي نسبة checkbox منفصلة.
- لا نعتبر هذه الدفعة إغلاقًا للفوترة أو جاهزية لتفعيل أي محرك.

### نقطة متابعة الجلسة القادمة
1. افحص Platform CI وRepository baseline وEngine runtime build على HEAD الجديد؛ شخّص فشل image-build فقط من logs فعلية، ولا تخمّن السبب.
2. وسّع اختبارات دفتر الرصيد، ثم أضف اختبار PostgreSQL disposable للتنافسية وNULL/idempotency إن كانت بيئة CI المتاحة تسمح، دون الاتصال بقاعدة المستخدم.
3. بعد ذلك صمّم ربط reserve/settle/release بمسار المحرك مع cost policy خادمية صريحة؛ لا تخترع أسعارًا ولا تفعّل worker/engine قبل اعتماد سياسة التكلفة واكتمال اختبارات العزل.


### نتائج CI بعد commit `1387b8960cd48056ea236485c749bab9d9712cb4`
- **Platform CI #1374 / run `44933680235`: نجاح كامل.** API compile نجح، واكتملت اختبارات API بنتيجة **757 passed, 5 warnings**. Client TypeScript typecheck وExpo dependency compatibility وWeb export نجحت أيضًا.
- **Repository baseline #1392 / run `44933680367`: نجاح.** فحوص وثائق المشروع ورفض ملفات البيئة والمفاتيح الخاصة tracked نجحت.
- **Engine runtime image build #44 / run `44933678909`: فشل.** GitHub Actions API أعاد `total_count=0` للـjobs، ولم تتوفر logs؛ لذلك لا يمكن تحديد هل الفشل في checkout أو build أو runner، ولا نعتبر بناء صور Hermes/OpenCode أو provisioner ناجحًا.
- Combined commit status أظهر check خارجيًا `strong-gentleness - suly-api` بحالة failure. لم ننفذ deploy ولم نتصل بخدمة Railway؛ هذا status خارجي لا يغيّر نتيجة Platform CI.
- نتيجة التحقق تخص commit `1387b8960cd48056ea236485c749bab9d9712cb4` تحديدًا. لا يوجد pytest محلي؛ إثبات الاختبارات هو run CI المذكور.


## جلسة تطوير — 2026-11-22 (Credits API وواجهة القراءة)

- بداية الجلسة: `69c129140ec0881a95b119499e11d6fbc493aee6`; بعد مراجعة roadmap/status/commits/CI تم العمل مباشرة على `main`.
- Commits:
  - `2467140c8bf16aebb6d0d15cedd5b6370be75779` — API summary, tests, config gate, router registration, .env example.
  - `129efc636c10141ef086ce2aaabdfe1a7b27ed19` — gate credit feature before client creation, test that the user JWT is passed to the scoped DB client.
  - `eee5d8a497fe540091ca9fda3221c92be4cc00be` — Expo read-only credits page and Settings navigation.
- API projection is bounded (25 reservations / 50 ledger entries), owner-filtered, RLS-backed via user token, and excludes task IDs and free-form metadata. No writes or engine activation.
- Client route `/credits` displays available/reserved balances, recent reservations, ledger deltas, refresh, loading/error/empty states, and a login entry. It is explicitly informational; purchases and execution are absent.
- 7 API tests added. Local pytest was not run. Platform CI #1377/run `44999376502` and #1378/run `44999424273` passed: **764 API tests passed, 5 warnings**; API compile, client typecheck, Expo compatibility, and Web export passed. Repository baseline #1395/run `44999376560` and #1396/run `44999424191` passed. Engine runtime image builds #217–#219 failed with empty job responses; cause is unknown. Upstream verification #316 was pending on an earlier commit.
- No migration applied, no deploy, no worker/runtime/provider enabled, no payments or new secret.
- Roadmap recount after CI confirmation: **59/154 (38%)**. Controlled Beta/Production readiness remains **~20%** pending integration and staging evidence.

### Follow-up
- Verify CI #1377/#1378; amend this checkpoint with the actual results in a later commit.
- Continue with disposable PostgreSQL ledger integration tests or the next safe engine/credits vertical slice, without live DB access.


### تحديث نتائج CI — 2026-11-22

- Platform CI #1377 `44999376502` و#1378 `44999424273` green؛ logs الاختبارات تؤكد **764 passed, 5 warnings** في كل run. compile/typecheck/Expo/Web export كلها ناجحة.
- Repository baseline #1395 `44999376560` و#1396 `44999424191` green.
- أحدث documentation commit `dad1bbb8afc8` ينتظر Platform CI #1379 وRepository baseline #1397.
- Engine runtime image builds #217–#219 failed، لكن jobs returned empty؛ لا diagnostic logs متاحة.
- CI لا يختبر RLS في Supabase الحقيقي، ولا migration apply، ولا provider أو engine runtime.


## جلسة تطوير — 2026-11-22 (اختبارات PostgreSQL لدفتر الرصيد)

- بداية slice: HEAD `58ef243786e8`; تم تطوير الاختبارات مباشرة على main، ثم تحديث RLS coverage.
- Commits:
  - `3a132086c39b` — workflow وdependency وPostgreSQL disposable tests.
  - `373f7a0e26b9` — إصلاح fixture تكرار المستخدم وتغلق اتصالات concurrency.
  - `5a51b10a1c07` — توسيع RLS tests إلى accounts/reservations/ledger وإثبات أن API query projection لا يتضمن metadata/task IDs.
- PostgreSQL 16 integration run #3 `44999917678` على commit d5a7: **5 passed**؛ run #4 `45000017619` على commit 5a51: **5 passed**.
- اختبارات حقيقية على disposable DB شملت grant/reserve/settle/release/expiry، idempotency/conflicts، insufficient balance، cross-user task/run، concurrent reservations لمنع overdraw، RLS owner-read للثلاث جداول، ورفض direct writes وgrant RPC للمستخدم authenticated.
- Platform CI #1385 `45000017691`: **764 passed, 5 skipped, 5 warnings**؛ API compile، TypeScript، Expo compatibility، Web export نجحت. الخمس skipped هي DB integration tests دون DSN في Platform CI؛ workflow منفصل شغلها. Repository baseline #1403 `45000017591` نجح.
- أول run #1/#2 فشل بسبب fixtures: engine_id غير مطابق في reserve، ومستخدم RLS غير موجود في auth.users. logs أظهرت السبب، وتم إصلاحه في d5a7 ثم تحقق green.
- لم نستخدم Supabase الحقيقي، ولم نطبق migration على production/staging. CI فقط أنشأ PostgreSQL disposable. لا workers/engines/providers/paid services.
- Checklist الحالية: **60/155 (39%)**؛ تقدير controlled-beta readiness ما يزال **~20%** لأن credits لم تُربط بالengine lifecycle ولا توجد policy أسعار أو usage metering.

### متابعة
1. افحص CI على أحدث commit documentation.
2. لا تربط reserve/settle بالworker قبل تصميم policy usage واضحة؛ لا تختر أسعارًا أو token-to-credit conversion.
3. تابع vertical slice مستقل وآمن (usage telemetry، أو مراجعة orchestration) مع الاختبارات.


## جلسة تطوير — 2026-11-22 (قياس tokens للchat دون فوترة)

- Commits:
  - `5e41f6753be9` — AI Gateway optional usage callback; chat stores provider counts in assistant metadata; client displays usage.
  - `d033fd274bfc` — إصلاح markup/null-safe metadata بعد اكتشاف typecheck failure.
  - `075a90ab1b2d` — توضيح Arabic usage display وإظهار الإجمالي.
- Counts normalized only from provider-reported usage: OpenAI-compatible `prompt_tokens/completion_tokens`, Ollama `prompt_eval_count/eval_count`. Counts bounded to 0–1e9 and rejected when malformed; total computed from validated input/output. No estimation/cost mapping.
- API test additions: standard usage, Ollama usage, 4 malformed usage variants, and chat persistence metadata. CI API job on commit d033 #1388 passed **770 tests, 5 warnings**; client typecheck was still in progress at this checkpoint. Platform CI #1387 failed due JSX syntax, which was corrected; #1389 for the latest UI commit still pending.
- No live provider call, no key, no billing, no credits charge. 
- Roadmap checklist: **60/156 (39%)**; controlled-beta readiness stays **~20%** until engine lifecycle usage metering and staging readiness.

### Follow-up
1. Confirm client typecheck and web export for d033/075.
2. Document this telemetry behavior in provider setup.
3. Continue with engine usage source normalization or other next safe vertical slice; do not invent prices or credits conversion.


### تحقق token telemetry — 2026-11-22

- Platform CI #1388 `45000436704` و#1389 `45000469647` green: **770 passed, 5 skipped, 5 warnings**؛ client typecheck/Expo compatibility/Web export green.
- #1387 failed بسبب malformed JSX؛ إصلاح d033 confirmed by #1388/#1389. لا نخفي failure.
- Repository baseline #1406 `45000436695` و#1407 `45000469682` و#1408 `45000536405` و#1409 `45000583353` و#1410 `45000601971` green. Platform CI #1390 `45000536420` و#1391 `45000583307` و#1392 `45000602027` green.
- Current checklist: **61/156 (39%)**؛ controlled beta readiness still **~20%**. No provider live or billing.


### توثيق CI على HEAD — 2026-11-22

- Platform CI #1390/#1391/#1392 success، بما في ذلك #1392 على docs HEAD `144dedf820a2`.
- Repository baseline #1408/#1409/#1410 success.
- Credits PostgreSQL disposable workflow #4: 5 passed.
- Engine runtime build #232 failed with no jobs/logs; السبب غير معلوم.

## جلسة تطوير — 2026-11-22 (خصوصية تخزين Runtime Provisioner)

- نقطة البداية: `main` HEAD `2bd642a4fb88444b1dc7ae22e9dab0fc877b34fd`. تمت مراجعة حالة CI والـroadmap وملفات Runtime Provisioner واختباراته قبل التعديل. لم يتم دمج أو نسخ أي تغيير من Pull Requests غير المدمجة.
- اكتُشف أن Dockerfile ينشئ `/var/lib/suly-runtime` بوضع افتراضي قد يكون `0755`، وأن SQLite كان يفتح قاعدة leases دون فحص صلاحيات الملف أو رفض symlink؛ قاعدة البيانات تحتوي معرفات المهام وتشغيل المحركات وبصمات رموز runtime.
- أضيف تحقق fail-closed لمسار SQLite: المسار مطلق، مجلد الأب مملوك لمستخدم الخدمة وبوضع `0700`، والملف regular/singly-linked ومملوك للخدمة وبوضع `0600`. إنشاء الملف يتم ذريًا مع `O_EXCL` و`O_NOFOLLOW` عند توفره.
- فُرضت شروط الخصوصية نفسها على workspace root، وضُبطت مجلدات الصورة الافتراضية إلى `0700`. أضيفت اختبارات للمجلدات والملفات permissive، symlink/hard-link، المسار النسبي، وصلاحيات الإنشاء.
- لم يتم تشغيل pytest محليًا لأن المستودع غير متاح كـworking tree في هذه الجلسة؛ اختبارات Runtime Provisioner CI مطلوبة على commit هذه الدفعة. لا يثبت fake Docker اختبارًا حيًا.
- لم تُطبق migrations، ولم يُشغّل Docker أو Worker أو Engine أو Provider، ولم يحدث deploy أو تعديل Production. لم تتغير upstream revisions أو تراخيصها أو dependencies.
- المتبقي: تشغيل CI، ثم اختبار runtime storage على volume تجريبي فعلي؛ وبعده استكمال host firewall/egress gateway وSSRF isolation. هذه الدفعة تحسن خصوصية ملفات المضيف لكنها لا تثبت عزل الحاويات عن المضيف أو الشبكة.

### متابعة CI وتوسعة فحص صورة Provisioner — 2026-11-22

- على commit `79ab8483d5fd095c1021c001371b9ca35d22918a`: Runtime Provisioner CI run `45015847028` نجح، **71 passed, 5 warnings**؛ compile وpytest اكتملتا. Repository baseline run `45015847002` نجح. Platform CI run `45015847068` نجح (API tests، client typecheck، Expo compatibility، Web export).
- Engine integration/runtime primitives run `45015847057` اكتمل بنجاح: **135 API tests passed**، upstream OpenCode pin/license verification، Bun frozen-lockfile install، server Typecheck، Docker image build، و`/api/info` smoke test كلها green.
- Workflow قديم `engine-runtime-build.yml` run `45015845696` فشل دون أن يعيد GitHub أي jobs؛ لا توجد logs أو سبب مؤكد، لذلك لا يُسجل كنجاح. حالة Railway `strong-gentleness - suly-api` خارجية وفاشلة؛ لم يتم deploy أو محاولة إصلاحها.
- أضيف إلى Runtime Provisioner CI بناء صورة provisioner محليًا دون push أو نشر، حتى يفحص Dockerfile الجديد وصلاحيات مجلدات التخزين بدل الاكتفاء باختبارات fake Docker. نتيجة هذا البناء تنتظر CI التالي.

### إغلاق نتائج CI لهذه الدفعة — 2026-11-22

- على HEAD `17fa2fd43c99d67d992a78edd46aede3f1f0db9d`: Runtime Provisioner CI run `45016051739` نجح: **71 passed, 5 warnings**، ونجح بناء صورة `suly-runtime-provisioner:ci` دون نشر. Repository baseline run `45016051763` نجح. Platform CI run `45016051806` نجح: **770 passed, 5 skipped, 5 warnings**؛ TypeScript typecheck وExpo compatibility وWeb export نجحت.
- OpenCode upstream engine verification run `45015847057` على commit `79ab8483d5fd095c1021c001371b9ca35d22918a` نجح: **135 passed**، وتحقق من upstream immutable SHA `4cca18d80450a3dd6a9a4142028bde84ccb3116e` وترخيص MIT، ثم Typecheck وبناء الصورة واختبار تشغيل `/api/info` داخل Docker.
- `engine-runtime-build.yml` run `45016050525` فشل دون jobs أو logs؛ تكرر النمط في `45015845696`، والسبب غير معلوم. لذلك لا ندعي بناء Hermes image أو اكتمال build pipeline الموحد.
- فحص Railway `strong-gentleness - suly-api` ما زال failure خارجيًا على HEAD الحالي. لم ننفذ deploy أو تعديل production أو إعادة تشغيل خدمة.
- لا تزال اختبارات Runtime Provisioner تعتمد Fake Docker؛ بناء الصورة وOpenCode smoke test لا يثبتان host firewall أو host isolation أو task-aware egress أو tenant isolation على خادم فعلي. لا migrations أو staging acceptance في هذه الدفعة.

### تقوية سلسلة بناء صورة Provisioner — 2026-11-22

- تم تثبيت `python:3.12-slim` على manifest digest الذي استخدمه Docker بنجاح في CI (`sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`) بدل tag متغير.
- أضيف `.dockerignore` بقائمة سماح ضيقة لـDockerfile وrequirements وملفات Python داخل `app/` فقط؛ لا يُرسل مجلد الاختبارات أو ملفات البيئة/المستندات إلى Docker build context.
- أضيف contract test يتحقق من digest pin وقائمة build context. سيشغل Runtime Provisioner CI الاختبار ثم يبني الصورة دون نشر.

