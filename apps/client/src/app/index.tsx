import { StyleSheet, Text, View } from "react-native";
import { colors } from "@/theme/tokens";

export default function HomeScreen() {
  return (
    <View style={styles.page}>
      <View style={styles.content}>
        <View style={styles.mark}>
          <Text style={styles.markText}>S</Text>
        </View>

        <Text style={styles.wordmark}>SULY</Text>
        <Text style={styles.tagline}>More Than AI. Your Intelligent Partner.</Text>

        <View style={styles.divider} />

        <Text style={styles.heading}>أهلاً بك في سولي</Text>
        <Text style={styles.description}>
          شريكك الذكي للبحث والتخطيط والإبداع وتنفيذ المهام.
        </Text>

        <View style={styles.status}>
          <View style={styles.statusDot} />
          <Text style={styles.statusText}>المنصة قيد التأسيس</Text>
        </View>
      </View>

      <Text style={styles.footer}>SULY TECHNOLOGIES</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  page: {
    flex: 1,
    minHeight: "100%",
    backgroundColor: colors.background,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 24,
    paddingVertical: 48,
    direction: "rtl",
  },
  content: {
    width: "100%",
    maxWidth: 520,
    alignItems: "center",
  },
  mark: {
    width: 76,
    height: 76,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: colors.gold,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
    marginBottom: 18,
  },
  markText: {
    color: colors.gold,
    fontSize: 42,
    fontWeight: "700",
  },
  wordmark: {
    color: colors.text,
    fontSize: 30,
    fontWeight: "700",
    letterSpacing: 7,
  },
  tagline: {
    color: colors.muted,
    fontSize: 13,
    marginTop: 8,
    textAlign: "center",
    writingDirection: "ltr",
  },
  divider: {
    width: 64,
    height: 1,
    backgroundColor: colors.goldDark,
    marginVertical: 34,
  },
  heading: {
    color: colors.text,
    fontSize: 25,
    fontWeight: "700",
    textAlign: "center",
    marginBottom: 12,
  },
  description: {
    color: colors.muted,
    fontSize: 15,
    lineHeight: 27,
    textAlign: "center",
    maxWidth: 360,
  },
  status: {
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    marginTop: 30,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 30,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  statusDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: colors.gold,
  },
  statusText: {
    color: colors.gold,
    fontSize: 12,
  },
  footer: {
    position: "absolute",
    bottom: 24,
    color: colors.faint,
    fontSize: 10,
    letterSpacing: 3,
  },
});
