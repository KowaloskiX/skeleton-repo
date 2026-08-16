import { screen } from "@testing-library/react";
import { API_ORIGIN, server } from "@tests/msw-server";
import { renderInRouter } from "@tests/render";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { SystemReadout } from "@/features/system";

describe("SystemReadout", () => {
  it("shows the state reported by /api/health", async () => {
    await renderInRouter(<SystemReadout />);
    expect(await screen.findByText("ok · test")).toBeInTheDocument();
  });

  it("does not pretend the API works when the backend does not answer", async () => {
    server.use(http.get(`${API_ORIGIN}/api/health`, () => HttpResponse.json({}, { status: 503 })));
    await renderInRouter(<SystemReadout />);
    expect(await screen.findByText("no response")).toBeInTheDocument();
  });

  it("shows the email of the signed-in user", async () => {
    server.use(
      http.get(`${API_ORIGIN}/api/auth/session`, () =>
        HttpResponse.json({
          user: { id: crypto.randomUUID(), email: "owner@example.com", organizations: [] },
        }),
      ),
    );
    await renderInRouter(<SystemReadout />);
    expect(await screen.findByText("owner@example.com")).toBeInTheDocument();
  });
});
