// Static image mapping for savings bucket backgrounds.
// Using earth-tone Pexels imagery per design guidelines.
export const BUCKET_IMAGES: Record<string, string> = {
  travel:
    "https://images.pexels.com/photos/34480294/pexels-photo-34480294.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
  house:
    "https://images.pexels.com/photos/2079246/pexels-photo-2079246.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
  emergency:
    "https://images.pexels.com/photos/4386431/pexels-photo-4386431.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
  invest:
    "https://images.pexels.com/photos/3943723/pexels-photo-3943723.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
  custom:
    "https://images.pexels.com/photos/1029604/pexels-photo-1029604.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
};

export const HERO_IMAGE =
  "https://images.pexels.com/photos/24416176/pexels-photo-24416176.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940";

export const BUCKET_LABELS: { key: string; label: string }[] = [
  { key: "travel", label: "Travel" },
  { key: "house", label: "House" },
  { key: "emergency", label: "Emergency" },
  { key: "invest", label: "Investment" },
  { key: "custom", label: "Custom" },
];
