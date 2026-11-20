import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { colors } from "@/theme/tokens";
import { useAuth } from "@/providers/AuthProvider";
import { listProjectFiles, readProjectFile, saveProjectFile, type ProjectFile } from "@/lib/project-files";

export default function ProjectFilesScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [selected, setSelected] = useState("");
  const [content, setContent] = useState("");
  const [newPath, setNewPath] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    if (!user || !id) { setLoading(false); return; }
    setLoading(true);
    try {
      const items = await listProjectFiles(id);
      setFiles(items);
      if (selected && items.some((item) => item.path === selected)) {
        const file = await readProjectFile(id, selected);
        setContent(file.content);
      } else if (selected) {
        setSelected("");
        setContent("");
      }
      setNotice("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر تحميل الملفات.");
    } finally { setLoading(false); }
  }, [user?.id, id, selected]);

  useFocusEffect(useCallback(() => { void refresh(); }, [refresh]));

  const openFile = async (path: string) => {
    setNotice("");
    try {
      const file = await readProjectFile(id, path);
      setSelected(path);
      setContent(file.content);
    } catch (error) { setNotice(error instanceof Error ? error.message : "تعذر فتح الملف."); }
  };

  const save = async () => {
    const path = selected || newPath.trim();
    if (!path) { setNotice("اكتب مسار الملف أولًا، مثل src/main.py"); return; }
    setSaving(true);
    setNotice("");
    try {
      await saveProjectFile(id, path, content);
      setSelected(path);
      setNewPath("");
      const items = await listProjectFiles(id);
      setFiles(items);
      setNotice("تم حفظ الملف داخل مساحة المشروع.");
    } catch (error) { setNotice(error instanceof Error ? error.message : "تعذر حفظ الملف."); }
    finally { setSaving(false); }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <Pressable style={styles.back} onPress={() => router.back()}><Text style={styles.backText}>→</Text></Pressable>
          <View style={styles.headerCopy}>
            <Text style={styles.title}>ملفات المشروع</Text>
            <Text style={styles.subtitle}>محرر ملفات نصية — حتى 256 كيلوبايت للملف</Text>
          </View>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
        </View>
        <ScrollView contentContainerStyle={styles.content}>
          {loading ? <View style={styles.state}><ActivityIndicator color={colors.gold} /></View> : null}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>ملفات مساحة العمل ({files.length}/200)</Text>
            {files.map((file) => (
              <Pressable key={file.id} style={[styles.fileRow, selected === file.path && styles.fileSelected]} onPress={() => void openFile(file.path)}>
                <Text style={styles.fileSize}>{Math.ceil(file.size / 1024)} KB</Text>
                <Text style={styles.filePath}>{file.path}</Text>
              </Pressable>
            ))}
            {files.length === 0 && !loading ? <Text style={styles.muted}>لا توجد ملفات بعد. أنشئ أول ملف بالأسفل.</Text> : null}
          </View>
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>{selected || "إنشاء ملف جديد"}</Text>
            {!selected && <TextInput value={newPath} onChangeText={setNewPath} placeholder="src/main.py" placeholderTextColor={colors.faint} autoCapitalize="none" style={styles.pathInput} />}
            <TextInput
              value={content}
              onChangeText={setContent}
              multiline
              textAlignVertical="top"
              autoCapitalize="none"
              autoCorrect={false}
              spellCheck={false}
              placeholder="اكتب محتوى الملف هنا..."
              placeholderTextColor={colors.faint}
              style={styles.editor}
            />
            <View style={styles.actions}>
              {selected ? <Pressable style={styles.secondary} onPress={() => { setSelected(""); setContent(""); setNewPath(""); }}><Text style={styles.secondaryText}>ملف جديد</Text></Pressable> : null}
              <Pressable style={[styles.save, saving && styles.disabled]} onPress={() => void save()} disabled={saving}>
                <Text style={styles.saveText}>{saving ? "جارٍ الحفظ..." : "حفظ الملف"}</Text>
              </Pressable>
            </View>
            {!!notice && <Text style={styles.notice}>{notice}</Text>}
          </View>
        </ScrollView>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  page: { flex: 1, width: "100%", maxWidth: 1100, alignSelf: "center", backgroundColor: colors.background },
  header: { minHeight: 70, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", gap: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  back: { width: 40, height: 40, borderRadius: 13, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  backText: { color: colors.gold, fontSize: 22 },
  headerCopy: { flex: 1 },
  title: { color: colors.text, fontSize: 15, fontWeight: "800", textAlign: "right" },
  subtitle: { color: colors.muted, fontSize: 10, marginTop: 4, textAlign: "right" },
  logo: { width: 40, height: 40, borderRadius: 13, borderWidth: 1, borderColor: colors.gold, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  logoText: { color: colors.gold, fontSize: 22, fontWeight: "800" },
  content: { padding: 16, paddingBottom: 40, gap: 14, width: "100%", maxWidth: 900, alignSelf: "center" },
  section: { padding: 14, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, gap: 10 },
  sectionTitle: { color: colors.text, fontSize: 13, fontWeight: "800", textAlign: "right" },
  fileRow: { minHeight: 42, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 10, borderRadius: 9, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border },
  fileSelected: { borderColor: colors.gold },
  filePath: { color: colors.text, fontSize: 11, textAlign: "left", flex: 1 },
  fileSize: { color: colors.faint, fontSize: 9, marginRight: 10 },
  pathInput: { minHeight: 42, borderRadius: 9, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, color: colors.text, paddingHorizontal: 12, textAlign: "left" },
  editor: { minHeight: 300, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, color: colors.text, padding: 12, fontSize: 12, lineHeight: 19, textAlign: "left", fontFamily: "monospace" },
  actions: { flexDirection: "row", gap: 9 },
  save: { flex: 1, minHeight: 44, borderRadius: 10, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center" },
  saveText: { color: colors.background, fontWeight: "800", fontSize: 12 },
  secondary: { paddingHorizontal: 14, minHeight: 44, borderRadius: 10, borderWidth: 1, borderColor: colors.goldDark, alignItems: "center", justifyContent: "center" },
  secondaryText: { color: colors.gold, fontSize: 11, fontWeight: "700" },
  disabled: { opacity: 0.5 },
  notice: { color: colors.gold, fontSize: 10, textAlign: "right" },
  muted: { color: colors.muted, fontSize: 10, textAlign: "center" },
  state: { padding: 12, alignItems: "center" },
});
