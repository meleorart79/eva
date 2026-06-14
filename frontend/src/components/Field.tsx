import React from "react";
import { TextInput, View, Text, StyleSheet, TextInputProps } from "react-native";
import { colors, fonts, radius, spacing, type } from "../theme";

type Props = TextInputProps & {
  label?: string;
  error?: string;
};

export default function Field({ label, error, style, ...rest }: Props) {
  return (
    <View style={{ width: "100%" }}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <TextInput
        placeholderTextColor={colors.muted}
        style={[styles.input, !!error && { borderColor: colors.error }, style]}
        {...rest}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  label: {
    fontFamily: fonts.bodyMedium,
    fontSize: type.sm,
    color: colors.onSurfaceSecondary,
    marginBottom: spacing.xs,
    letterSpacing: 0.4,
    textTransform: "uppercase",
  },
  input: {
    height: 52,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
    fontFamily: fonts.body,
    fontSize: type.lg,
    color: colors.onSurface,
  },
  error: {
    fontFamily: fonts.body,
    fontSize: type.sm,
    color: colors.error,
    marginTop: spacing.xs,
  },
});
