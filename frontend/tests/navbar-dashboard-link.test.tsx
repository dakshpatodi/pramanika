import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { auth } = vi.hoisted(() => ({
  auth: { user: null as unknown, isLoading: false, isAuthenticated: false, logout: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/context/CartContext", () => ({ useCart: () => ({ itemCount: 0 }) }));

import { Navbar } from "@/components/layout/Navbar";

beforeEach(() => {
  auth.user = { first_name: "Asha" };
  auth.isAuthenticated = true;
});
afterEach(cleanup);

describe("Navbar account links", () => {
  it("sends the signed-in user's name to the dashboard, not straight to the profile", () => {
    render(<Navbar />);
    const links = screen.getAllByRole("link", { name: "Asha" });
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) expect(link).toHaveAttribute("href", "/dashboard");
    expect(document.querySelector('a[href="/profile"]')).toBeNull();
  });

  it("still offers Orders and the login link when signed out", () => {
    render(<Navbar />);
    expect(screen.getAllByRole("link", { name: "Orders" })[0]).toHaveAttribute("href", "/orders");
    cleanup();
    auth.user = null;
    auth.isAuthenticated = false;
    render(<Navbar />);
    expect(screen.getAllByRole("link", { name: "Login" })[0]).toHaveAttribute("href", "/login");
  });
});
