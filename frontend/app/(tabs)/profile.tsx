import React from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";

import { useAuth } from "@/src/auth";
import { colors, fonts, radius, spacing, type, CURRENCY_SYMBOL } from "@/src/theme";
import Button from "@/src/components/Button";
import { api } from "@/src/api";

const CCY_OPTIONS: ("EUR" | "USD" | "GBP")[] = ["EUR", "USD", "GBP"];

export default function Profile() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, signOut, refresh } = useAuth();

  const setCurrency = async (c: "EUR" | "USD" | "GBP") => {
    await api.updateMe({ currency: c });
    await refresh();
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface }}
      contentContainerStyle={{
        paddingTop: insets.top + spacing.lg, paddingHorizontal: spacing.xl,
        paddingBottom: insets.bottom + 120, gap: spacing.xl,
      }}
      testID="profile-screen"
    >
      <Text style={styles.h1}>Profile</Text>

      <View style={styles.identity}>
        <View style={styles.avatarLg}>
          <Text style={styles.avatarTextLg}>{(user?.name ?? "?")[0]?.toUpperCase()}</Text>
        </View>
        <View>
          <Text style={styles.name} testID="profile-name">{user?.name}</Text>
          <Text style={styles.email} testID="profile-email">{user?.email}</Text>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionLabel}>Currency</Text>
        <View style={styles.row}>
          {CCY_OPTIONS.map((c) => {
            const active = user?.currency === c;
            return (
              <Pressable
                key={c}
                onPress={() => setCurrency(c)}
                style={[styles.ccyChip, active && styles.ccyChipActive]}
                testID={`profile-ccy-${c}`}
              >
                <Text style={[styles.ccySym, active && styles.activeText]}>{CURRENCY_SYMBOL[c]}</Text>
                <Text style={[styles.ccyCode, active && styles.activeText]}>{c}</Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      <Pressable onPress={() => router.push("/link-bank")} style={styles.linkRow} testID="profile-link-bank">
        <Feather name="link" size={20} color={colors.onSurface} />
        <Text style={styles.linkText}>Connect another bank</Text>
        <Feather name="chevron-right" size={20} color={colors.muted} />
      </Pressable>

      <Pressable onPress={() => router.push("/categories")} style={styles.linkRow} testID="profile-link-categories">
        <Feather name="tag" size={20} color={colors.onSurface} />
        <Text style={styles.linkText}>Manage categories & tax rates</Text>
        <Feather name="chevron-right" size={20} color={colors.muted} />
      </Pressable>

      <Pressable onPress={() => router.push("/bucket-new")} style={styles.linkRow} testID="profile-link-new-bucket">
        <Feather name="plus-circle" size={20} color={colors.onSurface} />
        <Text style={styles.linkText}>Create a new savings goal</Text>
        <Feather name="chevron-right" size={20} color={colors.muted} />
      </Pressable>

      <Button
        title="Sign out"
        variant="secondary"
        onPress={async () => { await signOut(); router.replace("/onboarding"); }}
        testID="profile-signout"
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  h1: { fontFamily: fonts.display, fontSize: 28, color: colors.onSurface },
  identity: { flexDirection: "row", alignItems: "center", gap: spacing.lg },
  avatarLg: { width: 64, height: 64, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  avatarTextLg: { fontFamily: fonts.displayBold, fontSize: 26, color: colors.onSurface },
  name: { fontFamily: fonts.display, fontSize: type.xl, color: colors.onSurface },
  email: { fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary, marginTop: 2 },

  section: { gap: spacing.sm },
  sectionLabel: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary, letterSpacing: 0.5, textTransform: "uppercase" },
  row: { flexDirection: "row", gap: spacing.sm },
  ccyChip: { flex: 1, height: 56, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  ccyChipActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  ccySym: { fontFamily: fonts.displayBold, fontSize: type.xl, color: colors.onSurface },
  ccyCode: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary },
  activeText: { color: colors.onSurfaceInverse },

  linkRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  linkText: { flex: 1, fontFamily: fonts.bodyMedium, fontSize: type.lg, color: colors.onSurface },
});
