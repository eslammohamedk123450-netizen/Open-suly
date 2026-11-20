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
