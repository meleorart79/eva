import React, { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";

import { colors, fonts, fmt, radius, spacing, type } from "@/src/theme";
import { useAuth } from "@/src/auth";
import { api, Bucket, Summary, Transaction } from "@/src/api";

export default function Dashboard() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const ccy = user?.currency || "EUR";

  const [summary, setSummary] = useState<Summary | null>(null);
  const [buckets, setBuckets] = useState<Bucket[]>([]);
  const [txs, setTxs] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, b, t] = await Promise.all([api.summary(), api.buckets(), api.transactions(8)]);
      setSummary(s);
      setBuckets(b);
      setTxs(t);
    } catch {
      // ignore here, retry on next focus
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    setLoading(true);
    load();
  }, [load]));

  const defaultBucket = buckets.find((b) => b.is_default) || buckets[0];

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="dashboard-screen">
      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + 120 }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.brand} />}
      >
        <View style={styles.header}>
          <View>
            <Text style={styles.greet}>Hello,</Text>
            <Text style={styles.name} testID="greeting-name">{user?.name ?? ""}</Text>
          </View>
          <Pressable onPress={() => router.push("/(tabs)/profile")} style={styles.avatar} testID="profile-avatar">
            <Text style={styles.avatarText}>{(user?.name ?? "?")[0]?.toUpperCase()}</Text>
          </Pressable>
        </View>

        {loading ? (
          <View style={styles.loadingBox}><ActivityIndicator color={colors.brand} /></View>
        ) : (
          <>
            <View style={styles.heroCard} testID="hero-saved">
              <Text style={styles.heroLabel}>Total saved via tax</Text>
              <Text style={styles.heroAmount}>{fmt(summary?.total_taxed ?? 0, ccy)}</Text>
              <View style={styles.heroRow}>
                <View style={styles.heroMini}>
                  <Text style={styles.heroMiniLabel}>Spent</Text>
                  <Text style={styles.heroMiniVal}>{fmt(summary?.total_spent ?? 0, ccy)}</Text>
                </View>
                <View style={styles.heroDivider} />
                <View style={styles.heroMini}>
                  <Text style={styles.heroMiniLabel}>Streak</Text>
                  <Text style={styles.heroMiniVal} testID="streak-days">{summary?.streak_days_no_impulse ?? 0}d</Text>
                </View>
                <View style={styles.heroDivider} />
                <View style={styles.heroMini}>
                  <Text style={styles.heroMiniLabel}>Logs</Text>
                  <Text style={styles.heroMiniVal}>{summary?.transactions ?? 0}</Text>
                </View>
              </View>
            </View>

            {defaultBucket ? (
              <View style={styles.bucketCard} testID="active-bucket-card">
                <View style={styles.bucketHeader}>
                  <View>
                    <Text style={styles.bucketLabel}>ACTIVE GOAL</Text>
                    <Text style={styles.bucketName}>{defaultBucket.name}</Text>
                  </View>
                  <Pressable onPress={() => router.push("/(tabs)/buckets")} testID="bucket-card-link">
                    <Feather name="arrow-up-right" size={20} color={colors.onSurface} />
                  </Pressable>
                </View>
                <View style={styles.progressBg}>
                  <View
                    style={[styles.progressFg, {
                      width: `${Math.min(100, defaultBucket.target_amount ? (defaultBucket.saved_amount / defaultBucket.target_amount) * 100 : 0)}%`,
                    }]}
                  />
                </View>
                <View style={styles.bucketRow}>
                  <Text style={styles.bucketSaved}>{fmt(defaultBucket.saved_amount, ccy)}</Text>
                  <Text style={styles.bucketTarget}>of {fmt(defaultBucket.target_amount, ccy)}</Text>
                </View>
              </View>
            ) : null}

            <View style={styles.sectionRow}>
              <Text style={styles.sectionTitle}>Recent transactions</Text>
              <Pressable onPress={() => router.push("/categories")} testID="manage-categories">
                <Text style={styles.sectionLink}>Categories</Text>
              </Pressable>
            </View>

            {txs.length === 0 ? (
              <View style={styles.empty} testID="empty-transactions">
                <Feather name="feather" size={26} color={colors.muted} />
                <Text style={styles.emptyTitle}>Log your first expense</Text>
                <Text style={styles.emptySub}>Tap the + button below to begin growing your savings.</Text>
              </View>
            ) : (
              txs.map((t) => (
                <View key={t.id} style={styles.txRow} testID={`tx-${t.id}`}>
                  <View style={styles.txIcon}>
                    <Feather name="shopping-bag" size={16} color={colors.onSurface} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.txMerchant} numberOfLines={1}>{t.merchant}</Text>
                    <Text style={styles.txMeta}>{t.category_name} · {Math.round(t.tax_rate * 100)}% tax</Text>
                  </View>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={styles.txAmount}>-{fmt(t.amount, ccy)}</Text>
                    <Text style={styles.txTax}>+{fmt(t.tax_amount, ccy)} saved</Text>
                  </View>
                </View>
              ))
            )}
          </>
        )}
      </ScrollView>

      <Pressable
        onPress={() => router.push("/add-transaction")}
        style={[styles.fab, { bottom: insets.bottom + 84 }]}
        testID="fab-add-transaction"
      >
        <Feather name="plus" size={26} color={colors.onSurfaceInverse} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: spacing.xl, gap: spacing.lg },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  greet: { fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary },
  name: { fontFamily: fonts.display, fontSize: 28, color: colors.onSurface, lineHeight: 32 },
  avatar: { width: 44, height: 44, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  avatarText: { fontFamily: fonts.displayBold, fontSize: type.lg, color: colors.onSurface },
  loadingBox: { padding: spacing.xxl, alignItems: "center" },

  heroCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.xl, gap: spacing.md },
  heroLabel: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary, letterSpacing: 0.4, textTransform: "uppercase" },
  heroAmount: { fontFamily: fonts.displayBold, fontSize: 44, color: colors.onSurface, lineHeight: 50 },
  heroRow: { flexDirection: "row", alignItems: "center", marginTop: spacing.sm },
  heroMini: { flex: 1 },
  heroMiniLabel: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary },
  heroMiniVal: { fontFamily: fonts.bodyBold, fontSize: type.lg, color: colors.onSurface, marginTop: 2 },
  heroDivider: { width: 1, height: 28, backgroundColor: colors.borderStrong, marginHorizontal: spacing.md, opacity: 0.5 },

  bucketCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, gap: spacing.md },
  bucketHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  bucketLabel: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary, letterSpacing: 0.6, textTransform: "uppercase" },
  bucketName: { fontFamily: fonts.display, fontSize: type.xl, color: colors.onSurface },
  progressBg: { height: 8, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary, overflow: "hidden" },
  progressFg: { height: "100%", backgroundColor: colors.brand },
  bucketRow: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between" },
  bucketSaved: { fontFamily: fonts.displayBold, fontSize: type.xl, color: colors.onSurface },
  bucketTarget: { fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary },

  sectionRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: spacing.sm },
  sectionTitle: { fontFamily: fonts.display, fontSize: type.xl, color: colors.onSurface },
  sectionLink: { fontFamily: fonts.bodyMedium, fontSize: type.base, color: colors.brand },

  empty: { padding: spacing.xxl, alignItems: "center", borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, borderStyle: "dashed", backgroundColor: colors.surfaceSecondary, gap: spacing.sm },
  emptyTitle: { fontFamily: fonts.display, fontSize: type.xl, color: colors.onSurface },
  emptySub: { fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary, textAlign: "center" },

  txRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  txIcon: { width: 40, height: 40, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  txMerchant: { fontFamily: fonts.bodyMedium, fontSize: type.lg, color: colors.onSurface },
  txMeta: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary, marginTop: 2 },
  txAmount: { fontFamily: fonts.bodyBold, fontSize: type.lg, color: colors.onSurface },
  txTax: { fontFamily: fonts.body, fontSize: type.sm, color: colors.success, marginTop: 2 },

  fab: {
    position: "absolute", right: spacing.xl, width: 60, height: 60, borderRadius: radius.pill,
    backgroundColor: colors.surfaceInverse, alignItems: "center", justifyContent: "center",
    shadowColor: "#000", shadowOpacity: 0.18, shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 6,
  },
});
