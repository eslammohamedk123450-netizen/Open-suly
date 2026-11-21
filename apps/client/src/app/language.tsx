import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { useTheme } from "@/providers/ThemeProvider";

const languages = [
  "العربية",
  "English",
  "فارسی",
  "Türkçe",
  "Français",
  "Español",
  "Deutsch",
  "Português",
  "Italiano",
  "Русский",
  "中文",
  "日本語",
  "हिन्दी",
  "বাঙালি",
  "اردو",
  "עברית",
];

export default function LanguageScreen() {
  const { palette } = useTheme();
  const [selected, setSelected] = useState("العربية");

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: palette.background }]}>
      <View style={[styles.page, { backgroundColor: palette.background }]}>
        <View style={[styles.header, { borderBottomColor: palette.border }]}>
          <Pressable onPress={() => router.back()} accessibilityLabel="رجوع">
            <Text style={[styles.headerAction, { color: palette.text }]}>‹</Text>
          </Pressable>
          <Text style={[styles.headerTitle, { color: palette.text }]}>اللغة</Text>
          <View style={styles.headerSpacer} />
        </View>
        <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
          {languages.map((language) => {
            const isSelected = language === selected;
            return (
              <Pressable
                key={language}
                style={[styles.row, { borderBottomColor: palette.border }]}
                onPress={() => setSelected(language)}
              >
                <Text style={[styles.rowLabel, { color: palette.text }]}>{language}</Text>
                {isSelected && <Text style={[styles.rowCheck, { color: palette.accent }]}>✓</Text>}
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
  list: { paddingHorizontal: 18, paddingBottom: 30 },
  row: { paddingVertical: 16, flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderBottomWidth: 1 },
  rowLabel: { fontSize: 14 },
  rowCheck: { fontSize: 16, fontWeight: "800" },
});
