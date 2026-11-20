# سجل استلام ومراجعة محركات الوكلاء مفتوحة المصدر — SULY

تاريخ المراجعة: 2026-11-20

## قواعد الدمج

- هذه القائمة تثبت مراجعة metadata وملفات المصدر المحددة فقط؛ لا تعني أن المشروع بُني أو شُغّل أو اجتاز اختبار أمان.
- كل SHA أدناه immutable audit pin، ويجب تثبيت نفس SHA في build recipe قبل البناء.
- لا ننسخ upstream داخل كود SULY دون حاجة؛ الأفضل تشغيل backend منفصل وعزله وربطه عبر Engine Adapter.
- لا يُفعّل أي محرك قبل فحص dependency tree وملفات Docker والـpermissions والـnetwork egress وحدود الموارد واختبار task lifecycle.
- GitHub license metadata ليست بديلًا عن مراجعة LICENSE والملفات الفرعية والاعتمادات والترخيص التجاري.
- كل المحركات تظل disabled افتراضيًا.

## نتائج المراجعة الأولية

| النظام | المستودع / SHA المثبت للمراجعة | الترخيص الظاهر | القرار الأولي |
|---|---|---|---|
| Hermes Agent | `NousResearch/hermes-agent` — `2de9f51b8008a7d49a49221c184f2f11cbfc4af1` | MIT | المحرك العام الأساسي؛ موجود له adapter في SULY، لكن runtime غير مفعّل ولا يوجد إثبات عزل حي. |
| OpenHands Agent Canvas | `OpenHands/OpenHands` — `3df9648874a901dd91c4d8a4fdb49401297a27a5` | MIT | هذا الـSHA يعرض Agent Canvas/control plane يدعم backends عبر ACP؛ لا نعتبره coding engine مستقلًا قبل تحديد backend الفعلي. توثيقه يحذر من host filesystem/shell/network access؛ لا تشغيل host mode. |
| OpenCode | `anomalyco/opencode` (branch `dev`) — `8e1c6a43a2840380650fad0ec5b3ba41ac388d27` | MIT | مرشح coding adapter منفصل؛ لا نثبت branch متحرك، بل SHA فقط. يلزم فحص API/runtime والتبعيات قبل الاختيار النهائي. |
| Aider | `Aider-AI/aider` — `5dc9490bb35f9729ef2c95d00a19ccd30c26339c` | Apache-2.0 (metadata) | مرشح coding CLI بديل؛ يحتاج workspace مؤقت وقيود أوامر وGit، ولا يُشغّل على مستودع المستخدم مباشرة قبل موافقته. |
| Browser Use | `browser-use/browser-use` — `ccbdb8095fbaf903c748880a600054a34c7b6191` | MIT | مرشح Browser Agent محلي. المصدر يصف persistent Python REPL وChrome CDP؛ لذلك يجب عزل browser profile وREPL والشبكة والـdownloads. لا حاجة إلى Browser Use Cloud. |
| Skyvern | `Skyvern-AI/skyvern` — `e48d8bbde49e40a6df324c39cae9a89aa20706c6` | AGPL-3.0 | مؤجل لمراجعة أثر AGPL على خدمة SULY متعددة المستخدمين قبل أي دمج أو تعديل/استضافة. |
| LangGraph | `langchain-ai/langgraph` — `58a6e1cc5b7dfc3619fc6e7e7573b040d554649b` | MIT | تكامل orchestration اختياري فقط إذا أثبت حاجة لا يغطيها SULY DAG الحالي؛ لا نستبدل durable task state. |
| CrewAI | `crewAIInc/crewAI` — `c24960bda1d34d9038d7da92c3eee18275331feb` | MIT | تقييم اختياري لتعاون الوكلاء؛ لا نضيفه بالتوازي مع LangGraph إلا لميزة مثبتة. |
| Dify | `langgenius/dify` — `4ab850e4f06047fb0a6dcba70f3f32ab2c521c90` | ترخيص معدل مبني على Apache-2.0 | لا دمج في multi-tenant SULY قبل ترخيص تجاري/موافقة مكتوبة؛ ملف LICENSE يمنع multi-tenant use دون إذن صريح. |
| n8n | `n8n-io/n8n` — `03689bec07e0a700a72c5e3f2f3f26caffe6394f` | Sustainable Use License 1.0 (not OSI permissive) | مؤجل حتى مراجعة Sustainable Use License وشروط embedding/white-label/commercial. |
| UI-TARS | `bytedance/UI-TARS` — `582f3a7ea5d285ee8ed9e2e84048d1ab01453c49` | Apache-2.0 | المستودع مؤرشف؛ لا يُعتمد كمحرك إنتاج حالي. |
| OpenClaw | `openclaw/openclaw` — `4bddfe904ddc48b07948fc0294c6514c80a297c7` | MIT | تقييم أمني/قدرات فقط؛ لا يضاف كقلب ثانٍ للوكلاء ولا يفتح قنوات خارجية تلقائيًا. |
| Nanobot | `HKUDS/nanobot` — `db0306b404954e48ffb82ceae70cbf6f73094348` | MIT | Benchmark خفيف فقط؛ لا دمج قبل إثبات فرق واضح عن Hermes. |
| IronClaw | `nearai/ironclaw` — `b0b999d96781516ee05e6ba961d6f3ead900da96` | Apache-2.0 | تقييم عزل وأمان؛ لا يكرر engine runtime الحالي. |
| ZeroClaw | `zeroclaw-labs/zeroclaw` — `dfc70a2b499a5e5ad777a9174a216a29fda7aa35` | Apache-2.0 | Benchmark runtime بديل؛ لا تشغيل حتى اكتمال threat model. |
| OpenManus | `FoundationAgents/OpenManus` — `3309bf4e416fb1c74b008f3e86494439a31bad53` | MIT | تقييم معماري/قدرات؛ لا نسخ planner أو agent loop إذا تكررت وظائف SULY. |

## نتائج تقنية وأمنية مهمة

1. **OpenHands**: README الحالي يوضح أن Agent Canvas يمكنه استخدام backends متعددة، لكنه يحذر صراحة من التشغيل دون sandbox لأن الوكيل يستطيع قراءة/تعديل filesystem وتشغيل shell والوصول للشبكة. كما يحذر دليل الاستضافة من التعامل مع الخادم كآلة تحمل credentials إنتاجية. لذلك لا نستخدم وضع host mode، ولا نعرضه على الإنترنت، ولا نربطه بمستودعات المستخدم قبل runtime عزل لكل مهمة.
2. **Browser Use**: التنفيذ قائم على REPL مستمر وChrome DevTools Protocol. يجب أن تكون جلسة المتصفح وملفات تعريف الارتباط والتنزيلات والـegress معزولة لكل task/tenant، مع موافقات للأفعال الحساسة.
3. **Dify**: شروط LICENSE الخاصة به تتضمن قيدًا صريحًا على تشغيل multi-tenant دون موافقة مكتوبة؛ لهذا لا يعتبر خيارًا مجانيًا صالحًا تلقائيًا لتشغيل منصة SULY متعددة المستخدمين.
4. **Skyvern**: AGPL-3.0 يتطلب مراجعة قانونية قبل تعديل أو تشغيل نسخة متاحة عبر الشبكة.
5. **n8n**: عدم ظهور SPDX license لا يعني permissive license؛ يجب مراجعة النص الفعلي لشروط الاستخدام التجاري قبل embedding.
6. **UI-TARS**: حالة الأرشفة تجعل الاعتماد الإنتاجي عليه غير مناسب دون fork وصيانة داخلية واضحة.
7. **Orchestration**: SULY يحتفظ بـPostgres/DAG/leases كمرجع الحالة الدائم. LangGraph/CrewAI لا يصبحان مصدر الحقيقة لحالة المهمة.

## خطة الاختيار والتنفيذ

- أول coding runtime للتجربة: Aider CLI داخل sandbox لكل task؛ نقارنه بـOpenCode server بعد مراجعة API والـpermissions. OpenHands Agent Canvas يُقيّم كطبقة control plane/ACP، وليس كبديل تلقائي للمحرك.
- لا نبدأ Aider أو OpenCode قبل Docker runner فعلي، image digest ثابت، workspace مؤقت، non-root، CPU/RAM/PID/disk/time quotas، network default-deny مع egress proxy محدود، وcleanup موثوق.
- نختار backend واحدًا بعد benchmark موحد (نجاح task، زمن، استهلاك، patch quality، cancellation، recovery).
- أول Browser backend مرشح: Browser Use المحلي، بعد بناء browser sandbox؛ لا تستخدم hosted cloud.
- لا نعتمد Dify أو n8n أو Skyvern قبل إغلاق مراجعة الترخيص.
- لا يتم نسخ upstream source حتى تُراجع dependencies وlicense notices وCVE/source provenance وتثبت نسخة قابلة لإعادة البناء.
- لا يتم تشغيل أي من هذه الأنظمة في هذا checkpoint.

## ما لم يكتمل

- لم يتم build أو run لأي من المرشحين أعلاه داخل بيئة اختبار SULY.
- لم يتم استكمال transitive dependency/license/SBOM/CVE audit.
- لم يُبنَ بعد per-task container manager أو default-deny egress policy.
- لا توجد نتيجة benchmark مقارنة، ولا موافقة لتفعيل providers أو خدمات مدفوعة.


## مصادر وردت ضمن قائمة التقييم ولم يثبت عنوانها/نسختها بعد

| النظام | الحالة |
|---|---|
| Open Interpreter | لم يتم تثبيت repository canonical/revision موثوق في هذه المراجعة؛ لا pin ولا دمج حتى تأكيد الرابط الأصلي الذي قصده المستخدم. |
| Screenpipe | لم يتم تأكيد المستودع المقصود أو إجراء license/source audit؛ مؤجل ولا يوجد pin. |
