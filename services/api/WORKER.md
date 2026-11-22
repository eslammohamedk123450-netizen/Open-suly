# SULY Worker — تشغيل منفصل وآمن

العامل عملية مستقلة عن API. لا يبدأ مع خادم API تلقائيًا، ولا يعمل ما لم تضبط `SULY_WORKER_ENABLED=true`.

## متطلبات الإعداد

- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY` (سر خادمي فقط؛ لا يوضع في تطبيق العميل أو المستودع)
- `SULY_WORKER_ID` اختياري؛ عند غيابه يُنشأ معرف للعملية.
- `SULY_WORKER_LEASE_SECONDS` بين 15 و900، الافتراضي 90.
- `SULY_WORKER_POLL_INTERVAL_SECONDS` بين 0.1 و60، الافتراضي 2.
- `SULY_WORKER_ENABLED=true` لتشغيل العامل صراحة.

تظل `HERMES_AGENT_ENABLED` و`OPENCODE_ENABLED` و`ENGINE_RECONCILER_ENABLED` معطلة افتراضيًا. تفعيل العامل وحده لا يفعّل أي محرك أو مزود نماذج. يتطلب تشغيل محرك لاحقًا إعداد Provisioner صريحًا، وموافقات SULY، وبيئة معزولة.

## بناء الصورة

من مجلد `services/api`:

```sh
docker build --file Dockerfile.worker --tag suly-worker:local .
```

الصورة تستخدم Python base مثبتًا ببصمة SHA-256، وتعمل بالمستخدم غير root `10001:10001`. سياق البناء يستبعد الاختبارات والملفات غير اللازمة.

## تشغيل محلي

```sh
docker run --rm \
  --name suly-worker \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --stop-timeout 30 \
  -e SULY_WORKER_ENABLED=true \
  -e SUPABASE_URL \
  -e SUPABASE_SECRET_KEY \
  suly-worker:local
```

مرر الأسرار من مدير أسرار أو بيئة تشغيل آمنة، ولا تكتب قيمها في shell history أو ملفات المستودع. لا تمنح العامل Docker socket. خدمة Runtime Provisioner وحدها هي التي تملك صلاحية Docker، وتتصل بها عبر HTTPS عند تفعيل المحركات.

## سلوك الإيقاف والاستعادة

- SIGTERM/SIGINT يوقف استقبال مهام جديدة.
- المهمة النشطة تتلقى إشارة إلغاء تعاونية؛ إذا لم تكتمل، يسجل العامل فشلًا آمنًا قابلًا لإعادة المحاولة بدل اعتماد ناتج جزئي.
- فقدان lease أو فشل heartbeat يمنع اعتماد النتيجة ويطلب إيقاف المحرك.
- إغلاق اتصال Provisioner مضمون عبر `finally`.
- لا يعني ذلك إثبات إيقاف العمليات على مضيف إنتاج؛ يجب أن ينجح اختبار Docker حي ومراجعة سياسة المضيف قبل تفعيل المحركات.

## حدود التحقق

بناء الصورة واختبارات GitHub Actions لا يساويان نشر العامل أو تشغيله على Supabase فعلي. لا تشغّل العامل في الإنتاج قبل إكمال إعداد الأسرار ومراجعة migrations واختبار cancellation/recovery على بيئة تشغيل معزولة.
