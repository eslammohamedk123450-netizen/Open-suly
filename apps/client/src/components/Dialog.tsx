import { useEffect, useRef, useState } from "react";
import { Animated, Easing, Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { useTheme } from "@/providers/ThemeProvider";

type DialogProps = {
  visible: boolean;
  title: string;
  message?: string;
  confirmLabel: string;
  destructive?: boolean;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
};

/** Centered confirmation dialog: fades in with a subtle scale, dark scrim behind. */
export function Dialog({
  visible,
  title,
  message,
  confirmLabel,
  destructive = true,
  cancelLabel = "إلغاء",
  onConfirm,
  onCancel,
}: DialogProps) {
  const { palette } = useTheme();
  const [mounted, setMounted] = useState(false);
  const progress = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      setMounted(true);
      Animated.timing(progress, { toValue: 1, duration: 200, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start();
    } else if (mounted) {
      Animated.timing(progress, { toValue: 0, duration: 160, useNativeDriver: true }).start(({ finished }) => {
        if (finished) setMounted(false);
      });
    }
    return undefined;
  }, [visible, mounted, progress]);

  if (!mounted) return null;
  return (
    <Modal transparent animationType="none" visible onRequestClose={onCancel} statusBarTranslucent>
      <View style={styles.overlay}>
        <Animated.View
          pointerEvents="none"
          style={[StyleSheet.absoluteFill, { backgroundColor: "#000000", opacity: progress }]}
        />
        <Pressable style={StyleSheet.absoluteFill} onPress={onCancel} accessibilityLabel="إغلاق" />
        <Animated.View
          style={[
            styles.card,
            {
              backgroundColor: palette.surface,
              opacity: progress,
              transform: [{
                scale: progress.interpolate({ inputRange: [0, 1], outputRange: [0.92, 1] }),
              }],
            },
          ]}
        >
          <Text style={[styles.title, { color: palette.text }]}>{title}</Text>
          {!!message && <Text style={[styles.message, { color: palette.muted }]}>{message}</Text>}
          <View style={styles.buttons}>
            <Pressable style={[styles.button, { backgroundColor: palette.surfaceSecondary }]} onPress={onCancel}>
              <Text style={[styles.buttonText, { color: palette.text }]}>{cancelLabel}</Text>
            </Pressable>
            <Pressable
              style={[styles.button, { backgroundColor: destructive ? palette.danger : palette.text }]}
              onPress={onConfirm}
            >
              <Text style={[styles.buttonText, { color: destructive ? "#FFFFFF" : palette.onPrimary }]}>
                {confirmLabel}
              </Text>
            </Pressable>
          </View>
        </Animated.View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, alignItems: "center", justifyContent: "center" },
  card: {
    direction: "rtl",
    marginHorizontal: 32,
    borderRadius: 18,
    paddingVertical: 22,
    paddingHorizontal: 20,
    minWidth: 280,
  },
  title: { fontSize: 16, fontWeight: "700", textAlign: "right" },
  message: { fontSize: 13, lineHeight: 21, textAlign: "right", marginTop: 10 },
  buttons: { flexDirection: "row", gap: 10, marginTop: 20 },
  button: { flex: 1, borderRadius: 12, paddingVertical: 12, alignItems: "center", justifyContent: "center" },
  buttonText: { fontSize: 14, fontWeight: "700" },
});
