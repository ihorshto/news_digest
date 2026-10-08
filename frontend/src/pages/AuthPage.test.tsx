import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import AuthPage from "./AuthPage";
import { t } from "../i18n/uk";

function renderPage(mode: "login" | "register") {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AuthPage mode={mode} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AuthPage", () => {
  it("shows client-side validation errors without calling the API", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    renderPage("register");
    await userEvent.type(screen.getByLabelText(t.auth.email), "bad");
    await userEvent.type(screen.getByLabelText(t.auth.password), "short");
    await userEvent.click(screen.getByRole("button", { name: t.auth.registerButton }));
    expect(screen.getByText(t.auth.errors.emailInvalid)).toBeInTheDocument();
    expect(screen.getByText(t.auth.errors.passwordShort)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("shows server error message on invalid credentials", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/csrf"))
        return new Response(JSON.stringify({ csrf_token: "x" }), { status: 200 });
      return new Response(JSON.stringify({ detail: "invalid_credentials" }), { status: 401 });
    });
    renderPage("login");
    await userEvent.type(screen.getByLabelText(t.auth.email), "a@b.co");
    await userEvent.type(screen.getByLabelText(t.auth.password), "password123");
    await userEvent.click(screen.getByRole("button", { name: t.auth.loginButton }));
    expect(await screen.findByText(t.apiErrors.invalid_credentials)).toBeInTheDocument();
  });
});
