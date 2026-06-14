import { View, Text, StyleSheet, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, fonts, spacing, type } from "@/src/theme";
import Button from "@/src/components/Button";
import { HERO_IMAGE } from "@/src/images";

export default function Onboarding() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  return (
    <View style={styles.container} testID="onboarding-screen">
      <Image source={{ uri: HERO_IMAGE }} style={StyleSheet.absoluteFill} contentFit="cover" transition={300} />
      <LinearGradient
        colors={["rgba(40,38,36,0.0)", "rgba(40,38,36,0.55)", "rgba(40,38,36,0.95)"]}
        locations={[0, 0.4, 1]}
        style={StyleSheet.absoluteFill}
      />
      <View style={[styles.content, { paddingBottom: insets.bottom + spacing.xl, paddingTop: insets.top + spacing.xl }]}>
        <View style={styles.brand}>
          <Text style={styles.brandMark} testID="brand-mark">Éva</Text>
        </View>
        <View style={styles.copy}>
          <Text style={styles.headline} testID="onboarding-headline">
            Turn every purchase into future wealth.
          </Text>
          <Text style={styles.sub} testID="onboarding-sub">
            Éva attaches a tiny tax to your spending and redirects it to your savings goals — automatically.
          </Text>
          <Button
            title="Get Started"
            onPress={() => router.push("/(auth)/register")}
            testID="onboarding-cta"
            style={{ backgroundColor: colors.surface }}
          />
          <Pressable
            onPress={() => router.push("/(auth)/login")}
            style={styles.signinRow}
            testID="onboarding-signin-link"
          >
            <Text style={styles.signinText}>I already have an account</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surfaceInverse },
  content: { flex: 1, justifyContent: "space-between", paddingHorizontal: spacing.xl },
  brand: { alignItems: "flex-start" },
  brandMark: {
    fontFamily: fonts.displayBold,
    color: colors.onSurfaceInverse,
    fontSize: type.xxl,
    letterSpacing: 0.5,
  },
  copy: { gap: spacing.lg },
  headline: {
    fontFamily: fonts.display,
    color: colors.onSurfaceInverse,
    fontSize: 38,
    lineHeight: 44,
  },
  sub: {
    fontFamily: fonts.body,
    color: "rgba(247,245,242,0.85)",
    fontSize: type.lg,
    lineHeight: 22,
    marginBottom: spacing.md,
  },
  signinRow: { alignSelf: "center", paddingVertical: spacing.md },
  signinText: {
    fontFamily: fonts.bodyMedium,
    color: "rgba(247,245,242,0.85)",
    fontSize: type.base,
  },
  ctaText: { color: colors.onSurface },
});
