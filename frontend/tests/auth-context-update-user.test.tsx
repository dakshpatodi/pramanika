import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { User } from "@/types/auth";

const { api, tokens } = vi.hoisted(() => ({
  api: { getCurrentUser: vi.fn(), loginUser: vi.fn(), logoutUser: vi.fn(), registerUser: vi.fn() },
  tokens: { getAccessToken: vi.fn(), getRefreshToken: vi.fn(), clearTokens: vi.fn() },
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/services/auth", () => api);
vi.mock("@/lib/token-storage", () => ({ tokenStorage: tokens }));

import { AuthProvider, useAuth } from "@/context/AuthContext";

const user = (over: Partial<User> = {}): User => ({
  id: "u1", first_name: "Asha", last_name: "Rao", email: "asha@example.com", phone_number: "9876543210",
  role: "customer", is_active: true, is_verified: false, last_login: null, created_at: "2026-01-01T00:00:00Z", ...over,
});

let ctx!: ReturnType<typeof useAuth>;
function Probe() {
  ctx = useAuth();
  return <p data-testid="name">{ctx.user ? ctx.user.first_name : "nobody"}</p>;
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  tokens.getAccessToken.mockReturnValue("token");
  tokens.getRefreshToken.mockReturnValue("refresh");
});
afterEach(cleanup);

async function signedIn() {
  api.getCurrentUser.mockResolvedValue(user());
  render(<AuthProvider><Probe /></AuthProvider>);
  await waitFor(() => expect(screen.getByTestId("name")).toHaveTextContent("Asha"));
}

describe("AuthContext.updateUser", () => {
  it("replaces the signed-in user so every consumer sees the new profile", async () => {
    await signedIn();
    act(() => ctx.updateUser(user({ first_name: "Meera" })));
    expect(screen.getByTestId("name")).toHaveTextContent("Meera");
    expect(ctx.isAuthenticated).toBe(true);
  });

  it("ignores a copy that belongs to a different account", async () => {
    await signedIn();
    act(() => ctx.updateUser(user({ id: "someone-else", first_name: "Intruder" })));
    expect(screen.getByTestId("name")).toHaveTextContent("Asha");
  });

  it("cannot sign anyone in when nobody is signed in", async () => {
    tokens.getAccessToken.mockReturnValue(null);
    tokens.getRefreshToken.mockReturnValue(null);
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(ctx.isLoading).toBe(false));
    act(() => ctx.updateUser(user()));
    expect(screen.getByTestId("name")).toHaveTextContent("nobody");
    expect(ctx.isAuthenticated).toBe(false);
  });

  it("cannot bring a user back after logout (a late save response)", async () => {
    await signedIn();
    api.logoutUser.mockResolvedValue(undefined);
    await act(async () => { await ctx.logout(); });
    expect(screen.getByTestId("name")).toHaveTextContent("nobody");
    act(() => ctx.updateUser(user({ first_name: "Late" })));
    expect(screen.getByTestId("name")).toHaveTextContent("nobody");
  });

  it("keeps the same function between renders so effects that use it do not re-run", async () => {
    await signedIn();
    const first = ctx.updateUser;
    act(() => ctx.updateUser(user({ first_name: "Meera" })));
    expect(ctx.updateUser).toBe(first);
  });
});
