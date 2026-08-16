import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { API_ORIGIN, server } from "@tests/msw-server";
import { renderInRouter } from "@tests/render";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { LoginForm } from "@/features/auth";

const VALID_PASSWORD = "correct-horse-battery-staple";

describe("LoginForm", () => {
  it("validates the email before sending a request", async () => {
    const user = userEvent.setup();
    await renderInRouter(<LoginForm />);

    await user.type(screen.getByLabelText("Email"), "not-an-email");
    await user.type(screen.getByLabelText("Password"), VALID_PASSWORD);
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText(/Enter an email address/)).toBeInTheDocument();
  });

  it("shows the API error message for bad credentials", async () => {
    server.use(
      http.post(`${API_ORIGIN}/api/auth/login`, () =>
        HttpResponse.json(
          { code: "invalid_credentials", message: "Invalid email or password." },
          { status: 401 },
        ),
      ),
    );
    const user = userEvent.setup();
    await renderInRouter(<LoginForm />);

    await user.type(screen.getByLabelText("Email"), "owner@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
  });

  it("goes to the dashboard after a successful sign-in", async () => {
    server.use(
      http.post(`${API_ORIGIN}/api/auth/login`, () =>
        HttpResponse.json({
          id: crypto.randomUUID(),
          email: "owner@example.com",
          organizations: [],
        }),
      ),
    );
    const user = userEvent.setup();
    const { navigatedTo } = await renderInRouter(<LoginForm />);

    await user.type(screen.getByLabelText("Email"), "owner@example.com");
    await user.type(screen.getByLabelText("Password"), VALID_PASSWORD);
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(navigatedTo()).toBe("/app"));
  });
});
