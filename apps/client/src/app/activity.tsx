import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { colors } from "@/theme/tokens";
import { useAuth } from "@/providers/AuthProvider";
import { listAgentTasks, type AgentTask } from "@/lib/agent-tasks";
import { BottomNavigation } from "@/components/BottomNavigation";

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
  };
  return labels[status] ?? status;
}

function statusColor(status: string): string {
  if (status === "completed") return "#69C99A";
  if (status === "failed" || status === "cancelled") return "#E88787";
  return colors.gold;
}

function formatDate(value?: string): string {
  if (!value) return "وقت الإنشاء غير متاح";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "وقت الإنشاء غير متاح";
  return date.toLocaleString("ar-EG", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ActivityScreen() {
  const { user } = useAuth();
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [notice, setNotice] = useState("");

  const loadTasks = useCallback(async (refresh = false) => {
    if (!user) {
      setTasks([]);
      setLoading(false);
      return;
    }
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setNotice("");
    try {
      setTasks(await listAgentTasks(50));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر تحميل سجل المهام.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [user?.id]);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <View style={styles.brand}>
            <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
            <View>
              <Text style={styles.brandName}>SULY</Text>
              <Text style={styles.brandCaption}>سجل تنفيذ المهام</Text>
            </View>
          </View>
          <Pressable style={styles.refreshButton} onPress={() => void loadTasks(true)} disabled={refreshing || loading}>
            {refreshing ? <ActivityIndicator color={colors.gold} /> : <Text style={styles.refreshText}>تحديث</Text>}
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.heading}>
            <View style={styles.headingCopy}>
              <Text style={styles.title}>النشاط</Text>
              <Text style={styles.description}>تابع المهام التي أرسلتها إلى SULY وحالتها ووقت إنشائها.</Text>
            </View>
            <Pressable style={styles.primaryButton} onPress={() => router.push("/agent")}>
              <Text style={styles.primaryText}>مساحة الوكيل</Text>
            </Pressable>
          </View>

          {!user ? (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyTitle}>سجّل الدخول لعرض نشاطك</Text>
              <Text style={styles.description}>سجل المهام مرتبط بحسابك ولا يظهر إلا لك.</Text>
              <Pressable style={styles.primaryButton} onPress={() => router.push("/auth")}>
                <Text style={styles.primaryText}>تسجيل الدخول</Text>
              </Pressable>
            </View>
          ) : loading ? (
            <View style={styles.stateCard}>
              <ActivityIndicator color={colors.gold} />
              <Text style={styles.description}>جارٍ تحميل سجل المهام...</Text>
            </View>
          ) : notice ? (
            <View style={styles.emptyCard}>
              <Text style={styles.notice}>{notice}</Text>
              <Pressable style={styles.secondaryButton} onPress={() => void loadTasks(true)}>
                <Text style={styles.secondaryText}>إعادة المحاولة</Text>
              </Pressable>
            </View>
          ) : tasks.length === 0 ? (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyTitle}>لا توجد مهام حتى الآن</Text>
              <Text style={styles.description}>عندما ترسل مهمة من مساحة الوكيل، ستظهر هنا مع حالتها.</Text>
              <Pressable style={styles.primaryButton} onPress={() => router.push("/agent")}>
                <Text style={styles.primaryText}>ابدأ أول مهمة</Text>
              </Pressable>
            </View>
          ) : (
            <View style={styles.list}>
              <Text style={styles.count}>{tasks.length} مهمة حديثة</Text>
              {tasks.map((task) => (
                <Pressable key={task.id} style={styles.taskCard} onPress={() => router.push({ pathname: "/task/[id]", params: { id: task.id } })}>
                  <View style={styles.taskHeader}>
                    <Text style={[styles.status, { color: statusColor(task.status) }]}>{statusLabel(task.status)}</Text>
                    <Text style={styles.taskTitle} numberOfLines={2}>{task.title}</Text>
                  </View>
                  <Text style={styles.request} numberOfLines={3}>{task.request}</Text>
                  <View style={styles.metaRow}>
                    <Text style={styles.date}>{formatDate(task.created_at)}</Text>
                    <Text style={styles.taskId}>{task.id.slice(0, 8)}</Text>
                  </View>
                  {!!task.error_message && <Text style={styles.error} numberOfLines={2}>{task.error_message}</Text>}
                </Pressable>
              ))}
            </View>
          )}
        </ScrollView>
        <BottomNavigation active="activity" />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  page: { flex: 1, direction: "rtl", width: "100%", maxWidth: 1100, alignSelf: "center", backgroundColor: colors.background },
  header: { minHeight: 72, paddingHorizontal: 20, flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderBottomWidth: 1, borderBottomColor: colors.border },
  brand: { flexDirection: "row", alignItems: "center", gap: 11 },
  logo: { width: 42, height: 42, borderRadius: 14, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  logoText: { color: colors.gold, fontSize: 25, fontWeight: "800" },
  brandName: { color: colors.text, fontSize: 17, fontWeight: "800", letterSpacing: 3 },
  brandCaption: { color: colors.faint, fontSize: 9, marginTop: 3 },
  refreshButton: { minWidth: 66, height: 38, borderRadius: 11, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  refreshText: { color: colors.gold, fontSize: 11, fontWeight: "700" },
  content: { padding: 18, paddingBottom: 30, gap: 16, width: "100%", maxWidth: 760, alignSelf: "center" },
  heading: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  headingCopy: { flex: 1, gap: 5 },
  title: { color: colors.text, fontSize: 23, fontWeight: "800", textAlign: "right" },
  description: { color: colors.muted, fontSize: 11, lineHeight: 20, textAlign: "right" },
  primaryButton: { minHeight: 40, borderRadius: 11, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center", paddingHorizontal: 14 },
  primaryText: { color: colors.background, fontSize: 11, fontWeight: "800" },
  secondaryButton: { minHeight: 40, borderRadius: 11, borderWidth: 1, borderColor: colors.goldDark, alignItems: "center", justifyContent: "center", paddingHorizontal: 14 },
  secondaryText: { color: colors.gold, fontSize: 11, fontWeight: "700" },
  list: { gap: 10 },
  count: { color: colors.faint, fontSize: 10, textAlign: "right" },
  taskCard: { padding: 14, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, gap: 9 },
  taskHeader: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 },
  taskTitle: { flex: 1, color: colors.text, fontSize: 13, fontWeight: "700", textAlign: "right" },
  status: { fontSize: 10, fontWeight: "700" },
  request: { color: colors.muted, fontSize: 11, lineHeight: 19, textAlign: "right" },
  metaRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  date: { color: colors.faint, fontSize: 9 },
  taskId: { color: colors.faint, fontSize: 9 },
  error: { color: "#E88787", fontSize: 10, textAlign: "right" },
  emptyCard: { padding: 22, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", gap: 12 },
  stateCard: { minHeight: 150, alignItems: "center", justifyContent: "center", gap: 12 },
  emptyTitle: { color: colors.text, fontSize: 15, fontWeight: "800", textAlign: "center" },
  notice: { color: "#E88787", fontSize: 11, lineHeight: 19, textAlign: "center" },
});
