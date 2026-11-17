import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { api, auth } = vi.hoisted(() => ({
  api: { listAdminOrders: vi.fn() },
  auth: { user: { id: "u1" }, isLoading: false },
}));
vi.mock("@/services/admin-orders", () => ({ listAdminOrders: api.listAdminOrders }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));

import { OrdersList } from "@/components/admin/orders/OrdersList";
import { orderListItem, pagination } from "./admin-fixtures";

const page = (orders = [orderListItem()], meta = {}) => ({ orders, pagination: pagination({ total: orders.length, ...meta }) });
const last = () => api.listAdminOrders.mock.calls[api.listAdminOrders.mock.calls.length - 1][0];

beforeEach(() => {
  api.listAdminOrders.mockReset();
  api.listAdminOrders.mockResolvedValue(page());
});
afterEach(cleanup);

describe("OrdersList", () => {
  it("shows a skeleton, then orders with number, customer, badge, items, total, and the next step", async () => {
    render(<OrdersList />);
    expect(screen.getByRole("status", { name: "Loading orders" })).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Orders" });
    const row = within(table).getAllByRole("row")[1];
    expect(within(row).getByRole("link", { name: "PRM-2026-000123" })).toHaveAttribute("href", "/admin/orders/o1");
    expect(within(row).getByText("Asha Rao")).toBeInTheDocument();
    expect(within(row).getByText("asha@example.com")).toBeInTheDocument();
    expect(within(row).getByText("Confirmed")).toBeInTheDocument();
    expect(within(row).getByText("Paid")).toBeInTheDocument();
    expect(within(row).getByText("3")).toBeInTheDocument();
    expect(within(row).getByText("₹1,049.50")).toBeInTheDocument();
    expect(within(row).getByText("Next: processing")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "View order PRM-2026-000123" })).toHaveAttribute("href", "/admin/orders/o1");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("shows an expired order as Expired, no next step, and an unnumbered order as 'Order'", async () => {
    api.listAdminOrders.mockResolvedValue(page([
      orderListItem({ id: "x", order_number: null, status: "cancelled", payment_status: "pending", cancellation_reason: "expired", next_status: null }),
    ]));
    render(<OrdersList />);
    const row = within(await screen.findByRole("table")).getAllByRole("row")[1];
    expect(within(row).getByText("Expired")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Order" })).toHaveAttribute("href", "/admin/orders/x");
    expect(within(row).queryByText(/^Next:/)).toBeNull();
  });

  it("starts unfiltered, newest first", async () => {
    render(<OrdersList />);
    await screen.findByRole("table");
    expect(last()).toEqual({ page: 1, page_size: 20, sort: "created_at", order: "desc" });
  });

  it("opens pre-filtered from a link (?status=pending)", async () => {
    render(<OrdersList initialStatus="pending" />);
    await screen.findByRole("table");
    expect(last().status).toBe("pending");
    expect(screen.getByLabelText("Status")).toHaveValue("pending");
  });

  it("sends status, payment and sort, and returns to page 1 on each change", async () => {
    api.listAdminOrders.mockResolvedValue(page([orderListItem()], { total: 60, total_pages: 3, has_next: true }));
    render(<OrdersList />);
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    await waitFor(() => expect(last().page).toBe(3));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "shipped" } });
    await waitFor(() => expect(last()).toMatchObject({ status: "shipped", page: 1 }));
    fireEvent.change(screen.getByLabelText("Payment"), { target: { value: "paid" } });
    await waitFor(() => expect(last().payment_status).toBe("paid"));
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "total-desc" } });
    await waitFor(() => expect(last()).toMatchObject({ sort: "total", order: "desc", status: "shipped", payment_status: "paid" }));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "" } });
    await waitFor(() => expect(last().status).toBeUndefined());
  });

  it("search is sent trimmed on submit and goes back to page 1", async () => {
    api.listAdminOrders.mockResolvedValue(page([orderListItem()], { total: 60, total_pages: 3, has_next: true }));
    render(<OrdersList />);
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "2" }));
    await waitFor(() => expect(last().page).toBe(2));
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "  PRM-2026  " } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(last()).toMatchObject({ search: "PRM-2026", page: 1 }));
  });

  it("placed-from / placed-to become whole days in India time", async () => {
    render(<OrdersList />);
    await screen.findByRole("table");
    fireEvent.change(screen.getByLabelText("Placed from"), { target: { value: "2026-10-01" } });
    await waitFor(() => expect(last().created_from).toBe("2026-10-01T00:00:00+05:30"));
    fireEvent.change(screen.getByLabelText("Placed to"), { target: { value: "2026-10-31" } });
    await waitFor(() => expect(last()).toMatchObject({ created_from: "2026-10-01T00:00:00+05:30", created_to: "2026-10-31T23:59:59.999+05:30" }));
  });

  it("an end date before the start is flagged and not sent", async () => {
    render(<OrdersList />);
    await screen.findByRole("table");
    fireEvent.change(screen.getByLabelText("Placed from"), { target: { value: "2026-10-10" } });
    await waitFor(() => expect(last().created_from).toBeDefined());
    fireEvent.change(screen.getByLabelText("Placed to"), { target: { value: "2026-10-01" } });
    expect(await screen.findByText(/before “Placed from”, so the dates are not applied/)).toBeInTheDocument();
    expect(screen.getByLabelText("Placed to")).toHaveAccessibleDescription(/not applied/);
    await waitFor(() => expect(last().created_from).toBeUndefined());
    expect(last().created_to).toBeUndefined();
  });

  it("error then retry; empty vs. filtered-empty", async () => {
    api.listAdminOrders.mockRejectedValueOnce(new Error("Orders unavailable"));
    render(<OrdersList />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Orders unavailable");
    api.listAdminOrders.mockResolvedValue(page([]));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No orders yet")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "shipped" } });
    expect(await screen.findByText("No orders match")).toBeInTheDocument();
  });

  it("keeps the old rows (busy) while the next page loads; a failed refresh keeps the list and says so", async () => {
    api.listAdminOrders.mockResolvedValueOnce(page([orderListItem()], { total: 60, total_pages: 3, has_next: true }));
    api.listAdminOrders.mockReturnValueOnce(new Promise(() => {}));
    render(<OrdersList />);
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByRole("link", { name: "PRM-2026-000123" })).toBeInTheDocument();
    expect(screen.getByRole("table").closest("[aria-busy]")).toHaveAttribute("aria-busy", "true");
    cleanup();

    api.listAdminOrders.mockReset();
    api.listAdminOrders.mockResolvedValueOnce(page());
    render(<OrdersList />);
    await screen.findByRole("table");
    api.listAdminOrders.mockRejectedValueOnce(new Error("Flaky network"));
    fireEvent.change(screen.getByLabelText("Payment"), { target: { value: "paid" } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/Flaky network.*last result/);
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});
