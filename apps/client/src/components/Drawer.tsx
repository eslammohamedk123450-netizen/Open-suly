import { useEffect, useRef, useState, type ReactNode } from "react";
import { Animated, Easing, Modal, Pressable, StyleSheet, View, useWindowDimensions } from "react-native";
import { useTheme } from "@/providers/ThemeProvider";

type DrawerProps = {
  visible: boolean;
  onClose: () => void;
  children: ReactNode;
  widthRatio?: number;
};

/** Side panel that slides in from the right edge over a dim scrim. */
export function Drawer({ visible, onClose, children, widthRatio = 0.82 }: DrawerProps) {
  const { palette } = useTheme();
  const { width: screenWidth } = useWindowDimensions();
  const [mounted, setMounted] = useState(false);
  const progress = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      setMounted(true);
      Animated.timing(progress, { toValue: 1, duration: 260, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start();
    } else if (mounted) {
      Animated.timing(progress, { toValue: 0, duration: 220, easing: Easing.in(Easing.cubic), useNativeDriver: true }).start(({ finished }) => {
        if (finished) setMounted(false);
      });
    }
    return undefined;
  }, [visible, mounted, progress]);

  if (!mounted) return null;
  const drawerWidth = Math.round(screenWidth * widthRatio);
  return (
    <Modal transparent animationType="none" visible onRequestClose={onClose} statusBarTranslucent>
      <View style={styles.overlay}>
        <Animated.View
          pointerEvents="none"
          style={[StyleSheet.absoluteFill, { backgroundColor: "#000000", opacity: progress }]}
        />
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="إغلاق القائمة" />
        <Animated.View
          style={[
            styles.panel,
            {
              width: drawerWidth,
              backgroundColor: palette.drawer,
              transform: [{
                translateX: progress.interpolate({ inputRange: [0, 1], outputRange: [drawerWidth, 0] }),
              }],
            },
          ]}
        >
          {children}
        </Animated.View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1 },
  panel: { position: "absolute", top: 0, bottom: 0, right: 0 },
});
