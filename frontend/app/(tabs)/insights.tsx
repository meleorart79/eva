import React, { useCallback, useMemo, useState } from "react";
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, Pressable } from "react-native";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Summary } from "@/src/api";
import { useAuth } from "@/src/auth";
import { colors, fonts, fmt, radius, spacing, type } from "@/src/theme";

export default function Insights() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const ccy = user?.currency || "EUR";

  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [years, setYears] = useState(20);
  const [rate, setRate] = useState(7);

  const load = useCallback(async () => {
    try {
      setSummary(await api.summary());
    } finally {
      setLoading(false);
    }
  }, []);
  useFocusEffect(useCallback(() => { setLoading(true); load(); }, [load]));

  // Compute annualized contribution from the last 7 days extrapolated.
  const annualTaxed = useMemo(() => {
    if (!summary) return 0;
    const weekly = summary.by_day.reduce((sum, d) => sum + d.taxed, 0);
    // If no week data, use total / period heuristic (just total*52 as floor).
    return weekly > 0 ? weekly * 52 : summary.total_taxed * 52;
  }, [summary]);

  const futureValue = useMemo(() => {
    // FV of annuity: PMT * (((1 + r)^n - 1) / r), PMT = annualTaxed.
    const r = rate / 100;
    if (annualTaxed <= 0) return 0;
    if (r === 0) return annualTaxed * years;
    return annualTaxed * ((Math.pow(1 + r, years) - 1) / r);
  }, [annualTaxed, years, rate]);

  const maxDay = useMemo(() => {
    if (!summary || summary.by_day.length === 0) return 1;
    return Math.max(...summary.by_day.map((d) => d.spent), 1);
  }, [summary]);

  const topCats = summary?.by_category.slice(0, 5) ?? [];

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface }}
      contentContainerStyle={{
        paddingTop: insets.top + spacing.lg,
        paddingHorizontal: spacing.xl,
        paddingBottom: insets.bottom + 120,
        gap: spacing.lg,
      }}
      testID="insights-screen"
    >
      <Text style={styles.h1}>Your habits, made visible.</Text>

      {loading ? (
        <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.xxl }} />
      ) : (
        <>
          <View style={styles.card}>
            <Text style={styles.cardLabel}>This week</Text>
            <View style={styles.barRow}>
              {summary?.by_day.length === 0 ? (
                <Text style={styles.emptyMsg}>Log expenses to see your weekly trend.</Text>
              ) : (
                summary?.by_day.map((d) => (
                  <View key={d.date} style={styles.barCol}>
                    <View style={[styles.bar, { height: Math.max(4, (d.spent / maxDay) * 110) }]} />
                    <Text style={styles.barLabel}>{d.date.slice(5)}</Text>
                  </View>
                ))
              )}
            </View>
          </View>

          <View style={styles.card}>
            <Text style={styles.cardLabel}>Future value</Text>
            <Text style={styles.fvAmount} testID="future-value-amount">{fmt(futureValue, ccy)}</Text>
            <Text style={styles.fvCaption}>
              If you keep your current pace and invest the taxes at {rate}% for {years} years.
            </Text>

            <View style={styles.sliderBlock}>
              <View style={styles.sliderHead}>
                <Text style={styles.sliderLabel}>Years</Text>
                <Text style={styles.sliderVal}>{years}</Text>
              </View>
              <View style={styles.chipsRow}>
                {[5, 10, 20, 30, 40].map((y) => (
                  <Chip key={y} value={y} active={years === y} onPress={() => setYears(y)} testID={`years-${y}`} />
                ))}
              </View>
            </View>
            <View style={styles.sliderBlock}>
              <View style={styles.sliderHead}>
                <Text style={styles.sliderLabel}>Interest rate</Text>
                <Text style={styles.sliderVal}>{rate}%</Text>
              </View>
              <View style={styles.chipsRow}>
                {[3, 5, 7, 9, 12].map((r) => (
                  <Chip key={r} value={`${r}%`} active={rate === r} onPress={() => setRate(r)} testID={`rate-${r}`} />
                ))}
              </View>
            </View>
          </View>

          <View style={styles.card}>
            <Text style={styles.cardLabel}>Top spending categories</Text>
            {topCats.length === 0 ? (
              <Text style={styles.emptyMsg}>No data yet.</Text>
            ) : (
              topCats.map((c) => (
                <View key={c.name} style={styles.catRow} testID={`cat-row-${c.name}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.catName}>{c.name}</Text>
                    <Text style={styles.catMeta}>{c.count} transactions · {fmt(c.taxed, ccy)} saved</Text>
                  </View>
                  <Text style={styles.catSpent}>{fmt(c.spent, ccy)}</Text>
                </View>
              ))
            )}
          </View>
        </>
      )}
    </ScrollView>
  );
}

// Local chip control (no slider lib used — keeps bundle small).
function Chip({ value, active, onPress, testID }: { value: number | string; active: boolean; onPress: () => void; testID?: string }) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={[chipStyles.chip, active && chipStyles.chipActive]}
    >
      <Text style={[chipStyles.chipText, active && chipStyles.chipTextActive]}>{value}</Text>
    </Pressable>
  );
}

const chipStyles = StyleSheet.create({
  chip: {
    height: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  chipActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  chipText: { fontFamily: fonts.bodyMedium, fontSize: type.base, color: colors.onSurface },
  chipTextActive: { color: colors.onSurfaceInverse },
});

const styles = StyleSheet.create({
  h1: { fontFamily: fonts.display, fontSize: 28, color: colors.onSurface, lineHeight: 34 },

  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, borderWidth: 1, borderColor: colors.border },
  cardLabel: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary, letterSpacing: 0.5, textTransform: "uppercase" },

  barRow: { flexDirection: "row", alignItems: "flex-end", gap: 6, height: 140 },
  barCol: { flex: 1, alignItems: "center", gap: 6 },
  bar: { width: "100%", backgroundColor: colors.brand, borderRadius: radius.sm },
  barLabel: { fontFamily: fonts.body, fontSize: 10, color: colors.onSurfaceSecondary },

  fvAmount: { fontFamily: fonts.displayBold, fontSize: 40, color: colors.onSurface, lineHeight: 44 },
  fvCaption: { fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary, lineHeight: 20 },

  sliderBlock: { gap: spacing.sm, marginTop: spacing.sm },
  sliderHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  sliderLabel: { fontFamily: fonts.bodyMedium, fontSize: type.base, color: colors.onSurfaceSecondary },
  sliderVal: { fontFamily: fonts.displayBold, fontSize: type.lg, color: colors.onSurface },
  chipsRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },

  catRow: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  catName: { fontFamily: fonts.bodyMedium, fontSize: type.lg, color: colors.onSurface },
  catMeta: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary, marginTop: 2 },
  catSpent: { fontFamily: fonts.bodyBold, fontSize: type.lg, color: colors.onSurface },

  emptyMsg: { fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary, padding: spacing.md },
});
