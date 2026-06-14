import React, { useState } from "react";
import {
  View, Text, StyleSheet, KeyboardAvoidingView, Platform,
  ScrollView, Pressable, TouchableWithoutFeedback, Keyboard,
} from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";

import { colors, fonts, radius, spacing, type } from "@/src/theme";
import Button from "@/src/components/Button";
import Field from "@/src/components/Field";
import { useAuth } from "@/src/auth";

const CURRENCIES: { code: "EUR" | "USD" | "GBP"; sym: string; label: string }[] = [
  { code: "EUR", sym: "€", label: "Euro" },
  { code: "USD", sym: "$", label: "US Dollar" },
  { code: "GBP", sym: "£", label: "Pound" },
];

export default function Register() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { signUp } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [currency, setCurrency] = useState<"EUR" | "USD" | "GBP">("EUR");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setErr(null);
    if (!name || !email || !password) {
      setErr("Please fill in all fields.");
      return;
    }
    if (password.length < 6) {
      setErr("Password must be at least 6 characters.");
      return;
    }
    setLoading(true);
    try {
      await signUp(email.trim(), password, name.trim(), currency);
      router.replace("/(tabs)");
    } catch (e: any) {
      setErr(e.message || "Could not register.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      style={styles.flex}
      testID="register-screen"
    >
      <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
        <ScrollView
          contentContainerStyle={[styles.scroll, { paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xxl }]}
          keyboardShouldPersistTaps="handled"
        >
          <Pressable onPress={() => router.back()} style={styles.back} testID="register-back">
            <Feather name="arrow-left" size={22} color={colors.onSurface} />
          </Pressable>

          <Text style={styles.h1}>Create your account.</Text>
          <Text style={styles.sub}>Set up Éva in seconds.</Text>

          <View style={styles.form}>
            <Field label="Name" value={name} onChangeText={setName} placeholder="Jane" testID="register-name" />
            <Field
              label="Email" value={email} onChangeText={setEmail} autoCapitalize="none"
              autoComplete="email" keyboardType="email-address" placeholder="you@example.com" testID="register-email"
            />
            <Field
              label="Password" value={password} onChangeText={setPassword}
              secureTextEntry placeholder="At least 6 characters" testID="register-password"
            />

            <View>
              <Text style={styles.label}>Currency</Text>
              <View style={styles.ccyRow}>
                {CURRENCIES.map((c) => {
                  const active = currency === c.code;
                  return (
                    <Pressable
                      key={c.code}
                      onPress={() => setCurrency(c.code)}
                      style={[styles.ccyChip, active && styles.ccyChipActive]}
                      testID={`register-ccy-${c.code}`}
                    >
                      <Text style={[styles.ccySym, active && styles.ccyActiveText]}>{c.sym}</Text>
                      <Text style={[styles.ccyLabel, active && styles.ccyActiveText]}>{c.code}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>

            {err ? <Text style={styles.err} testID="register-error">{err}</Text> : null}
            <Button title="Create account" onPress={submit} loading={loading} testID="register-submit" />
            <Pressable onPress={() => router.replace("/(auth)/login")} style={styles.linkRow} testID="register-go-login">
              <Text style={styles.linkText}>Already have an account? <Text style={styles.linkAccent}>Sign in</Text></Text>
            </Pressable>
          </View>
        </ScrollView>
      </TouchableWithoutFeedback>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.surface },
  scroll: { paddingHorizontal: spacing.xl, gap: spacing.lg },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center", marginLeft: -spacing.md, marginBottom: spacing.md },
  h1: { fontFamily: fonts.display, fontSize: 34, color: colors.onSurface, lineHeight: 40 },
  sub: { fontFamily: fonts.body, fontSize: type.lg, color: colors.onSurfaceSecondary, marginBottom: spacing.lg },
  form: { gap: spacing.lg },
  err: { fontFamily: fonts.body, color: colors.error, fontSize: type.base },
  label: {
    fontFamily: fonts.bodyMedium, fontSize: type.sm,
    color: colors.onSurfaceSecondary, marginBottom: spacing.sm,
    letterSpacing: 0.4, textTransform: "uppercase",
  },
  ccyRow: { flexDirection: "row", gap: spacing.sm },
  ccyChip: {
    flex: 1, height: 64, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1,
    borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  ccyChipActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  ccySym: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.onSurface },
  ccyLabel: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary },
  ccyActiveText: { color: colors.onSurfaceInverse },
  linkRow: { alignSelf: "center", paddingVertical: spacing.md },
  linkText: { fontFamily: fonts.body, color: colors.onSurfaceSecondary, fontSize: type.base },
  linkAccent: { color: colors.brand, fontFamily: fonts.bodyMedium },
});
