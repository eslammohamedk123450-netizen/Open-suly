import { useEffect, useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { BottomNavigation } from "@/components/BottomNavigation";
import { colors } from "@/theme/tokens";
import {
  getAIProviderStatus,
  saveAIProviderConfig,
  type AIProviderStatus,
} from "@/lib/ai-provider";

export default function AIProviderScreen() {
  const [status, setStatus] = useState<AIProviderStatus | null>(null);
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    let active = true;
    void getAIProviderStatus().then((nextStatus) => {
      if (!active) return;
      setStatus(nextStatus);
      if (nextStatus.base_url) setBaseUrl(nextStatus.base_url);
      if (nextStatus.model) setModel(nextStatus.model);
      setError("");
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : "تعذر التحقق من صلاحية المالك.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const handleSave = async () => {
    setError("");
    setSuccess("");
    if (!model.trim() || !apiKey.trim()) {
      setError("أدخل معرّف النموذج ومفتاح API.");
      return;
    }
    setSaving(true);
    try {
      const nextStatus = await saveAIProviderConfig({
        provider: "openai-compatible",
        base_url: baseUrl.trim(),
        model: model.trim(),
        api_key: apiKey,
      });
      setStatus(nextStatus);
      setApiKey("");
      setSuccess("تم حفظ إعداد المزود المشفر في Supabase Vault. لن يُعرض المفتاح مرة أخرى.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "تعذر حفظ إعداد مزود AI.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
          <View style={styles.headerCopy}>
            <Text style={styles.title}>مزود الذكاء الاصطناعي</Text>
            <Text style={styles.subtitle}>إعداد مركزي لمالك التطبيق فقط</Text>
          </View>
          <Pressable style={styles.backButton} onPress={() => router.replace("/settings")}>
            <Text style={styles.backText}>→</Text>
          </Pressable>
        </View>

        <KeyboardAvoidingView style={styles.keyboard} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
            <View style={styles.notice}>
              <Text style={styles.noticeTitle}>حماية المفتاح</Text>
              <Text style={styles.noticeText}>
                يُرسل المفتاح إلى خدمة SULY API الموثقة، ثم يُحفظ مشفرًا في Supabase Vault. لا يُخزّن في التطبيق أو Git، ولا يعيده الخادم في أي استجابة.
              </Text>
            </View>

            {status?.configured && (
              <View style={styles.statusCard}>
                <Text style={styles.statusTitle}>المزود مهيأ</Text>
                <Text style={styles.statusText}>
                  {status.model || "نموذج غير محدد"} · {status.source === "vault" ? "مخزن في Vault" : "من إعداد الخادم"}
                </Text>
                <Text style={styles.statusHint}>للتدوير، أدخل مفتاحًا جديدًا ثم احفظ. المفتاح الحالي غير قابل للعرض.</Text>
              </View>
            )}

            <Text style={styles.label}>عنوان API الأساسي</Text>
            <TextInput
              value={baseUrl}
              onChangeText={setBaseUrl}
              placeholder="https://api.openai.com/v1"
              placeholderTextColor={colors.faint}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              style={styles.inputLtr}
              accessibilityLabel="عنوان API الأساسي"
            />

            <Text style={styles.label}>معرّف النموذج</Text>
            <TextInput
              value={model}
              onChangeText={setModel}
              placeholder="مثال: اسم النموذج لدى المزود"
              placeholderTextColor={colors.faint}
              autoCapitalize="none"
              autoCorrect={false}
              style={styles.inputLtr}
              accessibilityLabel="معرّف النموذج"
            />

            <Text style={styles.label}>مفتاح API</Text>
            <TextInput
              value={apiKey}
              onChangeText={setApiKey}
              placeholder={status?.api_key_set ? "أدخل مفتاحًا جديدًا للتحديث" : "أدخل مفتاح المزود"}
              placeholderTextColor={colors.faint}
              autoCapitalize="none"
              autoCorrect={false}
              secureTextEntry
              style={styles.inputLtr}
              accessibilityLabel="مفتاح API"
            />
            <Text style={styles.fieldHint}>يدعم هذا النموذج واجهة OpenAI-compatible عبر HTTPS.</Text>

            {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
            {!!success && <Text accessibilityRole="status" style={styles.success}>{success}</Text>}

            <Pressable
              style={[styles.button, (loading || saving) && styles.buttonDisabled]}
              disabled={loading || saving}
              onPress={() => { void handleSave(); }}
            >
              <Text style={styles.buttonText}>{saving ? "جارٍ الحفظ..." : loading ? "جارٍ التحقق..." : "حفظ الإعداد المشفر"}</Text>
            </Pressable>
          </ScrollView>
        </KeyboardAvoidingView>
        <BottomNavigation active="settings" />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  page: { flex: 1, direction: "rtl", width: "100%", maxWidth: 1100, alignSelf: "center", backgroundColor: colors.background },
  header: { minHeight: 72, paddingHorizontal: 20, flexDirection: "row", alignItems: "center", borderBottomWidth: 1, borderBottomColor: colors.border, gap: 12 },
  logo: { width: 40, height: 40, borderRadius: 13, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  logoText: { color: colors.gold, fontSize: 23, fontWeight: "800" },
  headerCopy: { flex: 1, alignItems: "flex-end" },
  title: { color: colors.text, fontSize: 17, fontWeight: "800" },
  subtitle: { color: colors.muted, fontSize: 11, marginTop: 3 },
  backButton: { width: 40, height: 40, borderRadius: 13, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  backText: { color: colors.gold, fontSize: 22 },
  keyboard: { flex: 1 },
  content: { paddingHorizontal: 20, paddingTop: 22, paddingBottom: 30, width: "100%", maxWidth: 680, alignSelf: "center" },
  notice: { borderRadius: 16, padding: 15, borderWidth: 1, borderColor: colors.goldDark, backgroundColor: colors.surface, marginBottom: 18 },
  noticeTitle: { color: colors.gold, fontSize: 13, fontWeight: "800", textAlign: "right" },
  noticeText: { color: colors.muted, fontSize: 12, lineHeight: 20, textAlign: "right", marginTop: 7 },
  statusCard: { borderRadius: 14, padding: 13, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, marginBottom: 18 },
  statusTitle: { color: colors.gold, fontSize: 13, fontWeight: "700", textAlign: "right" },
  statusText: { color: colors.text, fontSize: 12, textAlign: "right", marginTop: 5 },
  statusHint: { color: colors.muted, fontSize: 11, lineHeight: 18, textAlign: "right", marginTop: 5 },
  label: { color: colors.text, fontSize: 12, fontWeight: "700", textAlign: "right", marginTop: 11, marginBottom: 7 },
  inputLtr: { minHeight: 48, borderRadius: 12, paddingHorizontal: 13, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, color: colors.text, textAlign: "left", writingDirection: "ltr", fontSize: 13 },
  fieldHint: { color: colors.faint, fontSize: 10, textAlign: "right", marginTop: 7 },
  error: { color: "#F08B8B", fontSize: 12, lineHeight: 18, textAlign: "right", marginTop: 14 },
  success: { color: "#90D7AB", fontSize: 12, lineHeight: 18, textAlign: "right", marginTop: 14 },
  button: { minHeight: 50, borderRadius: 14, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center", marginTop: 22 },
  buttonDisabled: { opacity: 0.55 },
  buttonText: { color: colors.background, fontSize: 13, fontWeight: "800" },
});
