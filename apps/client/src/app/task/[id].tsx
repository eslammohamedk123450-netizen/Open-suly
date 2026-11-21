import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useLocalSearchParams } from "expo-router";
import { colors } from "@/theme/tokens";
import { useAuth } from "@/providers/AuthProvider";
import { cancelAgentTask, getAgentApprovalDetails, getAgentTask, resolveAgentApproval, retryAgentTask, steerAgentRun, type AgentApprovalDetails, type AgentTaskSnapshot } from "@/lib/agent-tasks";

const terminalStatuses = new Set(["completed", "failed", "cancelled"]);

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    queued: "في قائمة الانتظار",
    planning: "جارٍ التخطيط",
    ready: "جاهزة للتنفيذ",
    running: "قيد التنفيذ",
    waiting_approval: "تنتظر الموافقة",
    cancel_requested: "جارٍ الإلغاء",
    completed: "اكتملت",
    failed: "فشلت",
    cancelled: "أُلغيت",
    pending: "في الانتظار",
    blocked: "متوقفة بانتظار خطوة أخرى",
    succeeded: "اكتمل المحرك",
  };
  return labels[status] ?? status;
}

function approvalKey(engineRunId: string, requestId: string): string {
  return engineRunId + ":" + requestId;
}

function formatDate(value?: string): string {
  if (!value) return "غير متاح";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "غير متاح" : date.toLocaleString("ar-EG");
}

function pretty(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function eventLabel(name: string): string {
  const labels: Record<string, string> = {
    "tool.started": "بدأ تنفيذ أداة",
    "tool.completed": "اكتمل تنفيذ أداة",
    "subagent.start": "بدأ وكيل فرعي",
    "subagent.complete": "اكتمل وكيل فرعي",
    "run.queued": "دخل التنفيذ قائمة الانتظار",
    "run.completed": "اكتمل تنفيذ المهمة",
    "run.failed": "فشل تنفيذ المحرك",
    "run.cancelled": "أُلغي تنفيذ المحرك",
    "run.interrupted": "توقف تنفيذ المحرك",
    "run.stopping": "جارٍ إيقاف المحرك",
    "run.steered": "تم تحديث توجيه المهمة",
    "approval.request": "طلب المحرك موافقة",
    "approval.responded": "تم الرد على طلب الموافقة",
  };
  return labels[name] ?? "تحديث في التنفيذ";
}

export default function TaskDetailsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const [snapshot, setSnapshot] = useState<AgentTaskSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [steerDraft, setSteerDraft] = useState("");
  const [steeringRunId, setSteeringRunId] = useState<string | null>(null);
  const [approvalBusyId, setApprovalBusyId] = useState<string | null>(null);
  const [approvalDetailsLoadingId, setApprovalDetailsLoadingId] = useState<string | null>(null);
  const [approvalDetails, setApprovalDetails] = useState<Record<string, AgentApprovalDetails>>({});

  const load = useCallback(async () => {
    if (!id || !user) return;
    try {
      setSnapshot(await getAgentTask(id));
      setNotice("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر تحميل تفاصيل المهمة.");
    } finally {
      setLoading(false);
    }
  }, [id, user?.id]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    const ids = (snapshot?.steps ?? [])
      .map((step) => step.output?.change_set_id)
      .filter((value): value is string => typeof value === "string" && !!value);
    for (const changeSetId of ids) {
      if (changeSets[changeSetId] || loadingChangeSets.current.has(changeSetId)) continue;
      loadingChangeSets.current.add(changeSetId);
      setChangeSets((current) => ({ ...current, [changeSetId]: { loading: true } }));
      void getOpenCodeChangeSet(changeSetId)
        .then((item) => setChangeSets((current) => ({ ...current, [changeSetId]: { item } })))
        .catch((error) => setChangeSets((current) => ({
          ...current, [changeSetId]: { error: error instanceof Error ? error.message : "تعذر تحميل تغييرات OpenCode." },
        })))
        .finally(() => loadingChangeSets.current.delete(changeSetId));
    }
  }, [snapshot?.steps, changeSets]);

  const reloadChangeSet = async (changeSetId: string) => {
    if (loadingChangeSets.current.has(changeSetId)) return;
    loadingChangeSets.current.add(changeSetId);
    setChangeSets((current) => ({ ...current, [changeSetId]: { loading: true } }));
    try {
      const item = await getOpenCodeChangeSet(changeSetId);
      setChangeSets((current) => ({ ...current, [changeSetId]: { item } }));
    } catch (error) {
      setChangeSets((current) => ({
        ...current, [changeSetId]: { error: error instanceof Error ? error.message : "تعذر تحميل تغييرات OpenCode." },
      }));
    } finally {
      loadingChangeSets.current.delete(changeSetId);
    }
  };

  const decideChangeSet = async (changeSetId: string, decision: "apply" | "reject") => {
    if (changeSetBusyId) return;
    setChangeSetBusyId(changeSetId);
    setNotice("");
    setActionMessage("");
    try {
      await decideOpenCodeChangeSet(changeSetId, decision);
      setChangeSets((current) => ({
        ...current,
        [changeSetId]: {
          item: current[changeSetId]?.item
            ? { ...current[changeSetId]!.item!, status: decision === "apply" ? "applied" : "rejected" }
            : current[changeSetId]?.item,
        },
      }));
      await load();
      setActionMessage(decision === "apply"
        ? "تم تطبيق التغييرات بعد التحقق من إصدار مساحة المشروع."
        : "تم رفض تغييرات OpenCode وإغلاق مجموعة التغييرات.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر اتخاذ قرار مجموعة التغييرات.");
      await reloadChangeSet(changeSetId);
    } finally {
      setChangeSetBusyId(null);
    }
  };

  useEffect(() => {
    if (!snapshot || terminalStatuses.has(snapshot.task.status)) return;
    const timer = setInterval(() => { void load(); }, 2500);
    return () => clearInterval(timer);
  }, [snapshot?.task.status, load]);


  const retry = async () => {
    if (!snapshot || busy || snapshot.task.status !== "failed") return;
    setBusy(true);
    setNotice("");
    try {
      await retryAgentTask(snapshot.task.id);
      await load();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذرت إعادة المحاولة.");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!snapshot || busy || terminalStatuses.has(snapshot.task.status)) return;
    setBusy(true);
    setNotice("");
    try {
      await cancelAgentTask(snapshot.task.id);
      await load();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر طلب إلغاء المهمة.");
    } finally {
      setBusy(false);
    }
  };

  const showApprovalDetails = async (engineRunId: string, requestId: string) => {
    const key = approvalKey(engineRunId, requestId);
    if (!snapshot || approvalDetailsLoadingId) return;
    setApprovalDetailsLoadingId(key);
    setNotice("");
    try {
      const details = await getAgentApprovalDetails(snapshot.task.id, engineRunId, requestId);
      setApprovalDetails((current) => ({ ...current, [key]: details }));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر تحميل تفاصيل العملية.");
    } finally {
      setApprovalDetailsLoadingId(null);
    }
  };

  const resolveApproval = async (engineRunId: string, requestId: string, choice: "once" | "deny") => {
    const key = approvalKey(engineRunId, requestId);
    if (!snapshot || approvalBusyId) return;
    setApprovalBusyId(key);
    setNotice("");
    setActionMessage("");
    try {
      await resolveAgentApproval(snapshot.task.id, engineRunId, requestId, choice);
      await load();
      setActionMessage(choice === "once" ? "تمت الموافقة على هذه العملية فقط." : "تم رفض العملية.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر إرسال قرار الموافقة.");
    } finally {
      setApprovalBusyId(null);
    }
  };

  const steer = async (engineRunId: string) => {
    if (!snapshot || !steerDraft.trim() || steeringRunId) return;
    setSteeringRunId(engineRunId);
    setNotice("");
    setActionMessage("");
    try {
      await steerAgentRun(snapshot.task.id, engineRunId, steerDraft);
      setSteerDraft("");
      await load();
      setActionMessage("تم إرسال التوجيه إلى Hermes.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر إرسال التوجيه.");
    } finally {
      setSteeringRunId(null);
    }
  };

  const pendingApprovals = snapshot?.engine_events.filter((event) =>
    event.event_name === "approval.request"
    && !!event.approval_request_id
    && !snapshot.engine_events.some((candidate) =>
      candidate.event_name === "approval.responded"
      && candidate.approval_request_id === event.approval_request_id
      && candidate.engine_run_id === event.engine_run_id
    )
  ) ?? [];

  if (!user) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}>
          <Text style={styles.title}>سجّل الدخول لعرض المهمة</Text>
          <Pressable style={styles.primaryButton} onPress={() => router.push("/auth")}>
            <Text style={styles.primaryText}>تسجيل الدخول</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <Pressable style={styles.back} onPress={() => router.back()}>
            <Text style={styles.backText}>→</Text>
          </Pressable>
          <View style={styles.headerCopy}>
            <Text style={styles.title}>تفاصيل المهمة</Text>
            <Text style={styles.subtitle}>متابعة التنفيذ والنتائج</Text>
          </View>
          <Pressable style={styles.refresh} onPress={() => void load()} disabled={loading}>
            <Text style={styles.refreshText}>تحديث</Text>
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={styles.content}>
          {loading ? (
            <View style={styles.stateCard}><ActivityIndicator color={colors.gold} /></View>
          ) : notice && !snapshot ? (
            <View style={styles.card}><Text style={styles.error}>{notice}</Text></View>
          ) : snapshot ? (
            <>
              <View style={styles.card}>
                <Text style={styles.status}>{statusLabel(snapshot.task.status)}</Text>
                <Text style={styles.taskTitle}>{snapshot.task.title}</Text>
                <Text style={styles.muted}>أُنشئت في {formatDate(snapshot.task.created_at)}</Text>
                <Text style={styles.sectionTitle}>الطلب</Text>
                <Text style={styles.body}>{snapshot.task.request}</Text>
                {!!snapshot.task.error_message && (
                  <>
                    <Text style={styles.sectionTitle}>سبب التعثر</Text>
                    <Text style={styles.error}>{snapshot.task.error_message}</Text>
                  </>
                )}
                {!terminalStatuses.has(snapshot.task.status) && (
                  <Pressable style={styles.cancelButton} onPress={cancel} disabled={busy}>
                    {busy ? <ActivityIndicator color="#E88787" /> : <Text style={styles.cancelText}>طلب إلغاء المهمة</Text>}
                  </Pressable>
                )}
                {snapshot.task.status === "failed" && (
                  <View style={styles.retryBox}>
                    <Text style={styles.muted}>
                      المحاولات اليدوية المستخدمة: {snapshot.task.manual_retry_count ?? 0} من 2
                    </Text>
                    {(snapshot.task.manual_retry_count ?? 0) < 2 ? (
                      <Pressable style={styles.retryButton} onPress={retry} disabled={busy}>
                        {busy ? <ActivityIndicator color={colors.gold} /> : <Text style={styles.retryText}>إعادة محاولة المهمة</Text>}
                      </Pressable>
                    ) : (
                      <Text style={styles.error}>وصلت المهمة إلى الحد الأقصى لإعادة المحاولة اليدوية.</Text>
                    )}
                  </View>
                )}
              </View>

              <Text style={styles.sectionHeading}>خطوات التنفيذ ({snapshot.steps.length})</Text>
              {snapshot.steps.length === 0 ? (
                <View style={styles.card}><Text style={styles.muted}>لم تُسجّل خطوات لهذه المهمة بعد.</Text></View>
              ) : snapshot.steps.map((step, index) => (
                <View key={step.id} style={styles.card}>
                  <View style={styles.stepHeader}>
                    <Text style={styles.status}>{statusLabel(step.status)}</Text>
                    <Text style={styles.stepTitle}>{index + 1}. {step.title}</Text>
                  </View>
                  <Text style={styles.muted}>المحاولات: {step.attempt_count} من {step.max_attempts}</Text>
                  {!!step.error_message && <Text style={styles.error}>{step.error_message}</Text>}
                  {typeof step.output?.change_set_id === "string" && (
                    <View style={styles.reviewBox}>
                      <Text style={styles.sectionTitle}>مراجعة تغييرات OpenCode</Text>
                      {changeSets[step.output.change_set_id]?.loading ? (
                        <View style={styles.inlineLoading}><ActivityIndicator color={colors.gold} /><Text style={styles.muted}>جارٍ تحميل ملفات التغيير...</Text></View>
                      ) : changeSets[step.output.change_set_id]?.error ? (
                        <View style={styles.reviewActions}>
                          <Text style={styles.error}>{changeSets[step.output.change_set_id]?.error}</Text>
                          <Pressable style={styles.detailsButton} onPress={() => void reloadChangeSet(step.output!.change_set_id as string)}><Text style={styles.steerText}>إعادة التحميل</Text></Pressable>
                        </View>
                      ) : changeSets[step.output.change_set_id]?.item ? (
                        <>
                          <Text style={styles.muted}>الحالة: {changeSets[step.output.change_set_id]!.item!.status} · {changeSets[step.output.change_set_id]!.item!.changes.length} ملف</Text>
                          {changeSets[step.output.change_set_id]!.item!.changes.map((change, changeIndex) => (
                            <View key={change.path + change.action + changeIndex} style={styles.changeCard}>
                              <Text style={styles.changePath}>{change.action === "create" ? "إنشاء" : change.action === "update" ? "تعديل" : "حذف"}: {change.path}</Text>
                              <Text selectable style={styles.changeDiff}>{change.diff.slice(0, 8000)}{change.diff.length > 8000 ? "\n… تم اختصار المعاينة (8KB)." : ""}</Text>
                            </View>
                          ))}
                          {changeSets[step.output.change_set_id]!.item!.status === "review_ready" && (
                            <View style={styles.reviewActions}>
                              <Pressable style={styles.applyButton} onPress={() => void decideChangeSet(step.output!.change_set_id as string, "apply")} disabled={changeSetBusyId !== null}>
                                {changeSetBusyId === step.output.change_set_id ? <ActivityIndicator color={colors.background} /> : <Text style={styles.applyText}>اعتماد وتطبيق التغييرات</Text>}
                              </Pressable>
                              <Pressable style={styles.denyButton} onPress={() => void decideChangeSet(step.output!.change_set_id as string, "reject")} disabled={changeSetBusyId !== null}>
                                <Text style={styles.denyText}>رفض التغييرات</Text>
                              </Pressable>
                            </View>
                          )}
                        </>
                      ) : (
                        <Text style={styles.muted}>لم تُرجع مجموعة تغييرات للمراجعة.</Text>
                      )}
                    </View>
                  )}
                  {step.output && (
                    <>
                      <Text style={styles.sectionTitle}>الناتج</Text>
                      {typeof step.output.content === "string" ? (
                        <Text selectable style={styles.output}>{step.output.content}</Text>
                      ) : typeof step.output.preview === "string" ? (
                        <Text selectable style={styles.output}>{step.output.preview}</Text>
                      ) : (
                        <Text selectable style={styles.output}>{pretty(step.output)}</Text>
                      )}
                    </>
                  )}
                </View>
              ))}

              {(snapshot.engine_runs?.length ?? 0) > 0 && (
                <>
                  <Text style={styles.sectionHeading}>سجل تشغيل المحركات ({snapshot.engine_runs.length})</Text>
                  {snapshot.engine_runs.map((run) => (
                    <View key={run.id} style={styles.card}>
                      <View style={styles.stepHeader}>
                        <Text style={styles.status}>{statusLabel(run.status)}</Text>
                        <Text style={styles.stepTitle}>{run.engine_id}</Text>
                      </View>
                      <Text style={styles.muted}>المحاولة رقم {run.attempt_count}</Text>
                      <Text style={styles.muted}>بدأت: {formatDate(run.started_at)}</Text>
                      {!!run.completed_at && <Text style={styles.muted}>انتهت: {formatDate(run.completed_at)}</Text>}
                      {!!run.error_code && <Text style={styles.error}>رمز الخطأ: {run.error_code}</Text>}
                      {run.engine_id === "hermes-agent" && run.status === "running" && (
                        <View style={styles.steerBox}>
                          <TextInput
                            value={steerDraft}
                            onChangeText={setSteerDraft}
                            placeholder="أرسل توجيهًا إضافيًا إلى الوكيل..."
                            placeholderTextColor={colors.faint}
                            multiline
                            maxLength={20000}
                            style={styles.steerInput}
                            textAlign="right"
                          />
                          <Pressable
                            style={[styles.steerButton, (!steerDraft.trim() || steeringRunId !== null) && styles.disabledButton]}
                            onPress={() => void steer(run.id)}
                            disabled={!steerDraft.trim() || steeringRunId !== null}
                          >
                            {steeringRunId === run.id
                              ? <ActivityIndicator color={colors.gold} />
                              : <Text style={styles.steerText}>إرسال توجيه</Text>}
                          </Pressable>
                        </View>
                      )}
                    </View>
                  ))}
                </>
              )}

              {pendingApprovals.length > 0 && (
                <>
                  <Text style={styles.sectionHeading}>موافقات مطلوبة ({pendingApprovals.length})</Text>
                  {pendingApprovals.map((event) => (
                    <View key={event.id} style={styles.approvalCard}>
                      <Text style={styles.approvalTitle}>المحرك ينتظر قرارك</Text>
                      <Text style={styles.muted}>اعرض تفاصيل العملية أولًا. لن تتم الموافقة قبل عرض ما أرسله Hermes بعد تنقيح بياناته.</Text>
                      {approvalDetails[approvalKey(event.engine_run_id, event.approval_request_id!)] ? (
                        <View style={styles.approvalDetails}>
                          {!!approvalDetails[approvalKey(event.engine_run_id, event.approval_request_id!)].description && (
                            <Text style={styles.body}>{approvalDetails[approvalKey(event.engine_run_id, event.approval_request_id!)].description}</Text>
                          )}
                          {!!approvalDetails[approvalKey(event.engine_run_id, event.approval_request_id!)].command && (
                            <Text selectable style={styles.approvalCommand}>{approvalDetails[approvalKey(event.engine_run_id, event.approval_request_id!)].command}</Text>
                          )}
                        </View>
                      ) : (
                        <Pressable
                          style={[styles.detailsButton, approvalDetailsLoadingId !== null && styles.disabledButton]}
                          disabled={approvalDetailsLoadingId !== null}
                          onPress={() => void showApprovalDetails(event.engine_run_id, event.approval_request_id!)}
                        >
                          {approvalDetailsLoadingId === approvalKey(event.engine_run_id, event.approval_request_id!)
                            ? <ActivityIndicator color={colors.gold} />
                            : <Text style={styles.steerText}>عرض تفاصيل العملية</Text>}
                        </Pressable>
                      )}
                      {!!approvalDetails[approvalKey(event.engine_run_id, event.approval_request_id!)] && (
                        <View style={styles.approvalActions}>
                          <Pressable
                            style={[styles.approveButton, approvalBusyId !== null && styles.disabledButton]}
                            disabled={approvalBusyId !== null}
                            onPress={() => void resolveApproval(event.engine_run_id, event.approval_request_id!, "once")}
                          >
                            {approvalBusyId === approvalKey(event.engine_run_id, event.approval_request_id!)
                              ? <ActivityIndicator color={colors.background} />
                              : <Text style={styles.approveText}>موافقة لمرة واحدة</Text>}
                          </Pressable>
                          <Pressable
                            style={[styles.denyButton, approvalBusyId !== null && styles.disabledButton]}
                            disabled={approvalBusyId !== null}
                            onPress={() => void resolveApproval(event.engine_run_id, event.approval_request_id!, "deny")}
                          >
                            <Text style={styles.denyText}>رفض</Text>
                          </Pressable>
                        </View>
                      )}
                    </View>
                  ))}
                </>
              )}

              {(snapshot.engine_events?.length ?? 0) > 0 && (
                <>
                  <Text style={styles.sectionHeading}>تحديثات التنفيذ ({snapshot.engine_events.length})</Text>
                  <View style={styles.card}>
                    {snapshot.engine_events.map((event) => (
                      <View key={event.id} style={styles.eventRow}>
                        <View style={styles.eventCopy}>
                          <Text style={styles.stepTitle}>{eventLabel(event.event_name)}</Text>
                          <Text style={styles.muted}>
                            {formatDate(event.received_at)}
                            {event.event_seq != null ? " · #" + event.event_seq : ""}
                          </Text>
                        </View>
                        <View style={styles.eventDot} />
                      </View>
                    ))}
                  </View>
                </>
              )}
            </>
          ) : null}
          {!!notice && !!snapshot && <Text style={styles.error}>{notice}</Text>}
          {!!actionMessage && <Text style={styles.success}>{actionMessage}</Text>}
        </ScrollView>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  page: { flex: 1, width: "100%", maxWidth: 900, alignSelf: "center", backgroundColor: colors.background },
  header: { minHeight: 72, paddingHorizontal: 18, flexDirection: "row", alignItems: "center", gap: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  backText: { color: colors.gold, fontSize: 25 },
  headerCopy: { flex: 1 },
  title: { color: colors.text, fontSize: 19, fontWeight: "800", textAlign: "right" },
  subtitle: { color: colors.faint, fontSize: 11, marginTop: 3, textAlign: "right" },
  refresh: { paddingHorizontal: 13, paddingVertical: 9, borderWidth: 1, borderColor: colors.border, borderRadius: 10 },
  refreshText: { color: colors.gold, fontSize: 12, fontWeight: "700" },
  content: { padding: 16, gap: 13, paddingBottom: 36 },
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: 16, padding: 16, gap: 9 },
  stateCard: { minHeight: 150, alignItems: "center", justifyContent: "center" },
  status: { color: colors.gold, fontSize: 12, fontWeight: "800", textAlign: "right" },
  taskTitle: { color: colors.text, fontSize: 17, fontWeight: "800", textAlign: "right" },
  sectionHeading: { color: colors.gold, fontSize: 16, fontWeight: "800", textAlign: "right", marginTop: 5 },
  sectionTitle: { color: colors.text, fontSize: 13, fontWeight: "800", textAlign: "right", marginTop: 8 },
  body: { color: colors.text, fontSize: 14, lineHeight: 23, textAlign: "right" },
  muted: { color: colors.faint, fontSize: 11, textAlign: "right" },
  error: { color: "#E88787", fontSize: 12, textAlign: "right", lineHeight: 20 },
  stepHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  stepTitle: { color: colors.text, fontSize: 14, fontWeight: "700", textAlign: "right", flex: 1 },
  reviewBox: { marginTop: 8, padding: 12, borderRadius: 12, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.goldDark, gap: 10 },
  inlineLoading: { flexDirection: "row", alignItems: "center", justifyContent: "flex-end", gap: 8 },
  changeCard: { borderWidth: 1, borderColor: colors.border, borderRadius: 9, overflow: "hidden", gap: 6 },
  changePath: { color: colors.gold, fontSize: 11, fontWeight: "700", textAlign: "right", padding: 8 },
  changeDiff: { color: colors.text, fontSize: 10, lineHeight: 16, textAlign: "left", backgroundColor: colors.surface, padding: 9, borderRadius: 6 },
  reviewActions: { flexDirection: "row", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "flex-start" },
  applyButton: { minHeight: 40, borderRadius: 9, backgroundColor: colors.gold, paddingHorizontal: 14, alignItems: "center", justifyContent: "center" },
  applyText: { color: colors.background, fontSize: 12, fontWeight: "800" },
  output: { color: colors.text, fontSize: 11, lineHeight: 18, textAlign: "left", backgroundColor: colors.background, padding: 10, borderRadius: 8, overflow: "hidden" },
  cancelButton: { borderWidth: 1, borderColor: "#8D4444", borderRadius: 10, padding: 12, alignItems: "center", marginTop: 8 },
  cancelText: { color: "#E88787", fontSize: 13, fontWeight: "700" },
  retryBox: { marginTop: 8, gap: 9 },
  retryButton: { borderWidth: 1, borderColor: colors.goldDark, borderRadius: 10, padding: 12, alignItems: "center" },
  retryText: { color: colors.gold, fontSize: 13, fontWeight: "700" },
  approvalCard: { backgroundColor: colors.surface, borderColor: colors.goldDark, borderWidth: 1, borderRadius: 14, padding: 15, gap: 10 },
  approvalTitle: { color: colors.gold, fontSize: 14, fontWeight: "800", textAlign: "right" },
  approvalDetails: { backgroundColor: colors.background, borderRadius: 9, padding: 10, gap: 8 },
  approvalCommand: { color: colors.text, fontSize: 12, lineHeight: 19, textAlign: "left" },
  detailsButton: { alignSelf: "flex-start", borderWidth: 1, borderColor: colors.goldDark, borderRadius: 9, paddingHorizontal: 13, paddingVertical: 9 },
  approvalActions: { flexDirection: "row", gap: 9, justifyContent: "flex-start" },
  approveButton: { backgroundColor: colors.gold, borderRadius: 9, paddingHorizontal: 13, paddingVertical: 10, alignItems: "center" },
  approveText: { color: colors.background, fontSize: 12, fontWeight: "800" },
  denyButton: { borderWidth: 1, borderColor: "#8D4444", borderRadius: 9, paddingHorizontal: 16, paddingVertical: 10, alignItems: "center" },
  denyText: { color: "#E88787", fontSize: 12, fontWeight: "800" },
  eventRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border },
  eventCopy: { flex: 1, gap: 4 },
  eventDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.gold },
  steerBox: { marginTop: 8, gap: 8 },
  steerInput: { minHeight: 72, maxHeight: 150, color: colors.text, backgroundColor: colors.background, borderColor: colors.border, borderWidth: 1, borderRadius: 10, padding: 10, fontSize: 13, textAlignVertical: "top" },
  steerButton: { alignSelf: "flex-start", borderWidth: 1, borderColor: colors.goldDark, borderRadius: 9, paddingHorizontal: 14, paddingVertical: 9, minWidth: 110, alignItems: "center" },
  steerText: { color: colors.gold, fontSize: 12, fontWeight: "800" },
  disabledButton: { opacity: 0.45 },
  success: { color: colors.gold, fontSize: 12, textAlign: "right" },
  primaryButton: { backgroundColor: colors.gold, padding: 13, borderRadius: 10, marginTop: 12 },
  primaryText: { color: colors.background, fontWeight: "800" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, gap: 12 },
});
