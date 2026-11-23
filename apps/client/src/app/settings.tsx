import { useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, Share, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { colors } from "@/theme/tokens";
import { BottomNavigation } from "@/components/BottomNavigation";
import { useAuth } from "@/providers/AuthProvider";
import { exportChatData } from "@/lib/conversations";

function SettingRow({ title, subtitle, value, onPress }: { title: string; subtitle: string; value?: string; onPress?: () => void }) {
  return (
    <Pressable style={styles.row} onPress={onPress} disabled={!onPress}>
      <View style={styles.rowCopy}>
        <Text style={styles.rowTitle}>{title}</Text>
        <Text style={styles.rowSubtitle}>{subtitle}</Text>
      </View>
      <View style={styles.rowEnd}>
        {!!value && <Text style={styles.rowValue}>{value}</Text>}
        {!!onPress && <Text style={styles.chevron}>‹</Text>}
      </View>
    </Pressable>
  );
}

export default function SettingsScreen() {
  const [language, setLanguage] = useState<"العربية" | "English">("العربية");
  const [notifications, setNotifications] = useState(true);
  const [privacy, setPrivacy] = useState(true);
  const [authError, setAuthError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [exportNotice, setExportNotice] = useState("");
  const [exportError, setExportError] = useState("");
  const { configured, loading, user, profile, signOut } = useAuth();


  // تصدير المحادثات من API موثوق دون الاعتماد على صلاحيات قاعدة البيانات في العميل.
  const handleExportChats = async () => {
    if (!user || exporting) return;
    setExportNotice("");
    setExportError("");
    setExporting(true);
    try {
      const payload = await exportChatData();
      const exportText = JSON.stringify(payload, null, 2);
      if (Platform.OS === "web") {
        const blob = new Blob([exportText], { type: "application/json;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `suly-chat-export-${new Date().toISOString().slice(0, 10)}.json`;
        anchor.style.display = "none";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
        setExportNotice(payload.truncated ? "تم تنزيل نسخة جزئية بسبب حدود حجم التصدير." : "تم تنزيل ملف محادثاتك JSON.");
      } else {
        // على الهاتف تظهر نافذة المشاركة لاختيار وجهة حفظ أو إرسال النص.
        await Share.share({ title: "SULY Chat Export", message: exportText });
        setExportNotice(payload.truncated ? "تم تجهيز تصدير جزئي؛ بعض السجلات تجاوزت الحدود المسموحة." : "تم تجهيز بيانات المحادثات للمشاركة أو الحفظ.");
      }
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "تعذر تصدير المحادثات.");
    } finally {
      setExporting(false);
    }
  };

  const handleSignOut = async () => {
    setAuthError("");
    const error = await signOut();
    if (error) setAuthError(error);
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
          <View style={styles.headerTitleWrap}>
            <Text style={styles.headerTitle}>الإعدادات</Text>
            <Text style={styles.headerSubtitle}>تحكم في تجربة SULY</Text>
          </View>
          <Pressable style={styles.backButton} onPress={() => router.replace("/")}><Text style={styles.backText}>→</Text></Pressable>
        </View>

        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.profileCard}>
            <View style={styles.profileMark}><Text style={styles.profileMarkText}>S</Text></View>
            <View style={styles.profileCopy}>
              <Text style={styles.profileTitle}>{profile?.display_name || user?.email || "حساب SULY"}</Text>
              <Text style={styles.profileSubtitle}>{loading ? "جارٍ التحقق من الجلسة..." : user ? user.email : configured ? "سجّل الدخول لمزامنة حسابك وبياناتك" : "الاتصال بـ Supabase يحتاج إعداد مفاتيح التطبيق"}</Text>
            </View>
            <View style={styles.previewBadge}><Text style={styles.previewBadgeText}>{user ? "متصل" : configured ? "زائر" : "غير مهيأ"}</Text></View>
          </View>
          {!user && configured && <Pressable style={styles.primaryButton} onPress={() => router.push("/auth")}><Text style={styles.primaryButtonText}>تسجيل الدخول أو إنشاء حساب</Text></Pressable>}
          {!!user && <Pressable style={styles.secondaryButton} onPress={handleSignOut}><Text style={styles.secondaryButtonText}>تسجيل الخروج</Text></Pressable>}
          {!!authError && <Text style={styles.errorText}>{authError}</Text>}

          <Text style={styles.sectionTitle}>التفضيلات</Text>
          <View style={styles.group}>
            <SettingRow title="اللغة" subtitle="لغة واجهة التطبيق" value={language} onPress={() => setLanguage((v) => v === "العربية" ? "English" : "العربية")} />
            <View style={styles.separator} />
            <SettingRow title="المظهر" subtitle="هوية Midnight Gold" value="داكن" />
            <View style={styles.separator} />
            <SettingRow title="الإشعارات" subtitle="تنبيهات المهام والتحديثات" value={notifications ? "مفعّلة" : "متوقفة"} onPress={() => setNotifications((v) => !v)} />
          </View>

          <Text style={styles.sectionTitle}>الذكاء الاصطناعي</Text>
          <View style={styles.group}>
            <SettingRow title="مزود الذكاء الاصطناعي" subtitle="إعداد مركزي للمفتاح والنموذج — لمالك التطبيق فقط" onPress={() => router.push("/ai-provider")} />
          </View>

          <Text style={styles.sectionTitle}>الخصوصية والأمان</Text>
          <View style={styles.group}>
            <SettingRow title="حماية البيانات" subtitle="إعدادات الخصوصية والتحكم في البيانات" value={privacy ? "مفعّلة" : "متوقفة"} onPress={() => setPrivacy((v) => !v)} />
            <View style={styles.separator} />
            <SettingRow title="الرصيد والاستخدام" subtitle="رصيد المحركات وحركات credits (قراءة فقط)" onPress={() => router.push("/credits")} />

            <View style={styles.separator} />
            {user ? (
              <Pressable
                style={[styles.exportButton, exporting && styles.exportButtonDisabled]}
                onPress={handleExportChats}
                disabled={exporting}
                accessibilityRole="button"
                accessibilityLabel="تصدير محادثاتك"
              >
                {exporting ? <ActivityIndicator color={colors.gold} /> : <Text style={styles.exportButtonIcon}>⇩</Text>}
                <Text style={styles.exportButtonText}>{exporting ? "جارٍ تجهيز التصدير..." : "تصدير محادثاتك"}</Text>
              </Pressable>
            ) : (
              <SettingRow title="تصدير محادثاتك" subtitle="سجّل الدخول أولًا للوصول إلى بيانات حسابك" onPress={() => router.push("/auth")} />
            )}
            {!!exportNotice && <Text style={styles.exportNotice}>{exportNotice}</Text>}
            {!!exportError && <Text style={styles.errorText}>{exportError}</Text>}
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
        <BottomNavigation active="settings" />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  page: { flex: 1, direction: "rtl", width: "100%", maxWidth: 1100, alignSelf: "center", backgroundColor: colors.background },
  header: { minHeight: 72, paddingHorizontal: 20, flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderBottomWidth: 1, borderBottomColor: colors.border },
  backButton: { width: 40, height: 40, borderRadius: 13, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  backText: { color: colors.gold, fontSize: 22 }, headerTitleWrap: { flex: 1, alignItems: "flex-end", marginRight: 14 },
  headerTitle: { color: colors.text, fontSize: 18, fontWeight: "800" }, headerSubtitle: { color: colors.muted, fontSize: 11, marginTop: 3 },
  logo: { width: 40, height: 40, borderRadius: 13, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  logoText: { color: colors.gold, fontSize: 23, fontWeight: "800" }, content: { paddingHorizontal: 20, paddingTop: 22, paddingBottom: 28, width: "100%", maxWidth: 760, alignSelf: "center" },
  profileCard: { minHeight: 86, borderRadius: 18, padding: 15, borderWidth: 1, borderColor: colors.goldDark, backgroundColor: colors.surface, flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 14 },
  profileMark: { width: 46, height: 46, borderRadius: 15, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" }, profileMarkText: { color: colors.gold, fontSize: 23, fontWeight: "800" },
  profileCopy: { flex: 1 }, profileTitle: { color: colors.text, fontSize: 14, fontWeight: "700", textAlign: "right" }, profileSubtitle: { color: colors.muted, fontSize: 10, marginTop: 5, textAlign: "right" },
  previewBadge: { borderRadius: 20, backgroundColor: colors.surfaceSecondary, paddingHorizontal: 10, paddingVertical: 6 }, previewBadgeText: { color: colors.gold, fontSize: 10 },
  primaryButton: { minHeight: 48, borderRadius: 14, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center", marginBottom: 22 }, primaryButtonText: { color: colors.background, fontSize: 13, fontWeight: "800" },
  secondaryButton: { minHeight: 44, borderRadius: 14, borderWidth: 1, borderColor: colors.goldDark, alignItems: "center", justifyContent: "center", marginBottom: 12 }, secondaryButtonText: { color: colors.gold, fontSize: 13, fontWeight: "700" }, errorText: { color: "#F08B8B", textAlign: "right", fontSize: 11, marginBottom: 12 },
  sectionTitle: { color: colors.gold, fontSize: 13, fontWeight: "700", textAlign: "right", marginBottom: 10, marginTop: 8 }, group: { borderRadius: 16, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, marginBottom: 22 },
  row: { minHeight: 68, flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 11 }, rowCopy: { flex: 1 }, rowTitle: { color: colors.text, fontSize: 13, fontWeight: "600", textAlign: "right" }, rowSubtitle: { color: colors.muted, fontSize: 10, lineHeight: 17, textAlign: "right", marginTop: 4 },
  rowEnd: { flexDirection: "row", alignItems: "center", gap: 9 }, rowValue: { color: colors.faint, fontSize: 10 }, chevron: { color: colors.gold, fontSize: 21 }, separator: { height: 1, backgroundColor: colors.border },
  footer: { color: colors.faint, fontSize: 9, textAlign: "center", letterSpacing: 2, marginTop: 5 },
  exportButton: { minHeight: 48, borderRadius: 14, borderWidth: 1, borderColor: colors.goldDark, backgroundColor: colors.surfaceSecondary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 9, paddingHorizontal: 14, marginVertical: 6 },
  exportButtonDisabled: { opacity: 0.65 }, exportButtonIcon: { color: colors.gold, fontSize: 17, fontWeight: "800" }, exportButtonText: { color: colors.gold, fontSize: 12, fontWeight: "700" }, exportNotice: { color: colors.muted, fontSize: 11, textAlign: "right", lineHeight: 18, marginBottom: 10 },

});
