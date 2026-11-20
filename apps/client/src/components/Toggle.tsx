import { useEffect, useRef } from "react";
import { Animated, Pressable, StyleSheet } from "react-native";
import { useTheme } from "@/providers/ThemeProvider";

type ToggleProps = {
  value: boolean;
  onChange: (value: boolean) => void;
};

/** Small animated switch; turns blue when enabled. */
export function Toggle({ value, onChange }: ToggleProps) {
  const { palette } = useTheme();
  const progress = useRef(new Animated.Value(value ? 1 : 0)).current;

  useEffect(() => {
    Animated.timing(progress, { toValue: value ? 1 : 0, duration: 180, useNativeDriver: false }).start();
  }, [value, progress]);

  return (
    <Pressable
      onPress={() => onChange(!value)}
      accessibilityRole="switch"
      accessibilityState={{ checked: value }}
      style={[styles.track, { backgroundColor: value ? palette.accent : palette.surfaceSecondary }]}
    >
      <Animated.View
        style={[
          styles.knob,
          {
            transform: [{
              translateX: progress.interpolate({ inputRange: [0, 1], outputRange: [0, 20] }),
            }],
          },
        ]}
      />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  track: { width: 46, height: 28, borderRadius: 14, padding: 2 },
  knob: { width: 24, height: 24, borderRadius: 12, backgroundColor: "#FFFFFF" },
});
