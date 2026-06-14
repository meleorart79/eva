// Soft earth-tone theme tokens. Source of truth for all styling.
export const colors = {
  surface: "#F7F5F2",
  onSurface: "#282624",
  surfaceSecondary: "#EBE7E0",
  onSurfaceSecondary: "#3E3B37",
  surfaceTertiary: "#DFD9CF",
  onSurfaceTertiary: "#4A4742",
  surfaceInverse: "#282624",
  onSurfaceInverse: "#F7F5F2",
  brand: "#7B8C73",
  brandSecondary: "#C2A888",
  brandTertiary: "#D9E0D5",
  onBrand: "#FFFFFF",
  success: "#728A6D",
  warning: "#D4A373",
  error: "#C27D72",
  border: "#DCD7CE",
  borderStrong: "#BDB6A8",
  muted: "#8E8A82",
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
};

export const radius = {
  sm: 6,
  md: 12,
  lg: 20,
  pill: 999,
};

export const fonts = {
  display: "Fraunces_500Medium",
  displayBold: "Fraunces_600SemiBold",
  body: "DMSans_400Regular",
  bodyMedium: "DMSans_500Medium",
  bodyBold: "DMSans_700Bold",
};

export const type = {
  sm: 12,
  base: 14,
  lg: 16,
  xl: 20,
  xxl: 24,
  display: 32,
  display2: 40,
};

export const CURRENCY_SYMBOL: Record<string, string> = {
  EUR: "€",
  USD: "$",
  GBP: "£",
};

export const fmt = (n: number, ccy = "EUR") => {
  const sym = CURRENCY_SYMBOL[ccy] || ccy;
  const v = (Math.round(n * 100) / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${sym}${v}`;
};
