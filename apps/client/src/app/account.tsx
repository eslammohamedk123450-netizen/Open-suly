import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { useTheme } from "@/providers/ThemeProvider";
import { useAuth } from "@/providers/AuthProvider";
import { Dialog } from "@/components/Dialog";

export default function AccountScreen() {
  const { palette } = useTheme();
  const { user, profile, signOut } = useAuth();
  const [logoutOpen, setLogoutOpen] = useState(false);

  const displayName = profile?.display_name?.trim() || user?.email?.split("@")[0] || "Suly User";

  const confirmLogout = async () => {
    setLogoutOpen(false);
    await signOut();
    router.replace("/");
  };

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: palette.background }]}>
      <View style={[styles.page, { backgroundColor: palette.background }]}>
        {/* Back header. */}
        <View style={[styles.header, { borderBottomColor: palette.border }]}>
          <Pressable onPress={() => router.back()} accessibilityLabel="رجوع">
            <Text style={[styles.headerAction, { color: palette.text }]}>‹</Text>
          </Pressable>
          <Text style={[styles.headerTitle, { color: palette.text }]}>الحساب</Text>
          <View style={styles.headerSpacer} />
        </View>

        <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
          <View style={[styles.avatarCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={[styles.avatar, { backgroundColor: palette.success }]}>
              <Text style={styles.avatarText}>S</Text>
            </View>
            <Text style={[styles.name, { color: palette.text }]}>{displayName}</Text>
            {!!user?.email && <Text style={[styles.meta, { color: palette.muted }]}>{user.email}</Text>}
          </View>

          <Pressable style={[styles.logoutButton, { borderColor: palette.border }]} onPress={() => setLogoutOpen(true)}>
            <Text style={[styles.logoutText, { color: palette.text }]}>تسجيل الخروج</Text>
          </Pressable>

          <Pressable
            style={[styles.deleteButton, { backgroundColor: palette.danger }]}
            onPress={() => undefined}
            accessibilityLabel="حذف الحساب"
          >
            <Text style={styles.deleteText}>حذف الحساب</Text>
          </Pressable>
        </ScrollView>
      </View>

      <Dialog
        visible={logoutOpen}
        title="هل أنت متأكد من تسجيل الخروج؟"
        confirmLabel="تسجيل الخروج"
        destructive={false}
        onConfirm={confirmLogout}
        onCancel={() => setLogoutOpen(false)}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  page: { flex: 1, direction: "rtl" },
  header: { minHeight: 60, paddingHorizontal: 18, flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderBottomWidth: 1 },
  headerAction: { fontSize: 26, fontWeight: "600" },
  headerTitle: { fontSize: 16, fontWeight: "700" },
  headerSpacer: { width: 26 },
  body: { padding: 20, gap: 16, alignItems: "center", paddingTop: 30 },
  avatarCard: { borderRadius: 18, borderWidth: 1, padding: 24, width: "100%", alignItems: "center", gap: 10 },
  avatar: { width: 72, height: 72, borderRadius: 36, alignItems: "center", justifyContent: "center" },
  avatarText: { color: "#FFFFFF", fontWeight: "800", fontSize: 30 },
  name: { fontSize: 18, fontWeight: "700" },
  meta: { fontSize: 13 },
  logoutButton: { borderRadius: 12, borderWidth: 1, paddingVertical: 14, width: "100%", alignItems: "center" },
  logoutText: { fontSize: 14, fontWeight: "700" },
  deleteButton: { borderRadius: 12, paddingVertical: 14, width: "100%", alignItems: "center" },
  deleteText: { color: "#FFFFFF", fontSize: 14, fontWeight: "700" },
});
