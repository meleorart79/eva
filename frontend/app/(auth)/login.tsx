import React, { useState } from "react";
import {
  View, Text, StyleSheet, KeyboardAvoidingView, Platform,
  ScrollView, Pressable, TouchableWithoutFeedback, Keyboard,
} from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";

import { colors, fonts, spacing, type } from "@/src/theme";
import Button from "@/src/components/Button";
import Field from "@/src/components/Field";
import { useAuth } from "@/src/auth";

export default function Login() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setErr(null);
    if (!email || !password) {
      setErr("Email and password are required.");
      return;
    }
    setLoading(true);
    try {
      await signIn(email.trim(), password);
      router.replace("/(tabs)");
    } catch (e: any) {
      setErr(e.message || "Could not sign in.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      style={styles.flex}
      testID="login-screen"
    >
      <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
        <ScrollView
          contentContainerStyle={[styles.scroll, { paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xxl }]}
          keyboardShouldPersistTaps="handled"
        >
          <Pressable onPress={() => router.back()} style={styles.back} testID="login-back">
            <Feather name="arrow-left" size={22} color={colors.onSurface} />
          </Pressable>

          <Text style={styles.h1}>Welcome back.</Text>
          <Text style={styles.sub}>Sign in to keep growing your savings.</Text>

          <View style={styles.form}>
            <Field
              label="Email"
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
              placeholder="you@example.com"
              testID="login-email"
            />
            <Field
              label="Password"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              placeholder="••••••••"
              testID="login-password"
            />
            {err ? <Text style={styles.err} testID="login-error">{err}</Text> : null}
            <Button title="Sign in" onPress={submit} loading={loading} testID="login-submit" />
            <Pressable onPress={() => router.replace("/(auth)/register")} style={styles.linkRow} testID="login-go-register">
              <Text style={styles.linkText}>New to Éva? <Text style={styles.linkAccent}>Create an account</Text></Text>
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
  linkRow: { alignSelf: "center", paddingVertical: spacing.md },
  linkText: { fontFamily: fonts.body, color: colors.onSurfaceSecondary, fontSize: type.base },
  linkAccent: { color: colors.brand, fontFamily: fonts.bodyMedium },
});
