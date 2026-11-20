import { Stack } from "expo-router";
import { StatusBar } from "react-native";
import { AuthProvider } from "@/providers/AuthProvider";
import { ThemeProvider, useTheme } from "@/providers/ThemeProvider";

export default function RootLayout() {
  return (
    <AuthProvider>
      <ThemeProvider>
        <RootNavigator />
      </ThemeProvider>
    </AuthProvider>
  );
}

function RootNavigator() {
  const { palette } = useTheme();
  const light = palette.background === "#F5F5F5";
  return (
    <>
      <StatusBar barStyle={light ? "dark-content" : "light-content"} />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: palette.background },
          animation: "fade",
        }}
      />
    </>
  );
}
