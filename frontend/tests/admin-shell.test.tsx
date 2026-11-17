import { cleanup, render, screen, within } from "@testing-library/react";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { Package } from "lucide-react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { nav } = vi.hoisted(() => ({ nav: { pathname: "/admin" as string | null } }));
vi.mock("next/navigation", () => ({ usePathname: () => nav.pathname }));

import { ADMIN_NAV, isActiveAdminItem, type AdminNavItem } from "@/components/admin/admin-nav";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { AdminShell } from "@/components/admin/AdminShell";

afterEach(cleanup);

const ITEMS: AdminNavItem[] = [
  { label: "Overview", href: "/admin", icon: Package, matchPrefix: false },
  { label: "Orders", href: "/admin/orders", icon: Package, matchPrefix: true },
  { label: "Products", href: "/admin/products", icon: Package, matchPrefix: true },
];

function renderAt(pathname: string | null, items = ITEMS) {
  nav.pathname = pathname;
  render(<AdminShell items={items}><p>page body</p></AdminShell>);
  return within(screen.getByRole("navigation", { name: "Admin" }));
}

describe("AdminShell", () => {
  it("has a labelled Admin menu and renders the page beside it", () => {
    const menu = renderAt("/admin");
    expect(menu.getAllByRole("link").map((l) => l.textContent)).toEqual(["Overview", "Orders", "Products"]);
    expect(screen.getByText("page body")).toBeInTheDocument();
  });

  it("links to real admin routes only", () => {
    const menu = renderAt("/admin");
    for (const link of menu.getAllByRole("link")) expect(link.getAttribute("href")).toMatch(/^\/admin(\/[a-z-]+)?$/);
  });

  it.each([
    ["/admin", "Overview"],
    ["/admin/orders", "Orders"],
    ["/admin/orders/abc-123", "Orders"],
    ["/admin/products", "Products"],
    ["/admin/products/new", "Products"],
  ])("marks exactly one item current at %s", (path, label) => {
    const menu = renderAt(path);
    const current = menu.getAllByRole("link").filter((l) => l.getAttribute("aria-current") === "page");
    expect(current.map((l) => l.textContent)).toEqual([label]);
  });

  it("does not highlight Overview on a deeper page, and handles an unknown path", () => {
    expect(isActiveAdminItem(ITEMS[0], "/admin/orders")).toBe(false);
    expect(isActiveAdminItem(ITEMS[1], "/admin/orders-archive")).toBe(false);
    expect(isActiveAdminItem(ITEMS[1], null)).toBe(false);
    const menu = renderAt("/somewhere-else");
    expect(menu.getAllByRole("link").some((l) => l.hasAttribute("aria-current"))).toBe(false);
  });

  it("the real menu starts with Overview at /admin", () => {
    expect(ADMIN_NAV[0]).toMatchObject({ label: "Overview", href: "/admin" });
    expect(new Set(ADMIN_NAV.map((i) => i.href)).size).toBe(ADMIN_NAV.length);
    const hrefs = ADMIN_NAV.map((i) => i.href);
    expect(hrefs).toEqual(expect.arrayContaining(["/admin/orders", "/admin/products", "/admin/categories", "/admin/inventory"]));
    for (const item of ADMIN_NAV.filter((i) => i.href !== "/admin")) expect(item.matchPrefix).toBe(true);
  });
});

describe("AdminPageHeader", () => {
  it("is the page's one h1, with a description and actions", () => {
    render(<AdminPageHeader title="Products" description="Everything we sell" actions={<button>New</button>} />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Products");
    expect(screen.getByText("Everything we sell")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New" })).toBeInTheDocument();
  });
});

describe("the guard lives in the layout", () => {
  const ADMIN_DIR = resolve(process.cwd(), "src/app/admin");
  const files = (dir: string): string[] =>
    readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? files(join(dir, n)) : [join(dir, n)]));

  it("wraps every admin page in AdminRoute", () => {
    const layout = readFileSync(join(ADMIN_DIR, "layout.tsx"), "utf8");
    expect(layout).toMatch(/<AdminRoute>[\s\S]*\{children\}[\s\S]*<\/AdminRoute>/);
  });

  it("has no admin page that sits outside the layout or hand-rolls its own check", () => {
    const pages = files(ADMIN_DIR).filter((f) => /page\.tsx$/.test(f));
    expect(pages.length).toBeGreaterThan(0);
    for (const page of pages) {
      const source = readFileSync(page, "utf8");
      expect(source).not.toMatch(/role\s*===/);                    // role checks belong in AdminRoute only
      expect(source).not.toMatch(/ProtectedRoute/);
    }
  });
});
