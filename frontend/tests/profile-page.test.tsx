import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { User } from "@/types/auth";

const { auth, router } = vi.hoisted(() => ({
  auth: { user: null as unknown, isLoading: false, isAuthenticated: true, logout: vi.fn(), updateUser: vi.fn() },
  router: { push: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/profile" }));
vi.mock("@/services/profile", () => ({ updateProfile: vi.fn() }));

import ProfilePage from "@/app/profile/page";

const user: User = {
  id: "u1", first_name: "Asha", last_name: "Rao", email: "asha@example.com", phone_number: "+919876543210",
  role: "customer", is_active: true, is_verified: true, last_login: null, created_at: "2026-01-15T00:00:00Z",
};

beforeEach(() => {
  auth.user = user;
  auth.isLoading = false;
  auth.isAuthenticated = true;
  auth.logout.mockReset();
  router.push.mockReset();
});
afterEach(cleanup);

describe("Profile page", () => {
  it("shows the account inside the dashboard frame with the Profile item current", () => {
    render(<ProfilePage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Profile");
    const menu = within(screen.getByRole("navigation", { name: "Account" }));
    expect(menu.getByRole("link", { name: "Profile" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Asha Rao")).toBeInTheDocument();
    expect(screen.getByText("AR")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByText("Member since")).toBeInTheDocument();
    expect(screen.getByText("Never")).toBeInTheDocument(); // last login
  });

  it("includes the edit form with the user's real values", () => {
    render(<ProfilePage />);
    expect((screen.getByLabelText("First name") as HTMLInputElement).value).toBe("Asha");
    expect(screen.getByLabelText("Email")).toHaveAttribute("readonly");
  });

  it("still lets the user log out", () => {
    render(<ProfilePage />);
    screen.getByRole("button", { name: /log out/i }).click();
    expect(auth.logout).toHaveBeenCalledTimes(1);
  });

  it("renders nothing and sends a visitor to log in", () => {
    auth.user = null;
    auth.isAuthenticated = false;
    const { container } = render(<ProfilePage />);
    expect(container).toBeEmptyDOMElement();
    expect(router.push).toHaveBeenCalledWith("/login?redirect=%2Fprofile");
  });

  it("shows only a spinner while the session is being restored", () => {
    auth.isLoading = true;
    auth.user = null;
    auth.isAuthenticated = false;
    render(<ProfilePage />);
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    expect(screen.queryByLabelText("Email")).toBeNull();
  });
});
