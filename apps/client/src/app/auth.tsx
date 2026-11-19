import { useEffect, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { colors } from "@/theme/tokens";
import { useAuth } from "@/providers/AuthProvider";

type Mode = "signin" | "signup";

export default function AuthScreen() {
  const [mode, setMode] = useState<Mode>("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [isError, setIsError] = useState(false);
  const { configured, user, signIn, signUp } = useAuth();

  useEffect(() => {
    if (user) router.replace("/");
  }, [user]);

  const submit = async () => {
    setMessage("");
    setIsError(false);
    if (!email.trim() || !password) {
      setMessage("اكتب البريد الإلكتروني وكلمة المرور أولًا.");
      setIsError(true);
      return;
    }
    if (password.length < 8) {
      setMessage("كلمة المرور يجب أن تكون 8 أحرف على الأقل.");
      setIsError(true);
      return;
    }
    if (mode === "signup" && !name.trim()) {
      setMessage("اكتب الاسم الذي سيظهر في حسابك.");
      setIsError(true);
      return;
    }
    setBusy(true);
    try {
      if (mode === "signin") {
        const error = await signIn(email, password);
        if (error) { setMessage(error); setIsError(true); }
      } else {
        const result = await signUp(email, password, name);
        if (result.error) { setMessage(result.error); setIsError(true); }
        else if (result.needsEmailConfirmation) setMessage("تم إنشاء الحساب. راجع بريدك الإلكتروني لتأكيده، ثم ارجع لتسجيل الدخول.");
        else setMessage("تم إنشاء الحساب وتسجيل الدخول بنجاح.");
      }
    } catch {
      setMessage("تعذر الاتصال بخدمة الحسابات. تحقق من الإنترنت وحاول مرة أخرى.");
      setIsError(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <Pressable style={styles.back} onPress={() => router.replace("/")}><Text style={styles.backText}>→ العودة للرئيسية</Text></Pressable>
          <View style={styles.brandMark}><Text style={styles.brandLetter}>S</Text></View>
          <Text style={styles.brand}>SULY</Text>
          <Text style={styles.heading}>{mode === "signin" ? "مرحبًا بعودتك" : "أنشئ حسابك"}</Text>
          <Text style={styles.subheading}>{mode === "signin" ? "سجّل الدخول لمتابعة مساحتك الذكية." : "ابدأ رحلتك مع SULY بحساب جديد."}</Text>

          {!configured ? (
            <View style={styles.notice}><Text style={styles.noticeText}>الاتصال غير مكتمل: أضف عنوان مشروع Supabase ومفتاحه العام إلى متغيرات بيئة التطبيق قبل تفعيل الحسابات.</Text></View>
          ) : (
            <View style={styles.form}>
              {mode === "signup" && <TextInput value={name} onChangeText={setName} placeholder="الاسم" placeholderTextColor={colors.faint} style={styles.input} textAlign="right" autoCapitalize="words" />}
              <TextInput value={email} onChangeText={setEmail} placeholder="البريد الإلكتروني" placeholderTextColor={colors.faint} style={styles.input} textAlign="right" keyboardType="email-address" autoCapitalize="none" autoComplete="email" />
              <TextInput value={password} onChangeText={setPassword} placeholder="كلمة المرور (8 أحرف على الأقل)" placeholderTextColor={colors.faint} style={styles.input} textAlign="right" secureTextEntry autoCapitalize="none" />
              <Pressable style={[styles.submit, busy && styles.disabled]} onPress={submit} disabled={busy}>
                {busy ? <ActivityIndicator color={colors.background} /> : <Text style={styles.submitText}>{mode === "signin" ? "تسجيل الدخول" : "إنشاء الحساب"}</Text>}
              </Pressable>
              {!!message && <Text style={isError ? styles.error : styles.success}>{message}</Text>}
              <Pressable style={styles.switch} onPress={() => { setMode((v) => v === "signin" ? "signup" : "signin"); setMessage(""); setIsError(false); }}>
                <Text style={styles.switchText}>{mode === "signin" ? "ليس لديك حساب؟ إنشاء حساب جديد" : "لديك حساب بالفعل؟ تسجيل الدخول"}</Text>
              </Pressable>
            </View>
          )}
          <Text style={styles.footer}>MORE THAN AI. YOUR INTELLIGENT PARTNER.</Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background }, flex: { flex: 1 },
  content: { flexGrow: 1, width: "100%", maxWidth: 520, alignSelf: "center", padding: 24, justifyContent: "center" },
  back: { alignSelf: "flex-start", paddingVertical: 12 }, backText: { color: colors.muted, fontSize: 12 },
  brandMark: { width: 58, height: 58, alignSelf: "center", borderRadius: 18, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", marginTop: 26 },
  brandLetter: { color: colors.gold, fontSize: 32, fontWeight: "900" }, brand: { color: colors.text, textAlign: "center", letterSpacing: 5, fontWeight: "900", fontSize: 18, marginTop: 12 },
  heading: { color: colors.text, textAlign: "center", fontSize: 25, fontWeight: "800", marginTop: 38 }, subheading: { color: colors.muted, textAlign: "center", fontSize: 12, marginTop: 10, lineHeight: 21 },
  form: { marginTop: 30, gap: 12 }, input: { minHeight: 52, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, color: colors.text, paddingHorizontal: 15, fontSize: 14 },
  submit: { minHeight: 52, borderRadius: 14, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center", marginTop: 4 }, disabled: { opacity: 0.65 }, submitText: { color: colors.background, fontSize: 14, fontWeight: "900" },
  switch: { paddingVertical: 15, alignItems: "center" }, switchText: { color: colors.gold, fontSize: 12, fontWeight: "600" },
  notice: { marginTop: 30, padding: 16, borderRadius: 14, borderWidth: 1, borderColor: colors.goldDark, backgroundColor: colors.surface }, noticeText: { color: colors.muted, fontSize: 12, lineHeight: 22, textAlign: "right" },
  error: { color: "#F08B8B", textAlign: "center", fontSize: 11, lineHeight: 20 }, success: { color: colors.gold, textAlign: "center", fontSize: 11, lineHeight: 20 },
  footer: { color: colors.faint, fontSize: 8, textAlign: "center", letterSpacing: 1.8, marginTop: 38 },
});
