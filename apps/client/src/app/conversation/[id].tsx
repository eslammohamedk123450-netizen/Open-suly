import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useLocalSearchParams } from "expo-router";
import { colors } from "@/theme/tokens";
/** واجهة المحادثة تعرض بيانات usage التي أرسلها مزود الخدمة دون تقدير سعر أو خصم credits. */
import { useAuth } from "@/providers/AuthProvider";
import { getConversation, listMessages, sendUserMessage, type ChatMessage } from "@/lib/conversations";
import { listProjectFiles, type ProjectFile } from "@/lib/project-files";
import { requestAssistantReplyStream } from "@/lib/chat-api";

function attachmentNames(metadata: ChatMessage["metadata"] | null | undefined): string[] {
  if (!metadata || typeof metadata !== "object" || !Array.isArray(metadata.attachments)) return [];
  return metadata.attachments
    .filter((item): item is { path: string } => !!item && typeof item === "object" && typeof (item as { path?: unknown }).path === "string")
    .map((item) => item.path);
}

function tokenUsage(metadata: ChatMessage["metadata"] | null | undefined): { input_tokens: number; output_tokens: number; total_tokens: number } | null {
  if (!metadata || typeof metadata !== "object") return null;
  const raw = metadata.usage;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const usage = raw as Record<string, unknown>;
  const input = usage.input_tokens;
  const output = usage.output_tokens;
  const total = usage.total_tokens;
  if (![input, output, total].every((value => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= 1_000_000_000))) return null;
  if (total !== (input as number) + (output as number)) return null;
  return { input_tokens: input as number, output_tokens: output as number, total_tokens: total as number };
}

export default function ConversationScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [engineNotice, setEngineNotice] = useState("");
  const [streamingText, setStreamingText] = useState("");
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectFiles, setProjectFiles] = useState<ProjectFile[]>([]);
  const [selectedAttachments, setSelectedAttachments] = useState<string[]>([]);
  const [pendingMessageId, setPendingMessageId] = useState<string | null>(null);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!user) { setMessages([]); setLoading(false); return; }
    let active = true;
    activeRequest.current?.abort();
    activeRequest.current = null;
    setStreamingText("");
    setProjectId(null);
    setProjectFiles([]);
    setSelectedAttachments([]);
    setPendingMessageId(null);
    getConversation(id).then(async (conversation) => {
      if (!active || !conversation.project_id) return;
      setProjectId(conversation.project_id);
      const files = await listProjectFiles(conversation.project_id);
      if (active) setProjectFiles(files);
    }).catch((e) => { if (active) setEngineNotice(e instanceof Error ? e.message : "تعذر تحميل مرفقات المشروع."); });
    setMessages([]);
    setError("");
    setEngineNotice("");
    setLoading(true);
    listMessages(id).then(async (rows) => {
      if (!active) return;
      setMessages(rows);
      const lastUserMessage = [...rows].reverse().find((row) => row.role === "user");
      const hasReply = lastUserMessage && rows.some((row) => row.role === "assistant" && row.metadata?.in_reply_to === lastUserMessage.id);
      if (lastUserMessage && !hasReply) {
        setPendingMessageId(lastUserMessage.id);
        setSending(true);
        try {
          const controller = new AbortController();
          activeRequest.current = controller;
          const reply = await requestAssistantReplyStream(id, lastUserMessage.id, { signal: controller.signal, onDelta: (part) => { if (active) setStreamingText((current) => current + part); } });
          if (active) setMessages((current) => current.some((row) => row.id === reply.id) ? current : [...current, reply]);
          if (active) setPendingMessageId(null);
          if (active) setStreamingText("");
        } catch (e) {
          if (active) setEngineNotice(e instanceof Error && e.name === "AbortError" ? "تم إيقاف الرد. يمكنك استكماله وقتما تريد." : e instanceof Error ? e.message : "محرك الردود غير متاح حاليًا.");
          if (active) setStreamingText("");
        } finally {
          activeRequest.current = null;
          if (active) setSending(false);
        }
      }
    })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "تعذر تحميل المحادثة."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; activeRequest.current?.abort(); activeRequest.current = null; };
  }, [id, user]);

  const send = async () => {
    if (!draft.trim() || sending || pendingMessageId) return;
    if (!user) { router.push("/auth"); return; }
    const content = draft.trim();
    setDraft("");
    setSending(true);
    setError("");
    setEngineNotice("");
    setStreamingText("");
    const controller = new AbortController();
    activeRequest.current = controller;
    try {
      const saved = await sendUserMessage(id, content, selectedAttachments);
      setPendingMessageId(saved.id);
      setMessages((current) => [...current, saved]);
      setSelectedAttachments([]);
      try {
        const reply = await requestAssistantReplyStream(id, saved.id, { signal: controller.signal, onDelta: (part) => setStreamingText((current) => current + part) });
        setMessages((current) => current.some((row) => row.id === reply.id) ? current : [...current, reply]);
        setPendingMessageId(null);
        setStreamingText("");
      } catch (replyError) {
        setEngineNotice(replyError instanceof Error && replyError.name === "AbortError" ? "تم إيقاف الرد. يمكنك استكماله وقتما تريد." : replyError instanceof Error ? replyError.message : "تم حفظ الرسالة، لكن الرد غير متاح حاليًا.");
        setStreamingText("");
      }
    } catch (e) {
      setDraft(content);
      setError(e instanceof Error ? e.message : "تعذر حفظ الرسالة.");
    } finally { activeRequest.current = null; setSending(false); }
  };


  const retryReply = async () => {
    if (!pendingMessageId || sending) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    setSending(true);
    setStreamingText("");
    setEngineNotice("");
    try {
      const reply = await requestAssistantReplyStream(id, pendingMessageId, {
        signal: controller.signal,
        onDelta: (part) => setStreamingText((current) => current + part),
      });
      setMessages((current) => current.some((row) => row.id === reply.id) ? current : [...current, reply]);
      setPendingMessageId(null);
      setStreamingText("");
    } catch (e) {
      setEngineNotice(e instanceof Error && e.name === "AbortError" ? "تم إيقاف الرد. يمكنك استكماله وقتما تريد." : e instanceof Error ? e.message : "تعذر استكمال الرد.");
      setStreamingText("");
    } finally {
      activeRequest.current = null;
      setSending(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView style={styles.page} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View style={styles.header}>
          <Pressable style={styles.backButton} onPress={() => router.replace("/projects")}><Text style={styles.backText}>→</Text></Pressable>
          <View style={styles.headerCopy}><Text style={styles.title}>محادثة SULY</Text><Text style={styles.subtitle}>مساحة محادثة خاصة بحسابك</Text></View>
          <Pressable style={styles.permissionButton} onPress={() => router.push({ pathname: "/agent", params: { conversationId: id } })}>
            <Text style={styles.permissionText}>الوكيل</Text>
          </Pressable>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
        </View>
        <ScrollView contentContainerStyle={styles.messages} keyboardShouldPersistTaps="handled">
          {loading ? <ActivityIndicator color={colors.gold} /> : messages.length === 0 ? (
            <View style={styles.welcome}><Text style={styles.welcomeTitle}>ابدأ من هنا</Text><Text style={styles.welcomeText}>اكتب أول رسالة. سيتم حفظها في حسابك بشكل خاص.</Text></View>
          ) : messages.map((message) => {
            const usage = message.role === "assistant" ? tokenUsage(message.metadata) : null;
            const attachments = attachmentNames(message.metadata);
            const roleLabel = message.role === "system" ? "النظام" : message.role === "tool" ? "أداة" : message.role === "agent" ? "الوكيل" : message.role === "error" ? "خطأ" : "";
            return (
            <View key={message.id} style={message.role === "user" ? styles.userMessage : message.role === "error" ? styles.errorMessage : styles.assistantMessage}>
              {!!roleLabel && <Text style={styles.roleLabel}>{roleLabel}</Text>}
              <Text style={message.role === "user" ? styles.userText : message.role === "error" ? styles.errorMessageText : styles.assistantText}>{message.content}</Text>
              {!!attachments.length && <Text style={styles.attachmentLabel}>ملفات مرفقة: {attachments.join("، ")}</Text>}
              {!!usage && <Text style={styles.usage}>عدد الرموز · إدخال {usage.input_tokens.toLocaleString("ar-EG")} / إخراج {usage.output_tokens.toLocaleString("ar-EG")} / الإجمالي {usage.total_tokens.toLocaleString("ar-EG")}</Text>}
              <Text style={styles.time}>{new Date(message.created_at).toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" })}</Text>
            </View>
            );
          })}
          {!!streamingText && <View style={styles.assistantMessage}><Text style={styles.assistantText}>{streamingText}</Text><Text style={styles.time}>SULY · يكتب الآن</Text></View>}
          {!!error && <Text style={styles.error}>{error}</Text>}
          {!!engineNotice && (
            <View style={styles.noticeBox}>
              <Text style={styles.engineNotice}>{engineNotice}</Text>
              {!!pendingMessageId && !sending && (
                <Pressable style={styles.permissionButton} onPress={() => void retryReply()}>
                  <Text style={styles.permissionText}>استكمال الرد</Text>
                </Pressable>
              )}
              {engineNotice.includes("موافقة صريحة") && (
                <Pressable style={styles.permissionButton} onPress={() => router.push("/agent")}>
                  <Text style={styles.permissionText}>فتح مساحة الوكيل لإدارة الموافقة</Text>
                </Pressable>
              )}
            </View>
          )}
        </ScrollView>
        {projectId && projectFiles.length > 0 && (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.attachmentPicker}>
            {projectFiles.map((file) => {
              const selected = selectedAttachments.includes(file.id);
              return (
                <Pressable
                  key={file.id}
                  style={[styles.attachmentChip, selected && styles.attachmentChipSelected]}
                  onPress={() => setSelectedAttachments((current) => selected
                    ? current.filter((value) => value !== file.id)
                    : current.length < 5 ? [...current, file.id] : current)}
                  accessibilityState={{ selected }}
                >
                  <Text style={selected ? styles.attachmentSelectedText : styles.attachmentText} numberOfLines={1}>
                    {selected ? "✓ " : "＋ "}{file.path}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>
        )}
        <View style={styles.composer}>
          <TextInput value={draft} onChangeText={setDraft} placeholder="اكتب رسالتك..." placeholderTextColor={colors.faint} style={styles.input} multiline textAlign="right" textAlignVertical="center" />
          {sending ? (
            <Pressable style={[styles.sendButton, styles.stopButton]} onPress={() => activeRequest.current?.abort()} accessibilityLabel="إيقاف الرد">
              <Text style={styles.sendText}>■</Text>
            </Pressable>
          ) : (
            <Pressable style={[styles.sendButton, (!draft.trim() || !!pendingMessageId) && styles.disabled]} onPress={send} disabled={!draft.trim() || !!pendingMessageId} accessibilityLabel="إرسال الرسالة">
              <Text style={styles.sendText}>↑</Text>
            </Pressable>
          )}
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background }, page: { flex: 1, width: "100%", maxWidth: 1100, alignSelf: "center", backgroundColor: colors.background },
  header: { minHeight: 70, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", gap: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  backButton: { width: 40, height: 40, borderRadius: 13, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border }, backText: { color: colors.gold, fontSize: 22 },
  headerCopy: { flex: 1 }, title: { color: colors.text, fontSize: 15, fontWeight: "800", textAlign: "right" }, subtitle: { color: colors.muted, fontSize: 10, marginTop: 4, textAlign: "right" },
  logo: { width: 40, height: 40, borderRadius: 13, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" }, logoText: { color: colors.gold, fontSize: 22, fontWeight: "800" },
  messages: { flexGrow: 1, padding: 18, gap: 12, width: "100%", maxWidth: 760, alignSelf: "center", justifyContent: "flex-end" },
  welcome: { alignItems: "center", padding: 28, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface }, welcomeTitle: { color: colors.gold, fontSize: 17, fontWeight: "800" }, welcomeText: { color: colors.muted, fontSize: 12, textAlign: "center", lineHeight: 21, marginTop: 8 },
  userMessage: { alignSelf: "flex-end", maxWidth: "88%", borderRadius: 18, borderBottomRightRadius: 5, padding: 13, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.goldDark }, assistantMessage: { alignSelf: "flex-start", maxWidth: "88%", borderRadius: 18, borderBottomLeftRadius: 5, padding: 13, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }, errorMessage: { alignSelf: "flex-start", maxWidth: "88%", borderRadius: 18, padding: 13, backgroundColor: colors.surface, borderWidth: 1, borderColor: "#A94B4B" }, roleLabel: { color: colors.gold, fontSize: 9, fontWeight: "800", marginBottom: 5, textAlign: "right" }, errorMessageText: { color: "#F08B8B", fontSize: 13, lineHeight: 22, textAlign: "left" },
  userText: { color: colors.text, fontSize: 13, lineHeight: 22, textAlign: "right" }, assistantText: { color: colors.muted, fontSize: 13, lineHeight: 22, textAlign: "left" }, time: { color: colors.faint, fontSize: 9, marginTop: 7, textAlign: "left" }, usage: { color: colors.faint, fontSize: 9, marginTop: 5, textAlign: "left" }, attachmentLabel: { color: colors.gold, fontSize: 9, marginTop: 5, textAlign: "right" },
  noticeBox: { alignItems: "center", gap: 8, padding: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  engineNotice: { color: colors.faint, fontSize: 10, textAlign: "center", marginTop: 8 }, permissionButton: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: 9, borderWidth: 1, borderColor: colors.goldDark }, permissionText: { color: colors.gold, fontSize: 10, fontWeight: "700" }, error: { color: "#F08B8B", fontSize: 11, textAlign: "center" },
  attachmentPicker: { width: "100%", maxWidth: 760, alignSelf: "center", paddingHorizontal: 12, paddingTop: 8, gap: 7 }, attachmentChip: { maxWidth: 190, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface }, attachmentChipSelected: { borderColor: colors.gold, backgroundColor: colors.surfaceSecondary }, attachmentText: { color: colors.muted, fontSize: 9 }, attachmentSelectedText: { color: colors.gold, fontSize: 9, fontWeight: "700" },
  composer: { width: "100%", maxWidth: 760, alignSelf: "center", padding: 12, flexDirection: "row", alignItems: "flex-end", gap: 9, borderTopWidth: 1, borderTopColor: colors.border }, input: { flex: 1, minHeight: 48, maxHeight: 130, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, color: colors.text, paddingHorizontal: 13, paddingVertical: 12, fontSize: 13 },
  sendButton: { width: 46, height: 46, borderRadius: 15, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center" }, stopButton: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.goldDark }, sendText: { color: colors.background, fontSize: 25, fontWeight: "900" }, disabled: { opacity: 0.45 },
});
