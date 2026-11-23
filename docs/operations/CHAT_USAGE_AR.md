# ملخص استهلاك Tokens للمحادثات — SULY

## Endpoint

- `GET /v1/usage/chat`
- يحتاج جلسة Supabase Auth؛ يستخدم JWT المستخدم وRLS ولا يستخدم service-role.
- يقرأ فقط حقلي `metadata` و`created_at` من رسائل المساعد، مع فلتر `user_id` و`role=assistant` في الاستعلام.
- يعرض إجمالي `input_tokens` و`output_tokens` و`total_tokens`، وعدد رسائل المساعد التي تم فحصها وعدد الرسائل التي سجلت usage صالحًا.
- لا يرجع نص الرسائل، metadata الخام، model/provider أو مفاتيف/أسرار.

## الحدود ودقة البيانات

- يقرأ أحدث 500 رسالة مساعد فقط، ويطلب 501 سجلًا لاكتشاف وجود سجلات أقدم.
- `truncated=true` يعني أن الملخص يقتصر على أحدث 500 رسالة؛ لا تعتبره إجمالي الحساب.
- يجمع الأرقام الصحيحة غير السالبة التي يبلّغ عنها provider فقط؛ يتجاهل missing أو malformed usage ويعيد حساب total من input/output.
- لا يقدّر token counts من النص، ولا يحسب التكلفة المالية أو credits.
- لا يشمل usage الخاص بمحركات Hermes/OpenCode أو agent/tool calls؛ هذا مسار telemetry للمحادثات فقط.
- الحد الحالي 20 طلبًا/دقيقة لكل مستخدم داخل عملية API. يجب إضافة ingress/global rate limit قبل الاعتماد عليه في نشر متعدد النسخ.

## واجهة العميل

- صفحة **الرصيد والاستخدام** تعرض بطاقة Tokens منفصلة عن رصيد credits، وتحمّل البيانات حتى عندما يكون دفتر credits معطلًا.
- Refresh يطلب تحديث ملخص المحادثات والرصيد بشكل مستقل؛ أخطاء كل قسم لا تخفي القسم الآخر.
- القيم تظل provider-reported؛ لا توجد أسعار/تحويلات tokens إلى credits حتى اعتماد cost policy.

## حالة التشغيل

هذا endpoint وواجهة العميل committed code فقط. لم يتم deploy API، ولم يُختبر اتصال Supabase حي أو مزود AI. اختبارات API الجديدة mocked/fake-store وتنتظر CI.
