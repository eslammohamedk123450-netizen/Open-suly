import { Pressable, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { colors } from "@/theme/tokens";

export type AppTab = "home" | "projects" | "activity" | "settings";

const items: { key: AppTab; title: string; icon: string; route: "/" | "/projects" | "/activity" | "/settings" }[] = [
  { key: "home", title: "الرئيسية", icon: "⌂", route: "/" },
  { key: "projects", title: "المشاريع", icon: "▦", route: "/projects" },
  { key: "activity", title: "النشاط", icon: "◷", route: "/activity" },
  { key: "settings", title: "الإعدادات", icon: "⚙", route: "/settings" },
];

export function BottomNavigation({ active }: { active: AppTab }) {
  return (
    <View style={styles.bottomNav}>
      {items.map((item) => {
        const selected = item.key === active;
        return (
          <Pressable
            key={item.key}
            style={styles.navItem}
            onPress={() => router.replace(item.route)}
            accessibilityRole="button"
            accessibilityState={{ selected }}
            accessibilityLabel={item.title}
          >
            <Text style={selected ? styles.navIconActive : styles.navIcon}>{item.icon}</Text>
            <Text style={selected ? styles.navLabelActive : styles.navLabel}>{item.title}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  bottomNav: { minHeight: 66, paddingHorizontal: 8, paddingTop: 8, paddingBottom: 5, borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.background, flexDirection: "row", justifyContent: "space-around", alignItems: "center" },
  navItem: { flex: 1, alignItems: "center", justifyContent: "center", gap: 3, paddingVertical: 4 },
  navIcon: { color: colors.faint, fontSize: 18 },
  navIconActive: { color: colors.gold, fontSize: 18 },
  navLabel: { color: colors.faint, fontSize: 10 },
  navLabelActive: { color: colors.gold, fontSize: 10, fontWeight: "700" },
});
