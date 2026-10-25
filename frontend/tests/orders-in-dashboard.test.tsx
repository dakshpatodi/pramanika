import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Order, OrderList, OrderSummary } from "@/types/order";

const { auth, router, nav, orderApi, invoiceApi, files } = vi.hoisted(() => ({
  auth: { user: null as null | { id: string }, isLoading: false, isAuthenticated: true },
  router: { push: vi.fn(), replace: vi.fn() },
  nav: { params: { id: "order-1" } as Record<string, string | string[]>, pathname: "/orders" },
  orderApi: { getOrder: vi.fn(), cancelOrder: vi.fn(), listOrders: vi.fn() },
  invoiceApi: { downloadInvoice: vi.fn(), listInvoices: vi.fn() },
  files: { saveBlob: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => nav.pathname, useParams: () => nav.params }));
vi.mock("@/services/orders", () => orderApi);
vi.mock("@/services/invoices", () => invoiceApi);
vi.mock("@/lib/download", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/download")>()), saveBlob: files.saveBlob }));

import OrderPage from "@/app/orders/[id]/page";
import OrdersPage from "@/app/orders/page";

function makeOrder(over: Partial<Order> = {}): Order {
  return {
    id: "order-1", order_number: "PRM-2026-000042", status: "confirmed", payment_status: "paid", can_cancel: false,
    can_pay: false, expires_at: null, cancellation_reason: null,
    payment: { last_attempt: null, refund_pending: false },
    coupon_code: null,
    items: [{ id: "it1", product_id: "p1", product_name: "Multigrain Cereal", sku: "S1", unit_price: 249, quantity: 2, line_total: 498 }],
    item_count: 2,
    totals: { subtotal: 498, discount: 0, taxable_amount: 498, gst_rate: 0.05, gst: 24.9, delivery_charge: 0, total: 522.9 },
    shipping_address: {
      full_name: "Asha Rao", phone_number: "9876543210", address_line_1: "12 MG Road", address_line_2: null,
      city: "Pune", state: "Maharashtra", postal_code: "411001", country: "India",
    },
    created_at: "2026-10-05T10:30:00Z", cancelled_at: null,
    ...over,
  };
}
const summary = (n: number): OrderSummary => ({
  id: `order-${n}`, order_number: `PRM-2026-00000${n}`, status: "confirmed", payment_status: "paid", can_pay: false, expires_at: null,
  cancellation_reason: null, total: 100 + n, item_count: 1, line_count: 1, item_names: ["Oats"], created_at: "2026-10-05T10:30:00Z",
});
const list = (orders: OrderSummary[]): OrderList => ({
  orders, pagination: { total: orders.length, page: 1, page_size: 10, total_pages: 1, has_next: false, has_previous: false },
});

beforeEach(() => {
  auth.user = { id: "u1" }; auth.isLoading = false; auth.isAuthenticated = true;
  nav.params = { id: "order-1" }; nav.pathname = "/orders";
  Object.values(orderApi).forEach((fn) => fn.mockReset());
  Object.values(invoiceApi).forEach((fn) => fn.mockReset());
  files.saveBlob.mockReset();
});
afterEach(cleanup);

describe("/orders inside the account frame", () => {
  it("keeps its heading and list and gains the account menu with Orders current", async () => {
    orderApi.listOrders.mockResolvedValue(list([summary(1), summary(2)]));
    render(<OrdersPage />);
    expect(await screen.findByText("PRM-2026-000001")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Your orders");
    const menu = within(screen.getByRole("navigation", { name: "Account" }));
    expect(menu.getByRole("link", { name: "Orders" })).toHaveAttribute("aria-current", "page");
    expect(menu.getByRole("link", { name: "Invoices" })).toHaveAttribute("href", "/dashboard/invoices");
  });

  it("shows the menu around the empty and error states too", async () => {
    orderApi.listOrders.mockResolvedValue(list([]));
    render(<OrdersPage />);
    expect(await screen.findByText("No orders yet")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Account" })).toBeInTheDocument();
  });
});

describe("/orders/[id] inside the account frame", () => {
  beforeEach(() => { nav.pathname = "/orders/order-1"; });

  it("has the account menu and exactly one h1 - the order number", async () => {
    orderApi.getOrder.mockResolvedValue(makeOrder());
    render(<OrderPage />);
    await screen.findByRole("heading", { level: 1, name: "PRM-2026-000042" });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(within(screen.getByRole("navigation", { name: "Account" })).getByRole("link", { name: "Orders" })).toHaveAttribute("aria-current", "page");
  });

  it("keeps the account menu while loading and when the order cannot be loaded", async () => {
    orderApi.getOrder.mockReturnValueOnce(new Promise(() => {}));
    render(<OrderPage />);
    expect(screen.getByRole("navigation", { name: "Account" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Loading your order" })).toBeInTheDocument();
    cleanup();
    orderApi.getOrder.mockReset();
    orderApi.getOrder.mockRejectedValue(new Error("Order was not found."));
    render(<OrderPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Order was not found.");
    expect(screen.getByRole("navigation", { name: "Account" })).toBeInTheDocument();
  });

  it("offers the invoice for a paid order and downloads that order's PDF", async () => {
    const user = userEvent.setup();
    orderApi.getOrder.mockResolvedValue(makeOrder());
    const blob = new Blob(["%PDF"]);
    invoiceApi.downloadInvoice.mockResolvedValue(blob);
    render(<OrderPage />);
    await user.click(await screen.findByRole("button", { name: "Download invoice for order PRM-2026-000042" }));
    await waitFor(() => expect(files.saveBlob).toHaveBeenCalledTimes(1));
    expect(invoiceApi.downloadInvoice).toHaveBeenCalledWith("order-1");
    expect(files.saveBlob).toHaveBeenCalledWith(blob, "invoice-PRM-2026-000042.pdf");
  });

  it.each([
    ["pending", "pending", true],
    ["failed", "failed", false],
    ["refunded", "refunded", false],
  ] as const)("offers no invoice when payment is %s", async (_label, payment_status, can_pay) => {
    orderApi.getOrder.mockResolvedValue(makeOrder({ status: "pending", payment_status, can_pay, can_cancel: true, expires_at: "2099-01-01T00:00:00Z" }));
    render(<OrderPage />);
    await screen.findByRole("heading", { level: 1, name: "PRM-2026-000042" });
    expect(screen.queryByRole("button", { name: /download invoice/i })).toBeNull();
  });
});
