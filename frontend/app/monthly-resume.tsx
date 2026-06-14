import React, { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, Share, Platform,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import * as WebBrowser from "expo-web-browser";

import { api, MonthlyReport } from "@/src/api";
import { useAuth } from "@/src/auth";
import { colors, fonts, fmt, radius, spacing, type } from "@/src/theme";

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function MonthlyResume() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const ccy = user?.currency || "EUR";

  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [report, setReport] = useState<MonthlyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [sharing, setSharing] = useState(false);

  const load = useCallback(async () => {
    try {
      setReport(await api.monthlyReport(year, month));
    } finally {
      setLoading(false);
    }
  }, [year, month]);

  useFocusEffect(useCallback(() => { setLoading(true); load(); }, [load]));

  const prev = () => {
    setLoading(true);
    if (month === 1) { setYear((y) => y - 1); setMonth(12); }
    else setMonth((m) => m - 1);
  };
  const next = () => {
    setLoading(true);
    if (month === 12) { setYear((y) => y + 1); setMonth(1); }
    else setMonth((m) => m + 1);
  };

  const exportCsv = async () => {
    setSharing(true);
    try {
      const url = api.monthlyReportCsvUrl(year, month);
      // On native Share API can't share remote URLs directly cross-platform; open in browser.
      if (Platform.OS === "web") {
        await WebBrowser.openBrowserAsync(url);
      } else {
        // Native: hand the URL to Share. The system share sheet lets the user open
        // or send the link to anyone (the URL renders the CSV with the download header).
        await Share.share({
          message: `Éva monthly resume — ${MONTH_NAMES[month - 1]} ${year}\n${url}`,
          url,
        });
      }
    } finally {
      setSharing(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="monthly-resume-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} testID="monthly-close">
          <Feather name="x" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Monthly resume</Text>
        <Pressable onPress={exportCsv} disabled={sharing} style={styles.iconBtn} testID="monthly-export">
          {sharing ? <ActivityIndicator size="small" color={colors.onSurface} /> : <Feather name="share" size={20} color={colors.onSurface} />}
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: insets.bottom + 100, gap: spacing.lg }}>
        <View style={styles.monthRow}>
          <Pressable onPress={prev} style={styles.monthBtn} testID="month-prev">
            <Feather name="chevron-left" size={22} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.monthLabel} testID="month-label">{MONTH_NAMES[month - 1]} {year}</Text>
          <Pressable onPress={next} style={styles.monthBtn} testID="month-next">
            <Feather name="chevron-right" size={22} color={colors.onSurface} />
          </Pressable>
        </View>

        {loading ? (
          <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.xxl }} />
        ) : !report ? null : (
          <>
            <View style={styles.totalsCard} testID="totals-card">
              <Text style={styles.totalsLabel}>Tax routed this month</Text>
              <Text style={styles.totalsAmount}>{fmt(report.totals.taxed, ccy)}</Text>
              <View style={styles.totalsRow}>
                <Mini label="Spent" value={fmt(report.totals.spent, ccy)} />
                <Sep />
                <Mini label="Events" value={String(report.totals.events)} />
                <Sep />
                <Mini label="Overridden" value={String(report.totals.overridden)} />
                <Sep />
                <Mini label="Review" value={String(report.totals.requires_review)} />
              </View>
            </View>

            <Section title="By category">
              {report.by_category.length === 0 ? <Empty /> : report.by_category.map((c) => (
                <Row key={c.name} label={c.name} value={fmt(c.taxed, ccy)} testID={`by-cat-${c.name}`} />
              ))}
            </Section>

            <Section title="By profile">
              {report.by_profile.length === 0 ? <Empty /> : report.by_profile.map((p) => (
                <Row key={p.name} label={p.name} value={fmt(p.taxed, ccy)} testID={`by-profile-${p.name}`} />
              ))}
            </Section>

            <Section title="By destination">
              {report.by_destination.length === 0 ? <Empty /> : report.by_destination.map((d) => (
                <Row key={d.label} label={d.label} value={fmt(d.taxed, ccy)} testID={`by-dest-${d.label}`} />
              ))}
            </Section>

            <Section title="Transfer status">
              {report.by_transfer_status.length === 0 ? <Empty /> : report.by_transfer_status.map((s) => (
                <Row key={s.status} label={s.status} value={`${s.count} event${s.count === 1 ? "" : "s"}`} testID={`by-status-${s.status}`} />
              ))}
            </Section>

            <Section title={`Events (${report.events.length})`}>
              {report.events.length === 0 ? <Empty /> : report.events.slice(0, 50).map((e, idx) => (
                <View key={`${e.transacted_at}-${idx}`} style={styles.eventRow} testID={`event-row-${idx}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.evMerchant} numberOfLines={1}>{e.merchant}</Text>
                    <Text style={styles.evMeta} numberOfLines={1}>
                      {e.category} · {new Date(e.transacted_at).toLocaleDateString()}
                      {e.transfer_status ? ` · ${e.transfer_status}` : ""}
                    </Text>
                  </View>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={styles.evAmount}>-{fmt(e.original_amount, e.currency)}</Text>
                    <Text style={styles.evTax}>+{fmt(e.tax_amount, e.currency)} saved</Text>
                  </View>
                </View>
              ))}
              {report.events.length > 50 ? (
                <Text style={styles.moreNote}>Showing first 50. Export CSV for the full list.</Text>
              ) : null}
            </Section>
          </>
        )}
      </ScrollView>
    </View>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={{ gap: spacing.sm }}>
      <Text style={styles.sectionLabel}>{title}</Text>
      <View style={styles.card}>{children}</View>
    </View>
  );
}
function Row({ label, value, testID }: { label: string; value: string; testID?: string }) {
  return (
    <View style={styles.kvRow} testID={testID}>
      <Text style={styles.kvLabel} numberOfLines={1}>{label}</Text>
      <Text style={styles.kvValue}>{value}</Text>
    </View>
  );
}
function Mini({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={styles.miniLabel}>{label}</Text>
      <Text style={styles.miniValue}>{value}</Text>
    </View>
  );
}
function Sep() { return <View style={styles.sep} />; }
function Empty() { return <Text style={styles.empty}>No data</Text>; }

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary },
  title: { fontFamily: fonts.display, fontSize: type.xl, color: colors.onSurface },

  monthRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  monthBtn: { width: 44, height: 44, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  monthLabel: { fontFamily: fonts.display, fontSize: type.xxl, color: colors.onSurface, lineHeight: 30 },

  totalsCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.xl, gap: spacing.sm },
  totalsLabel: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary, letterSpacing: 0.4, textTransform: "uppercase" },
  totalsAmount: { fontFamily: fonts.displayBold, fontSize: 40, color: colors.onSurface, lineHeight: 44 },
  totalsRow: { flexDirection: "row", alignItems: "center", marginTop: spacing.sm },
  miniLabel: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary },
  miniValue: { fontFamily: fonts.bodyBold, fontSize: type.lg, color: colors.onSurface, marginTop: 2 },
  sep: { width: 1, height: 28, backgroundColor: colors.borderStrong, marginHorizontal: spacing.sm, opacity: 0.5 },

  sectionLabel: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary, letterSpacing: 0.5, textTransform: "uppercase" },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md },

  kvRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  kvLabel: { flex: 1, fontFamily: fonts.body, fontSize: type.base, color: colors.onSurface },
  kvValue: { fontFamily: fonts.bodyBold, fontSize: type.base, color: colors.onSurface },

  eventRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  evMerchant: { fontFamily: fonts.bodyMedium, fontSize: type.base, color: colors.onSurface },
  evMeta: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary, marginTop: 2 },
  evAmount: { fontFamily: fonts.bodyBold, fontSize: type.base, color: colors.onSurface },
  evTax: { fontFamily: fonts.body, fontSize: type.sm, color: colors.success, marginTop: 2 },

  empty: { fontFamily: fonts.body, fontSize: type.base, color: colors.muted, paddingVertical: spacing.md, fontStyle: "italic" },
  moreNote: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary, padding: spacing.md, fontStyle: "italic" },
});
