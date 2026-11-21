import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { useTheme } from "@/providers/ThemeProvider";
import { useAuth } from "@/providers/AuthProvider";
import { Dialog } from "@/components/Dialog";

export default function LogoutScreen() {
  const { palette } = useTheme();
  const { signOut } = useAuth();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const confirmLogout = async () => {
    setConfirmOpen(false);
    await signOut();
    router.replace("/");
  };

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: palette.background }]}>
      <View style={[styles.page, { backgroundColor: palette.background }]}>
        <View style={[styles.header, { borderBottomColor: palette.border }]}>
          <Pressable onPress={() => router.back()} accessibilityLabel="رجوع">
            <Text style={[styles.headerAction, { color: palette.text }]}>‹</Text>
          </Pressable>
          <Text style={[styles.headerTitle, { color: palette.text }]}>تسجيل الخروج</Text>
          <View style={styles.headerSpacer} />
        </View>
        <View style={styles.body}>
          <Text style={[styles.message, { color: palette.muted }]}>هل أنت متأكد من تسجيل الخروج؟</Text>
          <Pressable
            style={[styles.logoutButton, { backgroundColor: palette.danger }]}
            onPress={() => setConfirmOpen(true)}
          >
            <Text style={styles.logoutText}>تسجيل الخروج</Text>
          </Pressable>
        </View>
      </View>
      <Dialog
        visible={confirmOpen}
        title="هل أنت متأكد من تسجيل الخروج؟"
        confirmLabel="تسجيل الخروج"
        destructive
        onConfirm={confirmLogout}
        onCancel={() => setConfirmOpen(false)}
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
  body: { flex:  1, alignItems: "center", justifyContent: "center", gap: 20 },
  message: { fontSize: 14 },
  logoutButton: { borderRadius: 12, paddingVertical: 12, paddingHorizontal: 32 },
  logoutText: { color: "#FFFFFF", fontSize: 14, fontWeight: "700" },
});
