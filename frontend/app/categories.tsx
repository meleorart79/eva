import React, { useCallback, useMemo, useState } from "react";
import {
    View,
    Text,
    StyleSheet,
    ScrollView,
    Pressable,
    TextInput,
    KeyboardAvoidingView,
    Platform,
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
    const [kwInput, setKwInput] = useState<Record<string, string>>({});

    const load = useCallback(async () => {
        setItems(await api.categories());
    }, []);

    useFocusEffect(
        useCallback(() => {
            load();
        }, [load])
    );

    const update = (id: string, patch: Partial<Category>) =>
        setItems((prev) =>
            prev.map((c) => (c.id === id ? { ...c, ...patch } : c))
        );

    const save = async (c: Category) => {
        try {
            await api.updateCategory(c.id, {
                name: c.name,
                icon: c.icon,
                tax_rate: c.tax_rate,
                merchant_keywords: c.merchant_keywords ?? [],
                rep_increment: c.rep_increment ?? 0.05,
                max_tax_rate: c.max_tax_rate ?? 0.5,
                daily_cap_amount: c.daily_cap_amount ?? 10.0,
            });
        } catch (e) {
            load();
        }
    };

    const remove = async (id: string) => {
        await api.deleteCategory(id);
        setItems((p) => p.filter((c) => c.id !== id));
    };

    const addNew = async () => {
        const created = await api.createCategory({
            name: "New category",
            icon: "tag",
            tax_rate: 0.1,
            merchant_keywords: [],
            rep_increment: 0.05,
            max_tax_rate: 0.5,
            daily_cap_amount: 10.0,
        });

        setItems((p) => [...p, created]);
    };

    const removeKeyword = (catId: string, kw: string) => {
        let updatedCat: Category | undefined;
        setItems((prev) =>
            prev.map((c) => {
                if (c.id !== catId) return c;
                updatedCat = {
                    ...c,
                    merchant_keywords: (c.merchant_keywords || []).filter((k) => k !== kw),
                };
                return updatedCat;
            })
        );
        if (updatedCat) save(updatedCat);
    };

    const addKeyword = (cat: Category, value: string) => {
        const clean = value.trim().toLowerCase();
        if (!clean) return;

        const updatedCat: Category = {
            ...cat,
            merchant_keywords: Array.from(new Set([...(cat.merchant_keywords || []), clean])),
        };

        setItems((prev) => prev.map((c) => (c.id === cat.id ? updatedCat : c)));
        setKwInput((p) => ({ ...p, [cat.id]: "" }));
        save(updatedCat);
    };

    const [testMerchant, setTestMerchant] = useState("");

    const matchedCategory = useMemo(() => {
        const name = testMerchant.trim().toLowerCase();
        if (!name) return null;
        const ordered = [...items].sort(
            (a, b) => (a.name === "Ethical Penalty" ? 0 : 1) - (b.name === "Ethical Penalty" ? 0 : 1)
        );
        for (const cat of ordered) {
            for (const kw of cat.merchant_keywords || []) {
                if (kw && name.includes(kw.toLowerCase())) return cat;
            }
        }
        return null;
    }, [testMerchant, items]);

    return (
        <KeyboardAvoidingView
            behavior={Platform.OS === "ios" ? "padding" : "height"}
            style={{ flex: 1, backgroundColor: colors.surface }}
            testID="categories-screen"
        >
            <View
                style={[
                    styles.header,
                    { paddingTop: insets.top + spacing.md },
                ]}
            >
                <Pressable
                    onPress={() => router.back()}
                    style={styles.iconBtn}
                >
                    <Feather name="x" size={22} color={colors.onSurface} />
                </Pressable>

                <Text style={styles.title}>Categories</Text>

                <Pressable onPress={addNew} style={styles.iconBtn}>
                    <Feather name="plus" size={22} color={colors.onSurface} />
                </Pressable>
            </View>

            <ScrollView
                contentContainerStyle={{
                    paddingHorizontal: spacing.xl,
                    paddingBottom: insets.bottom + 80,
                    gap: spacing.md,
                }}
            >
                <Text style={styles.helper}>
                    Set how much "tax" each category contributes to your savings.
                    Tap a row to edit.
                </Text>

                <View style={styles.testBox}>
                    <Text style={styles.testLabel}>Test a merchant name</Text>
                    <TextInput
                        value={testMerchant}
                        onChangeText={setTestMerchant}
                        placeholder="e.g. mcdonalds paris"
                        style={styles.testInput}
                        autoCapitalize="none"
                    />
                    {testMerchant.trim() ? (
                        matchedCategory ? (
                            <Text style={styles.testResultMatch}>
                                Matches: {matchedCategory.name} ({Math.round(matchedCategory.tax_rate * 100)}%)
                            </Text>
                        ) : (
                            <Text style={styles.testResultNone}>No category would match — unmatched.</Text>
                        )
                    )}
                </View>

                {items.map((c) => (
                    <View key={c.id} style={styles.row}>
                        <TextInput
                            value={c.name}
                            onChangeText={(v) => update(c.id, { name: v })}
                            onEndEditing={() => {
                                const fresh = items.find((i) => i.id === c.id);
                                if (fresh) save(fresh);
                            }}
                            style={styles.nameInput}
                        />

                        <View style={styles.rateRow}>
                            <Text style={styles.rateLabel}>Tax %</Text>

                            <TextInput
                                value={String(Math.round(c.tax_rate * 100))}
                                onChangeText={(v) => {
                                    const n = Math.max(
                                        0,
                                        Math.min(100, parseInt(v || "0", 10) || 0)
                                    );
                                    update(c.id, { tax_rate: n / 100 });
                                }}
                                onEndEditing={() => {
                                    const fresh = items.find((i) => i.id === c.id);
                                    if (fresh) save(fresh);
                                }}
                                keyboardType="number-pad"
                                style={styles.rateInput}
                            />

                            <Pressable
                                onPress={() => remove(c.id)}
                                style={styles.delete}
                            >
                                <Feather
                                    name="trash-2"
                                    size={18}
                                    color={colors.error}
                                />
                            </Pressable>
                        </View>

                        {/* KEYWORDS */}
                        {c.merchant_keywords &&
                            c.merchant_keywords.length > 0 ? (
                            <>
                                <View style={styles.kwRow}>
                                    {c.merchant_keywords.map((kw) => (
                                        <Pressable
                                            key={kw}
                                            style={styles.kwChip}
                                            onPress={() => {
                                                removeKeyword(c.id, kw);
                                                setTimeout(() => {
                                                    const fresh = items.find(
                                                        (i) => i.id === c.id
                                                    );
                                                    if (fresh) save(fresh);
                                                }, 0);
                                            }}
                                        >
                                            <Text style={styles.kwText}>
                                                {kw} ✕
                                            </Text>
                                        </Pressable>
                                    ))}
                                </View>

                                <View style={styles.kwAddRow}>
                                    <TextInput
                                        value={kwInput[c.id] || ""}
                                        onChangeText={(v) =>
                                            setKwInput((p) => ({
                                                ...p,
                                                [c.id]: v,
                                            }))
                                        }
                                        placeholder="Add keyword"
                                        style={styles.kwInput}
                                        onSubmitEditing={() => {
                                            addKeyword(c, kwInput[c.id] || "");
                                            setTimeout(() => {
                                                const fresh = items.find(
                                                    (i) => i.id === c.id
                                                );
                                                if (fresh) save(fresh);
                                            }, 0);
                                        }}
                                    />
                                </View>
                            </>
                        ) : (
                            <>
                                <Text style={styles.kwEmpty}>
                                    No merchant keywords · this category never
                                    auto-matches.
                                </Text>

                                <View style={styles.kwAddRow}>
                                    <TextInput
                                        value={kwInput[c.id] || ""}
                                        onChangeText={(v) =>
                                            setKwInput((p) => ({
                                                ...p,
                                                [c.id]: v,
                                            }))
                                        }
                                        placeholder="Add keyword"
                                        style={styles.kwInput}
                                        onSubmitEditing={() => {
                                            addKeyword(c, kwInput[c.id] || "");
                                            setTimeout(() => {
                                                const fresh = items.find(
                                                    (i) => i.id === c.id
                                                );
                                                if (fresh) save(fresh);
                                            }, 0);
                                        }}
                                    />
                                </View>
                            </>
                        )}
                    </View>
                ))}

                <Button
                    title="Add category"
                    variant="secondary"
                    onPress={addNew}
                />
            </ScrollView>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    header: {
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "space-between",
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.md,
    },
    iconBtn: {
        width: 40,
        height: 40,
        alignItems: "center",
        justifyContent: "center",
        borderRadius: radius.pill,
        backgroundColor: colors.surfaceSecondary,
    },
    title: {
        fontFamily: fonts.display,
        fontSize: type.xl,
        color: colors.onSurface,
    },
    helper: {
        fontFamily: fonts.body,
        fontSize: type.base,
        color: colors.onSurfaceSecondary,
        marginBottom: spacing.sm,
    },
    row: {
        backgroundColor: colors.surfaceSecondary,
        borderRadius: radius.md,
        padding: spacing.md,
        borderWidth: 1,
        borderColor: colors.border,
        gap: spacing.sm,
    },
    nameInput: {
        fontFamily: fonts.bodyMedium,
        fontSize: type.lg,
        color: colors.onSurface,
        paddingVertical: spacing.xs,
    },
    rateRow: {
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.md,
    },
    rateLabel: {
        fontFamily: fonts.body,
        fontSize: type.sm,
        color: colors.onSurfaceSecondary,
    },
    rateInput: {
        flex: 1,
        height: 40,
        backgroundColor: colors.surface,
        borderRadius: radius.sm,
        borderWidth: 1,
        borderColor: colors.border,
        paddingHorizontal: spacing.md,
        fontFamily: fonts.bodyMedium,
        fontSize: type.base,
        color: colors.onSurface,
    },
    delete: {
        width: 40,
        height: 40,
        alignItems: "center",
        justifyContent: "center",
    },
    kwRow: {
        flexDirection: "row",
        flexWrap: "wrap",
        gap: spacing.xs,
        marginTop: spacing.xs,
    },
    kwChip: {
        paddingHorizontal: spacing.sm,
        paddingVertical: 4,
        borderRadius: radius.pill,
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.border,
    },
    kwText: {
        fontFamily: fonts.body,
        fontSize: type.sm,
        color: colors.onSurfaceSecondary,
    },
    kwEmpty: {
        fontFamily: fonts.body,
        fontSize: type.sm,
        color: colors.muted,
        fontStyle: "italic",
        marginTop: spacing.xs,
    },
    kwAddRow: {
        marginTop: spacing.xs,
    },
    kwInput: {
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: radius.sm,
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.sm,
        fontFamily: fonts.body,
        color: colors.onSurface,
    },
    testBox: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border, gap: spacing.xs },
    testLabel: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.onSurfaceSecondary },
    testInput: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, fontFamily: fonts.body, color: colors.onSurface },
    testResultMatch: { fontFamily: fonts.bodyMedium, fontSize: type.sm, color: colors.success },
    testResultNone: { fontFamily: fonts.body, fontSize: type.sm, color: colors.muted, fontStyle: "italic" },
});