import React, { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";

import { colors, fonts, fmt, radius, spacing, type } from "@/src/theme";
import { useAuth } from "@/src/auth";
import { api, ActivityRow, Bucket, LinkedAccount, Summary } from "@/src/api";

const PROVIDER_LABEL: Record<string, string> = {
  revolut: "Revolut",
  spuerkeess: "Spuerkeess",
};

export default function Dashboard() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const ccy = user?.currency || "EUR";

  const [summary, setSummary] = useState<Summary | null>(null);
  const [buckets, setBuckets] = useState<Bucket[]>([]);
  const [accounts, setAccounts] = useState<LinkedAccount[]>([]);
  const [activity, setActivity] = useState<ActivityRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [now, setNow] = useState<number>(Date.now());

  const load = useCallback(async () => {
    try {
      const [s, b, a, act] = await Promise.all([
        api.summary(),
        api.buckets(),
        api.listAccounts(),
        api.activity(20),
      ]);
      setSummary(s);
      setBuckets(b);
      setAccounts(a);
      setActivity(act);
    } catch {
      // ignore
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    setLoading(true);
    load();
    const t = setInterval(() => setNow(Date.now()), 15_000);
    return () => clearInterval(t);
  }, [load]));

  const defaultBucket = buckets.find((b) => b.is_default) || buckets[0];

  const sync = async () => {
    setSyncing(true);
    setSyncMsg(null);
    try {
      const sres = await api.syncBank();
      const pres = await api.processTax();
      setSyncMsg(
        `Pulled ${sres.ingested} new · taxed ${pres.taxed} · skipped ${pres.skipped} · unmatched ${pres.unmatched}`
      );
      await load();
    } catch (e: any) {
      setSyncMsg(e.message || "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const override = async (eventId: string) => {
    try {
      await api.overrideTax(eventId);
      await load();
    } catch {
      // ignore
    }
  };

  const minutesLeft = (createdAt?: string | null) => {
    if (!createdAt) return 0;
    const created = new Date(createdAt).getTime();
    const elapsedMs = now - created;
    return Math.max(0, Math.ceil((10 * 60 * 1000 - elapsedMs) / 60000));
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="dashboard-screen">
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + 100 },
        ]}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => { setRefreshing(true); load(); }}
            tintColor={colors.brand}
          />
        }
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
          <View style={styles.loadingBox}>
            <ActivityIndicator color={colors.brand} />
          </View>
        ) : (
          <>
            <View style={styles.heroCard} testID="hero-saved">
              <Text style={styles.heroLabel}>Total auto-saved</Text>
              <Text style={styles.heroAmount}>{fmt(summary?.total_taxed ?? 0, ccy)}</Text>
              <View style={styles.heroRow}>
                <View style={styles.heroMini}>
                  <Text style={styles.heroMiniLabel}>Spent</Text>
                  <Text style={styles.heroMiniVal}>{fmt(summary?.total_spent ?? 0, ccy)}</Text>
                </View>
                <View style={styles.heroDivider} />
                <View style={styles.heroMini}>
                  <Text style={styles.heroMiniLabel}>Taxed</Text>
                  <Text style={styles.heroMiniVal} testID="taxed-count">{summary?.transactions ?? 0}</Text>
                </View>
                <View style={styles.heroDivider} />
                <View style={styles.heroMini}>
                  <Text style={styles.heroMiniLabel}>Streak</Text>
                  <Text style={styles.heroMiniVal}>{summary?.streak_days_no_impulse ?? 0}d</Text>
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
                    style={[
                      styles.progressFg,
                      {
                        width: `${Math.min(
                          100,
                          defaultBucket.target_amount
                            ? (defaultBucket.saved_amount / defaultBucket.target_amount) * 100
                            : 0,
                        )}%`,
                      },
                    ]}
                  />
                </View>
                <View style={styles.bucketRow}>
                  <Text style={styles.bucketSaved}>{fmt(defaultBucket.saved_amount, ccy)}</Text>
                  <Text style={styles.bucketTarget}>of {fmt(defaultBucket.target_amount, ccy)}</Text>
                </View>
              </View>
            ) : null}

            {accounts.length === 0 ? (
              <Pressable
                onPress={() => router.push("/link-bank")}
                style={styles.connectCard}
                testID="connect-bank-card"
              >
                <View style={styles.connectIcon}>
                  <Feather name="link" size={20} color={colors.onSurfaceInverse} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.connectTitle}>Connect your bank</Text>
                  <Text style={styles.connectSub}>
                    Éva reads transactions automatically — you'll never log a purchase by hand.
                  </Text>
                </View>
                <Feather name="chevron-right" size={20} color={colors.onSurface} />
              </Pressable>
            ) : (
              <View style={styles.bankStatus} testID="bank-status-card">
                <View style={styles.bankRow}>
                  <View style={styles.bankIcon}>
                    <Feather name="check-circle" size={18} color={colors.brand} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.bankName}>
                      {accounts.map((a) => PROVIDER_LABEL[a.provider] ?? a.provider).join(" · ")}
                    </Text>
                    <Text style={styles.bankSub}>Linked · auto-sync ready</Text>
                  </View>
                  <Pressable
                    onPress={sync}
                    disabled={syncing}
                    style={[styles.syncBtn, syncing && { opacity: 0.6 }]}
                    testID="sync-now"
                  >
                    {syncing ? (
                      <ActivityIndicator color={colors.onSurfaceInverse} size="small" />
                    ) : (
                      <Text style={styles.syncBtnText}>Sync now</Text>
                    )}
                  </Pressable>
                </View>
                {syncMsg ? <Text style={styles.syncMsg} testID="sync-msg">{syncMsg}</Text> : null}
              </View>
            )}

            <View style={styles.sectionRow}>
              <Text style={styles.sectionTitle}>Activity</Text>
              <Pressable onPress={() => router.push("/categories")} testID="manage-categories">
                <Text style={styles.sectionLink}>Categories</Text>
              </Pressable>
            </View>

            {activity.length === 0 ? (
              <View style={styles.empty} testID="empty-activity">
                <Feather name="feather" size={26} color={colors.muted} />
                <Text style={styles.emptyTitle}>
                  {accounts.length === 0 ? "No activity yet" : "Sync to fetch transactions"}
                </Text>
                <Text style={styles.emptySub}>
                  {accounts.length === 0
                    ? "Connect your bank to start auto-saving."
                    : "Tap 'Sync now' above to pull transactions and apply the behavior tax."}
                </Text>
              </View>
            ) : (
              activity.map((a) => {
                const mins = minutesLeft(a.created_at);
                const showOverride = a.can_override && mins > 0 && !!a.tax_event_id;
                const statusStyle = styles[`status_${a.status}` as keyof typeof styles] as any;
                return (
                  <View key={a.raw_txn_id} style={styles.actRow} testID={`act-${a.raw_txn_id}`}>
                    <View style={styles.actIcon}>
                      <Feather
                        name={
                          a.status === "saved" ? "trending-up" :
                          a.status === "overridden" ? "shield" :
                          a.status === "skipped" ? "slash" : "circle"
                        }
                        size={16}
                        color={colors.onSurface}
                      />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.actMerchant} numberOfLines={1}>{a.merchant_name}</Text>
                      <Text style={styles.actMeta}>
                        {a.category_name ?? "Unmatched"}
                        {a.repetition_number > 1 ? ` · repeat #${a.repetition_number}` : ""}
                        {a.tax_rate_applied > 0 ? ` · ${Math.round(a.tax_rate_applied * 100)}%` : ""}
                      </Text>
                      <View style={[styles.statusBadge, statusStyle]} testID={`act-status-${a.raw_txn_id}`}>
                        <Text style={styles.statusBadgeText}>
                          {a.status === "saved" ? "Saved" :
                            a.status === "overridden" ? "Overridden" :
                            a.status === "skipped" ? "Skipped — cap reached" :
                            a.status === "unmatched" ? "Unmatched" : "Pending"}
                        </Text>
                      </View>
                    </View>
                    <View style={{ alignItems: "flex-end", gap: spacing.xs }}>
                      <Text style={styles.actAmount}>-{fmt(a.amount, ccy)}</Text>
                      {a.tax_amount > 0 ? (
                        <Text
                          style={[
                            styles.actTax,
                            a.status === "overridden" && { color: colors.muted, textDecorationLine: "line-through" },
                          ]}
                        >
                          +{fmt(a.tax_amount, ccy)} saved
                        </Text>
                      ) : null}
                      {showOverride ? (
                        <Pressable
                          onPress={() => override(a.tax_event_id!)}
                          style={styles.overrideBtn}
                          testID={`override-${a.tax_event_id}`}
                        >
                          <Text style={styles.overrideText}>Override · {mins}m</Text>
                        </Pressable>
                      ) : null}
                    </View>
                  </View>
                );
              })
            )}
          </>
        )}
      </ScrollView>
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

  connectCard: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceInverse, padding: spacing.lg,
    borderRadius: radius.lg,
  },
  connectIcon: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: "rgba(247,245,242,0.18)", alignItems: "center", justifyContent: "center" },
  connectTitle: { fontFamily: fonts.displayBold, fontSize: type.lg, color: colors.onSurfaceInverse },
  connectSub: { fontFamily: fonts.body, fontSize: type.sm, color: "rgba(247,245,242,0.75)", marginTop: 2, lineHeight: 18 },

  bankStatus: { backgroundColor: colors.surfaceSecondary, padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, gap: spacing.sm },
  bankRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  bankIcon: { width: 36, height: 36, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  bankName: { fontFamily: fonts.bodyBold, fontSize: type.lg, color: colors.onSurface },
  bankSub: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary, marginTop: 2 },
  syncBtn: { paddingHorizontal: spacing.md, height: 36, borderRadius: radius.pill, backgroundColor: colors.surfaceInverse, alignItems: "center", justifyContent: "center", minWidth: 80 },
  syncBtnText: { fontFamily: fonts.bodyMedium, fontSize: type.base, color: colors.onSurfaceInverse },
  syncMsg: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary },

  sectionRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: spacing.sm },
  sectionTitle: { fontFamily: fonts.display, fontSize: type.xl, color: colors.onSurface },
  sectionLink: { fontFamily: fonts.bodyMedium, fontSize: type.base, color: colors.brand },

  empty: { padding: spacing.xxl, alignItems: "center", borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, borderStyle: "dashed", backgroundColor: colors.surfaceSecondary, gap: spacing.sm },
  emptyTitle: { fontFamily: fonts.display, fontSize: type.xl, color: colors.onSurface },
  emptySub: { fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary, textAlign: "center" },

  actRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  actIcon: { width: 40, height: 40, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  actMerchant: { fontFamily: fonts.bodyMedium, fontSize: type.lg, color: colors.onSurface },
  actMeta: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary, marginTop: 2 },
  actAmount: { fontFamily: fonts.bodyBold, fontSize: type.lg, color: colors.onSurface },
  actTax: { fontFamily: fonts.body, fontSize: type.sm, color: colors.success },

  statusBadge: { alignSelf: "flex-start", paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.pill, marginTop: 4 },
  statusBadgeText: { fontFamily: fonts.bodyMedium, fontSize: 11, color: colors.onSurface, letterSpacing: 0.3 },
  status_saved: { backgroundColor: colors.brandTertiary },
  status_skipped: { backgroundColor: "#F2E2C9" },
  status_overridden: { backgroundColor: colors.surfaceTertiary },
  status_unmatched: { backgroundColor: colors.surfaceTertiary },
  status_pending: { backgroundColor: colors.surfaceTertiary },

  overrideBtn: { paddingHorizontal: spacing.md, height: 30, borderRadius: radius.pill, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center" },
  overrideText: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurface },
});
