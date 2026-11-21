import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { useTheme, type ThemeMode } from "@/providers/ThemeProvider";

const options: { mode: ThemeMode; label: string }[] = [
  { mode: "system", label: "اتبع النظام" },
  { mode: "light", label: "الوضع الفاتح" },
  { mode: "dark", label: "الوضع الداكن" },
];

export default function AppearanceScreen() {
  const { palette, mode, setMode } = useTheme();

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: palette.background }]}>
      <View style={[styles.page, { backgroundColor: palette.background }]}>
        <View style={[styles.header, { borderBottomColor: palette.border }]}>
          <Pressable onPress={() => router.back()} accessibilityLabel="رجوع">
            <Text style={[styles.headerAction, { color: palette.text }]}>‹</Text>
          </Pressable>
          <Text style={[styles.headerTitle, { color: palette.text }]}>المظهر</Text>
          <View style={styles.headerSpacer} />
        </View>
        <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
          {options.map((option) => {
            const isSelected = option.mode === mode;
            return (
              <Pressable
                key={option.mode}
                style={[styles.option, { backgroundColor: palette.surface, borderColor: palette.border }]}
                onPress={() => setMode(option.mode)}
              >
                <Text style={[styles.optionLabel, { color: palette.text }]}>{option.label}</Text>
                {isSelected && <Text style={[styles.optionCheck, { color: palette.accent }]}>✓</Text>}
              </Pressable>
            );
          })}
        </ScrollView>
      </View>
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
  body: { padding: 20, gap: 12 },
  option: { borderRadius: 14, borderWidth: 1, paddingVertical: 16, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  optionLabel: { fontSize: 14 },
  optionCheck: { fontSize: 16, fontWeight: "800" },
});
