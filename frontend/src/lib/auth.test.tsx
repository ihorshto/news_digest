import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import AuthPage from "../pages/AuthPage";
import { t } from "../i18n/uk";
import { RedirectIfAuthed } from "./auth";

const USER = {
  id: 1,
  email: "a@b.co",
  timezone: "Europe/Paris",
  telegram_linked: false,
  telegram_username: null,
  telegram_blocked: false,
  created_at: "2026-10-08T00:00:00Z",
};

function mockApi(loggedIn: boolean) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/api/auth/csrf")) return Response.json({ csrf_token: "x" });
    if (url.endsWith("/api/auth/me"))
      return loggedIn ? Response.json(USER) : Response.json({ detail: "x" }, { status: 401 });
    if (url.endsWith("/api/auth/register")) return Response.json(USER, { status: 201 });
    throw new Error(`unexpected ${url}`);
  });
}

function renderAt(path: string) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/register"
            element={
              <RedirectIfAuthed>
                <AuthPage mode="register" />
              </RedirectIfAuthed>
            }
          />
          <Route path="/topics/new" element={<p>new-topic-page</p>} />
          <Route path="/" element={<p>dashboard-page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("auth redirects", () => {
  it("sends a freshly registered user to the new-topic page", async () => {
    mockApi(false);
    renderAt("/register");
    await userEvent.type(await screen.findByLabelText(t.auth.email), "a@b.co");
    await userEvent.type(screen.getByLabelText(t.auth.password), "password123");
    await userEvent.type(screen.getByLabelText(t.auth.passwordConfirm), "password123");
    await userEvent.click(screen.getByRole("button", { name: t.auth.registerButton }));
    expect(await screen.findByText("new-topic-page")).toBeInTheDocument();
  });

  it("sends an already signed-in visitor to the dashboard", async () => {
    mockApi(true);
    renderAt("/register");
    expect(await screen.findByText("dashboard-page")).toBeInTheDocument();
  });
});
