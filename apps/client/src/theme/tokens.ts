export type Palette = {
  background: string;
  surface: string;
  surfaceSecondary: string;
  sheet: string;
  drawer: string;
  text: string;
  muted: string;
  faint: string;
  border: string;
  accent: string;
  success: string;
  danger: string;
  onPrimary: string;
};

// Dark mode: pure black canvas with soft dark cards, as specified for the new UI.
export const darkPalette: Palette = {
  background: "#000000",
  surface: "#1A1A1A",
  surfaceSecondary: "#242424",
  sheet: "#141414",
  drawer: "#111111",
  text: "#FFFFFF",
  muted: "#9C9C9C",
  faint: "#5F5F5F",
  border: "#262626",
  accent: "#3B82F6",
  success: "#22C55E",
  danger: "#EF4444",
  onPrimary: "#000000",
};

// Light mode: the whole app flips to a light gray canvas with white cards.
export const lightPalette: Palette = {
  background: "#F5F5F5",
  surface: "#FFFFFF",
  surfaceSecondary: "#EAEAEA",
  sheet: "#FFFFFF",
  drawer: "#FFFFFF",
  text: "#111111",
  muted: "#5A5A5A",
  faint: "#9A9A9A",
  border: "#E3E3E3",
  accent: "#3B82F6",
  success: "#16A34A",
  danger: "#DC2626",
  onPrimary: "#FFFFFF",
};

// Legacy Midnight Gold tokens retained for screens not yet migrated in this pass.
export const colors = {
  background: "#080B14",
  surface: "#151A27",
  surfaceSecondary: "#252B3A",
  gold: "#D4AF37",
  goldDark: "#B88A2B",
  text: "#F5F0E2",
  muted: "#A7ADBA",
  faint: "#687080",
  border: "#343B4C",
} as const;

export const typography = {
  fontFamily: {
    arabic: "Tajawal",
    latin: "Inter",
  },
} as const;
