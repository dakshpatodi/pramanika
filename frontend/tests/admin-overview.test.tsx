import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AdminDashboardState } from "@/hooks/useAdminDashboard";

const { state, reload } = vi.hoisted(() => ({
  state: { data: null, loading: true, error: null } as Omit<AdminDashboardState, "reload">,
  reload: vi.fn(),
}));
vi.mock("@/hooks/useAdminDashboard", () => ({ useAdminDashboard: () => ({ ...state, reload }) }));

import { AdminOverview } from "@/components/admin/AdminOverview";
import { dashboard } from "./admin-fixtures";

beforeEach(() => {
  Object.assign(state, { data: null, loading: true, error: null });
  reload.mockReset();
});
afterEach(cleanup);

const stat = (label: string) => within(screen.getByRole("group", { name: label }));

describe("AdminOverview", () => {
  it("shows one h1 and a loading skeleton first, with no refresh button yet", () => {
    render(<AdminOverview />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Overview");
    expect(screen.getByRole("status", { name: /loading the dashboard/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /refresh/i })).toBeNull();
  });

  it("shows the failure with a retry when nothing has loaded", () => {
    Object.assign(state, { loading: false, error: "The server is unhappy." });
    render(<AdminOverview />);
    expect(screen.getByRole("alert")).toHaveTextContent("The server is unhappy.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("shows the real numbers", () => {
    Object.assign(state, { loading: false, data: dashboard() });
    render(<AdminOverview />);
    expect(stat("Revenue, last 30 days").getByText("₹20,480.00")).toBeInTheDocument();
    expect(stat("Revenue, last 30 days").getByText("1 paid order")).toBeInTheDocument();
    expect(stat("Revenue, all time").getByText("₹1,25,432.50")).toBeInTheDocument();
    expect(stat("Revenue, all time").getByText(/10 paid orders/)).toBeInTheDocument();
    expect(stat("Orders").getByText("13")).toBeInTheDocument();
    expect(stat("Customers").getByText("40")).toBeInTheDocument();
    expect(stat("Customers").getByText("7 new in the last 30 days")).toBeInTheDocument();
    expect(stat("Products").getByText("30")).toBeInTheDocument();
    expect(stat("Products").getByText("27 active, 3 inactive")).toBeInTheDocument();
    expect(stat("Stock alerts").getByText("6")).toBeInTheDocument();
    expect(stat("Stock alerts").getByText("4 low, 2 out of stock")).toBeInTheDocument();
    expect(screen.getByText(/Updated 26 Oct 2026/)).toBeInTheDocument();
  });

  it("lists orders by status in a fixed order, zero included", () => {
    Object.assign(state, { loading: false, data: dashboard() });
    render(<AdminOverview />);
    const terms = screen.getAllByRole("term").map((t) => t.textContent);
    expect(terms).toEqual(["Pending", "Confirmed", "Processing", "Shipped", "Delivered", "Cancelled", "Refunded"]);
    const values = screen.getAllByRole("definition").map((d) => d.textContent);
    expect(values).toEqual(["2", "5", "0", "3", "0", "3", "0"]);
  });

  it("shows a status the UI does not know about instead of hiding it", () => {
    Object.assign(state, { loading: false, data: dashboard({ orders: { total: 1, by_status: { on_hold: 1 } } }) });
    render(<AdminOverview />);
    expect(screen.getByText("on_hold")).toBeInTheDocument();
  });

  it("shows recent orders with customer, status badges, total and date", () => {
    Object.assign(state, { loading: false, data: dashboard() });
    render(<AdminOverview />);
    const table = screen.getByRole("table", { name: /ten most recent orders/i });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("PRM-2026-000123")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Asha Rao")).toBeInTheDocument();
    expect(within(rows[0]).getByText("asha@example.com")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Confirmed")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Paid")).toBeInTheDocument();
    expect(within(rows[0]).getByText("₹1,049.50")).toBeInTheDocument();
    expect(within(rows[0]).getByText(/25 Oct 2026/)).toBeInTheDocument();
    expect(within(rows[1]).getByText("Order")).toBeInTheDocument();        // no number yet
    expect(within(rows[1]).getByText("Payment pending")).toBeInTheDocument();
  });

  it("falls back to plain text for a status the badge does not know", () => {
    const data = dashboard();
    data.recent_orders[0].status = "on_hold";
    Object.assign(state, { loading: false, data });
    render(<AdminOverview />);
    expect(screen.getByText("on_hold / paid")).toBeInTheDocument();
  });

  it("has a proper empty state for a brand-new shop", () => {
    Object.assign(state, {
      loading: false,
      data: dashboard({
        orders: { total: 0, by_status: {} }, recent_orders: [],
        revenue: { currency: "INR", all_time: 0, all_time_orders: 0, last_30_days: 0, last_30_days_orders: 0 },
        products: { total: 0, active: 0, inactive: 0, low_stock: 0, out_of_stock: 0 },
        customers: { total: 0, new_last_30_days: 0 },
      }),
    });
    render(<AdminOverview />);
    expect(screen.getByText("No orders yet.")).toBeInTheDocument();                 // breakdown
    expect(screen.getByText("New orders will appear here as customers check out.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
    expect(stat("Revenue, all time").getByText("₹0.00")).toBeInTheDocument();
    expect(stat("Stock alerts").getByText("0")).toBeInTheDocument();
  });

  it("refreshes on request, disables the button meanwhile, and keeps the numbers on screen", () => {
    Object.assign(state, { loading: false, data: dashboard() });
    const { rerender } = render(<AdminOverview />);
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(reload).toHaveBeenCalledTimes(1);
    Object.assign(state, { loading: true });
    rerender(<AdminOverview />);
    expect(screen.getByRole("button", { name: "Refreshing" })).toBeDisabled();
    expect(stat("Orders").getByText("13")).toBeInTheDocument();
  });

  it("warns when a refresh failed but still shows the last numbers", () => {
    Object.assign(state, { loading: false, data: dashboard(), error: "Network down." });
    render(<AdminOverview />);
    expect(screen.getByRole("alert")).toHaveTextContent("Network down.");
    expect(screen.getByRole("alert")).toHaveTextContent(/last successful load/i);
    expect(stat("Orders").getByText("13")).toBeInTheDocument();
  });
});
