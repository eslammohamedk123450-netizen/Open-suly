/** صفحة قراءة الرصيد والحجوزات؛ لا توفر شراءً أو تنفيذًا أو تعديلًا. */
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { colors } from "@/theme/tokens";
import { BottomNavigation } from "@/components/BottomNavigation";
import { useAuth } from "@/providers/AuthProvider";
import { getEngineCredits, type EngineCredits, type CreditTransaction } from "@/lib/engine-credits";

function formatDate(value: string | null): string {
  if (!value) return "التاريخ غير متاح";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "التاريخ غير متاح";
  return date.toLocaleString("ar-EG", { year: "numeric", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function formatCredits(value: number): string {
  return value.toLocaleString("ar-EG");
}

function signed(value: number): string {
  return value > 0 ? "+" + formatCredits(value) : formatCredits(value);
}

function transactionLabel(value: CreditTransaction["transaction_type"]): string {
  const labels: Record<CreditTransaction["transaction_type"], string> = {
    grant: "إضافة رصيد",
    reserve: "حجز رصيد",
    settle: "تسوية استهلاك",
    release: "تحرير رصيد",
    expire: "انتهاء حجز",
  };
  return labels[value] ?? value;
}

function reservationStatus(value: EngineCredits["reservations"][number]["status"]): string {
  const labels = { reserved: "محجوز", settled: "تمت التسوية", released: "تم التحرير" };
  return labels[value] ?? value;
}

function engineLabel(value: string | null): string {
  if (value === "opencode") return "OpenCode";
  if (value === "hermes-agent") return "Hermes";
  return value || "غير محدد";
}

export default function CreditsScreen() {
  const { user } = useAuth();
  const [summary, setSummary] = useState<EngineCredits | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (refresh = false) => {
    if (!user) {
      setSummary(null);
      setLoading(false);
      setRefreshing(false);
      return;
    }
    if (refresh) setRefreshing(true);
    else {
      setSummary(null);
      setLoading(true);
    }
    setError("");
    try {
      setSummary(await getEngineCredits());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذر تحميل الرصيد.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [user?.id]);

  useEffect(() => { void load(); }, [load]);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
          <View style={styles.headerCopy}>
            <Text style={styles.title} accessibilityRole="header">الرصيد والاستخدام</Text>
            <Text style={styles.subtitle}>متابعة رصيد المحركات والحركات الأخيرة</Text>
          </View>
          <Pressable style={styles.back} onPress={() => router.back()} accessibilityRole="button" accessibilityLabel="رجوع">
            <Text style={styles.backText}>→</Text>
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.notice}>
            <Text style={styles.noticeTitle}>عرض للقراءة فقط</Text>
            <Text style={styles.noticeText}>
              لا يمكنك شراء أو إضافة رصيد من هذه الصفحة. تشغيل المحركات والفوترة لم يتم تفعيلهما؛ وقد يتطلب العرض إعداد دفتر الرصيد على الخادم.
            </Text>
          </View>

          {!user ? (
            <View style={styles.empty}>
              <Text style={styles.emptyTitle}>سجّل الدخول أولًا</Text>
              <Text style={styles.emptyText}>الرصيد وسجل الاستخدام مرتبطان بحسابك فقط.</Text>
              <Pressable style={styles.primary} onPress={() => router.push("/auth")} accessibilityRole="button">
                <Text style={styles.primaryText}>تسجيل الدخول</Text>
              </Pressable>
            </View>
          ) : (
            <>
              <Pressable style={styles.refresh} onPress={() => void load(true)} disabled={refreshing || loading} accessibilityRole="button" accessibilityLabel="تحديث الرصيد">
                {refreshing ? <ActivityIndicator color={colors.gold} /> : <Text style={styles.refreshText}>تحديث البيانات</Text>}
              </Pressable>

              {loading && <ActivityIndicator color={colors.gold} style={{ marginVertical: 24 }} />}
              {!!error && <View style={styles.errorCard}><Text style={styles.error}>{error}</Text>{!!summary && <Text style={styles.errorHint}>تعذر التحديث؛ البيانات الظاهرة هي آخر تحميل ناجح.</Text>}</View>}

              {!!summary && (
                <>
                  <View style={styles.balanceGrid}>
                    <View accessible accessibilityLabel={`الرصيد المتاح ${formatCredits(summary.account.available_credits)} credits`} style={styles.balanceCard}>
                      <Text style={styles.balanceCaption}>الرصيد المتاح</Text>
                      <Text style={styles.balanceValue}>{formatCredits(summary.account.available_credits)}</Text>
                      <Text style={styles.balanceUnit}>Credit</Text>
                    </View>
                    <View accessible accessibilityLabel={`الرصيد المحجوز ${formatCredits(summary.account.reserved_credits)} credits`} style={styles.balanceCardSecondary}>
                      <Text style={styles.balanceCaption}>الرصيد المحجوز</Text>
                      <Text style={styles.balanceValueSecondary}>{formatCredits(summary.account.reserved_credits)}</Text>
                      <Text style={styles.balanceUnit}>Credit</Text>
                    </View>
                  </View>

                  <View style={styles.sectionHeader}>
                    <Text style={styles.sectionTitle} accessibilityRole="header">حجوزات المحركات</Text>
                    <Text style={styles.count}>{summary.reservations.length}</Text>
                  </View>
                  {summary.reservations.length === 0 ? (
                    <View style={styles.emptyInline}><Text style={styles.emptyText}>لا توجد حجوزات محفوظة.</Text></View>
                  ) : summary.reservations.map((item, index) => (
                    <View key={item.id ?? "reservation-" + index} style={styles.reservationCard}>
                      <View style={styles.cardTop}>
                        <Text style={styles.cardTitle}>{engineLabel(item.engine_id)}</Text>
                        <Text style={item.status === "reserved" ? styles.pendingStatus : styles.doneStatus}>{reservationStatus(item.status)}</Text>
                      </View>
                      <Text style={styles.amount}>{formatCredits(item.reserved_credits)} <Text style={styles.amountUnit}>Credit</Text></Text>
                      {item.settled_credits !== null && <Text style={styles.meta}>استهلاك مسوّى: {formatCredits(item.settled_credits)}</Text>}
                      <Text style={styles.meta}>تاريخ الحجز: {formatDate(item.created_at)}</Text>
                      {item.status === "reserved" && <Text style={styles.meta}>انتهاء الحجز: {formatDate(item.expires_at)}</Text>}
                    </View>
                  ))}

                  <View style={styles.sectionHeader}>
                    <Text style={styles.sectionTitle} accessibilityRole="header">سجل الحركة</Text>
                    <Text style={styles.count}>{summary.transactions.length}</Text>
                  </View>
                  {summary.transactions.length === 0 ? (
                    <View style={styles.emptyInline}><Text style={styles.emptyText}>لا توجد حركات رصيد بعد.</Text></View>
                  ) : summary.transactions.map((item, index) => (
                    <View key={item.id ?? "transaction-" + index} style={styles.transactionCard}>
                      <View style={styles.cardTop}>
                        <Text style={styles.cardTitle}>{transactionLabel(item.transaction_type)}</Text>
                        <Text style={styles.transactionEngine}>{engineLabel(item.engine_id)}</Text>
                      </View>
                      <Text style={styles.transactionDelta}>المتاح {signed(item.available_delta)} · المحجوز {signed(item.reserved_delta)}</Text>
                      <Text style={styles.meta}>{formatDate(item.created_at)}</Text>
                    </View>
                  ))}
                  <Text style={styles.updatedAt}>آخر تحديث الحساب: {formatDate(summary.account.updated_at)}</Text>
                </>
              )}
            </>
          )}
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
  logo: { width: 42, height: 42, borderRadius: 14, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  logoText: { color: colors.gold, fontSize: 25, fontWeight: "800" },
  headerCopy: { flex: 1, marginRight: 12, alignItems: "flex-end" },
  title: { color: colors.text, fontSize: 17, fontWeight: "800" },
  subtitle: { color: colors.muted, fontSize: 10, marginTop: 4, textAlign: "right" },
  back: { width: 40, height: 40, borderRadius: 13, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  backText: { color: colors.gold, fontSize: 22 },
  content: { padding: 18, paddingBottom: 32, width: "100%", maxWidth: 760, alignSelf: "center", gap: 14 },
  notice: { borderWidth: 1, borderColor: colors.goldDark, backgroundColor: colors.surface, borderRadius: 16, padding: 15, gap: 7 },
  noticeTitle: { color: colors.gold, fontSize: 13, fontWeight: "800", textAlign: "right" },
  noticeText: { color: colors.muted, fontSize: 11, lineHeight: 19, textAlign: "right" },
  refresh: { alignSelf: "flex-start", minWidth: 105, minHeight: 38, borderWidth: 1, borderColor: colors.border, borderRadius: 12, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", paddingHorizontal: 12 },
  refreshText: { color: colors.gold, fontSize: 11, fontWeight: "700" },
  balanceGrid: { flexDirection: "row", gap: 12 },
  balanceCard: { flex: 1, borderRadius: 16, borderWidth: 1, borderColor: colors.goldDark, backgroundColor: colors.surface, padding: 15, gap: 7 },
  balanceCardSecondary: { flex: 1, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, padding: 15, gap: 7 },
  balanceCaption: { color: colors.muted, fontSize: 11, textAlign: "right" },
  balanceValue: { color: colors.gold, fontSize: 27, fontWeight: "800", textAlign: "right" },
  balanceValueSecondary: { color: colors.text, fontSize: 27, fontWeight: "800", textAlign: "right" },
  balanceUnit: { color: colors.faint, fontSize: 9, textAlign: "right" },
  sectionHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 8 },
  sectionTitle: { color: colors.text, fontSize: 14, fontWeight: "800", textAlign: "right" },
  count: { color: colors.faint, fontSize: 10 },
  reservationCard: { borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 14, gap: 7 },
  transactionCard: { borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 13, gap: 7 },
  cardTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  cardTitle: { color: colors.text, fontSize: 12, fontWeight: "700" },
  pendingStatus: { color: colors.gold, fontSize: 10, fontWeight: "700" },
  doneStatus: { color: "#69C99A", fontSize: 10, fontWeight: "700" },
  amount: { color: colors.gold, fontSize: 19, fontWeight: "800", textAlign: "right" },
  amountUnit: { color: colors.faint, fontSize: 9, fontWeight: "400" },
  transactionEngine: { color: colors.faint, fontSize: 10 },
  transactionDelta: { color: colors.text, fontSize: 11, textAlign: "right" },
  meta: { color: colors.faint, fontSize: 10, textAlign: "right" },
  updatedAt: { color: colors.faint, fontSize: 9, textAlign: "center", marginTop: 8 },
  empty: { borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 18, alignItems: "center", gap: 9 },
  emptyInline: { borderRadius: 13, backgroundColor: colors.surface, padding: 14, alignItems: "center" },
  emptyTitle: { color: colors.text, fontSize: 13, fontWeight: "800" },
  emptyText: { color: colors.muted, fontSize: 11, lineHeight: 18, textAlign: "center" },
  primary: { minHeight: 44, borderRadius: 12, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center", paddingHorizontal: 14, marginTop: 6 },
  primaryText: { color: colors.background, fontSize: 12, fontWeight: "800" },
  errorCard: { borderRadius: 13, borderWidth: 1, borderColor: "#854F4F", backgroundColor: colors.surface, padding: 12 },
  error: { color: "#E88787", fontSize: 11, textAlign: "right", lineHeight: 18 },
  errorHint: { color: colors.faint, fontSize: 9, textAlign: "right", lineHeight: 16, marginTop: 5 },
});
