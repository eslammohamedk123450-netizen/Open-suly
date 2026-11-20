import { useState } from "react";
import {
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
import { BottomNavigation } from "@/components/BottomNavigation";
import { useAuth } from "@/providers/AuthProvider";
import { createConversation, sendUserMessage } from "@/lib/conversations";

const suggestions = [
  { title: "ابحث بعمق", description: "اجمع المعلومات وقارن المصادر", prompt: "ابحث بعمق عن " },
  { title: "اكتب محتوى", description: "مقال أو خطة أو رسالة", prompt: "اكتب لي " },
  { title: "حلّل ملفًا", description: "استخرج النتائج والأفكار", prompt: "حلّل هذا الملف: " },
];

export default function HomeScreen() {
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const { user } = useAuth();

  const sendDraft = async () => {
    const request = draft.trim();
    if (!request || sending) return;
    if (!user) {
      setNotice("سجّل الدخول أولًا لحفظ محادثتك ومتابعتها.");
      router.push("/auth");
      return;
    }
    setSending(true);
    setNotice("");
    try {
      const conversation = await createConversation(request.slice(0, 40));
      await sendUserMessage(conversation.id, request);
      setDraft("");
      router.push({ pathname: "/conversation/[id]", params: { id: conversation.id } });
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر حفظ طلبك. حاول مرة أخرى.");
    } finally {
      setSending(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <View style={styles.brand}>
            <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
            <View>
              <Text style={styles.brandName}>SULY</Text>
              <Text style={styles.brandCaption}>INTELLIGENT PARTNER</Text>
            </View>
          </View>
          <View style={styles.headerActions}>
            <Pressable style={styles.iconButton} onPress={() => setMenuOpen((v) => !v)} accessibilityLabel="فتح القائمة">
              <Text style={styles.iconText}>☰</Text>
            </Pressable>
            <Pressable style={styles.avatar} onPress={() => router.push("/settings")} accessibilityLabel="الإعدادات">
              <Text style={styles.avatarText}>S</Text>
            </Pressable>
          </View>
        </View>

        {menuOpen && (
          <View style={styles.menu}>
            <Pressable style={styles.menuItem} onPress={() => { setMenuOpen(false); router.push("/settings"); }}>
              <Text style={styles.menuText}>الإعدادات</Text>
            </Pressable>
            <Pressable style={styles.menuItem} onPress={() => setMenuOpen(false)}>
              <Text style={styles.menuText}>إغلاق القائمة</Text>
            </Pressable>
          </View>
        )}

        <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
          <View style={styles.hero}>
            <View style={styles.eyebrow}><View style={styles.onlineDot} /><Text style={styles.eyebrowText}>مساحة عملك الذكية</Text></View>
            <Text style={styles.greeting}>أهلاً بك في <Text style={styles.gold}>SULY</Text></Text>
            <Text style={styles.subtitle}>فكرتك تبدأ هنا. اكتب ما تريد إنجازه، ودعنا نحوله إلى خطوات واضحة.</Text>
          </View>

          <View style={styles.composer}>
            <TextInput
              value={draft}
              onChangeText={(value) => { setDraft(value); setNotice(""); }}
              placeholder="اكتب مهمتك أو اسأل SULY عن أي شيء..."
              placeholderTextColor={colors.faint}
              multiline
              textAlignVertical="top"
              style={styles.input}
              selectionColor={colors.gold}
            />
            <View style={styles.composerFooter}>
              <View style={styles.tools}>
                <Pressable style={styles.toolButton} onPress={() => setNotice("إرفاق الملفات سيتم تفعيله ضمن مرحلة الملفات.")}>
                  <Text style={styles.toolText}>＋ ملف</Text>
                </Pressable>
                <Pressable style={styles.toolButton} onPress={() => router.push({ pathname: "/agent", params: draft.trim() ? { prompt: draft.trim() } : {} })}>
                  <Text style={styles.toolText}>◈ تنفيذ كمهمة</Text>
                </Pressable>
              </View>
              <Pressable style={[styles.sendButton, !draft.trim() && styles.sendDisabled]} onPress={sendDraft} accessibilityLabel="إرسال الطلب">
                <Text style={styles.sendText}>↑</Text>
              </Pressable>
            </View>
          </View>

          {!!notice && <Text style={styles.notice}>{notice}</Text>}

          <View style={styles.sectionHeading}>
            <Text style={styles.sectionTitle}>ابدأ من هنا</Text>
            <Text style={styles.sectionHint}>اختر نقطة بداية لمهمتك</Text>
          </View>
          <View style={styles.suggestionList}>
            {suggestions.map((item) => (
              <Pressable key={item.title} style={styles.suggestionCard} onPress={() => { setDraft(item.prompt); setNotice(""); }}>
                <View style={styles.suggestionIcon}><Text style={styles.suggestionIconText}>{item.title === "ابحث بعمق" ? "⌕" : item.title === "اكتب محتوى" ? "✎" : "▤"}</Text></View>
                <View style={styles.suggestionCopy}>
                  <Text style={styles.suggestionTitle}>{item.title}</Text>
                  <Text style={styles.suggestionDescription}>{item.description}</Text>
                </View>
                <Text style={styles.chevron}>‹</Text>
              </Pressable>
            ))}
          </View>

          <View style={styles.bottomNote}>
            <Text style={styles.bottomNoteTitle}>أكثر من مجرد ذكاء اصطناعي</Text>
            <Text style={styles.bottomNoteText}>SULY منصة مستقلة قيد البناء، مصممة لتساعدك على التخطيط والعمل والإنجاز.</Text>
          </View>
        </ScrollView>

        <BottomNavigation active="home" />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  page: { flex: 1, direction: "rtl", backgroundColor: colors.background, width: "100%", maxWidth: 1100, alignSelf: "center" },
  header: { minHeight: 72, paddingHorizontal: 22, flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderBottomWidth: 1, borderBottomColor: colors.border },
  brand: { flexDirection: "row", alignItems: "center", gap: 11 },
  logo: { width: 42, height: 42, borderRadius: 14, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  logoText: { color: colors.gold, fontSize: 25, fontWeight: "800" },
  brandName: { color: colors.text, fontSize: 17, fontWeight: "800", letterSpacing: 3 },
  brandCaption: { color: colors.faint, fontSize: 8, letterSpacing: 1.6, marginTop: 2 },
  headerActions: { flexDirection: "row", alignItems: "center", gap: 10 },
  iconButton: { width: 40, height: 40, borderRadius: 13, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  iconText: { color: colors.text, fontSize: 18 },
  avatar: { width: 40, height: 40, borderRadius: 14, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.goldDark, alignItems: "center", justifyContent: "center" },
  avatarText: { color: colors.gold, fontWeight: "800", fontSize: 17 },
  menu: { position: "absolute", top: 66, right: 20, zIndex: 5, width: 180, padding: 8, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  menuItem: { paddingVertical: 12, paddingHorizontal: 10 },
  menuText: { color: colors.text, textAlign: "right", fontSize: 14 },
  scrollContent: { paddingHorizontal: 22, paddingTop: 34, paddingBottom: 30, width: "100%", maxWidth: 760, alignSelf: "center" },
  hero: { marginBottom: 25 },
  eyebrow: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 16 },
  onlineDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.gold },
  eyebrowText: { color: colors.gold, fontSize: 12 },
  greeting: { color: colors.text, fontSize: 29, fontWeight: "800", textAlign: "right", lineHeight: 42 },
  gold: { color: colors.gold },
  subtitle: { color: colors.muted, fontSize: 14, lineHeight: 25, textAlign: "right", marginTop: 8 },
  composer: { borderRadius: 22, borderWidth: 1, borderColor: colors.goldDark, backgroundColor: colors.surface, padding: 15, minHeight: 170 },
  input: { minHeight: 94, color: colors.text, fontSize: 15, textAlign: "right", writingDirection: "rtl", lineHeight: 25, outlineStyle: "none" as never },
  composerFooter: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 10 },
  tools: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  toolButton: { paddingVertical: 8, paddingHorizontal: 11, borderRadius: 10, backgroundColor: colors.surfaceSecondary },
  toolText: { color: colors.muted, fontSize: 11 },
  sendButton: { width: 42, height: 42, borderRadius: 14, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center" },
  sendDisabled: { opacity: 0.45 },
  sendText: { color: colors.background, fontSize: 24, fontWeight: "800" },
  notice: { color: colors.gold, fontSize: 12, textAlign: "right", lineHeight: 20, marginTop: 12 },
  sectionHeading: { marginTop: 34, marginBottom: 14, flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" },
  sectionTitle: { color: colors.text, fontSize: 17, fontWeight: "700" },
  sectionHint: { color: colors.faint, fontSize: 11 },
  suggestionList: { gap: 10 },
  suggestionCard: { minHeight: 76, padding: 13, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, flexDirection: "row", alignItems: "center", gap: 12 },
  suggestionIcon: { width: 42, height: 42, borderRadius: 13, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  suggestionIconText: { color: colors.gold, fontSize: 22 },
  suggestionCopy: { flex: 1 },
  suggestionTitle: { color: colors.text, fontSize: 14, fontWeight: "700", textAlign: "right" },
  suggestionDescription: { color: colors.muted, fontSize: 11, marginTop: 5, textAlign: "right" },
  chevron: { color: colors.faint, fontSize: 23 },
  bottomNote: { marginTop: 26, padding: 17, borderRadius: 16, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  bottomNoteTitle: { color: colors.gold, fontSize: 13, fontWeight: "700", textAlign: "right" },
  bottomNoteText: { color: colors.muted, fontSize: 11, lineHeight: 20, textAlign: "right", marginTop: 7 },
  bottomNav: { minHeight: 66, paddingHorizontal: 8, paddingTop: 8, paddingBottom: 5, borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.background, flexDirection: "row", justifyContent: "space-around", alignItems: "center" },
  navItem: { flex: 1, alignItems: "center", justifyContent: "center", gap: 3, paddingVertical: 4 },
  navItemActive: { flex: 1, alignItems: "center", justifyContent: "center", gap: 3, paddingVertical: 4 },
  navIcon: { color: colors.faint, fontSize: 18 },
  navIconActive: { color: colors.gold, fontSize: 18 },
  navLabel: { color: colors.faint, fontSize: 10 },
  navLabelActive: { color: colors.gold, fontSize: 10, fontWeight: "700" },
});
