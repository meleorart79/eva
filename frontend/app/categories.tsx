import React, { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";

import { api, Category } from "@/src/api";
import Button from "@/src/components/Button";
import { colors, fonts, radius, spacing, type } from "@/src/theme";

export default function Categories() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<Category[]>([]);

  const load = useCallback(async () => setItems(await api.categories()), []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const update = (id: string, patch: Partial<Category>) =>
    setItems((prev) => prev.map((c) => (c.id === id ? { ...c, ...patch } : c)));

  const save = async (c: Category) => {
    await api.updateCategory(c.id, {
      name: c.name, icon: c.icon, tax_rate: c.tax_rate,
      merchant_keywords: c.merchant_keywords ?? [],
      rep_increment: c.rep_increment ?? 0.05,
      max_tax_rate: c.max_tax_rate ?? 0.50,
      daily_cap_amount: c.daily_cap_amount ?? 10.0,
    });
  };

  const remove = async (id: string) => {
    await api.deleteCategory(id);
    setItems((p) => p.filter((c) => c.id !== id));
  };

  const addNew = async () => {
    const created = await api.createCategory({
      name: "New category", icon: "tag", tax_rate: 0.1,
      merchant_keywords: [], rep_increment: 0.05,
      max_tax_rate: 0.50, daily_cap_amount: 10.0,
    });
    setItems((p) => [...p, created]);
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1, backgroundColor: colors.surface }} testID="categories-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} testID="categories-close">
          <Feather name="x" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Categories</Text>
        <Pressable onPress={addNew} style={styles.iconBtn} testID="categories-add">
          <Feather name="plus" size={22} color={colors.onSurface} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: insets.bottom + 80, gap: spacing.md }}>
        <Text style={styles.helper}>Set how much "tax" each category contributes to your savings. Tap a row to edit.</Text>
        {items.map((c) => (
          <View key={c.id} style={styles.row} testID={`cat-${c.id}`}>
            <TextInput
              value={c.name}
              onChangeText={(v) => update(c.id, { name: v })}
              onEndEditing={() => save(c)}
              style={styles.nameInput}
              testID={`cat-name-${c.id}`}
            />
            <View style={styles.rateRow}>
              <Text style={styles.rateLabel}>Tax %</Text>
              <TextInput
                value={String(Math.round(c.tax_rate * 100))}
                onChangeText={(v) => {
                  const n = Math.max(0, Math.min(100, parseInt(v || "0", 10) || 0));
                  update(c.id, { tax_rate: n / 100 });
                }}
                onEndEditing={() => save(c)}
                keyboardType="number-pad"
                style={styles.rateInput}
                testID={`cat-rate-${c.id}`}
              />
              <Pressable onPress={() => remove(c.id)} style={styles.delete} testID={`cat-delete-${c.id}`}>
                <Feather name="trash-2" size={18} color={colors.error} />
              </Pressable>
            </View>
            {c.merchant_keywords && c.merchant_keywords.length > 0 ? (
              <View style={styles.kwRow}>
                {c.merchant_keywords.map((kw) => (
                  <View key={kw} style={styles.kwChip} testID={`cat-kw-${c.id}-${kw}`}>
                    <Text style={styles.kwText}>{kw}</Text>
                  </View>
                ))}
              </View>
            ) : (
              <Text style={styles.kwEmpty}>No merchant keywords · this category never auto-matches.</Text>
            )}
          </View>
        ))}

        <Button title="Add category" variant="secondary" onPress={addNew} testID="categories-add-bottom" />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary },
  title: { fontFamily: fonts.display, fontSize: type.xl, color: colors.onSurface },
  helper: { fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary, marginBottom: spacing.sm },
  row: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border, gap: spacing.sm },
  nameInput: { fontFamily: fonts.bodyMedium, fontSize: type.lg, color: colors.onSurface, paddingVertical: spacing.xs },
  rateRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  rateLabel: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary },
  rateInput: { flex: 1, height: 40, backgroundColor: colors.surface, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, fontFamily: fonts.bodyMedium, fontSize: type.base, color: colors.onSurface },
  delete: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  kwRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, marginTop: spacing.xs },
  kwChip: { paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  kwText: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary },
  kwEmpty: { fontFamily: fonts.body, fontSize: type.sm, color: colors.muted, fontStyle: "italic", marginTop: spacing.xs },
});
