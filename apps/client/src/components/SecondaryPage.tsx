import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { colors } from "@/theme/tokens";
import { BottomNavigation, type AppTab } from "@/components/BottomNavigation";

export function SecondaryPage({ title, description, active }: { title: string; description: string; active: AppTab }) {
  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <View style={styles.brand}>
            <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
            <View>
              <Text style={styles.brandName}>SULY</Text>
              <Text style={styles.brandCaption}>INTELLIGENT PARTNER</Text>
            </View>
          </View>
          <Pressable style={styles.settingsButton} onPress={() => router.push("/settings")}>
            <Text style={styles.settingsIcon}>⚙</Text>
          </Pressable>
        </View>
        <View style={styles.body}>
          <View style={styles.placeholderMark}><Text style={styles.placeholderIcon}>{active === "projects" ? "▦" : "◷"}</Text></View>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.description}>{description}</Text>
          <Text style={styles.status}>سيتم بناء هذا القسم ضمن مراحل SULY الجديدة</Text>
        </View>
        <BottomNavigation active={active} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  page: { flex: 1, direction: "rtl", width: "100%", maxWidth: 1100, alignSelf: "center", backgroundColor: colors.background },
  header: { minHeight: 72, paddingHorizontal: 22, flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderBottomWidth: 1, borderBottomColor: colors.border },
  brand: { flexDirection: "row", alignItems: "center", gap: 11 },
  logo: { width: 42, height: 42, borderRadius: 14, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  logoText: { color: colors.gold, fontSize: 25, fontWeight: "800" },
  brandName: { color: colors.text, fontSize: 17, fontWeight: "800", letterSpacing: 3 },
  brandCaption: { color: colors.faint, fontSize: 8, letterSpacing: 1.6, marginTop: 2 },
  settingsButton: { width: 40, height: 40, borderRadius: 13, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  settingsIcon: { color: colors.gold, fontSize: 18 },
  body: { flex: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: 28, paddingBottom: 60 },
  placeholderMark: { width: 70, height: 70, borderRadius: 22, borderWidth: 1, borderColor: colors.goldDark, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", marginBottom: 20 },
  placeholderIcon: { color: colors.gold, fontSize: 30 },
  title: { color: colors.text, fontSize: 24, fontWeight: "800", textAlign: "center" },
  description: { color: colors.muted, fontSize: 13, lineHeight: 24, textAlign: "center", maxWidth: 340, marginTop: 10 },
  status: { color: colors.gold, fontSize: 11, textAlign: "center", marginTop: 22 },
});
