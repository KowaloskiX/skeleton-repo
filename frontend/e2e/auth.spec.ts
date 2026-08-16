import { expect, test } from "@playwright/test";

const PASSWORD = "correct-horse-battery-staple";

/** A unique email per run — the database is not cleaned between runs. */
function uniqueEmail(): string {
  return `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

test("registration creates an organization, sign-out and sign-in work", async ({ page }) => {
  const email = uniqueEmail();

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Sign-in works");
  // The readout reads the real /api/health — if the backend is down, the test fails here.
  await expect(page.getByText(/ok · (dev|test|staging|prod)/)).toBeVisible();

  await page.getByRole("link", { name: "Create account" }).first().click();
  await page.getByLabel("Organization").fill("Acme E2E");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(email);
  await expect(page.getByText("Acme E2E")).toBeVisible();
  await expect(page.getByText("owner")).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL("/");

  await page.getByRole("link", { name: "Sign in" }).first().click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);
});

test("a protected route sends an anonymous visitor to sign-in", async ({ page }) => {
  await page.goto("/app");
  await expect(page).toHaveURL(/\/login$/);
});

test("a wrong password shows a message and does not open the dashboard", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("nobody@example.com");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("alert")).toContainText("Invalid email or password.");
  await expect(page).toHaveURL(/\/login$/);
});

test("the HTML document carries security headers", async ({ page }) => {
  // A CSP only applies from the response that delivered the document — the headers from
  // FastAPI cover `/api` only, so this layer has to be checked separately.
  const response = await page.goto("/");
  const headers = response?.headers() ?? {};

  expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
});

test("an API response carries its own set of headers", async ({ request }) => {
  const response = await request.get("/api/auth/session");
  const headers = response.headers();

  expect(headers["content-security-policy"]).toContain("object-src 'none'");
  expect(headers["x-content-type-options"]).toBe("nosniff");
});

test("an unknown address shows a 404 rather than a blank page", async ({ page }) => {
  await page.goto("/no-such-page");

  await expect(page.getByRole("heading", { name: "No such page" })).toBeVisible();
  await page.getByRole("link", { name: "Back to the home page" }).click();
  await expect(page).toHaveURL("/");
});

test("an expired session redirects to sign-in instead of failing silently", async ({
  page,
  context,
}) => {
  const email = uniqueEmail();
  await page.goto("/register");
  await page.getByLabel("Organization").fill("Acme E2E");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);

  // ONLY the session cookie disappears — exactly what expiry, a sign-out on another device or
  // a password change look like. The CSRF token stays, but it is bound to a session that no
  // longer exists, so the backend bounces the mutation as 403 csrf_invalid.
  await context.clearCookies({ name: "session" });

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
});

test("dark mode is applied before the first paint", async ({ page }) => {
  // The class used to be set from a React effect, i.e. after hydration — several frames after
  // the browser had already painted the light theme. A dark-mode user saw a white flash on
  // every page load.
  await page.addInitScript(() => window.localStorage.setItem("theme", "dark"));

  await page.goto("/", { waitUntil: "commit" });
  await page.waitForFunction(() => document.readyState !== "loading");

  const applied = await page.evaluate(() => document.documentElement.classList.contains("dark"));
  expect(applied, "the theme has to be decided before hydration, not after").toBe(true);
});

test("an explicit theme choice survives a reload", async ({ page }) => {
  // `networkidle`, because a visible element proves nothing here: the header is server
  // rendered, so it appears long before React attaches any handlers. Clicking earlier lands on
  // dead markup.
  await page.goto("/", { waitUntil: "networkidle" });
  const toggle = page.getByRole("button", { name: /Switch to the (light|dark) theme/ });
  const wasDark = await page.evaluate(() => document.documentElement.classList.contains("dark"));

  await toggle.click();
  await expect
    .poll(() => page.evaluate(() => document.documentElement.classList.contains("dark")))
    .toBe(!wasDark);

  await page.reload();
  await expect
    .poll(() => page.evaluate(() => document.documentElement.classList.contains("dark")))
    .toBe(!wasDark);
});

test("an unknown API path answers with the shared error envelope", async ({ request }) => {
  // A client that has to recognize several error shapes handles some of them and falls back to
  // "something went wrong" on the rest.
  const response = await request.get("/api/no-such-resource");

  expect(response.status()).toBe(404);
  const body = await response.json();
  expect(body.code).toBe("not_found");
  expect(body.message).toBeTruthy();
  expect(body.request_id).toBe(response.headers()["x-request-id"]);
});

test("the server never renders a signed-out header it will have to take back", async ({ page }) => {
  // The session lives in a browser cookie, so the server cannot know it. Rendering "Sign in"
  // there means every signed-in visitor watches it flip after hydration — the flash this
  // placeholder exists to prevent.
  const response = await page.goto("/");
  const html = (await response?.text()) ?? "";
  // Only the header: the landing copy has its own permanent "Sign in" call to action, which is
  // not a statement about the session.
  const nav = html.match(/<nav[\s\S]*?<\/nav>/)?.[0] ?? "";

  expect(nav, "the server rendered a nav we could not parse").toContain("<button");
  expect(nav).not.toContain("Sign in");
  expect(nav).not.toContain("Sign out");
});

test("keyboard users can skip the header and land in the content", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  await page.keyboard.press("Tab");

  const skipLink = page.getByRole("link", { name: "Skip to content" });
  await expect(skipLink, "the skip link has to be the first tab stop").toBeFocused();
  // It stays invisible until focused, so it does not clutter the design.
  await expect(skipLink).toBeVisible();
});

test("focus moves to the content after a navigation", async ({ page }) => {
  // A single-page navigation changes no document, so a screen reader announces nothing and Tab
  // keeps going from the link that was clicked.
  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByRole("link", { name: "Sign in" }).last().click();
  await expect(page).toHaveURL(/\/login$/);

  await expect.poll(() => page.evaluate(() => document.activeElement?.id)).toBe("main-content");
});
