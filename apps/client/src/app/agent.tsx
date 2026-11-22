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
import {
  cancelAgentTask,
  createAgentTask,
  getAgentTask,
  getAgentToolCatalog,
  getAgentCatalog,
  getHermesSkillCatalog,
  getHermesToolsetCatalog,
  grantAIApproval,
  grantHermesApproval,
  grantOpenCodeApproval,
  revokeToolApproval,
  type AgentOperation,
  type AgentTaskSnapshot,
  type AgentProfile,
  type HermesSkill,
  type HermesToolset,
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
  const params = useLocalSearchParams<{ prompt?: string | string[]; projectId?: string | string[]; conversationId?: string | string[]; operation?: string | string[] }>();
  const initialPrompt = typeof params.prompt === "string" ? params.prompt : "";
  const projectId = typeof params.projectId === "string" ? params.projectId : undefined;
  const conversationId = typeof params.conversationId === "string" ? params.conversationId : undefined;
  const requestedOperation = typeof params.operation === "string" ? params.operation : undefined;
  const initialOperation: AgentOperation = requestedOperation === "ai.respond"
    || requestedOperation === "text.analyze"
    || requestedOperation === "hermes.agent.turn"
    || requestedOperation === "opencode.task.run"
    ? requestedOperation
    : conversationId ? "hermes.agent.turn" : initialPrompt ? "ai.respond" : "text.analyze";
  const [operation, setOperation] = useState<AgentOperation>(
    initialOperation,
  );
  const [prompt, setPrompt] = useState(initialPrompt);
  const [snapshot, setSnapshot] = useState<AgentTaskSnapshot | null>(null);
  const [approved, setApproved] = useState(false);
  const [aiApproved, setAiApproved] = useState(false);
  const [aiAvailable, setAiAvailable] = useState(false);
  const [hermesAvailable, setHermesAvailable] = useState(false);
  const [opencodeAvailable, setOpencodeAvailable] = useState(false);
  const [opencodeApproved, setOpencodeApproved] = useState(false);
  const [taskEngineAvailable, setTaskEngineAvailable] = useState(false);
  const [agentProfiles, setAgentProfiles] = useState<AgentProfile[]>([]);
  const [hermesSkills, setHermesSkills] = useState<HermesSkill[]>([]);
  const [hermesToolsets, setHermesToolsets] = useState<HermesToolset[]>([]);
  const [busy, setBusy] = useState(false);
  const [approving, setApproving] = useState(false);
  const [notice, setNotice] = useState("");
  const [loadingCatalog, setLoadingCatalog] = useState(true);

  const refreshCatalog = useCallback(async () => {
    try {
      const items = await getAgentToolCatalog();
      const taskEngine = items.find((item) => item.name === "text.analyze");
      const hermes = items.find((item) => item.name === "hermes.agent.turn");
      const opencode = items.find((item) => item.name === "opencode.task.run");
      setTaskEngineAvailable(Boolean(taskEngine?.available));
      const ai = items.find((item) => item.name === "ai.respond");
      setApproved(Boolean(hermes?.approved));
      setHermesAvailable(Boolean(hermes?.available));
      setAiApproved(Boolean(ai?.approved));
      setAiAvailable(Boolean(ai?.available));
      setOpencodeApproved(Boolean(opencode?.approved));
      setOpencodeAvailable(Boolean(opencode?.available));
      try {
        setAgentProfiles(await getAgentCatalog());
      } catch {
        setAgentProfiles([]);
      }
      const [skillsResult, toolsetsResult] = await Promise.allSettled([
        getHermesSkillCatalog(),
        getHermesToolsetCatalog(),
      ]);
      setHermesSkills(skillsResult.status === "fulfilled" ? skillsResult.value : []);
      setHermesToolsets(toolsetsResult.status === "fulfilled" ? toolsetsResult.value : []);
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
      } else if (operation === "hermes.agent.turn") {
        await grantHermesApproval();
        setApproved(true);
        setNotice("تم حفظ موافقتك على نطاق تشغيل Hermes. يمكنك إلغاء هذه الموافقة من إعدادات الصلاحيات لاحقًا.");
      } else {
        await grantOpenCodeApproval();
        setOpencodeApproved(true);
        setNotice("تم حفظ موافقتك على نطاق تشغيل OpenCode. هذه الموافقة لا تفعّل المحرك أو العامل على الخادم.");
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر حفظ الموافقة.");
    } finally {
      setApproving(false);
    }
  };

  const revokeSelectedApproval = async () => {
    setApproving(true);
    setNotice("");
    try {
      const scope = operation === "ai.respond" ? "ai.provider.run" : operation === "hermes.agent.turn" ? "agent.hermes.run" : "engine.opencode.run";
      await revokeToolApproval(scope);
      if (operation === "ai.respond") setAiApproved(false);
      else if (operation === "hermes.agent.turn") setApproved(false);
      else setOpencodeApproved(false);
      setNotice("تم إلغاء الموافقة. لن يستطيع العامل استخدام هذه الأداة في المحاولات التالية.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر إلغاء الموافقة.");
    } finally {
      setApproving(false);
    }
  };

  const submit = async () => {
    if (!user) { router.push("/auth"); return; }
    if (!prompt.trim() || busy) return;
    if (operation === "text.analyze" && !taskEngineAvailable) {
      setNotice("عامل المهام غير مفعّل على الخادم حاليًا. لا يمكن وضع مهمة في قائمة انتظار لن يتم تنفيذها.");
      return;
    }
    if (operation === "ai.respond" && !aiAvailable) {
      setNotice("مزود الذكاء الاصطناعي غير مضبوط على الخادم بعد. يلزم إعداد AI_PROVIDER وAI_BASE_URL وAI_MODEL، ومفتاح AI_API_KEY عند استخدام مزود متوافق فقط.");
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
    if (operation === "opencode.task.run" && !projectId) {
      setNotice("افتح الوكيل من داخل مشروع أولًا؛ OpenCode يحتاج مساحة ملفات مرتبطة بالمشروع.");
      return;
    }
    if (operation === "opencode.task.run" && !opencodeAvailable) {
      setNotice("محرك OpenCode غير مهيأ أو متوقف على الخادم. لن يتم وضع المهمة في قائمة انتظار غير قابلة للتنفيذ.");
      return;
    }
    if (operation === "opencode.task.run" && !opencodeApproved) {
      setNotice("يجب منح موافقة صريحة على تشغيل OpenCode أولًا.");
      return;
    }
    setBusy(true);
    setNotice("");
    setSnapshot(null);
    try {
      const created = await createAgentTask(operation, prompt, projectId, conversationId);
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
            <Text style={styles.muted}>{projectId ? "مهمة جديدة داخل المشروع" : "مهام محفوظة وتنفيذ قابل للتتبع"}</Text>
          </View>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
        </View>

        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.intro}>
            <Text style={styles.introTitle}>حوّل طلبك إلى مهمة</Text>
            <Text style={styles.muted}>
              {conversationId
                ? "سيستخدم Hermes سياق هذه المحادثة المملوكة لحسابك مع تشغيل جديد داخل Runtime مستقل."
                : "اختبر محرك المهام، أو استخدم SULY AI بعد إعداد المزود والموافقة، أو جهّز Hermes Agent في بيئته المعزولة."}
            </Text>
          </View>

          {agentProfiles.length > 0 && (
            <View style={styles.card}>
              <Text style={styles.label}>أدوار الوكلاء في SULY</Text>
              {agentProfiles.map((agent) => (
                <View key={agent.agent_id} style={styles.agentProfile}>
                  <View style={styles.taskHeader}>
                    <Text style={styles.stepTitle}>{agent.display_name}</Text>
                    <Text style={[styles.approvalState, agent.available ? styles.good : styles.warn]}>
                      {agent.available ? "متاح" : "قيد التجهيز"}
                    </Text>
                  </View>
                  <Text style={styles.modeHint}>{agent.capabilities.join(" · ")}</Text>
                  {!!agent.engines.length && <Text style={styles.modeHint}>المحرك: {agent.engines.join("، ")}</Text>}
                </View>
              ))}
            </View>
          )}

          {(hermesSkills.length > 0 || hermesToolsets.length > 0) && (
            <View style={styles.card}>
              <Text style={styles.label}>قدرات Hermes المكتشفة</Text>
              <Text style={styles.modeHint}>
                قائمة وصفية للمهارات ومجموعات الأدوات من مصدر Hermes. لا تعني أن الأدوات مفعّلة داخل Runtime المهمة، ولا توفر تثبيتًا أو تنفيذًا من هذه الشاشة.
              </Text>
              {hermesSkills.slice(0, 20).map((skill) => (
                <View key={skill.name} style={styles.agentProfile}>
                  <Text style={styles.stepTitle}>{skill.name}</Text>
                  {!!skill.category && <Text style={styles.modeHint}>{skill.category}</Text>}
                  {!!skill.description && <Text style={styles.modeHint}>{skill.description}</Text>}
                </View>
              ))}
              {hermesSkills.length > 20 && (
                <Text style={styles.modeHint}>تم عرض 20 من {hermesSkills.length} مهارة.</Text>
              )}
              {hermesToolsets.slice(0, 20).map((toolset) => (
                <View key={toolset.name} style={styles.agentProfile}>
                  <View style={styles.taskHeader}>
                    <Text style={styles.stepTitle}>{toolset.label || toolset.name}</Text>
                    <Text style={[styles.approvalState, toolset.enabled ? styles.good : styles.warn]}>
                      {toolset.enabled ? "مفعّلة في مصدر الكتالوج" : "غير مفعّلة"}
                    </Text>
                  </View>
                  {!!toolset.description && <Text style={styles.modeHint}>{toolset.description}</Text>}
                  <Text style={styles.modeHint}>{toolset.tools.slice(0, 12).join(" · ")}</Text>
                </View>
              ))}
              {hermesToolsets.length > 20 && (
                <Text style={styles.modeHint}>تم عرض 20 من {hermesToolsets.length} مجموعة أدوات.</Text>
              )}
            </View>
          )}

          <View style={styles.card}>
            <Text style={styles.label}>محرك التنفيذ</Text>
            <View style={styles.modeRow}>
              <Pressable style={[styles.mode, operation === "text.analyze" && styles.modeActive]} onPress={() => setOperation("text.analyze")}>
                <Text style={[styles.modeTitle, operation === "text.analyze" && styles.gold]}>اختبار محرك المهام</Text>
                <Text style={styles.modeHint}>تحليل نص بدون مزود ذكاء اصطناعي</Text>
              </Pressable>
              <Pressable style={[styles.mode, operation === "ai.respond" && styles.modeActive]} onPress={() => setOperation("ai.respond")}>
                <Text style={[styles.modeTitle, operation === "ai.respond" && styles.gold]}>SULY AI</Text>
                <Text style={styles.modeHint}>تنفيذ طلبك عبر نموذج الذكاء الاصطناعي</Text>
              </Pressable>
              <Pressable style={[styles.mode, operation === "hermes.agent.turn" && styles.modeActive]} onPress={() => setOperation("hermes.agent.turn")}>
                <Text style={[styles.modeTitle, operation === "hermes.agent.turn" && styles.gold]}>Hermes Agent</Text>
                <Text style={styles.modeHint}>يتطلب Runtime ومزود نموذج</Text>
              </Pressable>
              <Pressable style={[styles.mode, operation === "opencode.task.run" && styles.modeActive]} onPress={() => setOperation("opencode.task.run")}>
                <Text style={[styles.modeTitle, operation === "opencode.task.run" && styles.gold]}>OpenCode</Text>
                <Text style={styles.modeHint}>وكيل البرمجة • مشروع + Runtime معزول</Text>
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
                <Pressable style={styles.secondaryButton} onPress={aiApproved ? revokeSelectedApproval : enableSelectedApproval} disabled={approving || loadingCatalog}>
                  {approving ? <ActivityIndicator color={colors.gold} /> : <Text style={styles.secondaryText}>{aiApproved ? "إلغاء موافقة AI" : "أوافق على استخدام AI"}</Text>}
                </Pressable>
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
                <Pressable style={styles.secondaryButton} onPress={approved ? revokeSelectedApproval : enableSelectedApproval} disabled={approving || loadingCatalog}>
                  {approving ? <ActivityIndicator color={colors.gold} /> : <Text style={styles.secondaryText}>{approved ? "إلغاء موافقة Hermes" : "أوافق على تشغيل Hermes"}</Text>}
                </Pressable>
              </View>
            )}

            {operation === "opencode.task.run" && (
              <View style={styles.approvalBox}>
                <View style={styles.approvalHeader}>
                  <Text style={styles.label}>موافقة تشغيل OpenCode</Text>
                  <Text style={[styles.approvalState, opencodeApproved ? styles.good : styles.warn]}>{opencodeApproved ? "مفعّلة" : "غير مفعّلة"}</Text>
                </View>
                <Text style={styles.modeHint}>تسمح هذه الموافقة بإنشاء مهام برمجية عبر OpenCode فقط. التنفيذ يظل متوقفًا ما لم يكن Worker وRuntime معزولًا ومفعّلين صراحة على الخادم.</Text>
                <Text style={[styles.modeHint, opencodeAvailable ? styles.good : styles.warn]}>
                  {opencodeAvailable ? "إعدادات Runtime مكتملة (لم يُختبر الاتصال المباشر)." : "OpenCode غير متاح على الخادم حاليًا."}
                </Text>
                <Pressable style={styles.secondaryButton} onPress={opencodeApproved ? revokeSelectedApproval : enableSelectedApproval} disabled={approving || loadingCatalog}>
                  {approving ? <ActivityIndicator color={colors.gold} /> : <Text style={styles.secondaryText}>{opencodeApproved ? "إلغاء موافقة OpenCode" : "أوافق على تشغيل OpenCode"}</Text>}
                </Pressable>
              </View>
            )}

            <Text style={styles.label}>وصف المهمة</Text>
            <TextInput
              value={prompt}
              onChangeText={setPrompt}
              placeholder={operation === "text.analyze" ? "اكتب نصًا لاختبار التحليل..." : operation === "ai.respond" ? "اكتب ما تريد من SULY إنجازه..." : operation === "opencode.task.run" ? "اكتب مهمة البرمجة التي تريد من OpenCode تنفيذها..." : "اكتب ما تريد من Hermes إنجازه..."}
              placeholderTextColor={colors.faint}
              multiline
              textAlign="right"
              textAlignVertical="top"
              style={styles.input}
              maxLength={20000}
            />
            <Text style={styles.counter}>{prompt.length.toLocaleString("en-US")} / 20,000</Text>
            <Pressable style={[styles.primaryButton, (!prompt.trim() || busy || (operation === "text.analyze" && !taskEngineAvailable) || (operation === "hermes.agent.turn" && (!hermesAvailable || !approved)) || (operation === "ai.respond" && (!aiAvailable || !aiApproved)) || (operation === "opencode.task.run" && (!projectId || !opencodeAvailable || !opencodeApproved))) && styles.disabled]} onPress={submit} disabled={!prompt.trim() || busy || (operation === "text.analyze" && !taskEngineAvailable) || (operation === "hermes.agent.turn" && (!hermesAvailable || !approved)) || (operation === "ai.respond" && (!aiAvailable || !aiApproved)) || (operation === "opencode.task.run" && (!projectId || !opencodeAvailable || !opencodeApproved))}>
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
              <Pressable
                style={styles.secondaryButton}
                onPress={() => router.push({ pathname: "/task/[id]", params: { id: snapshot.task.id } })}
              >
                <Text style={styles.secondaryText}>عرض تفاصيل التنفيذ وسجل المحرك</Text>
              </Pressable>
              {snapshot.steps.map((step) => (
                <View key={step.id} style={styles.step}>
                  <View style={styles.taskHeader}>
                    <Text style={styles.stepTitle}>{step.title}</Text>
                    <Text style={styles.stepStatus}>{statusLabel(step.status)}</Text>
                  </View>
                  <Text style={styles.modeHint}>المحاولة {step.attempt_count} من {step.max_attempts}</Text>
                  {!!step.error_message && <Text style={styles.error}>{step.error_message}</Text>}
                  {typeof step.output?.content === "string" && (
                    <Text selectable style={styles.output}>{step.output.content}</Text>
                  )}
                  {typeof step.output?.preview === "string" && (
                    <Text selectable style={styles.output}>{step.output.preview}</Text>
                  )}
                  {step.output && Object.keys(step.output).length > 0
                    && typeof step.output.content !== "string"
                    && typeof step.output.preview !== "string" && (
                    <Text selectable style={styles.output}>{JSON.stringify(step.output, null, 2)}</Text>
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
  modeRow: { flexDirection: "row", flexWrap: "wrap", gap: 9 },
  mode: { flex: 1, minWidth: 140, padding: 12, borderRadius: 13, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, gap: 5 },
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
  agentProfile: { paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border, gap: 5 },
  step: { padding: 12, borderRadius: 12, backgroundColor: colors.background, gap: 7 },
  stepTitle: { color: colors.text, fontSize: 12, fontWeight: "700" },
  stepStatus: { color: colors.gold, fontSize: 10 },
  output: { color: colors.muted, fontSize: 10, lineHeight: 17, textAlign: "left" },
  error: { color: "#E88787", fontSize: 10, lineHeight: 17, textAlign: "right" },
  cancelButton: { minHeight: 40, borderRadius: 11, borderWidth: 1, borderColor: "#9B5656", alignItems: "center", justifyContent: "center" },
  cancelText: { color: "#E88787", fontSize: 12, fontWeight: "700" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 25, gap: 12 },
});
