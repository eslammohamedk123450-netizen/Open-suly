# حدود Rate Limiting في API — دليل التشغيل

## السلوك الحالي

- الـAPI يطبق Sliding Window داخل كل process وبمفتاح هوية المستخدم الموثّق، وليس بمعرّف يرسله العميل.
- كل scope مستقل: chat respond، conversations، messages، chat export، وowner AI provider.
- الحد الافتراضي لسجل المفاتيح في limiter هو 50,000؛ عندما تمتلئ السعة ولا يمكن إدخال principal جديد، الطلب يُرفض (fail closed) بدل إخلاء نافذة مستخدم نشطة.
- التنظيف الدوري يزيل المفاتيح التي لا تحتوي أحداثًا ضمن النافذة. التنظيف يحدث عند طلب لاحق بعد مرور 600 ثانية افتراضيًا، وليس بواسطة مهمة خلفية.
- القيمة `0` في إعداد limit تعطل حد ذلك scope؛ لا تستخدمها في production دون قرار مقصود وتدابير بديلة.

## حدود الحماية

هذا limiter ليس global أو distributed. كل replica/worker API لديها سجل مستقل في الذاكرة؛ زيادة عدد instances لا تزيد الحد الموحد، وإعادة تشغيل process تعيد سجل النوافذ. لا يغطي DDoS أو requests قبل الوصول إلى التطبيق.

قبل Production يجب أن تفرض طبقة ingress حدًا عامًا مستقلًا، وتحدد سياسات IP/connection وburst، مع مراقبة rejection/latency دون تسجيل tokens أو محتوى المستخدم. لا توجد خدمة مشتركة أو paid infrastructure مضافة في هذا التغيير.

## الاختبارات

الاختبارات تشمل نافذة الوقت، استقلال principals، استعادة الحد بعد انتهاء النافذة، pruning، fail-closed عند امتلاء key cap، تغيير الحد دون مسح الأحداث، والتزامن. شغّل من مجلد API:

```sh
python -m pytest -q tests/test_rate_limit.py
```

النتائج على GitHub Actions هي المرجع لهذا التغيير؛ لا تعتبر الاختبارات mocked/local proof of distributed rate limiting.
