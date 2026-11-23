# تصدير بيانات المحادثات — SULY

## ماذا يوفر؟

- زر **تصدير محادثاتك** في الإعدادات للمستخدم المسجل.
- على Web: تنزيل ملف JSON من المتصفح.
- على Android/iOS: فتح مشاركة النظام مع JSON كنص؛ اختيار الوجهة متروك للمستخدم.
- Endpoint: `GET /v1/chat/export` مع Supabase access token.

## الحماية والحدود

- API يشتق المالك من التوكن، ولا يقبل user_id من الطلب.
- يتم الاستعلام عن المحادثات والرسائل بفلتر مالك صريح.
- التصدير لا يحتوي message metadata، user_id، أسرار مزود AI، بيانات projects/files، engine outputs، memories أو credits.
- حدود التصدير: 1,000 محادثة، 10,000 رسالة، وحجم JSON أقصى 2 MiB. حجم الصفحة 200 سجل.
- يتم تضمين `truncated` و`truncation_reason` عند تجاوز حد السجلات أو الحجم؛ لا يُعرض الملف الجزئي على أنه كامل.
- الطلب محدود بمرتين في الدقيقة لكل مستخدم. الاستجابة `Cache-Control: no-store, private` و`X-Content-Type-Options: nosniff`.

## ملاحظات التطوير

- لا توجد migration جديدة ولا تغيير في صلاحيات RLS.
- الخدمة تستخدم server-side Supabase client الموجود بالفعل؛ لا تضيف client credentials.
- الاختبارات تستخدم fake PostgREST store وتغطي authentication، owner scope، استبعاد metadata، pagination، حجم التصدير وrate limit.
- هذا ليس تصديرًا كاملًا لكل بيانات الحساب، ولا يتضمن حذف الحساب. يجب توسيع scope (projects, memories, credits, storage) ومراجعة سياسة الاحتفاظ قبل الادعاء بتوفير export/delete كامل.
