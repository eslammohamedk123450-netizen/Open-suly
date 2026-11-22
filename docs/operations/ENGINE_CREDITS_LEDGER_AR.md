# دفتر أرصدة SULY واستهلاك المحركات

## الهدف

إنشاء أساس محاسبي واحد لرصيد المستخدم، والحجوزات المؤقتة، والحركات غير القابلة للتكرار. هذا الأساس يخدم OpenCode وHermes دون إنشاء نظام رصيد مستقل لكل محرك.

## مكونات قاعدة البيانات

- `credit_accounts`: رصيد متاح ورصيد محجوز لكل مستخدم. الحساب لا يمنح رصيدًا عند التسجيل؛ البداية دائمًا صفر.
- `credit_reservations`: حجز مرتبط بمعرف المهمة وتشغيل المحرك، مع مبلغ ثابت ومفتاح idempotency وحالة نهائية.
- `credit_ledger`: سجل فروق الرصيد المتاح والمحجوز لكل منحة أو حجز أو تسوية أو تحرير. كل مستخدم ومفتاح idempotency فريدان.

## دورة الرصيد

1. يبدأ العامل سجل engine run بعد امتلاك task-step lease.
2. قبل إنشاء runtime، يستدعي الخادم reserve RPC بمستخدم المهمة ومعرف task وengine run والمحرك ومبلغ محدد.
3. يخصم الحجز من available ويضيفه إلى reserved في معاملة واحدة.
4. بعد انتهاء المحرك وتحويل النتيجة إلى حالة نهائية، يرسل الخادم actual credits إلى settle RPC؛ تُعاد الزيادة غير المستهلكة إلى available.
5. عند الفشل أو الإلغاء، يحرر الخادم الحجز بعد انتهاء engine run.
6. reconciler محدود يعيد الحجوزات المنتهية فقط إذا لم يعد هناك engine run بحالة running.

## الأمان والملكية

- RLS يسمح للمستخدم بقراءة حسابه وحجوزاته وسجله فقط.
- لا توجد صلاحيات INSERT/UPDATE/DELETE مباشرة للمتصفح أو service-role table client؛ التغييرات تمر عبر SECURITY DEFINER RPCs محددة مع search_path فارغ.
- RPCs متاحة لـ service_role فقط، ولا يستطيع العميل منح رصيد لنفسه.
- reserve يتحقق داخل المعاملة من تطابق user/task/engine-run/engine وحالة المهمة، ومن عدم طلب الإلغاء.
- المفاتيح idempotent؛ إعادة الطلب نفسه لا تخصم مرتين، وإعادة استخدام المفتاح بمعاملات مختلفة تُرفض.
- مقارنة قيم `metadata` عند إعادة استخدام مفتاح المنحة أو التسوية أو التحرير تستخدم `IS DISTINCT FROM`؛ لذلك تُرفض القيمة المفقودة أو `NULL` كتعارض بدل أن تمر بسبب منطق `NULL` في SQL.
- actual credits لا يمكن أن يتجاوز الحجز. تجاوز الحد يرفض التسوية بدل إنشاء رصيد سالب.
- المنح محصورة في RPC خادمي؛ يجب أن يضيف أي Admin API لاحقًا تحقق صلاحية مدير مستقلًا قبل استدعائه.

## ما لم يُنفذ بعد

- لم تُطبق migration على أي قاعدة بيانات.
- لم نحدد أسعارًا أو token-to-credit conversion، ولم نربط reserve/settle/release بمسار تشغيل OpenCode أو Hermes بعد.
- أضيف endpoint قراءة `GET /v1/credits` وصفحة `/credits` في Expo لعرض available/reserved والحجوزات الأخيرة (25) والحركات (50). تعتمد على user JWT وRLS مع owner filter إضافي، وتستبعد metadata ومعرفات المهام.
- API/client العرض gated بإعداد `ENGINE_CREDITS_ENABLED=false` افتراضيًا، ولا ينشئ الحساب أو يمنح/يخصم الرصيد أو يشغل محركًا. لا توجد واجهة شراء أو منح رصيد.
- لا يوجد دفع أو شراء أو مكافأة مجانية؛ لم تُفعّل خدمة مدفوعة.
- يلزم اختبار تنافسية الحجوزات والتسوية على PostgreSQL disposable، ثم ربط الميزانية الفعلية بالمحرك، وإضافة اختبارات cancel/retry/recovery قبل تفعيل أي worker.

## الملفات

- `supabase/migrations/20261121250000_credit_ledger_foundation.sql`
- `services/api/app/services/engine_credit_store.py`
- `services/api/tests/test_engine_credit_store.py`
- `services/api/tests/test_sql_migration_static.py`

هذه مرحلة تأسيس محاسبي فقط، وليست إعلانًا عن جاهزية الفوترة أو تشغيل المحركات.


## API/UI قراءة الرصيد (مضاف 2026-11-22)

- `GET /v1/credits`: account summary، آخر 25 reservation، وآخر 50 ledger entry. لا يتيح pagination بعد.
- يستخدم API bearer user token مع Supabase publishable client؛ استعلامات owner-filtered وتخضع لـRLS. الـprojection محدود، ولا يعيد metadata أو task IDs.
- `ENGINE_CREDITS_ENABLED` يظل `false` افتراضيًا. يجب مراجعة/تطبيق migration في بيئة disposable/staging فقط، ثم ضبط flag يدويًا بعد التحقق.
- شاشة Expo `/credits` مربوطة من الإعدادات. لا شراء، grant، reservation، settlement، ولا تشغيل engines من الشاشة.
- اختبارات API الجديدة عبر fake PostgREST client؛ PostgreSQL integration وlive RLS لم تُنفذ بعد.


### CI confirmation

- Platform CI #1377/#1378 passed; API suite **764 passed, 5 warnings**; client typecheck, Expo compatibility, and web export passed.
- API tests use a fake PostgREST client. No disposable PostgreSQL integration test or live RLS verification has been run.
- The API remains disabled by default. Do not enable it until the ledger migration is validated in an isolated DB and applied only with explicit staging approval.


## PostgreSQL disposable integration

- Workflow `.github/workflows/credit-ledger-postgres.yml` يطبق migration على PostgreSQL 16 ephemeral، ولا يلمس Supabase أو staging.
- `services/api/tests/test_engine_credit_ledger_postgres.py` يثبت grant/reserve/settle/release/expiry وidempotency/conflict، insufficient/cross-owner validation، concurrent reserve دون overdraw، وRLS owner-read للثلاث tables مع رفض direct write وRPC من authenticated.
- Run #4 `45000017619` passed: **5 passed**. أول run #1/#2 failed بسبب test fixtures؛ الإصلاحات موثقة في progress.
- Platform CI #1385: 764 passed، 5 skipped، 5 warnings. PostgreSQL tests تُskip دون DSN في suite العام وتُنفذ في workflow منفصل.
- ما زالت migration غير مطبقة على live DB، ولا توجد cost policy أو usage metering أو engine lifecycle billing.
