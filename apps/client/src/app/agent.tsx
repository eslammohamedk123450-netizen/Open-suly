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
import { router } from "expo-router";
import { colors } from "@/theme/tokens";
import { useAuth } from "@/providers/AuthProvider";
import {
  cancelAgentTask,
  createAgentTask,
  getAgentTask,
  getAgentToolCatalog,
  grantAIApproval,
  grantHermesApproval,
  type AgentOperation,
  type AgentTaskSnapshot,
} from "@/lib/agent-tasks";

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
  };
  return labels[status] ?? status;
}

export default function AgentScreen() {
  const { user } = useAuth();
  const [operation, setOperation] = useState<AgentOperation>("text.analyze");
  const [prompt, setPrompt] = useState("");
  const [snapshot, setSnapshot] = useState<AgentTaskSnapshot | null>(null);
  const [approved, setApproved] = useState(false);
  const [aiApproved, setAiApproved] = useState(false);
  const [aiAvailable, setAiAvailable] = useState(false);
  const [hermesAvailable, setHermesAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [approving, setApproving] = useState(false);
  const [notice, setNotice] = useState("");
  const [loadingCatalog, setLoadingCatalog] = useState(true);

  const refreshCatalog = useCallback(async () => {
    try {
      const items = await getAgentToolCatalog();
      const hermes = items.find((item) => item.name === "hermes.agent.turn");
      const ai = items.find((item) => item.name === "ai.respond");
      setApproved(Boolean(hermes?.approved));
      setHermesAvailable(Boolean(hermes?.available));
      setAiApproved(Boolean(ai?.approved));
      setAiAvailable(Boolean(ai?.available));
      setNotice("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر تحميل أدوات الوكيل.");
    } finally {
      setLoadingCatalog(false);
    }
  }, []);

  useEffect(() => {
    if (!user) {
      setLoadingCatalog(false);
      return;
    }
    void refreshCatalog();
  }, [user?.id, refreshCatalog]);

  useEffect(() => {
    const taskId = snapshot?.task.id;
    if (!taskId || terminalStatuses.has(snapshot.task.status)) return;
    let active = true;
    const timer = setInterval(() => {
      void getAgentTask(taskId)
        .then((next) => { if (active) setSnapshot(next); })
        .catch((error) => {
          if (active) setNotice(error instanceof Error ? error.message : "تعذر تحديث حالة المهمة.");
        });
    }, 2500);
    return () => { active = false; clearInterval(timer); };
  }, [snapshot?.task.id, snapshot?.task.status]);

  const enableSelectedApproval = async () => {
    if (!user) { router.push("/auth"); return; }
    setApproving(true);
    setNotice("");
    try {
      if (operation === "ai.respond") {
        await grantAIApproval();
        setAiApproved(true);
        setNotice("تم حفظ موافقتك على استخدام مزود الذكاء الاصطناعي. يمكنك إلغاء الموافقة لاحقًا.");
      } else {
        await grantHermesApproval();
        setApproved(true);
        setNotice("تم حفظ موافقتك على نطاق تشغيل Hermes. يمكنك إلغاء هذه الموافقة من إعدادات الصلاحيات لاحقًا.");
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر حفظ الموافقة.");
    } finally {
      setApproving(false);
    }
  };

  const submit = async () => {
    if (!user) { router.push("/auth"); return; }
    if (!prompt.trim() || busy) return;
    if (operation === "ai.respond" && !aiAvailable) {
      setNotice("مزود الذكاء الاصطناعي غير مضبوط على الخادم بعد. يلزم إعداد AI_PROVIDER وAI_BASE_URL وAI_API_KEY وAI_MODEL.");
      return;
    }
    if (operation === "ai.respond" && !aiApproved) {
      setNotice("يجب منح موافقة صريحة على استخدام مزود الذكاء الاصطناعي أولًا.");
      return;
    }
    if (operation === "hermes.agent.turn" && !hermesAvailable) {
      setNotice("خدمة Hermes نفسها غير مهيأة أو متوقفة على الخادم. يمكنك اختبار محرك المهام الآن، أما Hermes فيحتاج تجهيز بيئته الآمنة ومزود النموذج.");
      return;
    }
    if (operation === "hermes.agent.turn" && !approved) {
      setNotice("يجب منح موافقة صريحة على تشغيل Hermes أولًا.");
      return;
    }
    setBusy(true);
    setNotice("");
    setSnapshot(null);
    try {
      const created = await createAgentTask(operation, prompt);
      setPrompt("");
      const current = await getAgentTask(created.id);
      setSnapshot(current);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر إنشاء المهمة.");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!snapshot || busy) return;
    setBusy(true);
    try {
      await cancelAgentTask(snapshot.task.id);
      const next = await getAgentTask(snapshot.task.id);
      setSnapshot(next);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر إلغاء المهمة.");
    } finally {
      setBusy(false);
    }
  };

  if (!user) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}>
          <Text style={styles.title}>مساحة الوكيل</Text>
          <Text style={styles.muted}>سجّل الدخول لاستخدام المهام ومتابعة تنفيذها.</Text>
          <Pressable style={styles.primaryButton} onPress={() => router.push("/auth")}><Text style={styles.primaryText}>تسجيل الدخول</Text></Pressable>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} style={styles.back}><Text style={styles.backText}>→</Text></Pressable>
          <View style={styles.headerCopy}>
            <Text style={styles.title}>مساحة الوكيل</Text>
            <Text style={styles.muted}>مهام محفوظة وتنفيذ قابل للتتبع</Text>
          </View>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
        </View>

        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.intro}>
            <Text style={styles.introTitle}>حوّل طلبك إلى مهمة</Text>
            <Text style={styles.muted}>ابدأ باختبار محرك المهام، أو اختر Hermes Agent عند تهيئة خدمته ومنح الصلاحية.</Text>
          </View>

          <View style={styles.card}>
            <Text style={styles.label}>محرك التنفيذ</Text>
            <View style={styles.modeRow}>
              <Pressable style={[styles.mode, operation === "text.analyze" && styles.modeActive]} onPress={() => setOperation("text.analyze")}>
                <Text style={[styles.modeTitle, operation === "text.analyze" && styles.gold]}>اختبار محرك المهام</Text>
                <Text style={styles.modeHint}>تحليل نص بدون مزود ذكاء اصطناعي</Text>
              </Pressable>
              <Pressable style={[styles.mode, operation === "ai.respond" && styles.modeActive]} onPress={() => setOperation("ai.respond")}>
                <Text style={[styles.modeTitle, operation === "ai.respond" && styles.gold]}>SULY AI</Text>
                <Text style={styles.modeHint}>رد ذكي عبر مزود النموذج</Text>
              </Pressable>
              <Pressable style={[styles.mode, operation === "hermes.agent.turn" && styles.modeActive]} onPress={() => setOperation("hermes.agent.turn")}>
                <Text style={[styles.modeTitle, operation === "hermes.agent.turn" && styles.gold]}>Hermes Agent</Text>
                <Text style={styles.modeHint}>يتطلب Runtime ومزود نموذج</Text>
              </Pressable>
            </View>

            {operation === "ai.respond" && (
              <View style={styles.approvalBox}>
                <View style={styles.approvalHeader}>
                  <Text style={styles.label}>موافقة استخدام مزود AI</Text>
                  <Text style={[styles.approvalState, aiApproved ? styles.good : styles.warn]}>{aiApproved ? "مفعّلة" : "غير مفعّلة"}</Text>
                </View>
                <Text style={styles.modeHint}>كل طلب قد يستهلك رصيدًا لدى مزود النموذج. الموافقة تخص نطاق ai.provider.run فقط.</Text>
                <Text style={[styles.modeHint, aiAvailable ? styles.good : styles.warn]}>{aiAvailable ? "مزود AI مضبوط على الخادم." : "مزود AI غير مضبوط أو متوقف حاليًا."}</Text>
                {!aiApproved && (
                  <Pressable style={styles.secondaryButton} onPress={enableSelectedApproval} disabled={approving || loadingCatalog}>
                    {approving ? <ActivityIndicator color={colors.gold} /> : <Text style={styles.secondaryText}>أوافق على استخدام AI</Text>}
                  </Pressable>
                )}
              </View>
            )}

            {operation === "hermes.agent.turn" && (
              <View style={styles.approvalBox}>
                <View style={styles.approvalHeader}>
                  <Text style={styles.label}>موافقة تشغيل Hermes</Text>
                  <Text style={[styles.approvalState, approved ? styles.good : styles.warn]}>{approved ? "مفعّلة" : "غير مفعّلة"}</Text>
                </View>
                <Text style={styles.modeHint}>الموافقة تمنح نطاق agent.hermes.run فقط. لا تفعّل أدوات النظام أو الطرفية تلقائيًا.</Text>
                <Text style={[styles.modeHint, hermesAvailable ? styles.good : styles.warn]}>
                  {hermesAvailable ? "خدمة Hermes مهيأة على الخادم." : "الخادم لا يعلن جاهزية Hermes حاليًا."}
                </Text>
                {!approved && (
                  <Pressable style={styles.secondaryButton} onPress={enableSelectedApproval} disabled={approving || loadingCatalog}>
                    {approving ? <ActivityIndicator color={colors.gold} /> : <Text style={styles.secondaryText}>أوافق على تشغيل Hermes</Text>}
                  </Pressable>
                )}
              </View>
            )}

            <Text style={styles.label}>وصف المهمة</Text>
            <TextInput
              value={prompt}
              onChangeText={setPrompt}
              placeholder={operation === "text.analyze" ? "اكتب نصًا لاختبار التحليل..." : "اكتب ما تريد من Hermes إنجازه..."}
              placeholderTextColor={colors.faint}
              multiline
              textAlign="right"
              textAlignVertical="top"
              style={styles.input}
              maxLength={20000}
            />
            <Text style={styles.counter}>{prompt.length.toLocaleString("en-US")} / 20,000</Text>
            <Pressable style={[styles.primaryButton, (!prompt.trim() || busy || (operation === "hermes.agent.turn" && !approved) || (operation === "ai.respond" && !aiApproved)) && styles.disabled]} onPress={submit} disabled={!prompt.trim() || busy || (operation === "hermes.agent.turn" && !approved) || (operation === "ai.respond" && !aiApproved)}>
              {busy ? <ActivityIndicator color={colors.background} /> : <Text style={styles.primaryText}>إنشاء المهمة وتشغيلها</Text>}
            </Pressable>
          </View>

          {!!notice && <Text style={styles.notice}>{notice}</Text>}

          {snapshot && (
            <View style={styles.card}>
              <View style={styles.taskHeader}>
                <Text style={styles.label}>حالة المهمة</Text>
                <Text style={[styles.status, snapshot.task.status === "completed" ? styles.good : snapshot.task.status === "failed" ? styles.bad : styles.gold]}>{statusLabel(snapshot.task.status)}</Text>
              </View>
              <Text style={styles.taskTitle}>{snapshot.task.title}</Text>
              <Text style={styles.taskId}>ID: {snapshot.task.id}</Text>
              {snapshot.steps.map((step) => (
                <View key={step.id} style={styles.step}>
                  <View style={styles.taskHeader}>
                    <Text style={styles.stepTitle}>{step.title}</Text>
                    <Text style={styles.stepStatus}>{statusLabel(step.status)}</Text>
                  </View>
                  <Text style={styles.modeHint}>المحاولة {step.attempt_count} من {step.max_attempts}</Text>
                  {!!step.error_message && <Text style={styles.error}>{step.error_message}</Text>}
                  {step.output && Object.keys(step.output).length > 0 && (
                    <Text style={styles.output}>{JSON.stringify(step.output, null, 2)}</Text>
                  )}
                </View>
              ))}
              {!terminalStatuses.has(snapshot.task.status) && (
                <Pressable style={styles.cancelButton} onPress={cancel} disabled={busy}><Text style={styles.cancelText}>إلغاء المهمة</Text></Pressable>
              )}
              {snapshot.task.status === "failed" && !!snapshot.task.error_message && <Text style={styles.error}>{snapshot.task.error_message}</Text>}
            </View>
          )}
        </ScrollView>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  page: { flex: 1, width: "100%", maxWidth: 1100, alignSelf: "center", backgroundColor: colors.background },
  header: { minHeight: 70, paddingHorizontal: 18, flexDirection: "row", alignItems: "center", gap: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  back: { width: 40, height: 40, borderRadius: 13, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  backText: { color: colors.gold, fontSize: 22 },
  headerCopy: { flex: 1 },
  title: { color: colors.text, fontSize: 17, fontWeight: "800", textAlign: "right" },
  muted: { color: colors.muted, fontSize: 11, lineHeight: 20, textAlign: "right", marginTop: 4 },
  logo: { width: 40, height: 40, borderRadius: 13, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  logoText: { color: colors.gold, fontSize: 22, fontWeight: "800" },
  content: { padding: 18, paddingBottom: 40, gap: 14, width: "100%", maxWidth: 760, alignSelf: "center" },
  intro: { gap: 7, marginBottom: 5 },
  introTitle: { color: colors.text, fontSize: 22, fontWeight: "800", textAlign: "right" },
  card: { padding: 16, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, gap: 12 },
  label: { color: colors.text, fontSize: 13, fontWeight: "700", textAlign: "right" },
  modeRow: { flexDirection: "row", gap: 9 },
  mode: { flex: 1, padding: 12, borderRadius: 13, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, gap: 5 },
  modeActive: { borderColor: colors.gold, backgroundColor: colors.surfaceSecondary },
  modeTitle: { color: colors.text, fontSize: 12, fontWeight: "700", textAlign: "right" },
  modeHint: { color: colors.muted, fontSize: 10, lineHeight: 18, textAlign: "right" },
  gold: { color: colors.gold },
  approvalBox: { padding: 12, borderRadius: 13, backgroundColor: colors.background, gap: 9 },
  approvalHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  approvalState: { fontSize: 11, fontWeight: "700" },
  good: { color: "#69C99A" },
  warn: { color: "#E8B85C" },
  bad: { color: "#E88787" },
  secondaryButton: { minHeight: 40, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.goldDark, borderRadius: 11 },
  secondaryText: { color: colors.gold, fontSize: 12, fontWeight: "700" },
  input: { minHeight: 130, borderRadius: 13, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, padding: 13, color: colors.text, fontSize: 13, lineHeight: 22 },
  counter: { color: colors.faint, fontSize: 10, textAlign: "left" },
  primaryButton: { minHeight: 46, borderRadius: 13, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center", paddingHorizontal: 14 },
  primaryText: { color: colors.background, fontSize: 13, fontWeight: "800" },
  disabled: { opacity: 0.45 },
  notice: { color: colors.gold, fontSize: 11, lineHeight: 19, textAlign: "right" },
  taskHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  status: { fontSize: 11, fontWeight: "700" },
  taskTitle: { color: colors.text, fontSize: 14, fontWeight: "700", textAlign: "right" },
  taskId: { color: colors.faint, fontSize: 9, textAlign: "left" },
  step: { padding: 12, borderRadius: 12, backgroundColor: colors.background, gap: 7 },
  stepTitle: { color: colors.text, fontSize: 12, fontWeight: "700" },
  stepStatus: { color: colors.gold, fontSize: 10 },
  output: { color: colors.muted, fontSize: 10, lineHeight: 17, textAlign: "left" },
  error: { color: "#E88787", fontSize: 10, lineHeight: 17, textAlign: "right" },
  cancelButton: { minHeight: 40, borderRadius: 11, borderWidth: 1, borderColor: "#9B5656", alignItems: "center", justifyContent: "center" },
  cancelText: { color: "#E88787", fontSize: 12, fontWeight: "700" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 25, gap: 12 },
});
