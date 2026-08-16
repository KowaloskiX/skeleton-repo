import { Moon, Sun } from "lucide-react";
import { type ReactNode, useEffect } from "react";

import { Button } from "@/components/ui/button";

import { useUiStore } from "./store";

/**
 * The `<html>` class is set before the first paint by `THEME_INIT_SCRIPT`. This component only
 * syncs the store with that decision, so the button shows the icon that matches what the user
 * is actually looking at.
 */
export function ThemeToggle(): ReactNode {
  const theme = useUiStore((state) => state.theme);
  const setTheme = useUiStore((state) => state.setTheme);
  const toggleTheme = useUiStore((state) => state.toggleTheme);

  useEffect(() => {
    const applied = document.documentElement.classList.contains("dark") ? "dark" : "light";
    if (applied !== theme) setTheme(applied);
    // Runs once: afterwards the store is the source of truth and writes the class itself.
  }, [setTheme, theme]);

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={toggleTheme}
      aria-label={theme === "dark" ? "Switch to the light theme" : "Switch to the dark theme"}
    >
      {theme === "dark" ? <Sun size={15} aria-hidden /> : <Moon size={15} aria-hidden />}
    </Button>
  );
}
