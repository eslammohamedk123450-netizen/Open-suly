# خريطة تعلم مشروع SULY — بالعربي

هذا الملف بوابة التعلم للمشروع. لا تحتاج أن تفهم كل النظام مرة واحدة. اقرأ حسب الترتيب وارجع إلى الملفات المذكورة.

## 1) خريطة التطبيق

### الواجهة (Expo / React Native / TypeScript)
- `apps/client/src/app/index.tsx`: نقطة شاشة التطبيق الرئيسية.
- `apps/client/src/app/_layout.tsx`: غلاف التنقل العام.
- `apps/client/src/app/auth.tsx`: واجهة تسجيل الدخول/المصادقة.
- `apps/client/src/app/conversation/[id].tsx`: شاشة محادثة محددة.
- `apps/client/src/app/agent.tsx`: واجهة مهام/Agent.
- `apps/client/src/app/activity.tsx`: النشاط ومتابعة المهام.
- `apps/client/src/app/task/[id].tsx`: تفاصيل مهمة معينة، الخطوات، ومحاولات المحركات.
- `apps/client/src/app/projects.tsx`: شاشة المشاريع.
- `apps/client/src/app/settings.tsx`: الإعدادات.

### API (FastAPI / Python)
- `services/api/app/main.py`: إنشاء تطبيق FastAPI وربط routers.
- `services/api/app/core/config.py`: قراءة إعدادات environment، والميزات متوقفة افتراضيًا.
- `services/api/app/core/auth.py`: التحقق من المستخدم/جلسة المصادقة.
- `services/api/app/core/supabase.py`: إنشاء اتصال server-side بقاعدة البيانات.
- `services/api/app/routers/chat.py`: نقاط API الخاصة بالمحادثات.
- `services/api/app/routers/tasks.py`: إنشاء المهام، تخطيطها، عرضها، إلغاؤها وإعادة المحاولة.
- `services/api/app/routers/tool_approvals.py`: إدارة الموافقات.

### أنظمة التنفيذ
- `services/api/app/services/agent_planner.py`: تحويل الطلب إلى خطة خطوات محددة وقابلة للتنفيذ؛ ليست LLM planner عامة.
- `services/api/app/services/task_worker.py`: يطالب بخطوة، يستلم lease، يجددها، ثم يسجل نجاحًا/فشلًا.
- `services/api/app/worker_runtime.py`: تشغيل العامل، فحص الموافقات، اختيار الأدوات والمحركات.
- `services/api/app/services/tool_registry.py`: قائمة الأدوات المسموح بها والتحقق من المدخلات والحدود.
- `services/api/app/services/tool_approvals.py`: حفظ/قراءة موافقات الأدوات.
- `services/api/app/services/engine_contract.py`: شكل الطلب والنتيجة الذي يجب أن تلتزم به المحركات.
- `services/api/app/services/engine_registry.py`: قائمة المحركات، القدرات، حدود الإدخال/الخرج والوقت.
- `services/api/app/services/engine_run_store.py`: حفظ سجل تشغيل المحرك ومعرف upstream تحت lease.
- `services/api/app/services/hermes_agent.py`: عميل Hermes Runs API (إنشاء، متابعة، إيقاف) لكنه متوقف افتراضيًا ويتطلب عزلًا مؤكدًا.
- `services/api/app/services/ai_gateway.py`: بوابة مزود AI؛ لا تفعل مزودًا دون إعداد/موافقة.

### قاعدة البيانات
- `supabase/migrations/`: تغييرات SQL متسلسلة؛ لا تطبقها على قاعدة حية دون خطة ونسخة staging.
- `20261119233548_durable_tasks_dag_foundation.sql`: أساس المهام والخطوات.
- `20261119233958_atomic_task_planning.sql`: تخطيط الخطوات بشكل ذري.
- `20261119234304_worker_lease_runtime.sql`: ملكية worker وlease والـRPC.
- `20261120003441_persisted_tool_approvals_audit.sql`: الموافقات وسجل تدقيق.
- `20261120153000_engine_run_ledger.sql`: سجل محاولات المحركات.
- `20261120170000_engine_run_reconciliation.sql`: إغلاق محاولات engine عند انتهاء step lease.
- `20261120173000_engine_upstream_run_identity.sql`: حفظ معرف run الخارجي (opaque ID) فقط.

## 2) الترتيب المقترح للتعلم
1. HTTP وJSON وAPI: افهم request/response وstatus codes.
2. Python functions وtypes وexceptions: اقرأ ملف planner ثم tool registry.
3. FastAPI: اقرأ `main.py` ثم router chat وtasks.
4. PostgreSQL basics: tables, foreign keys, unique constraints, indexes.
5. Supabase RLS: كيف يحمي كل مستخدم بياناته.
6. Durable tasks: task/step/attempt.
7. Worker lease + heartbeat: لماذا worker واحد فقط يملك الخطوة في اللحظة الحالية.
8. Tool Registry + approvals: allowlist وموافقة قبل أدوات حساسة.
9. Engine Registry: adapter contract وكيف نضيف محرك دون خلطه في API.
10. Hermes: API runs, idempotency, polling, stop, external ID.
11. Docker/Compose: عزل تشغيل خدمة منفصلة.
12. Deployment/observability/load testing: الاستعداد للإنتاج.

## 3) ماذا يعني كل جزء بصورة مبسطة؟
- **Router**: يستقبل HTTP request ويوجهه إلى الدالة الصحيحة.
- **Service**: منطق العمل الذي يمكن أن تستخدمه أكثر من route.
- **Migration**: ملف SQL يغير schema بطريقة قابلة للتتبع.
- **RLS**: سياسات قاعدة البيانات التي تحدد أي صفوف يحق للمستخدم رؤيتها/تعديلها.
- **RPC**: استدعاء دالة في قاعدة البيانات كعملية واحدة ذرية.
- **Lease**: قفل مؤقت بمالك ورمز ومدة انتهاء؛ ليس قفلًا دائمًا.
- **Heartbeat**: تجديد مدة الملكية أثناء العمل.
- **Adapter**: طبقة ترجمة بين SULY contract وبين API محرك خارجي.
- **Idempotency key**: معرف ثابت يمنع إعادة إنشاء نفس العملية عند إعادة الطلب.
- **Reconciliation**: إنهاء أو تصحيح السجل الذي بقي معلّقًا بعد تعطل غير متوقع.
- **Sandbox**: بيئة منفصلة ومحدودة تمنع المحرك من الوصول إلى host أو بيانات مستخدمين آخرين.
- **CI**: اختبارات تلقائية على كل تحديث؛ نجاحها لا يساوي اختبار تشغيل إنتاجي.

## 4) نظام التعليقات في الكود
- في الملفات التي نكتبها نحن: نشرح الغرض من كل class/function/branch، ونعليقات عربية على القرارات الأمنية والعمليات المهمة.
- لا نكرر تعليقًا حرفيًا لكل سطر syntax مثل imports أو الأقواس أو أسماء المتغيرات؛ نستخدم docstrings وتعليقات منطقية لتظل الملفات قابلة للصيانة.
- في upstream source نحافظ على الكود والتعليقات والترخيص الأصلي، ونكتب شرحًا عربيًا منفصلًا بدل تعديل ملايين الأسطر.
- لا نضيف شرحًا على ملفات generated lock files أو JSON/YAML حساس للبنية قد يسبب parsing errors.

## 5) قاعدة الدراسة: ملف واحد في كل جلسة
لكل ملف:
1. اقرأ سبب وجوده ومكانه في المعمارية.
2. افهم المدخلات والمخرجات.
3. ارسم مسار التنفيذ.
4. اشرح المصطلحات.
5. اكتب تمرينًا صغيرًا لا يغير قاعدة البيانات أو الأسرار.
6. اختبر إجابتك قبل الانتقال للملف التالي.

## 6) حدود الجاهزية الحالية
هذا الدليل خريطة تعليمية وليس ادعاء بأن النظام جاهز:
- Hermes API bridge متقدم لكنه disabled.
- العزل لكل task/user، egress policy، حدود الموارد ومراجعة sandbox ما زالت مطلوبة.
- migrations الخاصة engine_runs وupstream identity موجودة في repo ولم تُطبق على Supabase live.
- لا يوجد مزود AI configured.
- API وworker غير منشورين في بيئة production.
- CI على commits الأخيرة قد يكون ما زال جاريًا؛ راجع GitHub Actions قبل اعتماد أي حالة.
