import React, { useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform,
  TouchableWithoutFeedback, Keyboard,
} from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";

import { api } from "@/src/api";
import Button from "@/src/components/Button";
import { colors, fonts, radius, spacing, type } from "@/src/theme";
import { BUCKET_LABELS } from "@/src/images";

export default function NewBucket() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [imageKey, setImageKey] = useState("travel");
  const [isDefault, setIsDefault] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setErr(null);
    const t = parseFloat(target.replace(",", "."));
    if (!name.trim() || !t || t <= 0) {
      setErr("Add a name and a positive target amount.");
      return;
    }
    setSaving(true);
    try {
      await api.createBucket({
        name: name.trim(), target_amount: t,
        image_key: imageKey, is_default: isDefault,
      });
      router.back();
    } catch (e: any) {
      setErr(e.message || "Could not create goal.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1, backgroundColor: colors.surface }} testID="bucket-new-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} testID="bucket-new-close">
          <Feather name="x" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>New goal</Text>
        <View style={styles.iconBtn} />
      </View>

      <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
        <ScrollView contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: insets.bottom + 120, gap: spacing.lg }}>
          <View>
            <Text style={styles.label}>Name</Text>
            <TextInput
              value={name} onChangeText={setName}
              placeholder="e.g. Japan trip" placeholderTextColor={colors.muted}
              style={styles.input} testID="bucket-name"
            />
          </View>

          <View>
            <Text style={styles.label}>Target amount</Text>
            <TextInput
              value={target} onChangeText={setTarget} keyboardType="decimal-pad"
              placeholder="2000" placeholderTextColor={colors.muted}
              style={styles.input} testID="bucket-target"
            />
          </View>

          <View>
            <Text style={styles.label}>Cover</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingRight: spacing.lg }}>
              {BUCKET_LABELS.map((b) => {
                const active = imageKey === b.key;
                return (
                  <Pressable
                    key={b.key} onPress={() => setImageKey(b.key)}
                    style={[styles.imgChip, active && styles.imgChipActive]}
                    testID={`bucket-img-${b.key}`}
                  >
                    <Text style={[styles.imgChipText, active && styles.imgChipTextActive]}>{b.label}</Text>
                  </Pressable>
                );
              })}
            </ScrollView>
          </View>

          <Pressable onPress={() => setIsDefault((v) => !v)} style={styles.toggleRow} testID="bucket-default-toggle">
            <View style={[styles.checkbox, isDefault && styles.checkboxActive]}>
              {isDefault ? <Feather name="check" size={14} color={colors.onSurfaceInverse} /> : null}
            </View>
            <Text style={styles.toggleText}>Make this my active goal (auto-receive tax)</Text>
          </Pressable>

          {err ? <Text style={styles.err} testID="bucket-error">{err}</Text> : null}
          <Button title="Create goal" onPress={submit} loading={saving} testID="bucket-submit" />
        </ScrollView>
      </TouchableWithoutFeedback>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary },
  title: { fontFamily: fonts.display, fontSize: type.xl, color: colors.onSurface },
  label: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary, letterSpacing: 0.5, textTransform: "uppercase", marginBottom: spacing.sm },
  input: { height: 52, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.lg, fontFamily: fonts.body, fontSize: type.lg, color: colors.onSurface },
  imgChip: { height: 40, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center", flexShrink: 0 },
  imgChipActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  imgChipText: { fontFamily: fonts.bodyMedium, fontSize: type.base, color: colors.onSurface },
  imgChipTextActive: { color: colors.onSurfaceInverse },
  toggleRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm },
  checkbox: { width: 24, height: 24, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center" },
  checkboxActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  toggleText: { flex: 1, fontFamily: fonts.body, fontSize: type.base, color: colors.onSurface },
  err: { fontFamily: fonts.body, color: colors.error, fontSize: type.base },
});
