# تصدير بيانات المحادثات — SULY

## ماذا يوفر؟

- زر **تصدير محادثاتك** في الإعدادات للمستخدم المسجل.
- على Web: تنزيل ملف JSON من المتصفح.
- على Android/iOS: فتح مشاركة النظام مع JSON كنص؛ اختيار الوجهة متروك للمستخدم.
- Endpoint: `GET /v1/chat/export` مع Supabase access token.

## المصادقة وعزل قاعدة البيانات

- يمرر API نفس Bearer token الخاص بالمستخدم إلى PostgREST؛ لا يستخدم service-role في مسار التصدير. لذلك يخضع الاستعلام لسياسات RLS إضافة إلى فلاتر owner الصريحة.
- اختبار client dependency يثبت تمرير JWT المستخدم ويرفض fallback إلى admin client عند التصدير.

## الحماية والحدود

- API يشتق المالك من التوكن، ولا يقبل user_id من الطلب.
- يتم الاستعلام عن المحادثات والرسائل بفلتر مالك صريح.
- التصدير لا يحتوي message metadata، user_id، أسرار مزود AI، بيانات projects/files، engine outputs، memories أو credits.
- حدود التصدير: 1,000 محادثة، 10,000 رسالة، وحجم JSON أقصى 2 MiB. صفحات المحادثات 200 سجل، وصفحات الرسائل 25 سجلًا لتقليل تضخم الذاكرة عند قراءة محتوى الرسائل.
- يتم تضمين `truncated` و`truncation_reason` عند تجاوز حد السجلات أو الحجم؛ لا يُعرض الملف الجزئي على أنه كامل.
- حد الطلب مرتان في الدقيقة لكل مستخدم **داخل عملية API الواحدة فقط**؛ هذا ليس حدًا موزعًا بين النسخ ولا بديلًا عن ingress/global rate limit. الاستجابة `Cache-Control: no-store, private` و`X-Content-Type-Options: nosniff`.

## ملاحظات التطوير

- لا توجد migration جديدة ولا تغيير في صلاحيات RLS.
- الخدمة تستخدم server-side Supabase client الموجود بالفعل؛ لا تضيف client credentials.
- الاختبارات تستخدم fake PostgREST store وتغطي authentication، owner scope المزدوج للمستخدم والمحادثة، استبعاد metadata، حدود الصفحات، message/conversation caps، حجم التصدير وrate limit المحلي.
- هذا ليس تصديرًا كاملًا لكل بيانات الحساب، ولا يتضمن حذف الحساب. يجب توسيع scope (projects, memories, credits, storage) ومراجعة سياسة الاحتفاظ قبل الادعاء بتوفير export/delete كامل.
