import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { push, login, query } = vi.hoisted(() => ({ push: vi.fn(), login: vi.fn(), query: { value: "" } }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(query.value),
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ login }) }));

import LoginPage from "@/app/login/page";

async function logIn(search: string) {
  query.value = search;
  render(<LoginPage />);
  fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "a@b.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Secret123!" } });
  fireEvent.click(screen.getByRole("button", { name: /Log In/ }));
  await waitFor(() => expect(push).toHaveBeenCalled());
}

beforeEach(() => {
  push.mockReset();
  login.mockReset();
  login.mockResolvedValue(undefined);
});
afterEach(cleanup);

describe("login: where you land afterwards", () => {
  it("returns to the page that asked for the login", async () => {
    await logIn("redirect=%2Fadmin%2Forders");
    expect(push).toHaveBeenCalledWith("/admin/orders");
  });

  it("goes home when nothing was asked", async () => {
    await logIn("");
    expect(push).toHaveBeenCalledWith("/");
  });

  it.each(["https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)"])("never follows %s", async (target) => {
    await logIn(`redirect=${encodeURIComponent(target)}`);
    expect(push).toHaveBeenCalledWith("/");
  });
});
