import { useCallback, useState } from "react";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { colors } from "@/theme/tokens";
import { BottomNavigation } from "@/components/BottomNavigation";
import { useAuth } from "@/providers/AuthProvider";
import {
  createConversation, deleteConversation, listConversations, renameConversation,
  type Conversation,
} from "@/lib/conversations";

export default function ConversationsScreen() {
  const { user } = useAuth();
  const [items, setItems] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  const refresh = useCallback(async () => {
    if (!user) { setItems([]); setLoading(false); return; }
    setLoading(true);
    setError("");
    try { setItems(await listConversations()); }
    catch (e) { setError(e instanceof Error ? e.message : "تعذر تحميل المحادثات."); }
    finally { setLoading(false); }
  }, [user?.id]);

  useFocusEffect(useCallback(() => { void refresh(); }, [refresh]));

  const create = async () => {
    if (busy || !user) return;
    setBusy(true);
    setError("");
    try {
      const item = await createConversation(newTitle.trim() || "محادثة جديدة");
      setItems((current) => [item, ...current]);
      setNewTitle("");
      router.push({ pathname: "/conversation/[id]", params: { id: item.id } });
    } catch (e) { setError(e instanceof Error ? e.message : "تعذر إنشاء المحادثة."); }
    finally { setBusy(false); }
  };

  const saveRename = async () => {
    if (!editingId || busy) return;
    setBusy(true);
    setError("");
    try {
      const updated = await renameConversation(editingId, editingTitle);
      setItems((current) => current.map((item) => item.id === updated.id ? updated : item));
      setEditingId(null);
      setEditingTitle("");
    } catch (e) { setError(e instanceof Error ? e.message : "تعذر تعديل اسم المحادثة."); }
    finally { setBusy(false); }
  };

  const remove = (item: Conversation) => {
    Alert.alert("حذف المحادثة", "سيتم حذف المحادثة ورسائلها نهائيًا.", [
      { text: "إلغاء", style: "cancel" },
      { text: "حذف", style: "destructive", onPress: () => void (async () => {
        setBusy(true);
        setError("");
        try {
          await deleteConversation(item.id);
          setItems((current) => current.filter((row) => row.id !== item.id));
        } catch (e) { setError(e instanceof Error ? e.message : "تعذر حذف المحادثة."); }
        finally { setBusy(false); }
      })() },
    ]);
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
          <View style={styles.headerCopy}><Text style={styles.title}>محادثاتي</Text><Text style={styles.subtitle}>سجل محادثاتك الخاصة وإدارتها</Text></View>
        </View>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {!user ? (
            <View style={styles.empty}><Text style={styles.emptyTitle}>سجّل الدخول أولًا</Text><Pressable onPress={() => router.push("/auth")}><Text style={styles.link}>تسجيل الدخول</Text></Pressable></View>
          ) : (
            <>
              <View style={styles.createCard}>
                <Text style={styles.sectionTitle}>محادثة جديدة</Text>
                <TextInput value={newTitle} onChangeText={setNewTitle} placeholder="عنوان اختياري" placeholderTextColor={colors.faint} style={styles.input} maxLength={200} textAlign="right" />
                <Pressable style={[styles.primary, busy && styles.disabled]} onPress={create} disabled={busy}>
                  {busy ? <ActivityIndicator color={colors.background} /> : <Text style={styles.primaryText}>＋ ابدأ محادثة</Text>}
                </Pressable>
              </View>
              {!!error && <Text style={styles.error}>{error}</Text>}
              <View style={styles.listHeader}><Text style={styles.sectionTitle}>سجل المحادثات</Text><Text style={styles.count}>{items.length} محادثة</Text></View>
              {loading ? <ActivityIndicator color={colors.gold} /> : items.length === 0 ? (
                <View style={styles.empty}><Text style={styles.emptyTitle}>لا توجد محادثات بعد</Text><Text style={styles.muted}>ابدأ محادثة جديدة وستظهر هنا.</Text></View>
              ) : items.map((item) => (
                <View key={item.id} style={styles.card}>
                  {editingId === item.id ? (
                    <View style={styles.editArea}>
                      <TextInput value={editingTitle} onChangeText={setEditingTitle} style={styles.input} maxLength={200} textAlign="right" autoFocus />
                      <View style={styles.actions}>
                        <Pressable style={styles.smallPrimary} onPress={() => void saveRename()}><Text style={styles.smallPrimaryText}>حفظ</Text></Pressable>
                        <Pressable style={styles.smallButton} onPress={() => setEditingId(null)}><Text style={styles.smallText}>إلغاء</Text></Pressable>
                      </View>
                    </View>
                  ) : (
                    <>
                      <Pressable style={styles.main} onPress={() => router.push({ pathname: "/conversation/[id]", params: { id: item.id } })}>
                        <Text style={styles.itemTitle} numberOfLines={1}>{item.title}</Text>
                        <Text style={styles.muted}>آخر تحديث: {new Date(item.updated_at).toLocaleString("ar-EG")}</Text>
                        {!!item.project_id && <Text style={styles.projectTag}>مرتبطة بمشروع</Text>}
                      </Pressable>
                      <View style={styles.actions}>
                        <Pressable style={styles.smallButton} onPress={() => { setEditingId(item.id); setEditingTitle(item.title); }}><Text style={styles.smallText}>تعديل</Text></Pressable>
                        <Pressable style={styles.smallButton} onPress={() => remove(item)}><Text style={styles.deleteText}>حذف</Text></Pressable>
                      </View>
                    </>
                  )}
                </View>
              ))}
            </>
          )}
        </ScrollView>
        <BottomNavigation active="conversations" />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  page: { flex: 1, direction: "rtl", width: "100%", maxWidth: 1100, alignSelf: "center", backgroundColor: colors.background },
  header: { minHeight: 72, paddingHorizontal: 20, flexDirection: "row", alignItems: "center", gap: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  logo: { width: 42, height: 42, borderRadius: 14, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  logoText: { color: colors.gold, fontSize: 25, fontWeight: "800" },
  headerCopy: { flex: 1 },
  title: { color: colors.text, fontSize: 17, fontWeight: "800", textAlign: "right" },
  subtitle: { color: colors.muted, fontSize: 10, marginTop: 4, textAlign: "right" },
  content: { padding: 18, paddingBottom: 30, gap: 13, width: "100%", maxWidth: 760, alignSelf: "center", flexGrow: 1 },
  createCard: { padding: 15, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, gap: 10 },
  sectionTitle: { color: colors.text, fontSize: 14, fontWeight: "800", textAlign: "right" },
  input: { minHeight: 44, borderRadius: 11, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, paddingHorizontal: 12, color: colors.text, fontSize: 12 },
  primary: { minHeight: 46, borderRadius: 12, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center" },
  primaryText: { color: colors.background, fontSize: 12, fontWeight: "800" },
  disabled: { opacity: 0.5 },
  listHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  count: { color: colors.faint, fontSize: 10 },
  card: { padding: 13, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, flexDirection: "row", alignItems: "center", gap: 10 },
  main: { flex: 1, gap: 5 },
  itemTitle: { color: colors.text, fontSize: 12, fontWeight: "800", textAlign: "right" },
  muted: { color: colors.muted, fontSize: 10, textAlign: "right" },
  projectTag: { color: colors.gold, fontSize: 9, textAlign: "right" },
  actions: { flexDirection: "row", alignItems: "center", gap: 6 },
  smallButton: { paddingHorizontal: 10, paddingVertical: 8, borderRadius: 9, borderWidth: 1, borderColor: colors.border },
  smallText: { color: colors.muted, fontSize: 10 },
  deleteText: { color: "#E88787", fontSize: 10 },
  smallPrimary: { paddingHorizontal: 10, paddingVertical: 8, borderRadius: 9, backgroundColor: colors.gold },
  smallPrimaryText: { color: colors.background, fontSize: 10, fontWeight: "800" },
  editArea: { flex: 1, gap: 8 },
  empty: { padding: 22, borderRadius: 15, borderWidth: 1, borderColor: colors.border, alignItems: "center", gap: 8 },
  emptyTitle: { color: colors.text, fontSize: 13, fontWeight: "800" },
  link: { color: colors.gold, fontSize: 11, fontWeight: "700" },
  error: { color: "#E88787", fontSize: 11, textAlign: "center" },
});
