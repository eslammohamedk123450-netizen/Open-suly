import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { colors } from "@/theme/tokens";
import { useAuth } from "@/providers/AuthProvider";
import { listProjects, type SulyProject } from "@/lib/projects";
import { listAgentTasks, type AgentTask } from "@/lib/agent-tasks";

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    queued: "في الانتظار", planning: "جارٍ التخطيط", ready: "جاهزة",
    running: "قيد التنفيذ", waiting_approval: "تنتظر الموافقة",
    completed: "اكتملت", failed: "فشلت", cancelled: "أُلغيت",
  };
  return labels[status] ?? status;
}

export default function ProjectDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const [project, setProject] = useState<SulyProject | null>(null);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!user || !id) { setLoading(false); return; }
    setLoading(true);
    setError("");
    try {
      const [projects, projectTasks] = await Promise.all([listProjects(), listAgentTasks(100, id)]);
      setProject(projects.find((item) => item.id === id) ?? null);
      setTasks(projectTasks);
    } catch (e) { setError(e instanceof Error ? e.message : "تعذر تحميل المشروع."); }
    finally { setLoading(false); }
  }, [user?.id, id]);

  useFocusEffect(useCallback(() => { void refresh(); }, [refresh]));

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <Pressable style={styles.back} onPress={() => router.back()}><Text style={styles.backText}>→</Text></Pressable>
          <View style={styles.headerCopy}>
            <Text style={styles.title}>{project?.name ?? "المشروع"}</Text>
            <Text style={styles.subtitle}>مساحة عمل ومهام المشروع</Text>
          </View>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
        </View>
        <ScrollView contentContainerStyle={styles.content}>
          {loading ? (
            <View style={styles.state}><ActivityIndicator color={colors.gold} /><Text style={styles.muted}>جارٍ تحميل مساحة المشروع...</Text></View>
          ) : error ? (
            <View style={styles.empty}><Text style={styles.error}>{error}</Text><Pressable onPress={() => void refresh()}><Text style={styles.link}>إعادة المحاولة</Text></Pressable></View>
          ) : !project ? (
            <View style={styles.empty}><Text style={styles.heading}>المشروع غير موجود</Text><Text style={styles.muted}>قد يكون حُذف أو لا تملك صلاحية الوصول إليه.</Text></View>
          ) : (
            <>
              {!!project.description && <Text style={styles.description}>{project.description}</Text>}
              <View style={styles.summary}>
                <View><Text style={styles.summaryNumber}>{tasks.length}</Text><Text style={styles.muted}>المهام</Text></View>
                <View><Text style={styles.summaryNumber}>{tasks.filter((task) => task.status === "completed").length}</Text><Text style={styles.muted}>المكتملة</Text></View>
                <View><Text style={styles.summaryNumber}>{tasks.filter((task) => ["running", "ready", "queued", "planning"].includes(task.status)).length}</Text><Text style={styles.muted}>النشطة</Text></View>
              </View>
              <Pressable style={styles.primary} onPress={() => router.push({ pathname: "/agent", params: { projectId: project.id } })}>
                <Text style={styles.primaryText}>＋ إنشاء مهمة في المشروع</Text>
              </Pressable>
              <Pressable style={styles.filesButton} onPress={() => router.push({ pathname: "/project/[id]/files", params: { id: project.id } })}>
                <Text style={styles.filesButtonText}>⌘ ملفات المشروع ومحرر الأكواد</Text>
              </Pressable>
              <View style={styles.listHeader}><Text style={styles.heading}>مهام المشروع</Text><Text style={styles.muted}>{tasks.length} مهمة</Text></View>
              {tasks.length === 0 ? (
                <View style={styles.empty}><Text style={styles.heading}>لا توجد مهام بعد</Text><Text style={styles.muted}>ابدأ بمهمة وسيتم حفظها داخل مساحة المشروع.</Text></View>
              ) : (
                <View style={styles.list}>
                  {tasks.map((task) => (
                    <Pressable key={task.id} style={styles.taskCard} onPress={() => router.push({ pathname: "/task/[id]", params: { id: task.id } })}>
                      <View style={styles.taskHeader}>
                        <Text style={[styles.status, task.status === "completed" ? styles.success : task.status === "failed" ? styles.failure : styles.gold]}>{statusLabel(task.status)}</Text>
                        <Text style={styles.taskTitle} numberOfLines={2}>{task.title}</Text>
                      </View>
                      <Text style={styles.taskRequest} numberOfLines={3}>{task.request}</Text>
                      <Text style={styles.taskDate}>{task.created_at ? new Date(task.created_at).toLocaleString("ar-EG") : ""}</Text>
                    </Pressable>
                  ))}
                </View>
              )}
            </>
          )}
        </ScrollView>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  page: { flex: 1, direction: "rtl", width: "100%", maxWidth: 1100, alignSelf: "center", backgroundColor: colors.background },
  header: { minHeight: 70, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", gap: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  back: { width: 40, height: 40, borderRadius: 13, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  backText: { color: colors.gold, fontSize: 22 },
  headerCopy: { flex: 1 },
  title: { color: colors.text, fontSize: 15, fontWeight: "800", textAlign: "right" },
  subtitle: { color: colors.muted, fontSize: 10, marginTop: 4, textAlign: "right" },
  logo: { width: 40, height: 40, borderRadius: 13, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  logoText: { color: colors.gold, fontSize: 22, fontWeight: "800" },
  content: { padding: 18, paddingBottom: 36, gap: 15, width: "100%", maxWidth: 760, alignSelf: "center" },
  description: { color: colors.muted, fontSize: 12, lineHeight: 21, textAlign: "right" },
  summary: { flexDirection: "row", justifyContent: "space-around", padding: 16, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  summaryNumber: { color: colors.gold, fontSize: 21, fontWeight: "800", textAlign: "center" },
  muted: { color: colors.muted, fontSize: 10, textAlign: "center", marginTop: 4 },
  primary: { minHeight: 48, borderRadius: 13, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center" },
  primaryText: { color: colors.background, fontSize: 13, fontWeight: "800" },
  filesButton: { minHeight: 46, borderRadius: 13, borderWidth: 1, borderColor: colors.goldDark, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  filesButtonText: { color: colors.gold, fontSize: 12, fontWeight: "700" },
  listHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  heading: { color: colors.text, fontSize: 14, fontWeight: "800", textAlign: "right" },
  list: { gap: 10 },
  taskCard: { padding: 14, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, gap: 8 },
  taskHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10 },
  taskTitle: { flex: 1, color: colors.text, fontSize: 12, fontWeight: "700", textAlign: "right" },
  status: { fontSize: 10, fontWeight: "700" },
  gold: { color: colors.gold },
  success: { color: "#69C99A" },
  failure: { color: "#E88787" },
  taskRequest: { color: colors.muted, fontSize: 10, lineHeight: 18, textAlign: "right" },
  taskDate: { color: colors.faint, fontSize: 9 },
  empty: { padding: 22, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", gap: 8 },
  state: { padding: 28, alignItems: "center", gap: 10 },
  error: { color: "#E88787", fontSize: 11, textAlign: "center" },
  link: { color: colors.gold, fontSize: 11, fontWeight: "700" },
});
