import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { colors } from "@/theme/tokens";
import { BottomNavigation } from "@/components/BottomNavigation";
import { useAuth } from "@/providers/AuthProvider";
import { createConversation, deleteConversation, listConversations, type Conversation } from "@/lib/conversations";

export default function ProjectsScreen() {
  const { user } = useAuth();
  const [items, setItems] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!user) { setItems([]); setLoading(false); return; }
    setLoading(true);
    setError("");
    try { setItems(await listConversations()); }
    catch (e) { setError(e instanceof Error ? e.message : "تعذر تحميل المحادثات."); }
    finally { setLoading(false); }
  }, [user]);

  useFocusEffect(useCallback(() => { void refresh(); }, [refresh]));

  const startConversation = async () => {
    if (!user) { router.push("/auth"); return; }
    setBusy(true);
    setError("");
    try {
      const item = await createConversation();
      router.push({ pathname: "/conversation/[id]", params: { id: item.id } });
    } catch (e) { setError(e instanceof Error ? e.message : "تعذر إنشاء المحادثة."); }
    finally { setBusy(false); }
  };

  const removeConversation = async (id: string) => {
    try { await deleteConversation(id); setItems((current) => current.filter((item) => item.id !== id)); }
    catch (e) { setError(e instanceof Error ? e.message : "تعذر حذف المحادثة."); }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
          <View style={styles.headerCopy}><Text style={styles.title}>المشاريع والمحادثات</Text><Text style={styles.subtitle}>كل محادثاتك محفوظة في حسابك</Text></View>
        </View>
        <ScrollView contentContainerStyle={styles.content}>
          <Pressable style={styles.createButton} onPress={startConversation} disabled={busy}>
            {busy ? <ActivityIndicator color={colors.background} /> : <Text style={styles.createText}>＋ محادثة جديدة</Text>}
          </Pressable>
          {!!error && <Text style={styles.error}>{error}</Text>}
          {!user ? (
            <View style={styles.empty}><Text style={styles.emptyTitle}>سجّل الدخول أولًا</Text><Text style={styles.emptyText}>سجّل الدخول لبدء المحادثات وحفظها ومزامنتها.</Text><Pressable onPress={() => router.push("/auth")}><Text style={styles.link}>تسجيل الدخول</Text></Pressable></View>
          ) : loading ? (
            <View style={styles.loading}><ActivityIndicator color={colors.gold} /><Text style={styles.emptyText}>جارٍ تحميل محادثاتك...</Text></View>
          ) : items.length === 0 ? (
            <View style={styles.empty}><Text style={styles.emptyTitle}>مساحتك جاهزة</Text><Text style={styles.emptyText}>ابدأ محادثة جديدة، وستظهر هنا تلقائيًا.</Text></View>
          ) : (
            <View style={styles.list}>
              {items.map((item) => (
                <View key={item.id} style={styles.card}>
                  <Pressable style={styles.cardMain} onPress={() => router.push({ pathname: "/conversation/[id]", params: { id: item.id } })}>
                    <Text style={styles.cardTitle} numberOfLines={1}>{item.title}</Text>
                    <Text style={styles.cardDate}>{new Date(item.updated_at).toLocaleString("ar-EG")}</Text>
                  </Pressable>
                  <Pressable style={styles.deleteButton} onPress={() => void removeConversation(item.id)} accessibilityLabel="حذف المحادثة"><Text style={styles.deleteText}>×</Text></Pressable>
                </View>
              ))}
            </View>
          )}
        </ScrollView>
        <BottomNavigation active="projects" />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background }, page: { flex: 1, direction: "rtl", width: "100%", maxWidth: 1100, alignSelf: "center", backgroundColor: colors.background },
  header: { minHeight: 72, paddingHorizontal: 20, flexDirection: "row", alignItems: "center", gap: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  logo: { width: 42, height: 42, borderRadius: 14, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" }, logoText: { color: colors.gold, fontSize: 25, fontWeight: "800" }, headerCopy: { flex: 1 }, title: { color: colors.text, fontSize: 17, fontWeight: "800", textAlign: "right" }, subtitle: { color: colors.muted, fontSize: 10, marginTop: 4, textAlign: "right" },
  content: { padding: 20, width: "100%", maxWidth: 760, alignSelf: "center", flexGrow: 1 }, createButton: { minHeight: 52, borderRadius: 15, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center", marginBottom: 18 }, createText: { color: colors.background, fontSize: 14, fontWeight: "800" },
  list: { gap: 10 }, card: { minHeight: 76, padding: 14, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, flexDirection: "row", alignItems: "center", gap: 10 }, cardMain: { flex: 1 }, cardTitle: { color: colors.text, fontSize: 13, fontWeight: "700", textAlign: "right" }, cardDate: { color: colors.faint, fontSize: 10, marginTop: 7, textAlign: "right" }, deleteButton: { width: 34, height: 34, borderRadius: 11, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" }, deleteText: { color: "#F08B8B", fontSize: 22 },
  empty: { padding: 24, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", marginTop: 18 }, emptyTitle: { color: colors.text, fontSize: 15, fontWeight: "800" }, emptyText: { color: colors.muted, fontSize: 11, textAlign: "center", lineHeight: 21, marginTop: 8 }, link: { color: colors.gold, fontSize: 12, fontWeight: "700", marginTop: 14 }, loading: { alignItems: "center", gap: 10, marginTop: 40 }, error: { color: "#F08B8B", fontSize: 11, textAlign: "right", marginBottom: 12 },
});
