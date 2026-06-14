import React, { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput,
  KeyboardAvoidingView, Platform, TouchableWithoutFeedback, Keyboard, ActivityIndicator,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";

import { api, SavingsDestination } from "@/src/api";
import { useAuth } from "@/src/auth";
import Button from "@/src/components/Button";
import { colors, fonts, radius, spacing, type, CURRENCY_SYMBOL } from "@/src/theme";

const TYPES: { key: SavingsDestination["type"]; label: string; sub: string; icon: keyof typeof Feather.glyphMap }[] = [
  { key: "revolut_pocket", label: "Revolut pocket", sub: "Internal vault / sub-account", icon: "box" },
  { key: "external_iban", label: "External IBAN", sub: "Any euro/£/$ bank account", icon: "credit-card" },
];

export default function Destinations() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();

  const [items, setItems] = useState<SavingsDestination[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<SavingsDestination | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // form state
  const [ftype, setFtype] = useState<SavingsDestination["type"]>("revolut_pocket");
  const [flabel, setFlabel] = useState("");
  const [fid, setFid] = useState("");
  const [fccy, setFccy] = useState<"EUR" | "USD" | "GBP">((user?.currency as any) || "EUR");
  const [fdef, setFdef] = useState(false);

  const load = useCallback(async () => {
    try {
      const list = await api.listDestinations();
      setItems(list);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { setLoading(true); load(); }, [load]));

  const openCreate = () => {
    setEditing(null);
    setFtype("revolut_pocket");
    setFlabel("");
    setFid("");
    setFccy((user?.currency as any) || "EUR");
    setFdef(items.length === 0);
    setErr(null);
    setShowForm(true);
  };

  const openEdit = (d: SavingsDestination) => {
    setEditing(d);
    setFtype(d.type);
    setFlabel(d.label);
    setFid(d.identifier);
    setFccy(d.currency as any);
    setFdef(d.is_default);
    setErr(null);
    setShowForm(true);
  };

  const save = async () => {
    setErr(null);
    if (!flabel.trim() || !fid.trim()) {
      setErr("Label and identifier are required.");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        type: ftype, label: flabel.trim(), identifier: fid.trim(),
        currency: fccy, is_default: fdef,
      };
      if (editing) await api.updateDestination(editing.id, payload);
      else await api.createDestination(payload);
      setShowForm(false);
      await load();
    } catch (e: any) {
      setErr(e.message || "Could not save.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    await api.deleteDestination(id);
    await load();
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      style={{ flex: 1, backgroundColor: colors.surface }}
      testID="destinations-screen"
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} testID="destinations-close">
          <Feather name="x" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Savings destinations</Text>
        <Pressable onPress={openCreate} style={styles.iconBtn} testID="destinations-add">
          <Feather name="plus" size={22} color={colors.onSurface} />
        </Pressable>
      </View>

      {showForm ? (
        <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
          <ScrollView
            contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: insets.bottom + 140, gap: spacing.lg }}
            keyboardShouldPersistTaps="handled"
          >
            <Text style={styles.formTitle}>{editing ? "Edit destination" : "New destination"}</Text>

            <View>
              <Text style={styles.label}>Type</Text>
              <View style={{ gap: spacing.sm }}>
                {TYPES.map((t) => {
                  const active = ftype === t.key;
                  return (
                    <Pressable
                      key={t.key}
                      onPress={() => setFtype(t.key)}
                      style={[styles.providerRow, active && styles.providerRowActive]}
                      testID={`dest-type-${t.key}`}
                    >
                      <Feather name={t.icon} size={20} color={active ? colors.brand : colors.onSurface} />
                      <View style={{ flex: 1 }}>
                        <Text style={[styles.providerName, active && styles.providerNameActive]}>{t.label}</Text>
                        <Text style={styles.providerSub}>{t.sub}</Text>
                      </View>
                      {active ? <Feather name="check-circle" size={20} color={colors.brand} /> : null}
                    </Pressable>
                  );
                })}
              </View>
            </View>

            <View>
              <Text style={styles.label}>Label</Text>
              <TextInput
                value={flabel} onChangeText={setFlabel}
                placeholder={ftype === "revolut_pocket" ? "Travel pocket" : "Main account"}
                placeholderTextColor={colors.muted}
                style={styles.input} testID="dest-label"
              />
            </View>
            <View>
              <Text style={styles.label}>{ftype === "external_iban" ? "IBAN" : "Pocket / account ID"}</Text>
              <TextInput
                value={fid} onChangeText={setFid}
                autoCapitalize="characters" autoCorrect={false}
                placeholder={ftype === "external_iban" ? "LU28 0019 4006 4475 0000" : "pocket_travel_01"}
                placeholderTextColor={colors.muted}
                style={styles.input} testID="dest-identifier"
              />
            </View>
            <View>
              <Text style={styles.label}>Currency</Text>
              <View style={styles.ccyRow}>
                {(["EUR", "USD", "GBP"] as const).map((c) => {
                  const active = fccy === c;
                  return (
                    <Pressable
                      key={c} onPress={() => setFccy(c)}
                      style={[styles.ccyChip, active && styles.ccyChipActive]}
                      testID={`dest-ccy-${c}`}
                    >
                      <Text style={[styles.ccySym, active && styles.ccyActiveText]}>{CURRENCY_SYMBOL[c]}</Text>
                      <Text style={[styles.ccyCode, active && styles.ccyActiveText]}>{c}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>
            <Pressable onPress={() => setFdef((v) => !v)} style={styles.toggleRow} testID="dest-default-toggle">
              <View style={[styles.checkbox, fdef && styles.checkboxActive]}>
                {fdef ? <Feather name="check" size={14} color={colors.onSurfaceInverse} /> : null}
              </View>
              <Text style={styles.toggleText}>Make this my default destination</Text>
            </Pressable>

            {err ? <Text style={styles.err} testID="dest-error">{err}</Text> : null}

            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <Button title="Cancel" variant="secondary" onPress={() => setShowForm(false)} style={{ flex: 1 }} testID="dest-cancel" />
              <Button title={editing ? "Save" : "Create"} onPress={save} loading={busy} style={{ flex: 1 }} testID="dest-submit" />
            </View>
          </ScrollView>
        </TouchableWithoutFeedback>
      ) : (
        <ScrollView contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: insets.bottom + 120, gap: spacing.md }}>
          <Text style={styles.helper}>
            When Éva taxes a purchase, money is routed from the source bank account into one of these destinations.
          </Text>
          {loading ? (
            <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.xl }} />
          ) : items.length === 0 ? (
            <View style={styles.empty} testID="dest-empty">
              <Feather name="archive" size={26} color={colors.muted} />
              <Text style={styles.emptyTitle}>No destinations yet</Text>
              <Text style={styles.emptySub}>Add a Revolut pocket or external IBAN to start receiving tax transfers.</Text>
            </View>
          ) : (
            items.map((d) => (
              <View key={d.id} style={styles.row} testID={`dest-${d.id}`}>
                <View style={styles.rowIcon}>
                  <Feather name={d.type === "revolut_pocket" ? "box" : "credit-card"} size={18} color={colors.onSurface} />
                </View>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                    <Text style={styles.rowLabel}>{d.label}</Text>
                    {d.is_default ? (
                      <View style={styles.defaultBadge} testID={`dest-default-${d.id}`}>
                        <Text style={styles.defaultBadgeText}>Default</Text>
                      </View>
                    ) : null}
                  </View>
                  <Text style={styles.rowSub} numberOfLines={1}>
                    {d.identifier} · {d.currency}
                  </Text>
                </View>
                <Pressable onPress={() => openEdit(d)} style={styles.smallBtn} testID={`dest-edit-${d.id}`}>
                  <Feather name="edit-2" size={16} color={colors.onSurfaceSecondary} />
                </Pressable>
                <Pressable onPress={() => remove(d.id)} style={styles.smallBtn} testID={`dest-delete-${d.id}`}>
                  <Feather name="trash-2" size={16} color={colors.error} />
                </Pressable>
              </View>
            ))
          )}
        </ScrollView>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary },
  title: { fontFamily: fonts.display, fontSize: type.xl, color: colors.onSurface },
  helper: { fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary, lineHeight: 20 },

  empty: { padding: spacing.xxl, alignItems: "center", borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, borderStyle: "dashed", backgroundColor: colors.surfaceSecondary, gap: spacing.sm },
  emptyTitle: { fontFamily: fonts.display, fontSize: type.xl, color: colors.onSurface },
  emptySub: { fontFamily: fonts.body, fontSize: type.base, color: colors.onSurfaceSecondary, textAlign: "center" },

  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  rowIcon: { width: 36, height: 36, borderRadius: radius.pill, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  rowLabel: { fontFamily: fonts.bodyBold, fontSize: type.lg, color: colors.onSurface },
  rowSub: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary, marginTop: 2 },
  defaultBadge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.pill, backgroundColor: colors.brand },
  defaultBadgeText: { fontFamily: fonts.bodyMedium, fontSize: 10, color: colors.onBrand, letterSpacing: 0.3 },
  smallBtn: { width: 34, height: 34, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },

  formTitle: { fontFamily: fonts.display, fontSize: 28, color: colors.onSurface, marginTop: spacing.md },
  label: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary, letterSpacing: 0.5, textTransform: "uppercase", marginBottom: spacing.sm },
  input: { height: 52, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.lg, fontFamily: fonts.body, fontSize: type.lg, color: colors.onSurface },

  providerRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  providerRowActive: { backgroundColor: colors.brandTertiary, borderColor: colors.brand },
  providerName: { fontFamily: fonts.bodyMedium, fontSize: type.lg, color: colors.onSurface },
  providerNameActive: { fontFamily: fonts.displayBold },
  providerSub: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary, marginTop: 2 },

  ccyRow: { flexDirection: "row", gap: spacing.sm },
  ccyChip: { flex: 1, height: 60, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  ccyChipActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  ccySym: { fontFamily: fonts.displayBold, fontSize: 22, color: colors.onSurface },
  ccyCode: { fontFamily: fonts.body, fontSize: type.sm, color: colors.onSurfaceSecondary },
  ccyActiveText: { color: colors.onSurfaceInverse },

  toggleRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm },
  checkbox: { width: 24, height: 24, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center" },
  checkboxActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  toggleText: { flex: 1, fontFamily: fonts.body, fontSize: type.base, color: colors.onSurface },

  err: { fontFamily: fonts.body, color: colors.error, fontSize: type.base },
});
