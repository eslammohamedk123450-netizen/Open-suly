import { Stack } from "expo-router";
import { StatusBar } from "react-native";
import { AuthProvider } from "@/providers/AuthProvider";

export default function RootLayout() {
  return (
    <AuthProvider>
      <StatusBar barStyle="light-content" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: "#080B14" },
          animation: "fade",
        }}
      />
    </AuthProvider>
  );
}
