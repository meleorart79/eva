import { Tabs } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { Platform, StyleSheet, View } from "react-native";
import { colors, fonts } from "@/src/theme";

const ICONS: Record<string, keyof typeof Feather.glyphMap> = {
  index: "home",
  buckets: "target",
  insights: "bar-chart-2",
  settings: "sliders",
  profile: "user",
};

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarShowLabel: true,
        tabBarActiveTintColor: colors.surfaceInverse,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: { fontFamily: fonts.bodyMedium, fontSize: 11, marginBottom: 2 },
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: StyleSheet.hairlineWidth,
          height: Platform.OS === "ios" ? 84 : 64,
          paddingTop: 8,
        },
        tabBarIcon: ({ color, focused }) => (
          <View>
            <Feather
              name={ICONS[route.name as keyof typeof ICONS] ?? "circle"}
              size={focused ? 24 : 22}
              color={color}
            />
          </View>
        ),
      })}
    >
      <Tabs.Screen name="index" options={{ title: "Home" }} />
      <Tabs.Screen name="buckets" options={{ title: "Goals" }} />
      <Tabs.Screen name="insights" options={{ title: "Insights" }} />
      <Tabs.Screen name="settings" options={{ title: "Settings" }} />
      <Tabs.Screen name="profile" options={{ title: "Profile" }} />
    </Tabs>
  );
}
