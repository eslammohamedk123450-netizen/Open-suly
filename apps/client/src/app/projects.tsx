import { useCallback, useState } from "react";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { colors } from "@/theme/tokens";
import { BottomNavigation } from "@/components/BottomNavigation";
import { useAuth } from "@/providers/AuthProvider";
import { createProject, deleteProject, listProjects, type SulyProject } from "@/lib/projects";

export default function ProjectsScreen() {
  const { user } = useAuth();
  const [items, setItems] = useState<SulyProject[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!user) { setItems([]); setLoading(false); return; }
    setLoading(true);
    setError("");
    try { setItems(await listProjects()); }
    catch (e) { setError(e instanceof Error ? e.message : "تعذر تحميل المشاريع."); }
    finally { setLoading(false); }
  }, [user?.id]);

  useFocusEffect(useCallback(() => { void refresh(); }, [refresh]));

  const addProject = async () => {
    if (!user) { router.push("/auth"); return; }
    if (!name.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const project = await createProject(name, description);
      setItems((current) => [project, ...current]);
      setName("");
      setDescription("");
      router.push({ pathname: "/project/[id]", params: { id: project.id } });
    } catch (e) { setError(e instanceof Error ? e.message : "تعذر إنشاء المشروع."); }
    finally { setBusy(false); }
  };

  const confirmRemoveProject = (projectId: string, projectName: string) => {
    Alert.alert("حذف المشروع", `هل تريد حذف مشروع «${projectName}»؟ ستبقى المهام محفوظة خارج المشروع.`, [
      { text: "إلغاء", style: "cancel" },
      { text: "حذف", style: "destructive", onPress: () => void removeProject(projectId) },
    ]);
  };

  const removeProject = async (projectId: string) => {
    setBusy(true);
    setError("");
    try {
      await deleteProject(projectId);
      setItems((current) => current.filter((item) => item.id !== projectId));
    } catch (e) { setError(e instanceof Error ? e.message : "تعذر حذف المشروع."); }
    finally { setBusy(false); }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
          <View style={styles.headerCopy}><Text style={styles.title}>مشروعاتي</Text><Text style={styles.subtitle}>مساحات عمل مستقلة لمهامك وملفاتك</Text></View>
        </View>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {!user ? (
            <View style={styles.empty}>
              <Text style={styles.emptyTitle}>سجّل الدخول أولًا</Text>
              <Text style={styles.emptyText}>مشروعاتك ومهامك خاصة بحسابك.</Text>
              <Pressable onPress={() => router.push("/auth")}><Text style={styles.link}>تسجيل الدخول</Text></Pressable>
            </View>
          ) : (
            <>
              <View style={styles.form}>
                <Text style={styles.sectionTitle}>إنشاء مساحة مشروع</Text>
                <TextInput value={name} onChangeText={setName} placeholder="اسم المشروع" placeholderTextColor={colors.faint} style={styles.input} textAlign="right" maxLength={120} />
                <TextInput value={description} onChangeText={setDescription} placeholder="وصف مختصر (اختياري)" placeholderTextColor={colors.faint} style={[styles.input, styles.descriptionInput]} textAlign="right" multiline maxLength={2000} />
                <Pressable style={[styles.createButton, (!name.trim() || busy) && styles.disabled]} onPress={addProject} disabled={!name.trim() || busy}>
                  {busy ? <ActivityIndicator color={colors.background} /> : <Text style={styles.createText}>＋ إنشاء المشروع</Text>}
                </Pressable>
              </View>
              {!!error && <Text style={styles.error}>{error}</Text>}
              <View style={styles.listHeader}>
                <Text style={styles.sectionTitle}>مساحات العمل</Text>
                <Text style={styles.count}>{items.length} مشروع</Text>
              </View>
              {loading ? (
                <View style={styles.loading}><ActivityIndicator color={colors.gold} /><Text style={styles.emptyText}>جارٍ تحميل مشاريعك...</Text></View>
              ) : items.length === 0 ? (
                <View style={styles.empty}><Text style={styles.emptyTitle}>ابدأ أول مشروع</Text><Text style={styles.emptyText}>أنشئ مساحة تجمع المهام المرتبطة بنفس العمل.</Text></View>
              ) : (
                <View style={styles.list}>
                  {items.map((item) => (
                    <View key={item.id} style={styles.card}>
                      <Pressable style={styles.cardMain} onPress={() => router.push({ pathname: "/project/[id]", params: { id: item.id } })}>
                        <Text style={styles.cardTitle} numberOfLines={1}>{item.name}</Text>
                        {!!item.description && <Text style={styles.cardDescription} numberOfLines={2}>{item.description}</Text>}
                        <Text style={styles.cardDate}>آخر تحديث: {new Date(item.updated_at).toLocaleDateString("ar-EG")}</Text>
                      </Pressable>
                      <Pressable style={styles.openButton} onPress={() => router.push({ pathname: "/project/[id]", params: { id: item.id } })}><Text style={styles.openText}>فتح</Text></Pressable>
                      <Pressable style={styles.deleteButton} onPress={() => confirmRemoveProject(item.id, item.name)} disabled={busy} accessibilityLabel="حذف المشروع"><Text style={styles.deleteText}>×</Text></Pressable>
                    </View>
                  ))}
                </View>
              )}
            </>
          )}
        </ScrollView>
        <BottomNavigation active="projects" />
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
  content: { padding: 20, width: "100%", maxWidth: 760, alignSelf: "center", flexGrow: 1, gap: 16 },
  form: { padding: 16, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, gap: 10 },
  sectionTitle: { color: colors.text, fontSize: 14, fontWeight: "800", textAlign: "right" },
  input: { minHeight: 46, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, paddingHorizontal: 12, color: colors.text, fontSize: 12 },
  descriptionInput: { minHeight: 66, paddingVertical: 10, textAlignVertical: "top" },
  createButton: { minHeight: 48, borderRadius: 13, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center" },
  createText: { color: colors.background, fontSize: 13, fontWeight: "800" },
  disabled: { opacity: 0.45 },
  listHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  count: { color: colors.faint, fontSize: 10 },
  list: { gap: 10 },
  card: { minHeight: 82, padding: 13, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, flexDirection: "row", alignItems: "center", gap: 9 },
  cardMain: { flex: 1, gap: 5 },
  cardTitle: { color: colors.text, fontSize: 13, fontWeight: "800", textAlign: "right" },
  cardDescription: { color: colors.muted, fontSize: 10, lineHeight: 17, textAlign: "right" },
  cardDate: { color: colors.faint, fontSize: 9, textAlign: "right" },
  openButton: { paddingHorizontal: 12, minHeight: 34, borderRadius: 10, borderWidth: 1, borderColor: colors.goldDark, alignItems: "center", justifyContent: "center" },
  openText: { color: colors.gold, fontSize: 10, fontWeight: "700" },
  deleteButton: { width: 32, height: 34, borderRadius: 10, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  deleteText: { color: "#F08B8B", fontSize: 21 },
  empty: { padding: 24, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", gap: 8 },
  emptyTitle: { color: colors.text, fontSize: 15, fontWeight: "800" },
  emptyText: { color: colors.muted, fontSize: 11, textAlign: "center", lineHeight: 21 },
  link: { color: colors.gold, fontSize: 12, fontWeight: "700", marginTop: 8 },
  loading: { alignItems: "center", gap: 10, padding: 25 },
  error: { color: "#F08B8B", fontSize: 11, textAlign: "right" },
});
