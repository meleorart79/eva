import React, { useCallback, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, KeyboardAvoidingView,
  Platform, TextInput, ActivityIndicator, TouchableWithoutFeedback, Keyboard,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";

import { api, Bucket, Category } from "@/src/api";
import { useAuth } from "@/src/auth";
import Button from "@/src/components/Button";
import { colors, fonts, fmt, radius, spacing, type } from "@/src/theme";

export default function AddTransaction() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const ccy = user?.currency || "EUR";

  const [cats, setCats] = useState<Category[]>([]);
  const [buckets, setBuckets] = useState<Bucket[]>([]);
  const [merchant, setMerchant] = useState("");
  const [amount, setAmount] = useState("");
  const [catId, setCatId] = useState<string | null>(null);
  const [bucketId, setBucketId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useFocusEffect(useCallback(() => {
    (async () => {
      const [c, b] = await Promise.all([api.categories(), api.buckets()]);
      setCats(c);
      setBuckets(b);
      if (c.length && !catId) setCatId(c[0].id);
      const def = b.find((x) => x.is_default) || b[0];
      if (def && !bucketId) setBucketId(def.id);
    })();
  }, []));

  const amt = parseFloat(amount.replace(",", ".")) || 0;
  const selectedCat = useMemo(() => cats.find((c) => c.id === catId), [cats, catId]);
  const selectedBucket = useMemo(() => buckets.find((b) => b.id === bucketId), [buckets, bucketId]);
  const taxRate = selectedCat?.tax_rate ?? 0;
  const taxAmount = Math.round(amt * taxRate * 100) / 100;
  const remainingToGoal = selectedBucket
    ? Math.max(0, selectedBucket.target_amount - selectedBucket.saved_amount - taxAmount)
    : 0;
  const newPct = selectedBucket && selectedBucket.target_amount
    ? Math.min(100, ((selectedBucket.saved_amount + taxAmount) / selectedBucket.target_amount) * 100)
    : 0;

  const submit = async () => {
    setErr(null);
    if (!merchant.trim() || !catId || amt <= 0) {
      setErr("Add a merchant, an amount and a category.");
      return;
    }
    setSaving(true);
    try {
      await api.createTransaction({
        merchant: merchant.trim(), amount: amt, category_id: catId,
        bucket_id: bucketId || undefined,
      });
      router.back();
    } catch (e: any) {
      setErr(e.message || "Could not save expense.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      style={{ flex: 1, backgroundColor: colors.surface }}
      testID="add-tx-screen"
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} testID="add-tx-close">
          <Feather name="x" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>New expense</Text>
        <View style={styles.iconBtn} />
      </View>

      <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
        <ScrollView
          contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: 160, gap: spacing.lg }}
          keyboardShouldPersistTaps="handled"
        >
          <View>
            <Text style={styles.label}>Amount</Text>
            <View style={styles.amountWrap}>
              <Text style={styles.amountSym}>{ccy === "USD" ? "$" : ccy === "GBP" ? "£" : "€"}</Text>
              <TextInput
                value={amount}
                onChangeText={setAmount}
                keyboardType="decimal-pad"
                placeholder="0.00"
                placeholderTextColor={colors.muted}
                style={styles.amountInput}
                testID="add-tx-amount"
              />
            </View>
          </View>

          <View>
            <Text style={styles.label}>Merchant</Text>
            <TextInput
              value={merchant}
              onChangeText={setMerchant}
              placeholder="e.g. Uber Eats"
              placeholderTextColor={colors.muted}
              style={styles.input}
              testID="add-tx-merchant"
            />
          </View>

          <View>
            <Text style={styles.label}>Category</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipsRow}>
              {cats.map((c) => {
                const active = catId === c.id;
                return (
                  <Pressable
                    key={c.id}
                    onPress={() => setCatId(c.id)}
                    style={[styles.chip, active && styles.chipActive]}
                    testID={`add-tx-cat-${c.id}`}
                  >
                    <Text style={[styles.chipText, active && styles.chipTextActive]}>
                      {c.name} · {Math.round(c.tax_rate * 100)}%
                    </Text>
                  </Pressable>
                );
              })}
            </ScrollView>
          </View>

          <View>
            <Text style={styles.label}>Send tax to</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipsRow}>
              {buckets.map((b) => {
                const active = bucketId === b.id;
                return (
                  <Pressable
                    key={b.id}
                    onPress={() => setBucketId(b.id)}
                    style={[styles.chip, active && styles.chipActive]}
                    testID={`add-tx-bucket-${b.id}`}
                  >
                    <Text style={[styles.chipText, active && styles.chipTextActive]}>{b.name}</Text>
                  </Pressable>
                );
              })}
            </ScrollView>
          </View>

          <View style={styles.impactCard} testID="goal-impact-card">
            <Text style={styles.impactLabel}>Goal impact analysis</Text>
            <Text style={styles.impactMain}>+{fmt(taxAmount, ccy)}</Text>
            <Text style={styles.impactSub}>
              {selectedBucket
                ? `added to "${selectedBucket.name}" · ${remainingToGoal > 0 ? `${fmt(remainingToGoal, ccy)} left to reach goal` : "goal reached!"}`
                : "Create a goal to start saving."}
            </Text>
            <View style={styles.progressBg}>
              <View style={[styles.progressFg, { width: `${newPct}%` }]} />
            </View>
          </View>

          {err ? <Text style={styles.err} testID="add-tx-error">{err}</Text> : null}
        </ScrollView>
      </TouchableWithoutFeedback>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Button title="Save expense" onPress={submit} loading={saving} testID="add-tx-submit" />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary },
  title: { fontFamily: fonts.display, fontSize: type.xl, color: colors.onSurface },

  label: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary, letterSpacing: 0.5, textTransform: "uppercase", marginBottom: spacing.sm },
  input: { height: 52, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.lg, fontFamily: fonts.body, fontSize: type.lg, color: colors.onSurface },

  amountWrap: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, paddingHorizontal: spacing.lg, height: 90, borderWidth: 1, borderColor: colors.border },
  amountSym: { fontFamily: fonts.display, fontSize: 40, color: colors.onSurfaceSecondary, marginRight: spacing.sm },
  amountInput: { flex: 1, fontFamily: fonts.displayBold, fontSize: 44, color: colors.onSurface, paddingVertical: 0 },

  chipsRow: { gap: spacing.sm, paddingRight: spacing.lg },
  chip: { height: 40, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center", flexShrink: 0 },
  chipActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  chipText: { fontFamily: fonts.bodyMedium, fontSize: type.base, color: colors.onSurface },
  chipTextActive: { color: colors.onSurfaceInverse },

  impactCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  impactLabel: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary, letterSpacing: 0.5, textTransform: "uppercase" },
  impactMain: { fontFamily: fonts.displayBold, fontSize: 36, color: colors.onSurface, lineHeight: 40 },
  impactSub: { fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary, lineHeight: 20 },
  progressBg: { height: 8, borderRadius: radius.pill, backgroundColor: "rgba(40,38,36,0.12)", overflow: "hidden", marginTop: spacing.sm },
  progressFg: { height: "100%", backgroundColor: colors.brand },

  err: { fontFamily: fonts.body, color: colors.error, fontSize: type.base },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.xl, paddingTop: spacing.md, backgroundColor: colors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
});
