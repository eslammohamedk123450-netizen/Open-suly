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
import { cancelAgentTask, getAgentTask, resolveAgentApproval, retryAgentTask, steerAgentRun, type AgentTaskSnapshot } from "@/lib/agent-tasks";

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

  const resolveApproval = async (engineRunId: string, requestId: string, choice: "once" | "deny") => {
    if (!snapshot || approvalBusyId) return;
    setApprovalBusyId(requestId);
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
                  {step.output && (
                    <>
                      <Text style={styles.sectionTitle}>الناتج</Text>
                      <Text selectable style={styles.output}>{pretty(step.output)}</Text>
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
                      <Text style={styles.muted}>اختر السماح بهذه العملية مرة واحدة أو رفضها. لن يتم منح صلاحية دائمة.</Text>
                      <View style={styles.approvalActions}>
                        <Pressable
                          style={[styles.approveButton, approvalBusyId !== null && styles.disabledButton]}
                          disabled={approvalBusyId !== null}
                          onPress={() => void resolveApproval(event.engine_run_id, event.approval_request_id!, "once")}
                        >
                          {approvalBusyId === event.approval_request_id
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
  output: { color: colors.text, fontSize: 11, lineHeight: 18, textAlign: "left", backgroundColor: colors.background, padding: 10, borderRadius: 8, overflow: "hidden" },
  cancelButton: { borderWidth: 1, borderColor: "#8D4444", borderRadius: 10, padding: 12, alignItems: "center", marginTop: 8 },
  cancelText: { color: "#E88787", fontSize: 13, fontWeight: "700" },
  retryBox: { marginTop: 8, gap: 9 },
  retryButton: { borderWidth: 1, borderColor: colors.goldDark, borderRadius: 10, padding: 12, alignItems: "center" },
  retryText: { color: colors.gold, fontSize: 13, fontWeight: "700" },
  approvalCard: { backgroundColor: colors.surface, borderColor: colors.goldDark, borderWidth: 1, borderRadius: 14, padding: 15, gap: 10 },
  approvalTitle: { color: colors.gold, fontSize: 14, fontWeight: "800", textAlign: "right" },
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
