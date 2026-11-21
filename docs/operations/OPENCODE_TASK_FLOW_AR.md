# تكامل OpenCode داخل SULY — دليل التنفيذ الحالي

آخر تحديث: 2026-11-21

## الحالة

**تكامل الكود الأساسي مكتمل ومجتاز CI.** هذا لا يعني تشغيل OpenCode في Live/Production: worker/runtime والمفاتيح تظل غير مفعلة، ولا يوجد Staging provisioner متصل.

## مسار مهمة البرمجة

1. المستخدم ينشئ Task مرتبطة بمشروع (Project) في SULY.
2. تطبيق الوكيل يعرض وضع OpenCode فقط في واجهة الاختيار؛ يتطلب project ID وموافقة scope `engine.opencode.run`.
3. العميل يرسل `POST /v1/tasks/{task_id}/opencode-plan`. يتحقق API من أن task مملوكة للمستخدم، queued، مرتبطة بمشروع، وأن إعداد worker + OpenCode + runtime provisioner مكتمل.
4. RPC `plan_task` ينشئ step واحدة allow-listed باسم `opencode.task.run`.
5. Worker (إذا تم تشغيله بموافقة وإعدادات server-only) يفحص approval scope قبل handler. ينشئ EngineRun من خلال lease-protected RPC.
6. Handler يتحقق من prompt/project ID ويجهز server-side WorkspaceSnapshot وSessionStore وLifecycleStore؛ ثم ينفذ OpenCode Task Executor على Runtime lease مستقل.
7. Runtime يرسل أحداث metadata آمنة إلى سجل task lifecycle؛ وتجمع نتيجة الملفات المعدلة/المحذوفة ضمن change set قابلة للمراجعة.
8. Worker task output يحتوي IDs وstatus وعدد الملفات فقط، ولا يحتوي token أو prompt أو file contents.
9. Task details تعرض أحداث OpenCode وdiff preview (8KB افتراضي لكل ملف، مع زر لعرض كامل diff).
10. المستخدم يختار Reject أو Apply. Apply يستخدم CAS/Workspace revision، ويرفض التطبيق إذا تغير المشروع منذ snapshot. بعد القرار يطلب API إغلاق runtime lease.

## API endpoints المرتبطة

- `POST /v1/tasks/{task_id}/opencode-plan` — queue one OpenCode step.
- `GET /v1/projects/{project_id}/opencode/runs` — owner-scoped run metadata.
- `GET /v1/opencode/runs/{run_id}/events` — sanitized lifecycle events.
- `GET /v1/opencode/runs/{run_id}/approvals` — pending permission metadata.
- `POST /v1/opencode/approvals/{approval_id}/decision` — once/reject permission response.
- `GET /v1/opencode/change-sets/{change_set_id}` — owner-only review payload.
- `POST /v1/opencode/change-sets/{change_set_id}/decision` — reject/apply change set.
- `GET /v1/projects/{project_id}/opencode/sessions` — durable owner-scoped session metadata.

## الإعدادات الافتراضية

- `SULY_WORKER_ENABLED=false`
- `OPENCODE_ENABLED=false`
- Runtime provider is created only in the separate worker process when both flags and the full HTTPS allowlist/token configuration are present.
- No secret, runtime token, provider credential, or local filesystem path belongs in the repository.
- OpenCode's upstream revision is pinned in `engines/opencode/UPSTREAM.json` and the upstream submodule. Upstream source is not modified.

## CI evidence

- Platform CI #1059 on commit `7399ec775d25aa523ed0ba3a19d697d221e21e88`: **609 API tests passed, 5 warnings**; API compile, TypeScript typecheck, Expo dependency compatibility, and Web export all passed.
- Repository baseline #1077 on the same commit: success.
- OpenCode upstream verification #177 on `1a84d30dc60adf5777f3169a6983faa275904b1`: runtime primitive tests, bridge/protocol tests, provenance, lockfile install, upstream server typecheck, Docker build, and authenticated server smoke all passed. Upstream engine files were not changed after that run.
- The code is test-backed with mocks/contracts; no live provisioner/runtime or disposable Supabase staging integration was exercised.

## Before enabling controlled staging

1. Implement and verify coding-engine credit/usage metering. No agreed cost model/ledger is currently in this repository; do not expose unlimited paid runtime use.
2. Apply migrations only to disposable/staging after explicit approval.
3. Deploy a provisioner with one-task/one-runtime isolation, egress policy, CPU/RAM/disk/time limits, teardown confirmation, and secret rotation.
4. Validate end-to-end task lease renewal/loss, cancel-request propagation, runtime release, restart/orphan recovery, permission approval, events, change-set CAS/apply, and cross-user isolation.
5. Test Android and web UX with real account/session in staging, including long diffs, rejected/applied change sets, failure/retry, and accessible controls.
6. Keep worker/engine disabled until staging test results and metering are approved.

