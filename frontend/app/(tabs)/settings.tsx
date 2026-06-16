import React, { useCallback, useState } from "react";
import {
    View,
    Text,
    StyleSheet,
    ScrollView,
    Pressable,
    ActivityIndicator,
    Animated,
    Easing,
    Switch,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";  

import { api, LinkedAccount, Settings } from "@/src/api";
import { colors, fonts, radius, spacing, type } from "@/src/theme";

type ProfileKey = Settings["profile_type"];
type FreqKey = Settings["transfer_frequency"];

const PROFILES: {
    key: ProfileKey;
    name: string;
    desc: string;
    intensity: number;
}[] = [
        {
            key: "balanced",
            name: "Balanced",
            desc: "Steady taxes at your configured rates. A calm, sustainable approach.",
            intensity: 2,
        },
        {
            key: "aggressive",
            name: "Aggressive",
            desc: "1.5× on every tax. Maximum financial friction on every impulse.",
            intensity: 5,
        },
        {
            key: "ethical",
            name: "Ethical",
            desc: "Higher taxes on fast food, fast fashion, and corporate brands.",
            intensity: 3,
        },
        {
            key: "mindful",
            name: "Mindful",
            desc: "Half-rate taxes. Gentle nudges, not punishment.",
            intensity: 1,
        },
        {
            key: "savings_beast",
            name: "Savings Beast",
            desc: "Aggressive taxes + automatic transfers whenever your pot exceeds €5.",
            intensity: 5,
        },
    ];

const FREQS: { key: FreqKey; name: string; sub: string }[] = [
    { key: "instant", name: "Instant", sub: "After every detection" },
    { key: "daily", name: "Daily", sub: "Bundled overnight" },
    { key: "weekly", name: "Weekly", sub: "Once a week" },
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
            Animated.timing(opacity, {
                toValue: 1,
                duration: 200,
                useNativeDriver: true,
                easing: Easing.out(Easing.cubic),
            }),
            Animated.delay(1800),
            Animated.timing(opacity, {
                toValue: 0,
                duration: 250,
                useNativeDriver: true,
            }),
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
            const [s, a] = await Promise.all([
                api.getSettings(),
                api.listAccounts(),
            ]);
            setSettings(s);
            setAccounts(a);
        } finally {
            setLoading(false);
        }
    }, []);

    useFocusEffect(
        useCallback(() => {
            setLoading(true);
            load();
        }, [load])
    );

    const setProfile = async (key: ProfileKey) => {
        if (!settings) return;
        const prev = settings;
        setSettings({ ...settings, profile_type: key });

        try {
            const s = await api.patchSettings({ profile_type: key });
            setSettings(s);
            toast.show(`Active profile: ${key}`);
        } catch {
            setSettings(prev);
            toast.show("Couldn't switch profile");
        }
    };

    const setEthicalAll = async (v: boolean) => {
        if (!settings) return;
        const prev = settings;
        setSettings({ ...settings, apply_ethical_penalty_all_profiles: v });

        try {
            const s = await api.patchSettings({ apply_ethical_penalty_all_profiles: v });
            setSettings(s);
        } catch {
            setSettings(prev);
            toast.show("Couldn't update ethical penalty setting");
        }
    };

    const setFreq = async (key: FreqKey) => {
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
            toast.show(next ? "Taxes paused" : "Taxes resumed");
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
        <View style={{ flex: 1, backgroundColor: colors.surface }}>
            <ScrollView
                contentContainerStyle={{
                    paddingTop: insets.top + spacing.lg,
                    paddingHorizontal: spacing.xl,
                    paddingBottom: insets.bottom + 120,
                    gap: spacing.xl,
                }}
            >
                <Text style={styles.h1}>Behavioral profile</Text>

                {loading || !settings ? (
                    <ActivityIndicator color={colors.brand} />
                ) : (
                    <>
                        {PROFILES.map((p) => {
                            const active = settings.profile_type === p.key;

                            return (
                                <Pressable
                                    key={p.key}
                                    onPress={() => setProfile(p.key)}
                                    style={[
                                        styles.profileCard,
                                        active && styles.profileCardActive,
                                    ]}
                                >
                                    <View style={styles.profileTop}>
                                        <Text style={styles.profileName}>{p.name}</Text>
                                    </View>

                                    <Text style={styles.profileDesc}>{p.desc}</Text>

                                    <Intensity n={p.intensity} />
                                </Pressable>
                            );
                        })}

                        <View style={styles.switchRow}>
                            <Text style={styles.sectionLabel}>
                                Apply ethical penalty globally
                            </Text>
                            <Switch
                                value={settings.apply_ethical_penalty_all_profiles}
                                onValueChange={setEthicalAll}
                            />
                        </View>

                        <View>
                            <Text style={styles.sectionLabel}>Transfer timing</Text>
                            {FREQS.map((f) => (

                                <Pressable
                                    key={f.key}
                                    onPress={() => setFreq(f.key)}
                                    style={styles.freqChip}
                                >
                                    <Text>{f.name}</Text>
                                    <Text>{f.sub}</Text>
                                </Pressable>
                            ))}
                            {settings.transfer_last_run_at ? (
                                <Text style={styles.lastRunText}>
                                    Last run: {new Date(settings.transfer_last_run_at).toLocaleString()}
                                </Text>
                            ) : null}
                        </View>

                        <View>
                            <Text style={styles.sectionLabel}>Banks</Text>
                            {accounts.map((a) => (
                                <View key={a.id} style={styles.bankRow}>
                                    <Text>{PROVIDER_LABEL[a.provider] || a.provider}</Text>
                                    <Pressable onPress={() => unlink(a.id)}>
                                        <Text>Unlink</Text>
                                    </Pressable>
                                </View>
                            ))}
                        </View>

                        <Pressable onPress={togglePause} style={styles.pauseBtn}>
                            <Text>
                                {settings.pause_all_taxes
                                    ? "Taxes paused"
                                    : "Pause all taxes"}
                            </Text>
                        </Pressable>
                    </>
                )}
            </ScrollView>
        </View>
    );
}

function Intensity({ n }: { n: number }) {
    return (
        <View style={{ flexDirection: "row", gap: 4 }}>
            {Array.from({ length: 5 }).map((_, i) => (
                <View
                    key={i}
                    style={{
                        width: 6,
                        height: 14,
                        borderRadius: 3,
                        backgroundColor: i < n ? colors.brand : colors.border,
                    }}
                />
            ))}
        </View>
    );
}

const styles = StyleSheet.create({
    h1: { fontSize: 28, fontFamily: fonts.display },
    profileCard: {
        padding: spacing.lg,
        borderRadius: radius.lg,
        backgroundColor: colors.surfaceSecondary,
    },
    profileCardActive: {
        borderColor: colors.brand,
        borderWidth: 1,
    },
    profileName: { fontSize: 18, fontFamily: fonts.display },
    profileDesc: { marginTop: 6, opacity: 0.7 },
    profileTop: { flexDirection: "row", justifyContent: "space-between" },

    sectionLabel: {
        fontSize: 12,
        opacity: 0.6,
        marginBottom: 8,
    },

    freqChip: {
        padding: 12,
        borderRadius: 10,
        backgroundColor: colors.surfaceSecondary,
        marginBottom: 8,
    },

    bankRow: {
        flexDirection: "row",
        justifyContent: "space-between",
        padding: 12,
    },

    pauseBtn: {
        padding: 14,
        backgroundColor: colors.surfaceSecondary,
        borderRadius: 10,
        marginTop: 20,
    },

    switchRow: {
        flexDirection: "row",
        justifyContent: "space-between",
        alignItems: "center",
    },

    lastRunText: {
        fontSize: 12,
        opacity: 0.6,
        marginTop: 4,
    },
});