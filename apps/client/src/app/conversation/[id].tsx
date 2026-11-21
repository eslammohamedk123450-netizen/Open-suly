import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useLocalSearchParams } from "expo-router";
import { useTheme } from "@/providers/ThemeProvider";
import { useAuth } from "@/providers/AuthProvider";
import { BottomSheet } from "@/components/BottomSheet";
import { Toggle } from "@/components/Toggle";
import { createConversation, listMessages, sendUserMessage, type ChatMessage } from "@/lib/conversations";
import { requestAssistantReply } from "@/lib/chat-api";

type Integration = { key: string; name: string; meta: string; connected: boolean };
type UsageRow = { amount: number; title: string; date: string; flex: boolean };
type Model = { key: string; label: string };

const suggestions = [
  "تحليل بيانات ومقارنة نتائج",
  "ابحث عن أحدث الأخبار في موضوع محدد",
  "أنشئ خطة عمل لمشروعك الجديد",
];

const models: Model[] = [
  { key: "max-pro", label: "Suly 2.0 Max Pro" },
  { key: "pro", label: "Suly 2.0 Pro" },
  { key: "lite", label: "Suly 2.0 Lite" },
  { key: "flex", label: "Suly Flex - Gemini 3.1 Flash-Lite" },
];

const integrations: Integration[] = [
  { key: "github", name: "GitHub", meta: "0", connected: false },
  { key: "workspace", name: "Google Workspace", meta: "اتصال", connected: false },
  { key: "supabase", name: "Supabase", meta: "اتصال", connected: true },
  { key: "shopify", name: "Shopify Beta", meta: "اتصال", connected: false },
  { key: "outlook", name: "Outlook", meta: "اتصال", connected: false },
  { key: "instagram-creator", name: "Instagram Creator Marketplace Beta", meta: "اتصال", connected: false },
  { key: "meta-ads", name: "Meta مدير إعلانات Beta", meta: "اتصال", connected: false },
  { key: "outlook-mail", name: "Outlook Mail", meta: "اتصال", connected: false },
  { key: "instagram", name: "Instagram", meta: "0", connected: false },
  { key: "gcal", name: "تقويم جوجل", meta: "اتصال", connected: false },
];

const usageRows: UsageRow[] = [
  { amount: -5, title: "بحث سريع عن المنتجات المنافسة", date: "21 نوفمبر", flex: true },
  { amount: -12, title: "تلخيص تقرير ربع سنوي", date: "21 نوفمبر", flex: true },
  { amount: -8, title: "تحليل بيانات مبيعات", date: "20 نوفمبر", flex: true },
  { amount: -4, title: "صياغة رسالة تسويقية", date: "20 نوفمبر", flex: false },
  { amount: -20, title: "كتابة خطة تشغيل كاملة", date: "19 نوفمبر", flex: false },
];

export default function ConversationScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { palette } = useTheme();
  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [engineNotice, setEngineNotice] = useState("");
  const [modelOpen, setModelOpen] = useState(false);
  const [usageOpen, setUsageOpen] = useState(false);
  const [integrationsOpen, setIntegrationsOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState("lite");
  const [dismissedSuggestion, setDismissedSuggestion] = useState(false);
  const [connectedKeys, setConnectedKeys] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(integrations.map((item) => [item.key, item.connected])) as Record<string, boolean>,
  );

  const isNew = id === "new";
  const inputRef = useRef<TextInput>(null);

  useEffect(() => {
    if (!user || isNew) {
      setMessages([]);
      setLoading(false);
      return;
    }
    let active = true;
    setMessages([]);
    setError("");
    setEngineNotice("");
    setLoading(true);
    listMessages(id)
      .then(async (rows) => {
        if (!active) return;
        setMessages(rows);
        const lastUserMessage = [...rows].reverse().find((row) => row.role === "user");
        const hasReply =
          lastUserMessage &&
          rows.some((row) => row.role === "assistant" && row.metadata?.in_reply_to === lastUserMessage.id);
        if (lastUserMessage && !hasReply) {
          try {
            const reply = await requestAssistantReply(id, lastUserMessage.id);
            if (active)
              setMessages((current) =>
                current.some((row) => row.id === reply.id) ? current : [...current, reply],
              );
          } catch (e) {
            if (active) setEngineNotice(e instanceof Error ? e.message : "محرك الردود غير متاح حاليًا.");
          }
        }
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : "تعذر تحميل المحادثة.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id, user, isNew]);

  const send = async () => {
    const content = draft.trim();
    if (!content || sending) return;
    if (!user) {
      router.push("/auth");
      return;
    }
    if (isNew) {
      // A new chat must persist both the conversation and the first message
      // before navigating; otherwise the user's text is silently lost.
      setSending(true);
      setError("");
      try {
        const conversation = await createConversation(content.slice(0, 40));
        await sendUserMessage(conversation.id, content);
        setDraft("");
        router.replace({ pathname: "/conversation/[id]", params: { id: conversation.id } });
      } catch (e) {
        setError(e instanceof Error ? e.message : "تعذر إنشاء المحادثة.");
      } finally {
        setSending(false);
      }
      return;
    }
    setDraft("");
    setSending(true);
    setError("");
    setEngineNotice("");
    try {
      const saved = await sendUserMessage(id, content);
      setMessages((current) => [...current, saved]);
      try {
        const reply = await requestAssistantReply(id, saved.id);
        setMessages((current) =>
          current.some((row) => row.id === reply.id) ? current : [...current, reply],
        );
      } catch (replyError) {
        setEngineNotice(
          replyError instanceof Error ? replyError.message : "تم حفظ الرسالة، لكن الرد غير متاح حاليًا.",
        );
      }
    } catch (e) {
      setDraft(content);
      setError(e instanceof Error ? e.message : "تعذر حفظ الرسالة.");
    } finally {
      setSending(false);
    }
  };

  const showSuggestions = messages.length === 0 && !loading && !dismissedSuggestion;

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: palette.background }]}>
      <KeyboardAvoidingView style={styles.page} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        {/* Top bar: credit counter (left) and model selector (right). */}
        <View style={[styles.header, { borderBottomColor: palette.border }]}>
          <Pressable style={styles.headerButton} onPress={() => setUsageOpen(true)} accessibilityLabel="الاستخدام">
            <Text style={[styles.headerMeta, { color: palette.text }]}>300</Text>
            <Text style={[styles.headerStar, { color: palette.text }]}>★</Text>
          </Pressable>
          <Pressable style={styles.headerButton} onPress={() => setModelOpen(true)} accessibilityLabel="اختيار النموذج">
            <Text style={[styles.headerMeta, { color: palette.text }]}>Suly 2.0 Lite</Text>
            <Text style={[styles.headerChevron, { color: palette.muted }]}>⌄</Text>
          </Pressable>
        </View>

        {/* Message history */}
        <ScrollView contentContainerStyle={styles.messages} keyboardShouldPersistTaps="handled">
          {loading ? (
            <ActivityIndicator color={palette.muted} />
          ) : messages.length === 0 ? (
            <View style={styles.welcome}>
              <Text style={[styles.welcomeTitle, { color: palette.text }]}>Suly</Text>
            </View>
          ) : (
            messages.map((message) => (
              <View
                key={message.id}
                style={[
                  message.role === "user" ? styles.userMessage : styles.assistantMessage,
                  {
                    backgroundColor: message.role === "user" ? palette.surfaceSecondary : palette.surface,
                    borderColor: palette.border,
                  },
                ]}
              >
                <Text style={[styles.messageText, { color: palette.text }]}>{message.content}</Text>
                <Text style={[styles.time, { color: palette.faint }]}>
                  {new Date(message.created_at).toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" })}
                </Text>
              </View>
            ))
          )}
          {!!error && <Text style={[styles.error, { color: palette.danger }]}>{error}</Text>}
          {!!engineNotice && <Text style={[styles.engineNotice, { color: palette.faint }]}>{engineNotice}</Text>}
        </ScrollView>

        {/* Suggestions above the composer; first row dismissible. */}
        {showSuggestions && (
          <View style={[styles.suggestions, { borderColor: palette.border }]}>
            {suggestions.map((item, index) => (
              <View key={item} style={[styles.suggestionRow, index > 0 && styles.suggestionDivider]}>
                <Pressable
                  style={styles.suggestionBody}
                  onPress={() => {
                    setDraft(item);
                    inputRef.current?.focus();
                  }}
                >
                  <Text style={[styles.suggestionText, { color: palette.muted }]}>{item}</Text>
                </Pressable>
                {index === 0 && (
                  <Pressable onPress={() => setDismissedSuggestion(true)} accessibilityLabel="إخفاء الاقتراح">
                    <Text style={[styles.suggestionClose, { color: palette.faint }]}>✕</Text>
                  </Pressable>
                )}
              </View>
            ))}
          </View>
        )}

        {/* Composer: meta row above, icons left, input grows with typing. */}
        <View style={styles.composer}>
          <View style={[styles.composerTopRow, { borderBottomColor: palette.border }]}>
            <Pressable style={styles.composerMetaItem} onPress={() => undefined}>
              <Text style={[styles.composerMetaText, { color: palette.muted }]}>السماعة</Text>
            </Pressable>
            <Pressable style={styles.composerMetaItem} onPress={() => undefined}>
              <Text style={[styles.composerMetaText, { color: palette.muted }]}>لا يوجد منشوط</Text>
            </Pressable>
            <Pressable style={styles.composerMetaItem} onPress={() => undefined}>
              <Text style={[styles.composerMetaIcon, { color: palette.muted }]}>▦</Text>
            </Pressable>
            <Pressable style={styles.composerMetaItem} onPress={() => undefined}>
              <Text style={[styles.composerMetaIcon, { color: palette.muted }]}>1+</Text>
            </Pressable>
          </View>
          <View style={styles.composerInputRow}>
            <Pressable style={styles.composerIcon} onPress={() => setIntegrationsOpen(true)} accessibilityLabel="الموصلات">
              <Text style={[styles.composerIconText, { color: palette.muted }]}>＋</Text>
            </Pressable>
            <Pressable style={styles.composerIcon} onPress={() => undefined} accessibilityLabel="ميكروفون">
              <Text style={[styles.composerIconText, { color: palette.muted }]}>🎙</Text>
            </Pressable>
            <TextInput
              ref={inputRef}
              value={draft}
              onChangeText={setDraft}
              placeholder="اختر منطقة التحدث أو اكتب / للبدء"
              placeholderTextColor={palette.faint}
              multiline
              style={[
                styles.input,
                {
                  color: palette.text,
                  backgroundColor: palette.surface,
                  borderColor: palette.border,
                  height: Math.min(150, 52 + Math.ceil(draft.length / 42) * 18),
                },
              ]}
              selectionColor={palette.accent}
            />
            <Pressable
              style={[styles.sendButton, { backgroundColor: palette.text }]}
              onPress={send}
              disabled={!draft.trim() || sending}
              accessibilityLabel="إرسال"
            >
              {sending ? (
                <ActivityIndicator color={palette.background} />
              ) : (
                <Text style={[styles.sendText, { color: palette.background }]}>↑</Text>
              )}
            </Pressable>
          </View>
        </View>

        {/* Model selection sheet. */}
        <BottomSheet visible={modelOpen} onClose={() => setModelOpen(false)} heightRatio={0.5}>
          <View style={[styles.sheetHeader, { borderBottomColor: palette.border }]}>
            <Text style={[styles.sheetTitle, { color: palette.text }]}>اختر نموذجاً</Text>
            <Pressable onPress={() => setModelOpen(false)} accessibilityLabel="إغلاق">
              <Text style={[styles.sheetClose, { color: palette.muted }]}>✕</Text>
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={styles.sheetBody} showsVerticalScrollIndicator={false}>
            {models.map((model) => {
              const selected = selectedModel === model.key;
              return (
                <Pressable
                  key={model.key}
                  style={[styles.modelRow, { backgroundColor: selected ? palette.surfaceSecondary : "transparent" }]}
                  onPress={() => setSelectedModel(model.key)}
                >
                  <Text style={[styles.modelLabel, { color: palette.text }]}>{model.label}</Text>
                  {selected && <Text style={[styles.modelCheck, { color: palette.accent }]}>✓</Text>}
                </Pressable>
              );
            })}
            <Pressable style={styles.doneButton} onPress={() => setModelOpen(false)}>
              <Text style={styles.doneButtonText}>تم</Text>
            </Pressable>
          </ScrollView>
        </BottomSheet>

        {/* Usage sheet. */}
        <BottomSheet visible={usageOpen} onClose={() => setUsageOpen(false)} heightRatio={0.7}>
          <View style={[styles.sheetHeader, { borderBottomColor: palette.border }]}>
            <Text style={[styles.sheetTitle, { color: palette.text }]}>الاستخدام</Text>
            <Pressable onPress={() => setUsageOpen(false)} accessibilityLabel="إغلاق">
              <Text style={[styles.sheetClose, { color: palette.muted }]}>✕</Text>
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={styles.sheetBody} showsVerticalScrollIndicator={false}>
            <View style={[styles.usageCard, { backgroundColor: palette.surfaceSecondary, borderColor: palette.border }]}>
              <Text style={[styles.usagePlan, { color: palette.text }]}>Free</Text>
              <Text style={[styles.usageCredit, { color: palette.muted }]}>رصيد 300</Text>
              <Text style={[styles.usageRenew, { color: palette.faint }]}>يتم التجديد يومياً في 23:00</Text>
            </View>
            {usageRows.map((row, index) => (
              <View key={index} style={styles.usageRow}>
                <Text style={[styles.usageAmount, { color: palette.muted }]}>{row.amount}</Text>
                <View style={styles.usageTitle}>
                  <Text style={[styles.usageTask, { color: palette.text }]} numberOfLines={1}>
                    {row.title}
                  </Text>
                  <Text style={[styles.usageDate, { color: palette.faint }]}>
                    {row.date}
                    {row.flex ? " · Flex" : ""}
                  </Text>
                </View>
              </View>
            ))}
          </ScrollView>
        </BottomSheet>

        {/* Integrations sheet. */}
        <BottomSheet visible={integrationsOpen} onClose={() => setIntegrationsOpen(false)} heightRatio={0.8}>
          <View style={[styles.sheetHeader, { borderBottomColor: palette.border }]}>
            <Text style={[styles.sheetTitle, { color: palette.text }]}>الموصلات</Text>
            <Pressable onPress={() => setIntegrationsOpen(false)} accessibilityLabel="إغلاق">
              <Text style={[styles.sheetClose, { color: palette.muted }]}>✕</Text>
            </Pressable>
          </View>
          <View style={styles.sheetBody}>
            <View style={styles.integrationsActions}>
              <Pressable style={[styles.integrationsAction, { backgroundColor: palette.surfaceSecondary }]} onPress={() => undefined}>
                <Text style={[styles.integrationsActionText, { color: palette.text }]}>+ إضافة موصلات</Text>
              </Pressable>
              <Pressable style={[styles.integrationsAction, { backgroundColor: palette.surfaceSecondary }]} onPress={() => undefined}>
                <Text style={[styles.integrationsActionText, { color: palette.text }]}>إدارة الموصلات</Text>
              </Pressable>
            </View>
            <ScrollView contentContainerStyle={styles.integrationsList} showsVerticalScrollIndicator={false}>
              {integrations.map((item) => (
                <View key={item.key} style={[styles.integrationRow, { borderBottomColor: palette.border }]}>
                  <View style={[styles.integrationIcon, { backgroundColor: palette.surfaceSecondary }]}>
                    <Text style={[styles.integrationIconText, { color: palette.muted }]}>{item.name.charAt(0)}</Text>
                  </View>
                  <Text style={[styles.integrationName, { color: palette.text }]} numberOfLines={1}>
                    {item.name}
                  </Text>
                  <View style={styles.integrationTrailing}>
                    {item.connected ? (
                      <Toggle
                        value={connectedKeys[item.key]}
                        onChange={(value) => setConnectedKeys((current) => ({ ...current, [item.key]: value }))}
                      />
                    ) : (
                      <Text style={[styles.integrationMeta, { color: palette.muted }]}>{item.meta}</Text>
                    )}
                  </View>
                </View>
              ))}
            </ScrollView>
          </View>
        </BottomSheet>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  page: { flex: 1, direction: "rtl", width: "100%", maxWidth: 1100, alignSelf: "center" },
  header: { minHeight: 60, paddingHorizontal: 18, flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderBottomWidth: 1 },
  headerButton: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 8 },
  headerMeta: { fontSize: 14, fontWeight: "600" },
  headerChevron: { fontSize: 14 },
  headerStar: { fontSize: 13 },
  messages: { flexGrow: 1, padding: 18, gap: 12, width: "100%", maxWidth: 760, alignSelf: "center", justifyContent: "flex-end" },
  welcome: { alignItems: "center", paddingVertical: 24 },
  welcomeTitle: { fontSize: 26, fontWeight: "300" },
  userMessage: { alignSelf: "flex-end", maxWidth: "88%", borderRadius: 18, borderBottomRightRadius: 5, padding: 13, borderWidth: 1 },
  assistantMessage: { alignSelf: "flex-start", maxWidth: "88%", borderRadius: 18, borderBottomLeftRadius: 5, padding: 13, borderWidth: 1 },
  messageText: { fontSize: 13, lineHeight: 22 },
  time: { fontSize: 9, marginTop: 7 },
  error: { fontSize: 11, textAlign: "center" },
  engineNotice: { fontSize: 10, textAlign: "center" },
  suggestions: { borderTopWidth: 0 },
  suggestionRow: { flexDirection: "row", alignItems: "center", paddingHorizontal: 18, minHeight: 48 },
  suggestionBody: { flex: 1 },
  suggestionDivider: { borderTopWidth: 1 },
  suggestionText: { fontSize: 13, fontWeight: "300" },
  suggestionClose: { fontSize: 14 },
  composer: { paddingBottom: 10 },
  composerTopRow: { flexDirection: "row", alignItems: "center", paddingHorizontal: 18, paddingVertical: 8, gap: 14 },
  composerMetaItem: { paddingVertical: 4 },
  composerMetaText: { fontSize: 11 },
  composerMetaIcon: { fontSize: 12 },
  composerInputRow: { flexDirection: "row", alignItems: "flex-end", paddingHorizontal: 14, paddingTop: 6, gap: 8 },
  composerIcon: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center" },
  composerIconText: { fontSize: 18 },
  input: { flex: 1, borderRadius: 24, borderWidth: 1, paddingHorizontal: 16, paddingVertical: 12, fontSize: 13, textAlign: "right", textAlignVertical: "center" },
  sendButton: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center" },
  sendText: { fontSize: 20, fontWeight: "900" },
  sheetHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12, borderBottomWidth: 1 },
  sheetTitle: { fontSize: 17, fontWeight: "700" },
  sheetClose: { fontSize: 17 },
  sheetBody: { padding: 20, paddingBottom: 30 },
  modelRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 16, paddingHorizontal: 14, borderRadius: 14 },
  modelLabel: { fontSize: 14 },
  modelCheck: { fontSize: 16, fontWeight: "800" },
  doneButton: { backgroundColor: "#FFFFFF", borderRadius: 12, paddingVertical: 14, alignItems: "center", marginTop: 16, borderWidth: 1, borderColor: "#E3E3E3" },
  doneButtonText: { color: "#000000", fontWeight: "700", fontSize: 15 },
  usageCard: { borderRadius: 14, borderWidth: 1, padding: 16, marginBottom: 16 },
  usagePlan: { fontSize: 16, fontWeight: "800" },
  usageCredit: { fontSize: 13, marginTop: 6 },
  usageRenew: { fontSize: 11, marginTop: 4 },
  usageRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: "rgba(128,128,128,0.15)" },
  usageAmount: { fontSize: 13, fontWeight: "700", width: 42 },
  usageTitle: { flex: 1 },
  usageTask: { fontSize: 13 },
  usageDate: { fontSize: 10, marginTop: 3 },
  integrationsActions: { flexDirection: "row", gap: 10, marginBottom: 14 },
  integrationsAction: { flex: 1, borderRadius: 12, paddingVertical: 12, alignItems: "center", justifyContent: "center" },
  integrationsActionText: { fontSize: 12, fontWeight: "600" },
  integrationsList: { paddingBottom: 10 },
  integrationRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 14, borderBottomWidth: 1 },
  integrationIcon: { width: 34, height: 34, borderRadius: 17, alignItems: "center", justifyContent: "center" },
  integrationIconText: { fontSize: 13, fontWeight: "700" },
  integrationName: { flex: 1, fontSize: 13 },
  integrationTrailing: { alignItems: "flex-end" },
  integrationMeta: { fontSize: 12 },
});
