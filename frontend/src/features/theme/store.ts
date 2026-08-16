import { create } from "zustand";

/**
 * UI state only (ephemeral). API data lives in TanStack Query — do not mix the two.
 *
 * The theme is also written to `localStorage`, because an explicit choice that disappears on
 * refresh is not a choice. Reading it back happens in two places on purpose:
 *
 * - the inline script in the document head (`THEME_INIT_SCRIPT`) applies the class before the
 *   first paint, so nobody sees a light flash before dark mode kicks in,
 * - the toggle syncs this store from what that script decided, so the two never disagree.
 *
 * Deliberately no `persist` middleware from zustand: it hydrates after mount, which is exactly
 * one paint too late.
 */
export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "theme";

type UiState = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
};

function remember(theme: Theme): void {
  // A private window can refuse to store; a theme is not worth breaking the page over.
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // ignored on purpose
  }
}

function apply(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  remember(theme);
}

export const useUiStore = create<UiState>((set) => ({
  // SSR renders with the light value; the inline script has already set the real class on
  // <html> by then, and the toggle syncs this store on mount.
  theme: "light",
  setTheme: (theme) => {
    apply(theme);
    set({ theme });
  },
  toggleTheme: () =>
    set((state) => {
      const theme: Theme = state.theme === "dark" ? "light" : "dark";
      apply(theme);
      return { theme };
    }),
}));
