import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { useTheme } from "@/providers/ThemeProvider";
import { useAuth } from "@/providers/AuthProvider";
import { BottomSheet } from "@/components/BottomSheet";
import { Drawer } from "@/components/Drawer";

/** Home strip cards in the fixed order from the spec. */
const stripCards = [
  { key: "upgrade", label: "ترقية", icon: "✦", action: "upgrade" },
  { key: "computers", label: "أجهزة الحاسوب", icon: "▣", action: "none" },
  { key: "projects", label: "المشاريع", icon: "▤", action: "projects" },
  { key: "library", label: "المكتبة", icon: "❑", action: "none" },
  { key: "notifications", label: "الإشعارات", icon: "◉", action: "notifications" },
  { key: "explore", label: "الاستكشاف", icon: "⌖", action: "none" },
  { key: "skills", label: "المهارات", icon: "✧", action: "none" },
  { key: "tasks", label: "المهام", icon: "✓", action: "none" },
];

const upgradeFeatures = [
  "مهام غير محدودة في يوم واحد",
  "أولوية في الوصول إلى أقوى النماذج",
  "مساحة تخزين أكبر لملفاتك ومشاريعك",
  "دعم فني مباشر وأسرع",
];

type DrawerRow = { label: string; icon: string; page?: string };
type DrawerSection = { title: string; rows: DrawerRow[] };

const drawerSections: DrawerSection[] = [
  {
    title: "work",
    rows: [
      { label: "المهام المجدولة", icon: "⏱" },
      { label: "معرفة", icon: "✦" },
      { label: "Mail Suly", icon: "✉" },
      { label: "ضوابط البيانات", icon: "◈" },
      { label: "منتصف السحابة", icon: "☁" },
      { label: "المهارات", icon: "✧" },
      { label: "الموصلات", icon: "Ⓞ" },
      { label: "التكاملات", icon: "⇄" },
    ],
  },
  {
    title: "channels",
    rows: [
      { label: "البريد الإلكتروني", icon: "✉" },
      { label: "الهاتف", icon: "☎" },
      { label: "جهازي", icon: "▤" },
      { label: "المحفظة", icon: "❑" },
    ],
  },
  {
    title: "account",
    rows: [
      { label: "الحساب", icon: "◉", page: "/account" },
      { label: "اللغة · العربية", icon: "🌐", page: "/language" },
      { label: "المظهر", icon: "◐", page: "/appearance" },
      { label: "مسح ذاكرة التخزين المؤقت · MB 1007", icon: "⌫", page: "/cache" },
    ],
  },
  {
    title: "about",
    rows: [
      { label: "قيّم هذا التطبيق", icon: "★" },
      { label: "الحصول على مساعدة", icon: "?" },
      { label: "الإصدار v26.19.8", icon: "ⓘ" },
      { label: "تسجيل الخروج", icon: "→", page: "/logout" },
    ],
  },
];

export default function HomeScreen() {
  const { palette } = useTheme();
  const { user, profile } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [upgradeOpen, setUpgradeOpen] = useState(false);

  const displayName = profile?.display_name?.trim() || user?.email?.split("@")[0] || "Suly User";

  const openCard = (action: string) => {
    if (action === "upgrade") setUpgradeOpen(true);
    else if (action === "projects") router.push("/projects");
    else if (action === "notifications") router.push("/notifications");
  };

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: palette.background }]}>
      <View style={[styles.page, { backgroundColor: palette.background }]}>
        {/* Header: profile avatar left, centered wordmark, search right. */}
        <View style={[styles.header, { borderBottomColor: palette.border }]}>
          <Pressable onPress={() => setDrawerOpen(true)} accessibilityLabel="فتح القائمة الجانبية">
            <View style={[styles.avatar, { backgroundColor: palette.success }]}>
              <Text style={styles.avatarText}>S</Text>
            </View>
          </Pressable>
          <Text style={[styles.wordmark, { color: palette.text }]} numberOfLines={1}>Suly</Text>
          <Pressable accessibilityLabel="البحث" onPress={() => undefined}>
            <Text style={[styles.headerIcon, { color: palette.text }]}>⌕</Text>
          </Pressable>
        </View>

        {/* Horizontal scrolling strip of dark cards. */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.stripContent}
          style={styles.strip}
          nestedScrollEnabled
        >
          {stripCards.map((card) => (
            <Pressable
              key={card.key}
              style={({ pressed }) => [
                styles.stripCard,
                {
                  backgroundColor: pressed ? palette.surfaceSecondary : palette.surface,
                  borderColor: palette.border,
                },
              ]}
              onPress={() => openCard(card.action)}
            >
              <Text style={[styles.stripIcon, { color: palette.muted }]}>{card.icon}</Text>
              <Text style={[styles.stripLabel, { color: palette.text }]}>{card.label}</Text>
            </Pressable>
          ))}
        </ScrollView>

        {/* Empty state: dotted chat icon, caption, centered white task button. */}
        <View style={styles.emptyState}>
          <View style={[styles.emptyIcon, { borderColor: palette.faint }]}>
            <Text style={[styles.emptyIconText, { color: palette.faint }]}>◌</Text>
          </View>
          <Text style={[styles.emptyTitle, { color: palette.muted }]}>لا توجد مهام</Text>
          <Pressable
            style={({ pressed }) => [styles.newTaskButton, { opacity: pressed ? 0.85 : 1 }]}
            onPress={() => router.push("/conversation/new")}
          >
            <Text style={styles.newTaskText}>+ مهمة جديدة</Text>
          </Pressable>
        </View>
      </View>

      {/* Upgrade bottom sheet. */}
      <BottomSheet visible={upgradeOpen} onClose={() => setUpgradeOpen(false)} heightRatio={0.78}>
        <View style={[styles.sheetHeader, { borderBottomColor: palette.border }]}>
          <Text style={[styles.sheetTitle, { color: palette.text }]}>قم بالترقية إلى Suly Pro</Text>
          <Pressable onPress={() => setUpgradeOpen(false)} accessibilityLabel="إغلاق">
            <Text style={[styles.sheetClose, { color: palette.muted }]}>✕</Text>
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={styles.upgradeBody} showsVerticalScrollIndicator={false}>
          {upgradeFeatures.map((feature) => (
            <View key={feature} style={styles.upgradeRow}>
              <Text style={[styles.checkIcon, { color: palette.success }]}>✓</Text>
              <Text style={[styles.upgradeText, { color: palette.muted }]}>{feature}</Text>
            </View>
          ))}
          <View
            style={[
              styles.priceCard,
              { backgroundColor: palette.surfaceSecondary, borderColor: palette.border },
            ]}
          >
            <Text style={[styles.priceLabel, { color: palette.text }]}>سنوياً 12,999 ج.م / سنة</Text>
          </View>
          <Pressable
            style={({ pressed }) => [styles.upgradeButton, { opacity: pressed ? 0.85 : 1 }]}
            onPress={() => undefined}
          >
            <Text style={styles.upgradeButtonText}>قم بالترقية الآن</Text>
          </Pressable>
        </ScrollView>
      </BottomSheet>

      {/* Right drawer: profile summary and four sections of list cards. */}
      <Drawer visible={drawerOpen} onClose={() => setDrawerOpen(false)}>
        <ScrollView contentContainerStyle={styles.drawerContent} showsVerticalScrollIndicator={false}>
          <View style={[styles.drawerProfileCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={[styles.drawerAvatar, { backgroundColor: palette.success }]}>
              <Text style={styles.drawerAvatarText}>S</Text>
            </View>
            <View style={styles.drawerProfileMeta}>
              <Text style={[styles.drawerName, { color: palette.text }]} numberOfLines={1}>{displayName}</Text>
              <Text style={[styles.drawerPlan, { color: palette.muted }]}>Free · رصيد 300</Text>
            </View>
          </View>

          {drawerSections.map((section) => (
            <View
              key={section.title}
              style={[styles.drawerSection, { backgroundColor: palette.surface, borderColor: palette.border }]}
            >
              {section.rows.map((row) => (
                <Pressable
                  key={row.label}
                  style={({ pressed }) => [
                    styles.drawerRow,
                    { backgroundColor: pressed ? palette.surfaceSecondary : "transparent" },
                  ]}
                  onPress={() => {
                    setDrawerOpen(false);
                    if (row.page) router.push(row.page as never);
                  }}
                >
                  <Text style={[styles.drawerRowIcon, { color: palette.muted }]}>{row.icon}</Text>
                  <Text style={[styles.drawerRowLabel, { color: palette.text }]} numberOfLines={1}>{row.label}</Text>
                  <Text style={[styles.drawerRowChevron, { color: palette.faint }]}>‹</Text>
                </Pressable>
              ))}
            </View>
          ))}
        </ScrollView>
      </Drawer>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  page: { flex: 1, direction: "rtl" },
  header: {
    minHeight: 64,
    paddingHorizontal: 20,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottomWidth: 1,
  },
  avatar: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  avatarText: { color: "#FFFFFF", fontWeight: "800", fontSize: 14 },
  wordmark: { fontSize: 24, fontWeight: "300", letterSpacing: 1 },
  headerIcon: { fontSize: 22 },
  strip: { flexGrow: 0 },
  stripContent: { paddingHorizontal: 16, paddingVertical: 14, gap: 10, direction: "ltr" },
  stripCard: {
    minWidth: 96,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 16,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
  },
  stripIcon: { fontSize: 16 },
  stripLabel: { fontSize: 12 },
  emptyState: { flex: 1, alignItems: "center", justifyContent: "center", gap: 14, paddingBottom: 40 },
  emptyIcon: {
    width: 54,
    height: 54,
    borderRadius: 27,
    borderWidth: 2,
    borderStyle: "dashed",
    alignItems: "center",
    justifyContent: "center",
  },
  emptyIconText: { fontSize: 22 },
  emptyTitle: { fontSize: 14 },
  newTaskButton: { backgroundColor: "#FFFFFF", borderRadius: 12, paddingVertical: 12, paddingHorizontal: 28, borderWidth: 1, borderColor: "#E3E3E3" },
  newTaskText: { color: "#000000", fontWeight: "700", fontSize: 14 },
  sheetHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
  },
  sheetTitle: { fontSize: 17, fontWeight: "700" },
  sheetClose: { fontSize: 17 },
  upgradeBody: { padding: 20, gap: 12 },
  upgradeRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  checkIcon: { fontSize: 15, fontWeight: "800" },
  upgradeText: { fontSize: 13, flex: 1 },
  priceCard: { marginTop: 6, borderRadius: 14, borderWidth: 1, paddingVertical: 16, alignItems: "center" },
  priceLabel: { fontSize: 15, fontWeight: "700" },
  upgradeButton: { backgroundColor: "#FFFFFF", borderRadius: 12, paddingVertical: 14, alignItems: "center", marginTop: 4 },
  upgradeButtonText: { color: "#000000", fontWeight: "700", fontSize: 15 },
  drawerContent: { padding: 16, gap: 12 },
  drawerProfileCard: {
    borderRadius: 16,
    borderWidth: 1,
    padding: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  drawerAvatar: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  drawerAvatarText: { color: "#FFFFFF", fontWeight: "800", fontSize: 18 },
  drawerProfileMeta: { flex: 1 },
  drawerName: { fontSize: 15, fontWeight: "700" },
  drawerPlan: { fontSize: 11, marginTop: 3 },
  drawerSection: { borderRadius: 16, borderWidth: 1, overflow: "hidden" },
  drawerRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 14, paddingHorizontal: 14 },
  drawerRowIcon: { fontSize: 16, width: 22, textAlign: "center" },
  drawerRowLabel: { flex: 1, fontSize: 13 },
  drawerRowChevron: { fontSize: 20 },
});
