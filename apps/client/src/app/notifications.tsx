import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useTheme } from "@/providers/ThemeProvider";

const tabs = ["الكل", "التحديثات", "الإرسال"] as const;

type NotificationCard =
  | { kind: "announce"; title: string; body: string }
  | { kind: "thumbs"; title: string; items: string[] };

const notifications: NotificationCard[] = [
  {
    kind: "announce",
    title: "Introducing Suly Flex",
    body: "نموذج مرن جديد أسرع وأخف للمهام اليومية. جرّبه الآن من قائمة اختيار النموذج.",
  },
  {
    kind: "thumbs",
    title: "قدرات جديدة",
    items: ["Automation", "Video editor", "Game Dev", "Research", "Data", "Documents"],
  },
];

export default function NotificationsScreen() {
  const { palette } = useTheme();
  const [active, setActive] = useState<(typeof tabs)[number]>("الكل");

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: palette.background }]}>
      <View style={[styles.page, { backgroundColor: palette.background }]}>
        {/* Tabs: الكل / التحديثات / الإرسال */}
        <View style={[styles.tabs, { borderBottomColor: palette.border }]}>
          {tabs.map((tab) => {
            const selected = tab === active;
            return (
              <Pressable key={tab} style={styles.tab} onPress={() => setActive(tab)}>
                <Text style={[styles.tabText, { color: selected ? palette.text : palette.faint }]}>{tab}</Text>
                {selected && <View style={[styles.tabIndicator, { backgroundColor: palette.text }]} />}
              </Pressable>
            );
          })}
        </View>

        <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
          {notifications.map((card) =>
            card.kind === "announce" ? (
              <View
                key={card.title}
                style={[styles.announceCard, { backgroundColor: "#FFFFFF", borderColor: "#E3E3E3" }]}
              >
                <Text style={styles.announceTitle}>Introducing Suly Flex</Text>
                <Text style={styles.announceBody}>{card.body}</Text>
              </View>
            ) : (
              <View
                key={card.title}
                style={[styles.thumbsCard, { backgroundColor: palette.surface, borderColor: palette.border }]}
              >
                <Text style={[styles.thumbsTitle, { color: palette.text }]}>{card.title}</Text>
                <View style={styles.thumbsRow}>
                  {card.items.map((item) => (
                    <View key={item} style={[styles.thumb, { backgroundColor: palette.surfaceSecondary }]}>
                      <Text style={[styles.thumbText, { color: palette.muted }]} numberOfLines={1}>{item}</Text>
                    </View>
                  ))}
                </View>
              </View>
            ),
          )}
        </ScrollView>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  page: { flex: 1, direction: "rtl" },
  tabs: { flexDirection: "row", paddingHorizontal: 16, borderBottomWidth: 1 },
  tab: { paddingVertical: 14, paddingHorizontal: 14, position: "relative" },
  tabText: { fontSize: 14, fontWeight: "700" },
  tabIndicator: { position: "absolute", bottom: -1, left: 14, right: 14, height: 2, borderRadius: 1 },
  list: { padding: 16, gap: 14 },
  announceCard: { borderRadius: 16, borderWidth: 1, padding: 18 },
  announceTitle: { color: "#000000", fontSize: 17, fontWeight: "800" },
  announceBody: { color: "#444444", fontSize: 13, lineHeight: 22, marginTop: 8 },
  thumbsCard: { borderRadius: 16, borderWidth: 1, padding: 16 },
  thumbsTitle: { fontSize: 15, fontWeight: "700" },
  thumbsRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 12 },
  thumb: { borderRadius: 10, paddingVertical: 8, paddingHorizontal: 12 },
  thumbText: { fontSize: 11 },
});
