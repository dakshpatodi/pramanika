import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Order, OrderList, OrderSummary } from "@/types/order";

const { auth, router, nav, api } = vi.hoisted(() => ({
  auth: { user: null as null | { id: string }, isLoading: false, isAuthenticated: true },
  router: { push: vi.fn(), replace: vi.fn() },
  nav: { params: { id: "order-1" } as Record<string, string | string[]> },
  api: { getOrder: vi.fn(), cancelOrder: vi.fn(), listOrders: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/orders",
  useParams: () => nav.params,
}));
vi.mock("@/services/orders", () => api);

import OrderPage from "@/app/orders/[id]/page";
import OrdersPage from "@/app/orders/page";
import { formatMoney } from "@/lib/money";

function makeOrder(over: Partial<Order> = {}): Order {
  return {
    id: "order-1", order_number: "PRM-2026-000042", status: "pending", payment_status: "pending", can_cancel: true,
    can_pay: true, expires_at: "2099-01-01T00:00:00Z", cancellation_reason: null,
    payment: { last_attempt: null, refund_pending: false },
    coupon_code: null,
    items: [
      { id: "it1", product_id: "p1", product_name: "Multigrain Cereal", sku: "S1", unit_price: 249, quantity: 2, line_total: 498 },
      { id: "it2", product_id: null, product_name: "Retired Poha", sku: "S2", unit_price: 189, quantity: 1, line_total: 189 },
    ],
    item_count: 3,
    totals: { subtotal: 687, discount: 0, taxable_amount: 687, gst_rate: 0.05, gst: 34.35, delivery_charge: 0, total: 721.35 },
    shipping_address: {
      full_name: "Asha Rao", phone_number: "9876543210", address_line_1: "12 MG Road", address_line_2: "Flat 4",
      city: "Pune", state: "Maharashtra", postal_code: "411001", country: "India",
    },
    created_at: "2026-10-05T10:30:00Z", cancelled_at: null,
    ...over,
  };
}
function summary(n: number, over: Partial<OrderSummary> = {}): OrderSummary {
  return {
    id: `order-${n}`, order_number: `PRM-2026-0000${n}`, status: "pending", payment_status: "pending", can_pay: true, expires_at: "2099-01-01T00:00:00Z", cancellation_reason: null,
    total: 100 + n,
    item_count: 2, line_count: 1, item_names: ["Oats"], created_at: "2026-10-05T10:30:00Z", ...over,
  };
}
function makeList(orders: OrderSummary[], page = 1, totalPages = 1, total = orders.length): OrderList {
  return { orders, pagination: { total, page, page_size: 10, total_pages: totalPages, has_next: page < totalPages, has_previous: page > 1 } };
}
function deferred<T>() {
  let resolve!: (v: T) => void; let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  auth.user = { id: "u1" }; auth.isLoading = false; auth.isAuthenticated = true;
  nav.params = { id: "order-1" };
  router.push.mockReset(); router.replace.mockReset();
  api.getOrder.mockReset(); api.cancelOrder.mockReset(); api.listOrders.mockReset();
});
afterEach(cleanup);

describe("/orders/[id] - access and states", () => {
  it("renders nothing and redirects to login when logged out, without fetching", () => {
    auth.user = null; auth.isAuthenticated = false;
    const { container } = render(<OrderPage />);
    expect(container.innerHTML).toBe("");
    expect(router.push).toHaveBeenCalledWith("/login?redirect=%2Forders");
    expect(api.getOrder).not.toHaveBeenCalled();
  });

  it("shows a skeleton while loading", () => {
    api.getOrder.mockReturnValue(new Promise(() => undefined));
    render(<OrderPage />);
    expect(screen.getByRole("status", { name: "Loading your order" })).toBeTruthy();
  });

  it("asks for the order named in the URL", async () => {
    nav.params = { id: "abc-123" };
    api.getOrder.mockResolvedValue(makeOrder({ id: "abc-123" }));
    render(<OrderPage />);
    await screen.findByRole("heading", { name: "PRM-2026-000042" });
    expect(api.getOrder).toHaveBeenCalledWith("abc-123");
  });

  it("copes with a route param that arrives as an array", async () => {
    nav.params = { id: ["arr-1"] };
    api.getOrder.mockResolvedValue(makeOrder({ id: "arr-1" }));
    render(<OrderPage />);
    await screen.findByRole("heading", { name: "PRM-2026-000042" });
    expect(api.getOrder).toHaveBeenCalledWith("arr-1");
  });

  it("shows the server's message (not found / not yours) with a retry and a way out - and no order data", async () => {
    api.getOrder.mockRejectedValueOnce(new Error("Order was not found."));
    render(<OrderPage />);
    expect((await screen.findByRole("alert")).textContent).toBe("Order was not found.");
    expect(screen.getByRole("link", { name: "All orders" }).getAttribute("href")).toBe("/orders");
    expect(screen.queryByText("Order total")).toBeNull();

    api.getOrder.mockResolvedValue(makeOrder());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "PRM-2026-000042" })).toBeTruthy();
  });
});

describe("/orders/[id] - confirmation content", () => {
  it("shows the order number, date, status, items snapshot, totals and the delivery address", async () => {
    api.getOrder.mockResolvedValue(makeOrder({ coupon_code: "WELCOME10", totals: { ...makeOrder().totals, discount: 68.7, total: 652.65 } }));
    render(<OrderPage />);
    await screen.findByRole("heading", { name: "PRM-2026-000042" });

    expect(screen.getByText(/Placed on 5 Oct 2026, 4:00\s?pm/i)).toBeTruthy();
    expect(screen.getByText("Pending")).toBeTruthy();
    expect(screen.getByText("Payment pending")).toBeTruthy();

    const items = within(screen.getByRole("region", { name: "Items" }));
    expect(items.getByText("Multigrain Cereal")).toBeTruthy();
    expect(items.getByText(`2 x ${formatMoney(249)}`)).toBeTruthy();
    expect(items.getByText("Retired Poha")).toBeTruthy(); // product since deleted: the snapshot still shows

    const totals = within(screen.getByRole("region", { name: "Order total" }));
    expect(totals.getByText("Subtotal")).toBeTruthy();
    expect(totals.getByText("Discount (WELCOME10)")).toBeTruthy();
    expect(totals.getByText("-₹68.70")).toBeTruthy();
    expect(totals.getByText("GST (5%)")).toBeTruthy();
    expect(totals.getByText("Free")).toBeTruthy();
    expect(totals.getByText("₹652.65")).toBeTruthy();

    const address = within(screen.getByRole("region", { name: "Delivery address" }));
    expect(address.getByText("Asha Rao")).toBeTruthy();
    expect(address.getByText("12 MG Road, Flat 4")).toBeTruthy();
    expect(address.getByText("Pune, Maharashtra 411001")).toBeTruthy();
  });

  it("shows a delivery charge when there is one", async () => {
    api.getOrder.mockResolvedValue(makeOrder({ totals: { ...makeOrder().totals, delivery_charge: 49, total: 770 } }));
    render(<OrderPage />);
    const totals = within(await screen.findByRole("region", { name: "Order total" }));
    expect(totals.getByText("₹49.00")).toBeTruthy();
    expect(totals.queryByText("Free")).toBeNull();
  });

  it("NEVER says an unpaid order is paid", async () => {
    api.getOrder.mockResolvedValue(makeOrder());
    render(<OrderPage />);
    await screen.findByRole("heading", { name: "PRM-2026-000042" });
    expect(screen.getByText(/No payment has been taken yet/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/\bPaid\b|payment (successful|received|complete)|thank you for your payment/i);
  });

  it("shows 'Paid' only when the server says so", async () => {
    api.getOrder.mockResolvedValue(makeOrder({ status: "confirmed", payment_status: "paid", can_cancel: false }));
    render(<OrderPage />);
    await screen.findByRole("heading", { name: "PRM-2026-000042" });
    expect(screen.getByText("Paid")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cancel order" })).toBeNull();
  });

  it("links onward to shopping and to all orders", async () => {
    api.getOrder.mockResolvedValue(makeOrder());
    render(<OrderPage />);
    await screen.findByRole("heading", { name: "PRM-2026-000042" });
    expect(screen.getByRole("link", { name: "Continue shopping" }).getAttribute("href")).toBe("/shop");
    expect(screen.getByRole("link", { name: "All orders" }).getAttribute("href")).toBe("/orders");
  });
});

describe("/orders/[id] - cancelling", () => {
  it("offers Cancel only when the server says the order can be cancelled", async () => {
    api.getOrder.mockResolvedValue(makeOrder({ can_cancel: false }));
    render(<OrderPage />);
    await screen.findByRole("heading", { name: "PRM-2026-000042" });
    expect(screen.queryByRole("button", { name: "Cancel order" })).toBeNull();
  });

  it("asks for confirmation first, and 'Keep order' backs out without calling the API", async () => {
    api.getOrder.mockResolvedValue(makeOrder());
    render(<OrderPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel order" }));
    expect(screen.getByText("Cancel this order?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Keep order" }));
    expect(screen.getByRole("button", { name: "Cancel order" })).toBeTruthy();
    expect(api.cancelOrder).not.toHaveBeenCalled();
  });

  it("cancels, then shows the cancelled state: no Cancel button, release message, no payment pill", async () => {
    api.getOrder.mockResolvedValue(makeOrder());
    api.cancelOrder.mockResolvedValue(makeOrder({ status: "cancelled", can_cancel: false, cancelled_at: "2026-10-06T08:00:00Z" }));
    render(<OrderPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel order" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, cancel order" }));

    expect(await screen.findByText("Cancelled")).toBeTruthy();
    expect(api.cancelOrder).toHaveBeenCalledWith("order-1");
    expect(screen.getByText(/cancelled on 6 Oct 2026/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cancel order" })).toBeNull();
    expect(screen.queryByText("Payment pending")).toBeNull();
    expect(screen.getByText("Total (cancelled)")).toBeTruthy();
  });

  it("sends ONE cancel request even if the confirm button is hit repeatedly", async () => {
    api.getOrder.mockResolvedValue(makeOrder());
    const pending = deferred<Order>();
    api.cancelOrder.mockReturnValue(pending.promise);
    render(<OrderPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel order" }));
    const confirm = screen.getByRole("button", { name: "Yes, cancel order" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    expect(api.cancelOrder).toHaveBeenCalledTimes(1);
    expect((await screen.findByRole("status")).textContent).toContain("Cancelling your order");
    expect((screen.getByRole("button", { name: "Cancel order" }) as HTMLButtonElement).disabled).toBe(true);

    pending.resolve(makeOrder({ status: "cancelled", can_cancel: false }));
    await screen.findByText("Cancelled");
    expect(api.cancelOrder).toHaveBeenCalledTimes(1);
  });

  it("shows the server's reason when cancelling is refused, and refreshes what the order now looks like", async () => {
    api.getOrder.mockResolvedValueOnce(makeOrder());
    api.cancelOrder.mockRejectedValue(new Error("An order that is paid can no longer be cancelled."));
    api.getOrder.mockResolvedValue(makeOrder({ status: "confirmed", payment_status: "paid", can_cancel: false }));
    render(<OrderPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel order" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, cancel order" }));

    expect(await screen.findByText("An order that is paid can no longer be cancelled.")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("Paid")).toBeTruthy());
    expect(screen.queryByRole("button", { name: "Cancel order" })).toBeNull();
  });
});

describe("/orders - history", () => {
  it("renders nothing and redirects when logged out", () => {
    auth.user = null; auth.isAuthenticated = false;
    const { container } = render(<OrdersPage />);
    expect(container.innerHTML).toBe("");
    expect(router.push).toHaveBeenCalledWith("/login?redirect=%2Forders");
    expect(api.listOrders).not.toHaveBeenCalled();
  });

  it("shows a skeleton, then the orders as links to their detail pages", async () => {
    api.listOrders.mockResolvedValue(makeList([
      summary(2, { status: "cancelled", total: 250.5, item_names: ["Oats", "Poha"], item_count: 3, line_count: 2 }),
      summary(1),
    ]));
    render(<OrdersPage />);
    expect(screen.getByRole("status", { name: "Loading your orders" })).toBeTruthy();

    const first = await screen.findByRole("link", { name: /PRM-2026-00002/ });
    expect(first.getAttribute("href")).toBe("/orders/order-2");
    expect(within(first).getByText("Cancelled")).toBeTruthy();
    expect(within(first).getByText("Oats, Poha")).toBeTruthy();
    expect(within(first).getByText("₹250.50")).toBeTruthy();
    expect(within(first).getByText("3 items")).toBeTruthy();
    expect(within(first).getByText("Placed on 5 Oct 2026")).toBeTruthy();
    const second = screen.getByRole("link", { name: /PRM-2026-00001/ });
    expect(second.getAttribute("href")).toBe("/orders/order-1");
    expect(within(second).getByText("2 items")).toBeTruthy();
    expect(api.listOrders).toHaveBeenCalledWith(1, 10);
  });

  it("says how many more products there are when only the first three names are listed", async () => {
    api.listOrders.mockResolvedValue(makeList([summary(1, { item_names: ["A", "B", "C"], line_count: 5, item_count: 9 })]));
    render(<OrdersPage />);
    expect(await screen.findByText("A, B, C and 2 more")).toBeTruthy();
  });

  it("does not claim 'more' just because one product was bought in several units", async () => {
    api.listOrders.mockResolvedValue(makeList([summary(1, { item_names: ["Oats"], line_count: 1, item_count: 5 })]));
    render(<OrdersPage />);
    expect(await screen.findByText("Oats")).toBeTruthy();
    expect(screen.queryByText(/more/)).toBeNull();
  });

  it("shows a friendly empty state with a way to start shopping", async () => {
    api.listOrders.mockResolvedValue(makeList([], 1, 0, 0));
    render(<OrdersPage />);
    expect(await screen.findByText("No orders yet")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Start shopping" }).getAttribute("href")).toBe("/shop");
    expect(screen.queryByRole("navigation", { name: "Order pages" })).toBeNull();
  });

  it("shows the error with a retry", async () => {
    api.listOrders.mockRejectedValueOnce(new Error("Server down"));
    render(<OrdersPage />);
    expect((await screen.findByRole("alert")).textContent).toBe("Server down");
    api.listOrders.mockResolvedValue(makeList([summary(1)]));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: /PRM-2026-00001/ })).toBeTruthy();
  });

  it("pages forward and back, disabling the buttons at the ends", async () => {
    api.listOrders.mockImplementation(async (page: number) => makeList([summary(page)], page, 3, 3));
    render(<OrdersPage />);
    await screen.findByRole("link", { name: /PRM-2026-00001/ });
    const nav = within(screen.getByRole("navigation", { name: "Order pages" }));
    expect(nav.getByText("Page 1 of 3")).toBeTruthy();
    expect((nav.getByRole("button", { name: "Previous" }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(nav.getByRole("button", { name: "Next" }));
    await screen.findByRole("link", { name: /PRM-2026-00002/ });
    expect(api.listOrders).toHaveBeenLastCalledWith(2, 10);
    expect(nav.getByText("Page 2 of 3")).toBeTruthy();

    fireEvent.click(nav.getByRole("button", { name: "Next" }));
    await screen.findByRole("link", { name: /PRM-2026-00003/ });
    expect((nav.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(nav.getByRole("button", { name: "Previous" }));
    await screen.findByRole("link", { name: /PRM-2026-00002/ });
    expect(api.listOrders).toHaveBeenLastCalledWith(2, 10);
  });

  it("never shows 'Paid' for unpaid orders in the list", async () => {
    api.listOrders.mockResolvedValue(makeList([summary(1)]));
    render(<OrdersPage />);
    await screen.findByRole("link", { name: /PRM-2026-00001/ });
    expect(screen.getByText("Payment pending")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/\bPaid\b/);
  });

  it("marks only payable orders with 'Complete payment' (the server's can_pay decides)", async () => {
    api.listOrders.mockResolvedValue(makeList([
      summary(1),
      summary(2, { can_pay: false, payment_status: "paid", status: "confirmed" }),
      summary(3, { can_pay: false, status: "cancelled", cancellation_reason: "customer" }),
      summary(4, { can_pay: false, expires_at: "2026-01-01T00:00:00Z" }),
    ]));
    render(<OrdersPage />);
    const payable = await screen.findByRole("link", { name: /PRM-2026-00001/ });
    expect(within(payable).getByText("Complete payment")).toBeTruthy();
    for (const n of [2, 3, 4]) {
      expect(within(screen.getByRole("link", { name: new RegExp(`PRM-2026-0000${n}`) })).queryByText("Complete payment")).toBeNull();
    }
    expect(screen.getAllByText("Complete payment")).toHaveLength(1);
  });

  it("shows an expired order as Expired (not Cancelled) and a closed window as such", async () => {
    api.listOrders.mockResolvedValue(makeList([
      summary(5, { status: "cancelled", can_pay: false, cancellation_reason: "expired" }),
      summary(6, { status: "cancelled", can_pay: false, cancellation_reason: "customer" }),
      summary(7, { can_pay: false, expires_at: "2026-01-01T00:00:00Z" }),
    ]));
    render(<OrdersPage />);
    const expired = await screen.findByRole("link", { name: /PRM-2026-00005/ });
    expect(within(expired).getByText("Expired")).toBeTruthy();
    expect(within(expired).queryByText("Cancelled")).toBeNull();
    expect(within(screen.getByRole("link", { name: /PRM-2026-00006/ })).getByText("Cancelled")).toBeTruthy();
    expect(within(screen.getByRole("link", { name: /PRM-2026-00007/ })).getByText("Payment window closed")).toBeTruthy();
  });
});
