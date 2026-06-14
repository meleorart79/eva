// Loads Fraunces (display) and DM Sans (body) from Google Fonts CDN.
// We avoid the @expo-google-fonts/* packages per environment policy.
import { useFonts } from "expo-font";

const GFONT = "https://cdn.jsdelivr.net/fontsource";

const APP_FONTS: Record<string, string> = {
  Fraunces_400Regular: `${GFONT}/fonts/fraunces@latest/latin-400-normal.ttf`,
  Fraunces_500Medium: `${GFONT}/fonts/fraunces@latest/latin-500-normal.ttf`,
  Fraunces_600SemiBold: `${GFONT}/fonts/fraunces@latest/latin-600-normal.ttf`,
  DMSans_400Regular: `${GFONT}/fonts/dm-sans@latest/latin-400-normal.ttf`,
  DMSans_500Medium: `${GFONT}/fonts/dm-sans@latest/latin-500-normal.ttf`,
  DMSans_700Bold: `${GFONT}/fonts/dm-sans@latest/latin-700-normal.ttf`,
};

export const useAppFonts = (): readonly [boolean, Error | null] => useFonts(APP_FONTS);
