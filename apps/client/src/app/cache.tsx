import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { useTheme } from "@/providers/ThemeProvider";
import { Dialog } from "@/components/Dialog";

export default function CacheScreen() {
  const { palette } = useTheme();
  const [confirmOpen, setConfirmOpen] = useState(false);

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: palette.background }]}>
      <View style={[styles.page, { backgroundColor: palette.background }]}>
        <View style={[styles.header, { borderBottomColor: palette.border }]}>
          <Pressable onPress={() => router.back()} accessibilityLabel="رجوع">
            <Text style={[styles.headerAction, { color: palette.text }]}>‹</Text>
          </Pressable>
          <Text style={[styles.headerTitle, { color: palette.text }]}>مسح ذاكرة التخزين المؤقت</Text>
          <View style={styles.headerSpacer} />
        </View>
        <View style={styles.body}>
          <Text style={[styles.size, { color: palette.muted }]}>MB 1007</Text>
          <Pressable
            style={[styles.clearButton, { backgroundColor: palette.danger }]}
            onPress={() => setConfirmOpen(true)}
          >
            <Text style={styles.clearText}>مسح</Text>
          </Pressable>
        </View>
      </View>
      <Dialog
        visible={confirmOpen}
        title="مسح ذاكرة التخزين المؤقت؟"
        confirmLabel="مسح"
        destructive
        onConfirm={() => setConfirmOpen(false)}
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
  body: { flex: 1, alignItems: "center", justifyContent: "center", gap: 20 },
  size: { fontSize: 15 },
  clearButton: { borderRadius: 12, paddingVertical: 12, paddingHorizontal: 32 },
  clearText: { color: "#FFFFFF", fontSize: 14, fontWeight: "700" },
});
