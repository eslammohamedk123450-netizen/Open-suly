import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet,
  Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { colors } from "@/theme/tokens";
import { BottomNavigation } from "@/components/BottomNavigation";
import { useAuth } from "@/providers/AuthProvider";
import {
  createAgentMemory, deleteAgentMemory, listAgentMemories, type AgentMemory,
} from "@/lib/agent-memory";

export default function AgentMemoryScreen() {
  const { user, configured } = useAuth();
  const [items, setItems] = useState<AgentMemory[]>([]);
  const [content, setContent] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError("");
    try {
      setItems(await listAgentMemories());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذر تحميل الذاكرة.");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => { void load(); }, [load]);

  const save = async () => {
    const clean = content.trim();
    if (!clean) {
      setError("اكتب المعلومة التي تريد حفظها أولًا.");
      return;
    }
    if (clean.length > 2000) {
      setError("الحد الأقصى للملاحظة 2000 حرف.");
      return;
    }
    const tags = [...new Set(tagsText.split(",").map((tag) => tag.trim().toLowerCase()).filter(Boolean))].slice(0, 8);
    if (tags.some((tag) => !/^[a-z0-9][a-z0-9_-]{0,31}$/.test(tag))) {
      setError("اكتب الوسوم بالإنجليزية الصغيرة، مثل learning أو preferences.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await createAgentMemory(clean, tags);
      setContent("");
      setTagsText("");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذر حفظ الملاحظة.");
    } finally {
      setSaving(false);
    }
  };

  const remove = (item: AgentMemory) => {
    Alert.alert(
      "حذف الملاحظة",
      "سيتم حذف هذه الملاحظة من ذاكرة SULY نهائيًا.",
      [
        { text: "إلغاء", style: "cancel" },
        {
          text: "حذف",
          style: "destructive",
          onPress: async () => {
            setDeletingId(item.id);
            setError("");
            try {
              await deleteAgentMemory(item.id);
              setItems((current) => current.filter((entry) => entry.id !== item.id));
            } catch (cause) {
              setError(cause instanceof Error ? cause.message : "تعذر حذف الملاحظة.");
            } finally {
              setDeletingId("");
            }
          },
        },
      ],
    );
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
          <View style={styles.headerCopy}>
            <Text style={styles.title}>ذاكرة SULY</Text>
            <Text style={styles.subtitle}>معلومات تحفظها أنت وتتحكم فيها</Text>
          </View>
          <Pressable style={styles.back} onPress={() => router.back()}>
            <Text style={styles.backText}>→</Text>
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.notice}>
            <Text style={styles.noticeTitle}>ذاكرة بموافقتك فقط</Text>
            <Text style={styles.noticeText}>
              لا يحفظ SULY الملاحظات تلقائيًا. ما تضيفه هنا يمكن إرفاقه كسياق محدود لمهام Hermes وOpenCode عند تفعيل الذاكرة على الخادم.
              لا تحفظ كلمات المرور أو مفاتيح API أو البيانات الشخصية الحساسة.
            </Text>
          </View>

          {!configured && <Text style={styles.error}>اتصال الحساب غير مهيأ.</Text>}
          {!user && (
            <Pressable style={styles.primary} onPress={() => router.push("/auth")}>
              <Text style={styles.primaryText}>سجّل الدخول لإدارة الذاكرة</Text>
            </Pressable>
          )}

          {!!user && (
            <>
              <Text style={styles.section}>إضافة ملاحظة</Text>
              <View style={styles.form}>
                <TextInput
                  value={content}
                  onChangeText={setContent}
                  multiline
                  maxLength={2000}
                  placeholder="مثال: أفضل الشرح المختصر مع مهمة عملية بعد كل درس."
                  placeholderTextColor={colors.faint}
                  style={styles.input}
                  textAlignVertical="top"
                />
                <TextInput
                  value={tagsText}
                  onChangeText={setTagsText}
                  placeholder="وسوم اختيارية: learning, preferences"
                  placeholderTextColor={colors.faint}
                  style={styles.tagInput}
                  autoCapitalize="none"
                />
                <View style={styles.formFooter}>
                  <Text style={styles.counter}>{content.length}/2000</Text>
                  <Pressable style={[styles.saveButton, saving && styles.disabled]} onPress={() => void save()} disabled={saving}>
                    {saving ? <ActivityIndicator color={colors.background} /> : <Text style={styles.saveText}>حفظ الملاحظة</Text>}
                  </Pressable>
                </View>
              </View>

              <View style={styles.listHeader}>
                <Text style={styles.section}>الملاحظات المحفوظة</Text>
                <Pressable onPress={() => void load()}><Text style={styles.refresh}>تحديث</Text></Pressable>
              </View>

              {loading && <ActivityIndicator color={colors.gold} style={{ marginVertical: 22 }} />}
              {!loading && items.length === 0 && (
                <View style={styles.empty}>
                  <Text style={styles.emptyTitle}>لا توجد ملاحظات بعد</Text>
                  <Text style={styles.emptyText}>أضف المعلومات التي تريد أن يستفيد منها SULY في المهام القادمة.</Text>
                </View>
              )}
              {items.map((item) => (
                <View key={item.id} style={styles.memoryCard}>
                  <Text style={styles.memoryContent}>{item.content}</Text>
                  {!!item.tags?.length && (
                    <View style={styles.tags}>
                      {item.tags.map((tag) => <Text key={tag} style={styles.tag}>{tag}</Text>)}
                    </View>
                  )}
                  <View style={styles.cardFooter}>
                    <Text style={styles.date}>{new Date(item.updated_at).toLocaleDateString()}</Text>
                    <Pressable onPress={() => remove(item)} disabled={deletingId === item.id}>
                      {deletingId === item.id
                        ? <ActivityIndicator color="#E58B8B" />
                        : <Text style={styles.delete}>حذف</Text>}
                    </Pressable>
                  </View>
                </View>
              ))}
            </>
          )}
          {!!error && <Text style={styles.error}>{error}</Text>}
        </ScrollView>
        <BottomNavigation active="settings" />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  page: { flex: 1, width: "100%", maxWidth: 1100, alignSelf: "center", backgroundColor: colors.background },
  header: { minHeight: 72, paddingHorizontal: 20, flexDirection: "row", alignItems: "center", borderBottomWidth: 1, borderBottomColor: colors.border },
  logo: { width: 40, height: 40, borderRadius: 13, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  logoText: { color: colors.gold, fontSize: 23, fontWeight: "800" },
  headerCopy: { flex: 1, alignItems: "flex-end", marginHorizontal: 14 },
  title: { color: colors.text, fontSize: 17, fontWeight: "800" },
  subtitle: { color: colors.muted, fontSize: 10, marginTop: 4 },
  back: { width: 40, height: 40, borderRadius: 13, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  backText: { color: colors.gold, fontSize: 22 },
  content: { padding: 20, paddingBottom: 36, width: "100%", maxWidth: 760, alignSelf: "center" },
  notice: { borderRadius: 16, borderWidth: 1, borderColor: colors.goldDark, backgroundColor: colors.surface, padding: 15, marginBottom: 20 },
  noticeTitle: { color: colors.gold, fontSize: 13, fontWeight: "800", textAlign: "right" },
  noticeText: { color: colors.muted, fontSize: 11, lineHeight: 20, textAlign: "right", marginTop: 8 },
  section: { color: colors.gold, fontSize: 13, fontWeight: "800", textAlign: "right", marginBottom: 10 },
  form: { borderRadius: 16, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, padding: 13, marginBottom: 22 },
  input: { minHeight: 110, color: colors.text, fontSize: 13, lineHeight: 21, textAlign: "right", padding: 10, borderRadius: 12, backgroundColor: colors.surfaceSecondary },
  tagInput: { height: 42, color: colors.text, fontSize: 11, textAlign: "right", paddingHorizontal: 10, marginTop: 9, borderRadius: 10, backgroundColor: colors.surfaceSecondary },
  formFooter: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 12 },
  counter: { color: colors.faint, fontSize: 10 },
  saveButton: { minWidth: 125, height: 40, borderRadius: 12, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center", paddingHorizontal: 14 },
  saveText: { color: colors.background, fontSize: 11, fontWeight: "800" },
  disabled: { opacity: 0.6 },
  listHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 8 },
  refresh: { color: colors.gold, fontSize: 11, fontWeight: "700" },
  empty: { borderRadius: 15, padding: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: "center" },
  emptyTitle: { color: colors.text, fontSize: 13, fontWeight: "700" },
  emptyText: { color: colors.muted, fontSize: 11, textAlign: "center", marginTop: 6, lineHeight: 18 },
  memoryCard: { borderRadius: 15, padding: 15, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, marginBottom: 10 },
  memoryContent: { color: colors.text, fontSize: 12, lineHeight: 20, textAlign: "right" },
  tags: { flexDirection: "row", justifyContent: "flex-end", flexWrap: "wrap", gap: 6, marginTop: 10 },
  tag: { color: colors.gold, fontSize: 9, backgroundColor: colors.surfaceSecondary, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 8 },
  cardFooter: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 12 },
  date: { color: colors.faint, fontSize: 9 },
  delete: { color: "#E58B8B", fontSize: 11, fontWeight: "700" },
  error: { color: "#E58B8B", fontSize: 11, textAlign: "right", marginTop: 10 },
  primary: { minHeight: 46, borderRadius: 12, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center" },
  primaryText: { color: colors.background, fontSize: 12, fontWeight: "800" },
});
