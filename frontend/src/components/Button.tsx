import React from "react";
import { Pressable, Text, StyleSheet, ActivityIndicator, ViewStyle } from "react-native";
import { colors, fonts, radius, spacing, type } from "../theme";

type Variant = "primary" | "secondary" | "ghost";
type Props = {
  title: string;
  onPress?: () => void;
  variant?: Variant;
  disabled?: boolean;
  loading?: boolean;
  style?: ViewStyle;
  testID?: string;
};

export default function Button({
  title,
  onPress,
  variant = "primary",
  disabled,
  loading,
  style,
  testID,
}: Props) {
  const isDisabled = disabled || loading;
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.base,
        variant === "primary" && styles.primary,
        variant === "secondary" && styles.secondary,
        variant === "ghost" && styles.ghost,
        pressed && !isDisabled && { opacity: 0.85 },
        isDisabled && { opacity: 0.5 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={variant === "primary" ? colors.onBrand : colors.onSurface} />
      ) : (
        <Text
          style={[
            styles.text,
            variant === "primary" && { color: colors.onBrand },
            variant === "secondary" && { color: colors.onSurface },
            variant === "ghost" && { color: colors.brand },
          ]}
        >
          {title}
        </Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    height: 52,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.xl,
    alignItems: "center",
    justifyContent: "center",
  },
  primary: { backgroundColor: colors.surfaceInverse },
  secondary: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  ghost: { backgroundColor: "transparent" },
  text: { fontFamily: fonts.bodyMedium, fontSize: type.lg, letterSpacing: 0.2 },
});
