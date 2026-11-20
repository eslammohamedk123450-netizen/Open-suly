import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useColorScheme } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { darkPalette, lightPalette, type Palette } from "@/theme/tokens";

export type ThemeMode = "system" | "light" | "dark";

const STORAGE_KEY = "suly.theme.mode";

type ThemeContextValue = {
  mode: ThemeMode;
  palette: Palette;
  setMode: (mode: ThemeMode) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>("dark");
  const systemScheme = useColorScheme();

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((stored) => {
        if (stored === "light" || stored === "dark" || stored === "system") setMode(stored);
      })
      .catch(() => undefined);
  }, []);

  const setAndPersist = (next: ThemeMode) => {
    setMode(next);
    AsyncStorage.setItem(STORAGE_KEY, next).catch(() => undefined);
  };

  const palette = useMemo<Palette>(
    () => (mode === "light" || (mode === "system" && systemScheme === "light") ? lightPalette : darkPalette),
    [mode, systemScheme],
  );

  const value = useMemo<ThemeContextValue>(() => ({ mode, palette, setMode: setAndPersist }), [mode, palette]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
}
