import React, { useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput,
  KeyboardAvoidingView, Platform, TouchableWithoutFeedback, Keyboard,
} from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";

import { api } from "@/src/api";
import Button from "@/src/components/Button";
import { colors, fonts, radius, spacing, type } from "@/src/theme";

type Provider = "revolut" | "spuerkeess";

const PROVIDERS: { key: Provider; name: string; sub: string; note: string }[] = [
  {
    key: "revolut",
    name: "Revolut",
    sub: "Open Banking · sandbox",
    note: "Paste a Revolut Business sandbox access token. Éva will pull transactions and run the tax engine.",
  },
  {
    key: "spuerkeess",
    name: "Spuerkeess",
    sub: "PSD2 · stubbed",
    note: "PSD2 access requires registration. For now Éva will use realistic stub transactions so you can preview the experience end-to-end.",
  },
];

export default function LinkBank() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [provider, setProvider] = useState<Provider>("revolut");
  const [token, setToken] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setErr(null);
    if (provider === "revolut" && token.trim().length < 4) {
      setErr("Paste a Revolut sandbox access token.");
      return;
    }
    setSaving(true);
    try {
      // Spuerkeess is stubbed — accept any non-empty token (or auto-fill).
      const t = provider === "spuerkeess" && !token.trim() ? "stub-spuerkeess" : token.trim();
      await api.linkBank(provider, t);
      router.back();
    } catch (e: any) {
      setErr(e.message || "Could not link account.");
    } finally {
      setSaving(false);
    }
  };

  const active = PROVIDERS.find((p) => p.key === provider)!;

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      style={{ flex: 1, backgroundColor: colors.surface }}
      testID="link-bank-screen"
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} testID="link-bank-close">
          <Feather name="x" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Connect your bank</Text>
        <View style={styles.iconBtn} />
      </View>

      <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
        <ScrollView
          contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: insets.bottom + 140, gap: spacing.lg }}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={styles.helper}>
            Éva reads your transactions automatically. You'll never enter a purchase by hand.
          </Text>

          <View>
            <Text style={styles.label}>Provider</Text>
            <View style={{ gap: spacing.sm }}>
              {PROVIDERS.map((p) => {
                const isActive = provider === p.key;
                return (
                  <Pressable
                    key={p.key}
                    onPress={() => setProvider(p.key)}
                    style={[styles.providerRow, isActive && styles.providerRowActive]}
                    testID={`provider-${p.key}`}
                  >
                    <View style={[styles.providerDot, isActive && styles.providerDotActive]} />
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.providerName, isActive && styles.providerNameActive]}>{p.name}</Text>
                      <Text style={styles.providerSub}>{p.sub}</Text>
                    </View>
                    {isActive ? (
                      <Feather name="check-circle" size={20} color={colors.brand} />
                    ) : null}
                  </Pressable>
                );
              })}
            </View>
          </View>

          <View>
            <Text style={styles.label}>{provider === "revolut" ? "Access token" : "Reference (optional)"}</Text>
            <TextInput
              value={token}
              onChangeText={setToken}
              placeholder={provider === "revolut" ? "eyJ... or rvlt_sandbox_..." : "Any reference label"}
              placeholderTextColor={colors.muted}
              autoCapitalize="none"
              autoCorrect={false}
              secureTextEntry={provider === "revolut"}
              style={styles.input}
              testID="link-bank-token"
            />
          </View>

          <View style={styles.note}>
            <Feather name="info" size={16} color={colors.onSurfaceSecondary} />
            <Text style={styles.noteText}>{active.note}</Text>
          </View>

          {err ? <Text style={styles.err} testID="link-bank-error">{err}</Text> : null}
        </ScrollView>
      </TouchableWithoutFeedback>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Button title="Connect" onPress={submit} loading={saving} testID="link-bank-submit" />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary },
  title: { fontFamily: fonts.display, fontSize: type.xl, color: colors.onSurface },

  helper: { fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary, lineHeight: 20 },
  label: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary, letterSpacing: 0.5, textTransform: "uppercase", marginBottom: spacing.sm },

  providerRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    padding: spacing.lg, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
  },
  providerRowActive: { backgroundColor: colors.brandTertiary, borderColor: colors.brand },
  providerDot: { width: 18, height: 18, borderRadius: radius.pill, borderWidth: 2, borderColor: colors.borderStrong },
  providerDotActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  providerName: { fontFamily: fonts.bodyMedium, fontSize: type.lg, color: colors.onSurface },
  providerNameActive: { fontFamily: fonts.displayBold },
  providerSub: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary, marginTop: 2 },

  input: { height: 52, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.lg, fontFamily: fonts.body, fontSize: type.lg, color: colors.onSurface },

  note: { flexDirection: "row", gap: spacing.sm, padding: spacing.md, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md },
  noteText: { flex: 1, fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary, lineHeight: 20 },

  err: { fontFamily: fonts.body, color: colors.error, fontSize: type.base },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.xl, paddingTop: spacing.md, backgroundColor: colors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
});
