import { useCallback, useState } from "react";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { colors } from "@/theme/tokens";
import { useAuth } from "@/providers/AuthProvider";
import {
  listProjectFileHistory, listProjectFiles, readProjectFile,
  restoreProjectFileRevision, saveProjectFile, previewProjectFile, searchProjectFiles,
  type ProjectFile, type ProjectFileRevision, type ProjectFileDiffPreview, type ProjectFileSearchResult,
} from "@/lib/project-files";

export default function ProjectFilesScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [selected, setSelected] = useState("");
  const [selectedUpdatedAt, setSelectedUpdatedAt] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [newPath, setNewPath] = useState("");
  const [history, setHistory] = useState<ProjectFileRevision[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<ProjectFileDiffPreview | null>(null);
  const [notice, setNotice] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<ProjectFileSearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  const runSearch = async () => {
    if (searching) return;
    setSearching(true);
    setNotice("");
    try {
      setSearchResults(await searchProjectFiles(id, searchQuery));
    } catch (error) {
      setSearchResults([]);
      setNotice(error instanceof Error ? error.message : "تعذر البحث داخل الملفات.");
    } finally {
      setSearching(false);
    }
  };

  const loadHistory = async (path: string) => setHistory(await listProjectFileHistory(id, path));

  const refresh = useCallback(async () => {
    if (!user || !id) { setLoading(false); return; }
    setLoading(true);
    try {
      const items = await listProjectFiles(id);
      setFiles(items);
      if (selected && items.some((item) => item.path === selected)) {
        const file = await readProjectFile(id, selected);
        setContent(file.content);
        setSelectedUpdatedAt(file.updated_at);
        await loadHistory(selected);
      } else if (selected) {
        setSelected("");
        setContent("");
        setSelectedUpdatedAt(null);
        setHistory([]);
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
      setSelectedUpdatedAt(file.updated_at);
      await loadHistory(path);
    } catch (error) { setNotice(error instanceof Error ? error.message : "تعذر فتح الملف."); }
  };

  const reviewChanges = async () => {
    const path = selected || newPath.trim();
    if (!path) { setNotice("اكتب مسار الملف أولًا، مثل src/main.py"); return; }
    setPreviewing(true);
    setNotice("");
    try {
      const result = await previewProjectFile(id, path, content, selected ? selectedUpdatedAt : null);
      setPreview(result);
      setNotice(result.has_changes ? "راجع الفروقات قبل حفظ الملف." : "لا توجد تغييرات عن النسخة الحالية.");
    } catch (error) {
      setPreview(null);
      setNotice(error instanceof Error ? error.message : "تعذرت مراجعة التغييرات.");
    } finally { setPreviewing(false); }
  };

  const save = async () => {
    const path = selected || newPath.trim();
    if (!path) { setNotice("اكتب مسار الملف أولًا، مثل src/main.py"); return; }
    setSaving(true);
    setNotice("");
    try {
      const saved = await saveProjectFile(id, path, content, selected ? selectedUpdatedAt : null);
      setSelected(path);
      setSelectedUpdatedAt(saved.updated_at);
      setPreview(null);
      setNewPath("");
      setFiles(await listProjectFiles(id));
      await loadHistory(path);
      setNotice("تم حفظ الملف. النسخ السابقة محفوظة في سجل الإصدارات.");
    } catch (error) { setNotice(error instanceof Error ? error.message : "تعذر حفظ الملف."); }
    finally { setSaving(false); }
  };

  const restore = (revision: ProjectFileRevision) => {
    Alert.alert(
      "استعادة نسخة قديمة",
      "سيتم استبدال محتوى الملف بهذه النسخة، مع الاحتفاظ بالمحتوى الحالي في سجل الإصدارات.",
      [
        { text: "إلغاء", style: "cancel" },
        { text: "استعادة", style: "destructive", onPress: () => {
          setRestoring(true);
          if (!selectedUpdatedAt) { setNotice("أعد تحميل الملف قبل الاستعادة."); setRestoring(false); return; }
          void restoreProjectFileRevision(id, revision.id, selectedUpdatedAt)
            .then(async (result) => {
              const file = await readProjectFile(id, revision.path);
              setContent(file.content);
              setSelectedUpdatedAt(result.updated_at);
              await loadHistory(revision.path);
              setNotice("تمت الاستعادة، وحُفظت النسخة السابقة في السجل.");
            })
            .catch((error) => setNotice(error instanceof Error ? error.message : "تعذرت استعادة النسخة."))
            .finally(() => setRestoring(false));
        } },
      ],
    );
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <View style={styles.header}>
          <Pressable style={styles.back} onPress={() => router.back()}><Text style={styles.backText}>→</Text></Pressable>
          <View style={styles.headerCopy}>
            <Text style={styles.title}>ملفات المشروع</Text>
            <Text style={styles.subtitle}>محرر ملفات نصية وسجل نسخ قابل للاستعادة</Text>
          </View>
          <View style={styles.logo}><Text style={styles.logoText}>S</Text></View>
        </View>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {loading ? <View style={styles.state}><ActivityIndicator color={colors.gold} /></View> : null}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>بحث داخل ملفات المشروع</Text>
            <TextInput
              value={searchQuery}
              onChangeText={setSearchQuery}
              onSubmitEditing={() => void runSearch()}
              placeholder="ابحث عن دالة أو نص أو اسم..."
              placeholderTextColor={colors.faint}
              autoCapitalize="none"
              style={styles.pathInput}
              returnKeyType="search"
            />
            <Pressable style={[styles.secondary, searching && styles.disabled]} onPress={() => void runSearch()} disabled={searching || searchQuery.trim().length < 2}>
              {searching ? <ActivityIndicator color={colors.gold} /> : <Text style={styles.secondaryText}>بحث في محتوى الملفات</Text>}
            </Pressable>
            {searchResults.map((result, index) => (
              <Pressable key={result.path + ":" + index} style={styles.searchResult} onPress={() => void openFile(result.path)}>
                <Text style={styles.filePath}>{result.path}</Text>
                <Text selectable style={styles.searchSnippet}>{result.snippet}</Text>
              </Pressable>
            ))}
            {searchQuery.trim().length >= 2 && searchResults.length === 0 && !searching
              ? <Text style={styles.muted}>لا توجد نتائج مطابقة لآخر بحث.</Text>
              : null}
          </View>
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
          {selected ? (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>سجل الإصدارات ({history.length})</Text>
              {history.length === 0 ? <Text style={styles.muted}>ستظهر النسخ السابقة بعد أول تعديل محفوظ.</Text> : history.map((revision) => (
                <View key={revision.id} style={styles.revisionRow}>
                  <View style={styles.revisionCopy}>
                    <Text style={styles.revisionDate}>{new Date(revision.created_at).toLocaleString()}</Text>
                    <Text style={styles.fileSize}>{Math.ceil(revision.size_bytes / 1024)} KB</Text>
                  </View>
                  <Pressable style={[styles.restoreButton, restoring && styles.disabled]} disabled={restoring} onPress={() => restore(revision)}>
                    <Text style={styles.restoreText}>استعادة</Text>
                  </Pressable>
                </View>
              ))}
            </View>
          ) : null}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>{selected || "إنشاء ملف جديد"}</Text>
            {!selected && <TextInput value={newPath} onChangeText={setNewPath} placeholder="src/main.py" placeholderTextColor={colors.faint} autoCapitalize="none" style={styles.pathInput} />}
            <TextInput value={content} onChangeText={(value) => { setContent(value); setPreview(null); }} multiline textAlignVertical="top"
              autoCapitalize="none" autoCorrect={false} spellCheck={false}
              placeholder="اكتب محتوى الملف هنا..." placeholderTextColor={colors.faint} style={styles.editor} />
            <View style={styles.actions}>
              {selected ? <Pressable style={styles.secondary} onPress={() => { setSelected(""); setSelectedUpdatedAt(null); setContent(""); setNewPath(""); setHistory([]); setPreview(null); }}>
                <Text style={styles.secondaryText}>ملف جديد</Text>
              </Pressable> : null}
              <Pressable style={[styles.secondary, (saving || restoring || previewing) && styles.disabled]} onPress={() => void reviewChanges()} disabled={saving || restoring || previewing}>
                <Text style={styles.secondaryText}>{previewing ? "جارٍ الفحص..." : "مراجعة التغييرات"}</Text>
              </Pressable>
              <Pressable style={[styles.save, (saving || restoring || previewing) && styles.disabled]} onPress={() => void save()} disabled={saving || restoring || previewing}>
                <Text style={styles.saveText}>{saving ? "جارٍ الحفظ..." : "حفظ الملف"}</Text>
              </Pressable>
            </View>
            {preview ? (
              <View style={styles.diffPanel}>
                <Text style={styles.diffTitle}>{preview.has_changes ? "معاينة الفروقات" : "لا توجد فروقات"}</Text>
                <ScrollView horizontal style={styles.diffScroll}>
                  <Text selectable style={styles.diffText}>{preview.diff || "المحتوى مطابق للنسخة الحالية."}</Text>
                </ScrollView>
              </View>
            ) : null}
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
  searchResult: { padding: 10, borderRadius: 9, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, gap: 7 },
  searchSnippet: { color: colors.muted, fontSize: 10, lineHeight: 17, textAlign: "left" },
  filePath: { color: colors.text, fontSize: 11, textAlign: "left", flex: 1 },
  fileSize: { color: colors.faint, fontSize: 9, marginRight: 10 },
  revisionRow: { minHeight: 48, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 10, borderRadius: 9, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border },
  revisionCopy: { flex: 1, gap: 3 },
  revisionDate: { color: colors.text, fontSize: 10, textAlign: "left" },
  restoreButton: { minHeight: 34, paddingHorizontal: 12, borderRadius: 8, borderWidth: 1, borderColor: colors.goldDark, alignItems: "center", justifyContent: "center" },
  restoreText: { color: colors.gold, fontSize: 10, fontWeight: "700" },
  pathInput: { minHeight: 42, borderRadius: 9, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, color: colors.text, paddingHorizontal: 12, textAlign: "left" },
  editor: { minHeight: 300, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, color: colors.text, padding: 12, fontSize: 12, lineHeight: 19, textAlign: "left", fontFamily: "monospace" },
  actions: { flexDirection: "row", gap: 9 },
  save: { flex: 1, minHeight: 44, borderRadius: 10, backgroundColor: colors.gold, alignItems: "center", justifyContent: "center" },
  saveText: { color: colors.background, fontWeight: "800", fontSize: 12 },
  secondary: { paddingHorizontal: 14, minHeight: 44, borderRadius: 10, borderWidth: 1, borderColor: colors.goldDark, alignItems: "center", justifyContent: "center" },
  secondaryText: { color: colors.gold, fontSize: 11, fontWeight: "700" },
  disabled: { opacity: 0.5 },
  notice: { color: colors.gold, fontSize: 10, textAlign: "right" },
  diffPanel: { padding: 12, borderRadius: 10, borderWidth: 1, borderColor: colors.goldDark, backgroundColor: colors.background, gap: 8 },
  diffTitle: { color: colors.gold, fontSize: 11, fontWeight: "800", textAlign: "right" },
  diffScroll: { maxHeight: 280 },
  diffText: { color: colors.text, fontSize: 10, lineHeight: 17, fontFamily: "monospace", textAlign: "left" },
  muted: { color: colors.muted, fontSize: 10, textAlign: "center" },
  state: { padding: 12, alignItems: "center" },
});
