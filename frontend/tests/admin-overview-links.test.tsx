import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { hook } = vi.hoisted(() => ({ hook: { useAdminDashboard: vi.fn() } }));
vi.mock("@/hooks/useAdminDashboard", () => hook);

import { AdminOverview } from "@/components/admin/AdminOverview";
import { dashboard } from "./admin-fixtures";

beforeEach(() => {
  hook.useAdminDashboard.mockReturnValue({ data: dashboard(), loading: false, error: null, reload: vi.fn() });
});
afterEach(cleanup);

describe("overview links to the pages that now exist", () => {
  it("the headline cards link to Orders and Products", () => {
    render(<AdminOverview />);
    expect(within(screen.getByRole("group", { name: "Orders" })).getByRole("link", { name: "View orders" })).toHaveAttribute("href", "/admin/orders");
    expect(within(screen.getByRole("group", { name: "Products" })).getByRole("link", { name: "View products" })).toHaveAttribute("href", "/admin/products");
  });

  it("stock alerts link to the low and out-of-stock lists", () => {
    render(<AdminOverview />);
    const card = screen.getByRole("group", { name: "Stock alerts" });
    expect(within(card).getByRole("link", { name: "Low stock" })).toHaveAttribute("href", "/admin/inventory?stock=low");
    expect(within(card).getByRole("link", { name: "Out of stock" })).toHaveAttribute("href", "/admin/inventory?stock=out");
  });

  it("each status with orders links to that filtered list; zero counts are plain text", () => {
    render(<AdminOverview />);
    const section = screen.getByRole("heading", { name: "Orders by status" }).closest("div")!.parentElement!;
    expect(within(section).getByRole("link", { name: "Confirmed" })).toHaveAttribute("href", "/admin/orders?status=confirmed");
    expect(within(section).getByRole("link", { name: "Pending" })).toHaveAttribute("href", "/admin/orders?status=pending");
    expect(within(section).queryByRole("link", { name: "Delivered" })).toBeNull();
    expect(within(section).getByText("Delivered")).toBeInTheDocument();
  });

  it("an unknown status from the API is never linked", () => {
    hook.useAdminDashboard.mockReturnValue({
      data: dashboard({ orders: { total: 1, by_status: { weird: 1 } } }), loading: false, error: null, reload: vi.fn(),
    });
    render(<AdminOverview />);
    expect(screen.getByText("weird")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "weird" })).toBeNull();
  });

  it("recent orders link to the order, and there is a link to all orders", () => {
    render(<AdminOverview />);
    const table = screen.getByRole("table", { name: "The ten most recent orders" });
    expect(within(table).getByRole("link", { name: "PRM-2026-000123" })).toHaveAttribute("href", "/admin/orders/o1");
    expect(within(table).getByRole("link", { name: "Order" })).toHaveAttribute("href", "/admin/orders/o2");
    expect(screen.getByRole("link", { name: "View all orders" })).toHaveAttribute("href", "/admin/orders");
  });

  it("every admin link on the overview points at a page that exists", () => {
    render(<AdminOverview />);
    const known = /^\/admin(\/(orders|products|inventory)(\/[a-z0-9]+|\?(status|stock)=[a-z]+)?)?$/;
    for (const link of screen.getAllByRole("link")) expect(link.getAttribute("href")).toMatch(known);
  });
});
