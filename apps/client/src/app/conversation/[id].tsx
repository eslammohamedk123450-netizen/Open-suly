import { useEffect, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useLocalSearchParams } from "expo-router";
import { colors } from "@/theme/tokens";
import { useAuth } from "@/providers/AuthProvider";
import { listMessages, sendUserMessage, type ChatMessage } from "@/lib/conversations";
import { requestAssistantReply } from "@/lib/chat-api";

export default function ConversationScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [engineNotice, setEngineNotice] = useState("");

  useEffect(() => {
    if (!user) { setMessages([]); setLoading(false); return; }
    let active = true;
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
        try {
          const reply = await requestAssistantReply(id, lastUserMessage.id);
          if (active) setMessages((current) => current.some((row) => row.id === reply.id) ? current : [...current, reply]);
        } catch (e) {
          if (active) setEngineNotice(e instanceof Error ? e.message : "محرك الردود غير متاح حاليًا.");
        }
      }
    })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "تعذر تحميل المحادثة."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, user]);

  const send = async () => {
    if (!draft.trim() || sending) return;
    if (!user) { router.push("/auth"); return; }
    const content = draft.trim();
    setDraft("");
    setSending(true);
    setError("");
    setEngineNotice("");
    try {
      const saved = await sendUserMessage(id, content);
      setMessages((current) => [...current, saved]);
      try {
        const reply = await requestAssistantReply(id, saved.id);
        setMessages((current) => current.some((row) => row.id === reply.id) ? current : [...current, reply]);
      } catch (replyError) {
        setEngineNotice(replyError instanceof Error ? replyError.message : "تم حفظ الرسالة، لكن الرد غير متاح حاليًا.");
      }
    } catch (e) {
      setDraft(content);
      setError(e instanceof Error ? e.message : "تعذر حفظ الرسالة.");
    } finally { setSending(false); }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView style={styles.page} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View style={styles.header}>
          <Pressable style={styles.backButton} onPress={() => router.replace("/projects")}><Text style={styles.backText}>→</Text></Pressable>
          <View style={styles.headerCopy}><Text style={styles.title}>محادثة SULY</Text><Text style={styles.subtitle}>مساحة محادثة خاصة بحسابك</Text></View>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
        </View>
        <ScrollView contentContainerStyle={styles.messages} keyboardShouldPersistTaps="handled">
          {loading ? <ActivityIndicator color={colors.gold} /> : messages.length === 0 ? (
            <View style={styles.welcome}><Text style={styles.welcomeTitle}>ابدأ من هنا</Text><Text style={styles.welcomeText}>اكتب أول رسالة. سيتم حفظها في حسابك بشكل خاص.</Text></View>
          ) : messages.map((message) => (
            <View key={message.id} style={message.role === "user" ? styles.userMessage : styles.assistantMessage}>
              <Text style={message.role === "user" ? styles.userText : styles.assistantText}>{message.content}</Text>
              <Text style={styles.time}>{new Date(message.created_at).toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" })}</Text>
            </View>
          ))}
          {!!error && <Text style={styles.error}>{error}</Text>}
          {!!engineNotice && <Text style={styles.engineNotice}>{engineNotice}</Text>}
        </ScrollView>
        <View style={styles.composer}>
          <TextInput value={draft} onChangeText={setDraft} placeholder="اكتب رسالتك..." placeholderTextColor={colors.faint} style={styles.input} multiline textAlign="right" textAlignVertical="center" />
          <Pressable style={[styles.sendButton, (!draft.trim() || sending) && styles.disabled]} onPress={send} disabled={!draft.trim() || sending}>
            {sending ? <ActivityIndicator color={colors.background} /> : <Text style={styles.sendText}>↑</Text>}
          </Pressable>
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
  userMessage: { alignSelf: "flex-end", maxWidth: "88%", borderRadius: 18, borderBottomRightRadius: 5, padding: 13, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.goldDark }, assistantMessage: { alignSelf: "flex-start", maxWidth: "88%", borderRadius: 18, borderBottomLeftRadius: 5, padding: 13, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  userText: { color: colors.text, fontSize: 13, lineHeight: 22, textAlign: "right" }, assistantText: { color: colors.muted, fontSize: 13, lineHeight: 22, textAlign: "left" }, time: { color: colors.faint, fontSize: 9, marginTop: 7, textAlign: "left" },
  engineNotice: { color: colors.faint, fontSize: 10, textAlign: "center", marginTop: 8 }, error: { color: "#F08B8B", fontSize: 11, textAlign: "center" },
  composer: { width: "100%", maxWidth: 760, alignSelf: "center", padding: 12, flexDirection: "row", alignItems: "flex-end", gap: 9, borderTopWidth: 1, borderTopColor: colors.border }, input: { flex: 1, minHeight: 48, maxHeight: 130, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, color: colors.text, paddingHorizontal: 13, paddingVertical: 12, fontSize: 13 },
  sendButton: { width: 46, height: 46, borderRadius: 15, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center" }, sendText: { color: colors.background, fontSize: 25, fontWeight: "900" }, disabled: { opacity: 0.45 },
});
