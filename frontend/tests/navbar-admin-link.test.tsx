import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { vi } from "vitest";

const { auth } = vi.hoisted(() => ({
  auth: { user: null as unknown, isLoading: false, isAuthenticated: true, logout: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/context/CartContext", () => ({ useCart: () => ({ itemCount: 0 }) }));

import { Navbar } from "@/components/layout/Navbar";

afterEach(cleanup);

describe("Navbar admin link", () => {
  it("shows Admin (desktop and mobile) to an admin only", () => {
    auth.user = { first_name: "Asha", role: "admin" };
    render(<Navbar />);
    const links = screen.getAllByRole("link", { name: "Admin" });
    expect(links.length).toBe(2);
    for (const link of links) expect(link).toHaveAttribute("href", "/admin");
  });

  it.each([["customer"], [undefined]])("hides it from a %s", (role) => {
    auth.user = { first_name: "Asha", role };
    render(<Navbar />);
    expect(screen.queryByRole("link", { name: "Admin" })).toBeNull();
  });

  it("hides it when signed out", () => {
    auth.user = null;
    auth.isAuthenticated = false;
    render(<Navbar />);
    expect(screen.queryByRole("link", { name: "Admin" })).toBeNull();
    auth.isAuthenticated = true;
  });
});
