import React, { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { Feather } from "@expo/vector-icons";

import { api, Bucket } from "@/src/api";
import { useAuth } from "@/src/auth";
import { colors, fonts, fmt, radius, spacing, type } from "@/src/theme";
import { BUCKET_IMAGES } from "@/src/images";

export default function Buckets() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, refresh } = useAuth();
  const ccy = user?.currency || "EUR";

  const [items, setItems] = useState<Bucket[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const b = await api.buckets();
      setItems(b);
    } catch {
      // ignore
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { setLoading(true); load(); }, [load]));

  const setDefault = async (id: string) => {
    const b = items.find((x) => x.id === id);
    if (!b) return;
    await api.updateBucket(id, {
      name: b.name, target_amount: b.target_amount, image_key: b.image_key, is_default: true,
    });
    await Promise.all([refresh(), load()]);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="buckets-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.lg }]}>
        <Text style={styles.h1}>Savings goals</Text>
        <Pressable onPress={() => router.push("/bucket-new")} style={styles.addBtn} testID="buckets-add">
          <Feather name="plus" size={20} color={colors.onSurfaceInverse} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: insets.bottom + 120, gap: spacing.lg }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.brand} />}
      >
        {loading ? (
          <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.xxl }} />
        ) : items.length === 0 ? (
          <View style={styles.empty} testID="buckets-empty">
            <Feather name="target" size={28} color={colors.muted} />
            <Text style={styles.emptyTitle}>Create your first goal</Text>
            <Text style={styles.emptySub}>Your behavior tax will pour into the goal you mark as active.</Text>
          </View>
        ) : (
          items.map((b) => {
            const pct = b.target_amount ? Math.min(100, (b.saved_amount / b.target_amount) * 100) : 0;
            return (
              <View key={b.id} style={styles.card} testID={`bucket-${b.id}`}>
                <Image
                  source={{ uri: BUCKET_IMAGES[b.image_key] || BUCKET_IMAGES.custom }}
                  style={StyleSheet.absoluteFill}
                  contentFit="cover"
                />
                <LinearGradient
                  colors={["rgba(40,38,36,0.15)", "rgba(40,38,36,0.55)", "rgba(40,38,36,0.92)"]}
                  locations={[0, 0.5, 1]}
                  style={StyleSheet.absoluteFill}
                />
                <View style={styles.cardContent}>
                  <View style={styles.topRow}>
                    {b.is_default ? (
                      <View style={styles.activeBadge} testID={`bucket-active-${b.id}`}>
                        <Text style={styles.activeBadgeText}>Active</Text>
                      </View>
                    ) : (
                      <Pressable onPress={() => setDefault(b.id)} style={styles.setActive} testID={`bucket-set-active-${b.id}`}>
                        <Text style={styles.setActiveText}>Make active</Text>
                      </Pressable>
                    )}
                  </View>
                  <View style={{ gap: spacing.sm }}>
                    <Text style={styles.cardName}>{b.name}</Text>
                    <View style={styles.progressBg}>
                      <View style={[styles.progressFg, { width: `${pct}%` }]} />
                    </View>
                    <View style={styles.cardRow}>
                      <Text style={styles.cardSaved}>{fmt(b.saved_amount, ccy)}</Text>
                      <Text style={styles.cardTarget}>of {fmt(b.target_amount, ccy)}</Text>
                    </View>
                  </View>
                </View>
              </View>
            );
          })
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.xl, paddingBottom: spacing.lg },
  h1: { fontFamily: fonts.display, fontSize: 28, color: colors.onSurface },
  addBtn: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.surfaceInverse, alignItems: "center", justifyContent: "center" },

  empty: { padding: spacing.xxl, alignItems: "center", borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, borderStyle: "dashed", backgroundColor: colors.surfaceSecondary, gap: spacing.sm, marginTop: spacing.lg },
  emptyTitle: { fontFamily: fonts.display, fontSize: type.xl, color: colors.onSurface },
  emptySub: { fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary, textAlign: "center" },

  card: { height: 200, borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.surfaceTertiary },
  cardContent: { flex: 1, justifyContent: "space-between", padding: spacing.lg },
  topRow: { flexDirection: "row", justifyContent: "flex-end" },
  activeBadge: { paddingHorizontal: spacing.md, paddingVertical: 6, backgroundColor: colors.brand, borderRadius: radius.pill },
  activeBadgeText: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onBrand },
  setActive: { paddingHorizontal: spacing.md, paddingVertical: 6, backgroundColor: "rgba(247,245,242,0.18)", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(247,245,242,0.4)" },
  setActiveText: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceInverse },
  cardName: { fontFamily: fonts.displayBold, fontSize: 26, color: colors.onSurfaceInverse },
  progressBg: { height: 8, borderRadius: radius.pill, backgroundColor: "rgba(247,245,242,0.25)", overflow: "hidden" },
  progressFg: { height: "100%", backgroundColor: colors.onSurfaceInverse },
  cardRow: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between" },
  cardSaved: { fontFamily: fonts.displayBold, fontSize: type.xl, color: colors.onSurfaceInverse },
  cardTarget: { fontFamily: fonts.body, fontSize: type.base, color: "rgba(247,245,242,0.85)" },
});
