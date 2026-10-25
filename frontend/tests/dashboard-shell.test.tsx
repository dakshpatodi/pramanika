import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { nav } = vi.hoisted(() => ({ nav: { pathname: "/dashboard" as string | null } }));
vi.mock("next/navigation", () => ({ usePathname: () => nav.pathname }));

import { DASHBOARD_NAV, isActiveNavItem } from "@/components/dashboard/dashboard-nav";
import { DashboardShell } from "@/components/dashboard/DashboardShell";

afterEach(cleanup);

function renderAt(pathname: string | null) {
  nav.pathname = pathname;
  render(<DashboardShell title="Anything" description="About this page"><p>page body</p></DashboardShell>);
  return within(screen.getByRole("navigation", { name: "Account" }));
}

describe("DashboardShell", () => {
  it("has one h1 (the page title), the description, the body, and a labelled account menu", () => {
    const menu = renderAt("/dashboard");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Anything");
    expect(screen.getByText("About this page")).toBeInTheDocument();
    expect(screen.getByText("page body")).toBeInTheDocument();
    expect(menu.getAllByRole("link").map((l) => l.textContent)).toEqual([
      "Overview", "Profile", "Orders", "Wishlist", "Saved addresses", "Invoices",
    ]);
  });

  it("links to the real routes", () => {
    const menu = renderAt("/dashboard");
    expect(menu.getByRole("link", { name: "Overview" })).toHaveAttribute("href", "/dashboard");
    expect(menu.getByRole("link", { name: "Profile" })).toHaveAttribute("href", "/profile");
    expect(menu.getByRole("link", { name: "Orders" })).toHaveAttribute("href", "/orders");
    expect(menu.getByRole("link", { name: "Wishlist" })).toHaveAttribute("href", "/dashboard/wishlist");
    expect(menu.getByRole("link", { name: "Saved addresses" })).toHaveAttribute("href", "/dashboard/addresses");
    expect(menu.getByRole("link", { name: "Invoices" })).toHaveAttribute("href", "/dashboard/invoices");
  });

  it.each([
    ["/dashboard", "Overview"],
    ["/profile", "Profile"],
    ["/orders", "Orders"],
    ["/orders/abc-123", "Orders"],
    ["/dashboard/wishlist", "Wishlist"],
    ["/dashboard/addresses", "Saved addresses"],
    ["/dashboard/invoices", "Invoices"],
  ])("marks exactly one item as the current page at %s", (path, label) => {
    const menu = renderAt(path);
    const current = menu.getAllByRole("link").filter((l) => l.getAttribute("aria-current") === "page");
    expect(current.map((l) => l.textContent)).toEqual([label]);
  });

  it("marks nothing as current on a path outside the menu", () => {
    const menu = renderAt("/somewhere-else");
    expect(menu.getAllByRole("link").some((l) => l.hasAttribute("aria-current"))).toBe(false);
    cleanup();
    expect(renderAt(null).getAllByRole("link").some((l) => l.hasAttribute("aria-current"))).toBe(false);
  });

  it("draws no heading of its own when a page brings its own h1 (order detail)", () => {
    nav.pathname = "/orders/abc";
    render(<DashboardShell><h1>PRM-2026-000042</h1></DashboardShell>);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("PRM-2026-000042");
    expect(screen.getByRole("navigation", { name: "Account" })).toBeInTheDocument();
  });

  it("omits the description when there is none", () => {
    nav.pathname = "/dashboard";
    render(<DashboardShell title="T"><p>x</p></DashboardShell>);
    expect(document.querySelector("h1 + p")).toBeNull();
  });
});

describe("isActiveNavItem", () => {
  const overview = DASHBOARD_NAV[0];
  const orders = DASHBOARD_NAV[2];
  it("matches Overview only on its own path, so it does not light up for every account page", () => {
    expect(isActiveNavItem(overview, "/dashboard")).toBe(true);
    expect(isActiveNavItem(overview, "/dashboard/wishlist")).toBe(false);
  });
  it("matches a section's children but not look-alike paths", () => {
    expect(isActiveNavItem(orders, "/orders/1")).toBe(true);
    expect(isActiveNavItem(orders, "/orders-archive")).toBe(false);
  });
});
