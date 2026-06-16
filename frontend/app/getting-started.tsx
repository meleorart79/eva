import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";

import { colors, fonts, radius, spacing, type } from "@/src/theme";
import Button from "@/src/components/Button";

const STEPS = [
    {
        icon: "link" as const,
        title: "Connect your bank",
        body: "Éva reads your transactions automatically — no manual entry, ever.",
    },
    {
        icon: "refresh-cw" as const,
        title: "Run your first sync",
        body: "Tap \"Sync now\" on your dashboard. Éva matches your spending against your categories and applies the tax.",
    },
    {
        icon: "trending-up" as const,
        title: "See your savings grow",
        body: "Every taxed purchase moves money toward your goal, automatically.",
    },
];

export default function GettingStarted() {
    const router = useRouter();
    const insets = useSafeAreaInsets();
    const [step, setStep] = useState(0);
    const isLast = step === STEPS.length - 1;
    const current = STEPS[step];

    const finish = () => router.replace("/(tabs)");

    return (
        <View style={[styles.container, { paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.xl }]} testID="getting-started-screen">
            <Pressable onPress={finish} style={styles.skip} testID="getting-started-skip">
                <Text style={styles.skipText}>Skip</Text>
            </Pressable>

            <View style={styles.dots}>
                {STEPS.map((_, i) => (
                    <View key={i} style={[styles.dot, i === step && styles.dotActive]} />
                ))}
            </View>

            <View style={styles.body}>
                <View style={styles.iconCircle}>
                    <Feather name={current.icon} size={28} color={colors.onSurfaceInverse} />
                </View>
                <Text style={styles.title} testID={`getting-started-title-${step}`}>{current.title}</Text>
                <Text style={styles.desc}>{current.body}</Text>
            </View>

            <Button
                title={isLast ? "Go to dashboard" : "Next"}
                onPress={isLast ? finish : () => setStep((s) => s + 1)}
                testID="getting-started-next"
            />
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.surface, paddingHorizontal: spacing.xl, justifyContent: "space-between" },
    skip: { alignSelf: "flex-end" },
    skipText: { fontFamily: fonts.bodyMedium, fontSize: type.base, color: colors.onSurfaceSecondary },
    dots: { flexDirection: "row", justifyContent: "center", gap: spacing.sm },
    dot: { width: 8, height: 8, borderRadius: radius.pill, backgroundColor: colors.border },
    dotActive: { backgroundColor: colors.brand, width: 20 },
    body: { alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.lg },
    iconCircle: { width: 64, height: 64, borderRadius: radius.pill, backgroundColor: colors.surfaceInverse, alignItems: "center", justifyContent: "center", marginBottom: spacing.sm },
    title: { fontFamily: fonts.display, fontSize: type.xxl, color: colors.onSurface, textAlign: "center" },
    desc: { fontFamily: fonts.body, fontSize: type.lg, color: colors.onSurfaceSecondary, textAlign: "center", lineHeight: 24 },
});