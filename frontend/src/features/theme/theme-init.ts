import { THEME_STORAGE_KEY } from "./store";

/**
 * Runs in the document head, before the first paint.
 *
 * Without it a dark-mode user sees a light flash on every page load: the class on `<html>` was
 * set from a React effect, which runs after hydration — several frames after the browser has
 * already painted the light theme. This is the same class of bug as rendering "signed out"
 * before the session answer arrives, and it has the same fix: decide before painting.
 *
 * It is a string rather than a module because it has to execute before any bundle loads. The
 * CSP allows it: `script-src` already carries `'unsafe-inline'` for the hydration payload that
 * TanStack Start injects.
 */
export const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});
    var dark = stored ? stored === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    if (dark) document.documentElement.classList.add("dark");
  } catch (e) {}
})();
`.trim();
