# عقد وسيط تشغيل معزول لكل محاولة — SULY

## الهدف

OpenCode وBrowser Use لا يمكن تشغيلهما داخل عملية API مشتركة بين المستخدمين. يحتاج كل تشغيل إلى runtime منفصل مرتبط بمحاولة واحدة فقط.

## الموجود في الكود

- RuntimeLease يربط runtime_id وtask_id وengine_run_id وengine_id في سجل واحد.
- بيانات الوصول مخفية من repr ولا يجب تسجيلها أو إرسالها إلى العميل.
- عنوان runtime يجب أن يطابق host allowlist صريحة من إعدادات الخادم؛ لا يقبل عنوانًا يرسله المستخدم.
- lease قصيرة العمر، وبحد أقصى ساعة واحدة.
- TaskScopedRuntimeBroker يرفض تكرار محاولة سبق منحها lease، ويرفض إعادة استخدام runtime_id عبر محاولات مختلفة.
- context manager يحاول release حتى عند حدوث استثناء داخل تنفيذ المحرك.
- إذا لم يؤكد مزود التشغيل teardown، يبقى runtime محجوزًا داخل broker process ولا يعاد استخدامه.

## ما لم يتم بناؤه بعد

- لا يوجد Provider فعلي ينشئ حاويات أو يوقفها.
- لا يوجد خدمة broker منفصلة تتصل بOCI runtime.
- لا يوجد OpenCode adapter يستهلك lease بعد.
- لا يوجد اختبار عزل فعلي بين حاويتين أو منع egress على شبكة حقيقية.
- هذه الوحدة عقد تحقق وإدارة lease فقط، وليست دليلًا على تشغيل محركات.

## شروط تنفيذ Provider

1. يعمل في خدمة منفصلة عن API، ولا يمرر Docker socket إلى حاويات المحركات.
2. ينشئ runtime جديدًا لكل engine_run_id، ولا يعيد استخدام الحاوية حتى بعد release.
3. يطبق image digest ثابتًا، non-root، read-only rootfs، workspace واحد، وحدود CPU/RAM/PID/disk/time.
4. يمنع host mounts وhost networking وprivileged وcapabilities الإضافية.
5. يسمح باتصال broker من خلال host allowlist فقط، ويمنع runtime من اختيار عنوانه بنفسه.
6. يستخدم credential عشوائيًا لكل runtime ويبطله عند teardown.
7. يزيل runtime عند timeout/cancel/lease loss/worker restart، مع reconciler مستقل للموارد اليتيمة.
8. يثبت بالاختبارات أن محاولة لا تستطيع قراءة ملفات أو sessions أو env أو processes لمحاولة أخرى.

## قرار التفعيل

OpenCode وBrowser Use يظلان disabled. لا تنشئ الخدمة حاويات ولا تفتح منافذ ولا تفعل أي worker تلقائيًا. يلزم Provider حقيقي واختبارات عزل قبل بناء adapters أو تفعيل المحركات.