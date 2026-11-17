import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AxiosError } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { auth, router, getAdminMe } = vi.hoisted(() => ({
  auth: { user: null as unknown as { id: string; role: string } | null, isLoading: false, isAuthenticated: false },
  router: { push: vi.fn() },
  getAdminMe: vi.fn(),
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/admin/products" }));
vi.mock("@/services/admin", () => ({ getAdminMe }));

import { AdminRoute } from "@/components/admin/AdminRoute";

function signIn(role: string, id = "u1") {
  auth.user = { id, role };
  auth.isAuthenticated = true;
  auth.isLoading = false;
}
function httpError(status: number) {
  return new AxiosError("x", "ERR", undefined, undefined, {
    status, data: { success: false, message: "Admin access required." }, statusText: "", headers: {}, config: {} as never,
  });
}
const SECRET = "admin-only-content";
const page = () => (
  <AdminRoute>
    <p>{SECRET}</p>
  </AdminRoute>
);

beforeEach(() => {
  auth.user = null;
  auth.isAuthenticated = false;
  auth.isLoading = false;
  router.push.mockReset();
  getAdminMe.mockReset();
});
afterEach(cleanup);

describe("AdminRoute", () => {
  it("shows a spinner while the session is being restored, and asks the server nothing", () => {
    auth.isLoading = true;
    render(page());
    expect(document.querySelector(".animate-spin")).not.toBeNull();
    expect(screen.queryByText(SECRET)).toBeNull();
    expect(getAdminMe).not.toHaveBeenCalled();
    expect(router.push).not.toHaveBeenCalled();
  });

  it("sends a signed-out visitor to login, remembering where they were going, and renders nothing", async () => {
    render(page());
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/login?redirect=%2Fadmin%2Fproducts"));
    expect(screen.queryByText(SECRET)).toBeNull();
    expect(getAdminMe).not.toHaveBeenCalled();
  });

  it("turns a customer away without a request and never renders the page", () => {
    signIn("customer");
    render(page());
    expect(screen.getByRole("heading", { level: 1, name: /don.t have access/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the shop" })).toHaveAttribute("href", "/");
    expect(screen.queryByText(SECRET)).toBeNull();
    expect(getAdminMe).not.toHaveBeenCalled();
    expect(router.push).not.toHaveBeenCalled();     // told, not bounced to login
  });

  it("shows the page only after the server confirms the admin role", async () => {
    signIn("admin");
    let resolve!: (v: unknown) => void;
    getAdminMe.mockReturnValue(new Promise((r) => (resolve = r)));
    render(page());
    expect(screen.queryByText(SECRET)).toBeNull();                       // not while checking
    expect(screen.getByRole("status", { name: /checking/i })).toBeInTheDocument();
    resolve({ id: "u1", email: "a@x.com", first_name: "A", last_name: "B", role: "admin" });
    expect(await screen.findByText(SECRET)).toBeInTheDocument();
    expect(getAdminMe).toHaveBeenCalledTimes(1);
  });

  it("trusts the server over the cached role: a demoted admin gets 403 and sees no page", async () => {
    signIn("admin");
    getAdminMe.mockRejectedValue(httpError(403));
    render(page());
    expect(await screen.findByRole("heading", { level: 1, name: /don.t have access/i })).toBeInTheDocument();
    expect(screen.queryByText(SECRET)).toBeNull();
  });

  it("refuses when the server answers with a role that is not admin, or a different account", async () => {
    signIn("admin");
    getAdminMe.mockResolvedValue({ id: "u1", email: "a@x.com", first_name: "A", last_name: "B", role: "customer" });
    render(page());
    expect(await screen.findByText(/don.t have access/i)).toBeInTheDocument();
    cleanup();
    getAdminMe.mockResolvedValue({ id: "someone-else", email: "a@x.com", first_name: "A", last_name: "B", role: "admin" });
    render(page());
    expect(await screen.findByText(/don.t have access/i)).toBeInTheDocument();
    expect(screen.queryByText(SECRET)).toBeNull();
  });

  it("on a network or server error shows a message and lets the admin retry", async () => {
    signIn("admin");
    getAdminMe.mockRejectedValueOnce(httpError(500));
    render(page());
    expect(await screen.findByRole("alert")).toHaveTextContent("Admin access required.");
    expect(screen.queryByText(SECRET)).toBeNull();
    getAdminMe.mockResolvedValue({ id: "u1", email: "a@x.com", first_name: "A", last_name: "B", role: "admin" });
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(SECRET)).toBeInTheDocument();
  });

  it("re-checks when a different account signs in, and drops the page when access is lost", async () => {
    signIn("admin", "u1");
    getAdminMe.mockResolvedValue({ id: "u1", email: "a@x.com", first_name: "A", last_name: "B", role: "admin" });
    const { rerender } = render(page());
    expect(await screen.findByText(SECRET)).toBeInTheDocument();
    signIn("customer", "u2");
    rerender(page());
    await waitFor(() => expect(screen.queryByText(SECRET)).toBeNull());
    expect(screen.getByText(/don.t have access/i)).toBeInTheDocument();
  });

  it("ignores a late answer for a previous account", async () => {
    signIn("admin", "u1");
    let resolveFirst!: (v: unknown) => void;
    getAdminMe.mockReturnValueOnce(new Promise((r) => (resolveFirst = r)));
    const { rerender } = render(page());
    signIn("customer", "u2");
    rerender(page());
    resolveFirst({ id: "u1", email: "a@x.com", first_name: "A", last_name: "B", role: "admin" });
    await new Promise((r) => setTimeout(r, 10));
    expect(screen.queryByText(SECRET)).toBeNull();
  });
});
