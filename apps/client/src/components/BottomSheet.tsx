import { useEffect, useRef, useState, type ReactNode } from "react";
import { Animated, Easing, Modal, Pressable, StyleSheet, View, useWindowDimensions } from "react-native";
import { useTheme } from "@/providers/ThemeProvider";

type BottomSheetProps = {
  visible: boolean;
  onClose: () => void;
  children: ReactNode;
  heightRatio?: number;
};

/**
 * Bottom sheet that slides up from the bottom of the screen over a dim scrim.
 * Closing animates back down before unmounting so the exit matches the entry.
 */
export function BottomSheet({ visible, onClose, children, heightRatio = 0.75 }: BottomSheetProps) {
  const { palette } = useTheme();
  const { height: screenHeight } = useWindowDimensions();
  const [mounted, setMounted] = useState(false);
  const progress = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      setMounted(true);
      Animated.timing(progress, { toValue: 1, duration: 280, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start();
    } else if (mounted) {
      Animated.timing(progress, { toValue: 0, duration: 240, easing: Easing.in(Easing.cubic), useNativeDriver: true }).start(({ finished }) => {
        if (finished) setMounted(false);
      });
    }
    return undefined;
  }, [visible, mounted, progress]);

  if (!mounted) return null;
  const sheetHeight = Math.round(screenHeight * heightRatio);
  return (
    <Modal transparent animationType="none" visible onRequestClose={onClose} statusBarTranslucent>
      <View style={styles.overlay}>
        <Animated.View
          pointerEvents="none"
          style={[StyleSheet.absoluteFill, { backgroundColor: "#000000", opacity: progress }]}
        />
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="إغلاق" />
        <Animated.View
          style={[
            styles.sheet,
            {
              height: sheetHeight,
              backgroundColor: palette.sheet,
              transform: [{
                translateY: progress.interpolate({ inputRange: [0, 1], outputRange: [sheetHeight, 0] }),
              }],
            },
          ]}
        >
          <View style={[styles.grab, { backgroundColor: `${palette.faint}66` }]} />
          {children}
        </Animated.View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: "transparent" },
  sheet: { position: "absolute", left: 0, right: 0, bottom: 0, borderTopLeftRadius: 24, borderTopRightRadius: 24 },
  grab: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, marginTop: 8 },
});
