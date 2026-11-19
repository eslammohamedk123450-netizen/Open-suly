import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { colors } from "@/theme/tokens";

function SettingRow({ title, subtitle, value, onPress }: { title: string; subtitle: string; value?: string; onPress?: () => void }) {
  return (
    <Pressable style={styles.row} onPress={onPress}>
      <View style={styles.rowCopy}>
        <Text style={styles.rowTitle}>{title}</Text>
        <Text style={styles.rowSubtitle}>{subtitle}</Text>
      </View>
      <View style={styles.rowEnd}>
        {!!value && <Text style={styles.rowValue}>{value}</Text>}
        <Text style={styles.chevron}>‹</Text>
      </View>
    </Pressable>
  );
}

export default function SettingsScreen() {
  const [language, setLanguage] = useState<"العربية" | "English">("العربية");
  const [notifications, setNotifications] = useState(true);
  const [privacy, setPrivacy] = useState(true);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
          <View style={styles.headerTitleWrap}>
            <Text style={styles.headerTitle}>الإعدادات</Text>
            <Text style={styles.headerSubtitle}>تحكم في تجربة SULY</Text>
          </View>
          <Pressable style={styles.backButton} onPress={() => router.replace("/")}>
            <Text style={styles.backText}>→</Text>
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.profileCard}>
            <View style={styles.profileMark}><Text style={styles.profileMarkText}>S</Text></View>
            <View style={styles.profileCopy}>
              <Text style={styles.profileTitle}>حساب SULY</Text>
              <Text style={styles.profileSubtitle}>إعدادات الحساب ستظهر بعد تفعيل نظام الدخول</Text>
            </View>
            <View style={styles.previewBadge}><Text style={styles.previewBadgeText}>قريبًا</Text></View>
          </View>

          <Text style={styles.sectionTitle}>التفضيلات</Text>
          <View style={styles.group}>
            <SettingRow title="اللغة" subtitle="لغة واجهة التطبيق" value={language} onPress={() => setLanguage((v) => v === "العربية" ? "English" : "العربية")} />
            <View style={styles.separator} />
            <SettingRow title="المظهر" subtitle="هوية Midnight Gold" value="داكن" onPress={() => {}} />
            <View style={styles.separator} />
            <SettingRow title="الإشعارات" subtitle="تنبيهات المهام والتحديثات" value={notifications ? "مفعّلة" : "متوقفة"} onPress={() => setNotifications((v) => !v)} />
          </View>

          <Text style={styles.sectionTitle}>الخصوصية والأمان</Text>
          <View style={styles.group}>
            <SettingRow title="حماية البيانات" subtitle="إعدادات الخصوصية والتحكم في البيانات" value={privacy ? "مفعّلة" : "متوقفة"} onPress={() => setPrivacy((v) => !v)} />
            <View style={styles.separator} />
            <SettingRow title="الجلسات والأجهزة" subtitle="إدارة الأجهزة المتصلة" value="قريبًا" />
          </View>

          <Text style={styles.sectionTitle}>عن SULY</Text>
          <View style={styles.group}>
            <SettingRow title="عن المنصة" subtitle="More Than AI. Your Intelligent Partner." value="SULY" />
            <View style={styles.separator} />
            <SettingRow title="الإصدار" subtitle="نسخة تأسيسية جديدة" value="0.1.0" />
          </View>
          <Text style={styles.footer}>SULY TECHNOLOGIES · 2026</Text>
        </ScrollView>

        <View style={styles.bottomNav}>
          <Pressable style={styles.navItem} onPress={() => router.replace("/")}><Text style={styles.navIcon}>⌂</Text><Text style={styles.navLabel}>الرئيسية</Text></Pressable>
          <View style={styles.navItemActive}><Text style={styles.navIconActive}>⚙</Text><Text style={styles.navLabelActive}>الإعدادات</Text></View>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  page: { flex: 1, direction: "rtl", width: "100%", maxWidth: 1100, alignSelf: "center", backgroundColor: colors.background },
  header: { minHeight: 72, paddingHorizontal: 20, flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderBottomWidth: 1, borderBottomColor: colors.border },
  backButton: { width: 40, height: 40, borderRadius: 13, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  backText: { color: colors.gold, fontSize: 22 },
  headerTitleWrap: { flex: 1, alignItems: "flex-end", marginRight: 14 },
  headerTitle: { color: colors.text, fontSize: 18, fontWeight: "800" },
  headerSubtitle: { color: colors.muted, fontSize: 11, marginTop: 3 },
  logo: { width: 40, height: 40, borderRadius: 13, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  logoText: { color: colors.gold, fontSize: 23, fontWeight: "800" },
  content: { paddingHorizontal: 20, paddingTop: 22, paddingBottom: 28, width: "100%", maxWidth: 760, alignSelf: "center" },
  profileCard: { minHeight: 86, borderRadius: 18, padding: 15, borderWidth: 1, borderColor: colors.goldDark, backgroundColor: colors.surface, flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 26 },
  profileMark: { width: 46, height: 46, borderRadius: 15, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  profileMarkText: { color: colors.gold, fontSize: 23, fontWeight: "800" },
  profileCopy: { flex: 1 },
  profileTitle: { color: colors.text, fontSize: 14, fontWeight: "700", textAlign: "right" },
  profileSubtitle: { color: colors.muted, fontSize: 10, marginTop: 5, textAlign: "right" },
  previewBadge: { borderRadius: 20, backgroundColor: colors.surfaceSecondary, paddingHorizontal: 10, paddingVertical: 6 },
  previewBadgeText: { color: colors.gold, fontSize: 10 },
  sectionTitle: { color: colors.gold, fontSize: 13, fontWeight: "700", textAlign: "right", marginBottom: 10, marginTop: 8 },
  group: { borderRadius: 16, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, marginBottom: 22 },
  row: { minHeight: 68, flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 11 },
  rowCopy: { flex: 1 },
  rowTitle: { color: colors.text, fontSize: 13, fontWeight: "600", textAlign: "right" },
  rowSubtitle: { color: colors.muted, fontSize: 10, lineHeight: 17, textAlign: "right", marginTop: 4 },
  rowEnd: { flexDirection: "row", alignItems: "center", gap: 9 },
  rowValue: { color: colors.faint, fontSize: 10 },
  chevron: { color: colors.gold, fontSize: 21 },
  separator: { height: 1, backgroundColor: colors.border },
  footer: { color: colors.faint, fontSize: 9, textAlign: "center", letterSpacing: 2, marginTop: 5 },
  bottomNav: { minHeight: 64, borderTopWidth: 1, borderTopColor: colors.border, flexDirection: "row", alignItems: "center", justifyContent: "space-around" },
  navItem: { flex: 1, alignItems: "center", gap: 3 },
  navItemActive: { flex: 1, alignItems: "center", gap: 3 },
  navIcon: { color: colors.faint, fontSize: 18 },
  navIconActive: { color: colors.gold, fontSize: 18 },
  navLabel: { color: colors.faint, fontSize: 10 },
  navLabelActive: { color: colors.gold, fontSize: 10, fontWeight: "700" },
});
