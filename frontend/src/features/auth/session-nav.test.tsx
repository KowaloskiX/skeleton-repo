import { screen, waitFor } from "@testing-library/react";
import { API_ORIGIN, server } from "@tests/msw-server";
import { delay, HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { SessionNav } from "@/features/auth";

const USER = { id: crypto.randomUUID(), email: "owner@example.com", organizations: [] };

describe("SessionNav", () => {
  it("shows neither state while the session is still unknown", async () => {
    // The session query runs on the client, so the first paint has no answer. Rendering the
    // signed-out variant then makes every signed-in user see "Sign in" flash before it swaps.
    server.use(
      http.get(`${API_ORIGIN}/api/auth/session`, async () => {
        await delay(100);
        return HttpResponse.json({ user: USER });
      }),
    );

    await renderNav();

    expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();

    // …and once the answer arrives, the signed-in variant appears.
    expect(await screen.findByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("shows the sign-in links for an anonymous visitor", async () => {
    await renderNav();
    expect(await screen.findByRole("link", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create account" })).toBeInTheDocument();
  });

  it("shows the email and a sign-out button for a signed-in user", async () => {
    server.use(http.get(`${API_ORIGIN}/api/auth/session`, () => HttpResponse.json({ user: USER })));
    await renderNav();

    await waitFor(() => expect(screen.getByText(USER.email)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });
});

async function renderNav() {
  const { renderInRouter } = await import("@tests/render");
  return renderInRouter(<SessionNav />);
}
