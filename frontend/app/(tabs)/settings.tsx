import React, { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, Animated, Easing,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";

import { api, LinkedAccount, Settings } from "@/src/api";
import { colors, fonts, radius, spacing, type } from "@/src/theme";

type ProfileKey = Settings["profile_type"];
type FreqKey = Settings["transfer_frequency"];

const PROFILES: { key: ProfileKey; name: string; desc: string; intensity: number }[] = [
  { key: "balanced", name: "Balanced", desc: "Steady taxes at your configured rates. A calm, sustainable approach.", intensity: 2 },
  { key: "aggressive", name: "Aggressive", desc: "1.5× on every tax. Maximum financial friction on every impulse.", intensity: 5 },
  { key: "ethical", name: "Ethical", desc: "Higher taxes on fast food, fast fashion, and corporate brands. Vote with your wallet.", intensity: 3 },
  { key: "mindful", name: "Mindful", desc: "Half-rate taxes. Gentle nudges, not punishment.", intensity: 1 },
  { key: "savings_beast", name: "Savings Beast", desc: "Aggressive taxes + automatic transfers whenever your pot exceeds €5. Money moves constantly.", intensity: 5 },
];

const FREQS: { key: FreqKey; name: string; comingSoon?: boolean }[] = [
  { key: "instant", name: "Instant" },
  { key: "daily", name: "Daily", comingSoon: true },
  { key: "weekly", name: "Weekly", comingSoon: true },
];

const PROVIDER_LABEL: Record<string, string> = {
  revolut: "Revolut",
  spuerkeess: "Spuerkeess",
};

function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  const opacity = React.useRef(new Animated.Value(0)).current;
  const show = (text: string) => {
    setMsg(text);
    Animated.sequence([
      Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true, easing: Easing.out(Easing.cubic) }),
      Animated.delay(1800),
      Animated.timing(opacity, { toValue: 0, duration: 250, useNativeDriver: true }),
    ]).start(() => setMsg(null));
  };
  return { msg, opacity, show };
}

export default function SettingsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [accounts, setAccounts] = useState<LinkedAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  const load = useCallback(async () => {
    try {
      const [s, a] = await Promise.all([api.getSettings(), api.listAccounts()]);
      setSettings(s);
      setAccounts(a);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { setLoading(true); load(); }, [load]));

  const setProfile = async (key: ProfileKey) => {
    if (!settings) return;
    const prev = settings;
    setSettings({ ...settings, profile_type: key });
    try {
      const s = await api.patchSettings({ profile_type: key });
      setSettings(s);
      toast.show(`Active profile: ${PROFILES.find((p) => p.key === key)?.name}`);
    } catch {
      setSettings(prev);
      toast.show("Couldn't switch profile");
    }
  };

  const setFreq = async (key: FreqKey) => {
    const opt = FREQS.find((f) => f.key === key)!;
    if (opt.comingSoon) {
      toast.show(`${opt.name} transfers — coming soon`);
      return;
    }
    if (!settings) return;
    const prev = settings;
    setSettings({ ...settings, transfer_frequency: key });
    try {
      const s = await api.patchSettings({ transfer_frequency: key });
      setSettings(s);
    } catch {
      setSettings(prev);
    }
  };

  const togglePause = async () => {
    if (!settings) return;
    const next = !settings.pause_all_taxes;
    const prev = settings;
    setSettings({ ...settings, pause_all_taxes: next });
    try {
      const s = await api.patchSettings({ pause_all_taxes: next });
      setSettings(s);
      toast.show(next ? "All taxes paused" : "Taxes resumed");
    } catch {
      setSettings(prev);
    }
  };

  const unlink = async (id: string) => {
    await api.unlinkBank(id);
    await load();
    toast.show("Bank disconnected");
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="settings-screen">
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + spacing.lg,
          paddingHorizontal: spacing.xl,
          paddingBottom: insets.bottom + 120,
          gap: spacing.xl,
        }}
      >
        <View style={{ gap: spacing.xs }}>
          <Text style={styles.kicker}>HOW ÉVA TAXES YOU</Text>
          <Text style={styles.h1}>Behavioral profile</Text>
        </View>

        {loading || !settings ? (
          <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.xl }} />
        ) : (
          <>
            <View style={{ gap: spacing.md }}>
              {PROFILES.map((p) => {
                const active = settings.profile_type === p.key;
                return (
                  <Pressable
                    key={p.key}
                    onPress={() => setProfile(p.key)}
                    style={[styles.profileCard, active && styles.profileCardActive]}
                    testID={`profile-${p.key}`}
                  >
                    <View style={styles.profileTop}>
                      <Text style={[styles.profileName, active && styles.profileNameActive]}>{p.name}</Text>
                      <Intensity n={p.intensity} active={active} />
                    </View>
                    <Text style={styles.profileDesc}>{p.desc}</Text>
                    {active ? (
                      <View style={styles.activeChip}>
                        <Feather name="check" size={12} color={colors.onBrand} />
                        <Text style={styles.activeChipText}>Active</Text>
                      </View>
                    ) : null}
                  </Pressable>
                );
              })}
            </View>

            <View style={{ gap: spacing.sm }}>
              <Text style={styles.sectionLabel}>Transfer timing</Text>
              <View style={styles.freqRow}>
                {FREQS.map((f) => {
                  const active = settings.transfer_frequency === f.key && !f.comingSoon;
                  return (
                    <Pressable
                      key={f.key}
                      onPress={() => setFreq(f.key)}
                      style={[styles.freqChip, active && styles.freqChipActive]}
                      testID={`freq-${f.key}`}
                    >
                      <Text style={[styles.freqText, active && styles.freqTextActive]}>{f.name}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>

            <View style={{ gap: spacing.sm }}>
              <Text style={styles.sectionLabel}>Bank connections</Text>
              {accounts.length === 0 ? (
                <Pressable
                  onPress={() => router.push("/link-bank")}
                  style={styles.bankRowEmpty}
                  testID="settings-link-bank"
                >
                  <Feather name="link" size={18} color={colors.onSurface} />
                  <Text style={styles.bankRowText}>Connect a bank</Text>
                  <Feather name="chevron-right" size={18} color={colors.muted} />
                </Pressable>
              ) : (
                accounts.map((a) => (
                  <View key={a.id} style={styles.bankRow} testID={`bank-row-${a.id}`}>
                    <View style={styles.bankDot}><Feather name="check" size={14} color={colors.onBrand} /></View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.bankName}>{PROVIDER_LABEL[a.provider] || a.provider}</Text>
                      <Text style={styles.bankSub}>Linked · {new Date(a.linked_at).toLocaleDateString()}</Text>
                    </View>
                    <Pressable onPress={() => unlink(a.id)} style={styles.unlinkBtn} testID={`unlink-${a.id}`}>
                      <Text style={styles.unlinkText}>Unlink</Text>
                    </Pressable>
                  </View>
                ))
              )}
              {accounts.length > 0 ? (
                <Pressable
                  onPress={() => router.push("/link-bank")}
                  style={styles.addBankRow}
                  testID="settings-add-bank"
                >
                  <Feather name="plus" size={18} color={colors.onSurface} />
                  <Text style={styles.bankRowText}>Add bank</Text>
                </Pressable>
              ) : null}
            </View>

            <View style={styles.danger} testID="danger-zone">
              <Text style={styles.dangerLabel}>Danger zone</Text>
              <Pressable
                onPress={togglePause}
                style={styles.pauseRow}
                testID="pause-toggle"
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.pauseTitle}>Pause all taxes</Text>
                  <Text style={styles.pauseHint}>
                    {settings.pause_all_taxes
                      ? "Taxes are PAUSED — no automatic savings will be made until you turn this off."
                      : "While paused, no taxes will be applied to incoming transactions."}
                  </Text>
                </View>
                <View style={[styles.switch, settings.pause_all_taxes && styles.switchOn]}>
                  <View style={[styles.knob, settings.pause_all_taxes && styles.knobOn]} />
                </View>
              </Pressable>
            </View>
          </>
        )}
      </ScrollView>

      {toast.msg ? (
        <Animated.View style={[styles.toast, { opacity: toast.opacity, bottom: insets.bottom + 80 }]} testID="toast">
          <Text style={styles.toastText}>{toast.msg}</Text>
        </Animated.View>
      ) : null}
    </View>
  );
}

function Intensity({ n, active }: { n: number; active: boolean }) {
  return (
    <View style={{ flexDirection: "row", gap: 3 }}>
      {[0, 1, 2, 3, 4].map((i) => (
        <View
          key={i}
          style={{
            width: 6, height: 14, borderRadius: 3,
            backgroundColor: i < n
              ? (active ? colors.brand : colors.brand)
              : (active ? colors.borderStrong : colors.surfaceTertiary),
          }}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  kicker: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary, letterSpacing: 0.6, textTransform: "uppercase" },
  h1: { fontFamily: fonts.display, fontSize: 28, color: colors.onSurface, lineHeight: 32 },

  profileCard: { padding: spacing.lg, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, gap: spacing.sm },
  profileCardActive: { backgroundColor: colors.brandTertiary, borderColor: colors.brand },
  profileTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  profileName: { fontFamily: fonts.display, fontSize: type.xxl, color: colors.onSurface, lineHeight: 28 },
  profileNameActive: { fontFamily: fonts.displayBold },
  profileDesc: { fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary, lineHeight: 20 },
  activeChip: { flexDirection: "row", alignSelf: "flex-start", paddingHorizontal: spacing.sm, paddingVertical: 4, gap: 4, borderRadius: radius.pill, backgroundColor: colors.brand, alignItems: "center" },
  activeChipText: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onBrand },

  sectionLabel: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary, letterSpacing: 0.5, textTransform: "uppercase" },
  freqRow: { flexDirection: "row", gap: spacing.sm },
  freqChip: { flex: 1, height: 48, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  freqChipActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  freqText: { fontFamily: fonts.bodyMedium, fontSize: type.base, color: colors.onSurface },
  freqTextActive: { color: colors.onSurfaceInverse },

  bankRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  bankRowEmpty: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderStyle: "dashed" },
  bankRowText: { flex: 1, fontFamily: fonts.bodyMedium, fontSize: type.lg, color: colors.onSurface },
  addBankRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, borderStyle: "dashed" },
  bankDot: { width: 28, height: 28, borderRadius: radius.pill, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  bankName: { fontFamily: fonts.bodyBold, fontSize: type.lg, color: colors.onSurface },
  bankSub: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary, marginTop: 2 },
  unlinkBtn: { paddingHorizontal: spacing.md, height: 32, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center" },
  unlinkText: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary },

  danger: { padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, gap: spacing.sm, marginTop: spacing.md },
  dangerLabel: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.error, letterSpacing: 0.5, textTransform: "uppercase" },
  pauseRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm },
  pauseTitle: { fontFamily: fonts.bodyBold, fontSize: type.lg, color: colors.onSurface },
  pauseHint: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary, marginTop: 2, lineHeight: 18 },
  switch: { width: 48, height: 28, borderRadius: 14, backgroundColor: colors.surfaceTertiary, padding: 2, justifyContent: "center" },
  switchOn: { backgroundColor: colors.error },
  knob: { width: 24, height: 24, borderRadius: 12, backgroundColor: colors.surface },
  knobOn: { transform: [{ translateX: 20 }] },

  toast: { position: "absolute", left: spacing.xl, right: spacing.xl, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceInverse, alignItems: "center" },
  toastText: { fontFamily: fonts.bodyMedium, fontSize: type.base, color: colors.onSurfaceInverse },
});
