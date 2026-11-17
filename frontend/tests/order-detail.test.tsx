import { AxiosError } from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { api, auth } = vi.hoisted(() => ({
  api: { getAdminOrder: vi.fn(), advanceAdminOrder: vi.fn() },
  auth: { user: { id: "u1" }, isLoading: false },
}));
vi.mock("@/services/admin-orders", () => api);
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));

import { OrderDetail } from "@/components/admin/orders/OrderDetail";
import { orderDetail } from "./admin-fixtures";

const rejection = (status: number, message: string) =>
  new AxiosError("x", "ERR", undefined, undefined, { status, data: { success: false, message }, statusText: "", headers: {}, config: {} as never });

beforeEach(() => {
  api.getAdminOrder.mockReset();
  api.advanceAdminOrder.mockReset();
  api.getAdminOrder.mockResolvedValue(orderDetail());
});
afterEach(cleanup);

async function ready() {
  render(<OrderDetail id="o1" />);
  await screen.findByRole("heading", { level: 1, name: "Order PRM-2026-000123" });
}
const open = () => fireEvent.click(screen.getByRole("button", { name: "Mark as processing" }));

describe("OrderDetail - the facts", () => {
  it("loads by id and shows customer, address, items, totals and payment", async () => {
    await ready();
    expect(api.getAdminOrder).toHaveBeenCalledWith("o1");
    expect(screen.getByRole("link", { name: "asha@example.com" })).toHaveAttribute("href", "mailto:asha@example.com");
    const address = screen.getByText("12 MG Road").closest("address")!;
    expect(address).toHaveTextContent("Pune, Maharashtra, 411001");
    const items = screen.getByRole("table", { name: "Items in this order" });
    expect(within(items).getByRole("link", { name: "Muesli" })).toHaveAttribute("href", "/admin/products/p1");
    expect(within(items).getByText("Retired Millet")).toBeInTheDocument();
    expect(within(items).queryByRole("link", { name: "Retired Millet" })).toBeNull();
    expect(within(items).getByText("₹498.00")).toBeInTheDocument();
    expect(screen.getByText("GST (5%)")).toBeInTheDocument();
    expect(screen.getByText("Free")).toBeInTheDocument();
    expect(screen.getAllByText("₹627.90").length).toBeGreaterThan(0);
    const payments = screen.getByRole("table", { name: "Payment attempts" });
    expect(within(payments).getByText("Order order_AAA")).toBeInTheDocument();
    expect(within(payments).getByText("Payment pay_BBB")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("shows a discount with its coupon, and a delivery charge", async () => {
    api.getAdminOrder.mockResolvedValue(orderDetail({ coupon_code: "WELCOME10", totals: { subtotal: 598, discount: 59.8, taxable_amount: 538.2, gst_rate: 5, gst: 26.91, delivery_charge: 40, total: 605.11 } }));
    await ready();
    expect(screen.getByText("Discount (WELCOME10)")).toBeInTheDocument();
    expect(screen.getByText("-₹59.80")).toBeInTheDocument();
    expect(screen.getByText("₹40.00")).toBeInTheDocument();
    expect(screen.queryByText("Free")).toBeNull();
  });

  it("never shows a payment signature, and notes when no payment was attempted", async () => {
    api.getAdminOrder.mockResolvedValue(orderDetail({ payments: [] }));
    await ready();
    expect(screen.getByText("No payment has been attempted.")).toBeInTheDocument();
    expect(document.body.textContent?.toLowerCase()).not.toContain("signature");
  });

  it("flags a payment that needs a refund, and says it is not done here", async () => {
    api.getAdminOrder.mockResolvedValue(orderDetail({
      status: "cancelled", next_status: null, can_advance: false,
      payments: [{ ...orderDetail().payments[0], refund_required: true }],
    }));
    await ready();
    expect(screen.getByRole("alert")).toHaveTextContent(/needs a refund \(₹627\.90\).*payment gateway dashboard, not here/);
    expect(screen.getByText("Refund required")).toBeInTheDocument();
  });

  it("shows a pay-by time and held stock for an unpaid order", async () => {
    api.getAdminOrder.mockResolvedValue(orderDetail({
      status: "pending", payment_status: "pending", can_advance: false, next_status: null, payments: [],
      reserved_units: 3, expires_at: "2026-10-25T09:00:00Z",
    }));
    await ready();
    expect(screen.getByText("Pay by")).toBeInTheDocument();
    expect(screen.getByText("3 units")).toBeInTheDocument();
  });

  it("shows 'Pay by' only while the order is still pending", async () => {
    api.getAdminOrder.mockResolvedValue(orderDetail({ expires_at: "2026-10-25T09:00:00Z" }));   // confirmed + paid
    await ready();
    expect(screen.queryByText("Pay by")).toBeNull();
  });

  it("explains load failures (not found) and retries", async () => {
    api.getAdminOrder.mockRejectedValueOnce(new Error("Order not found."));
    render(<OrderDetail id="nope" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Order not found.");
    expect(screen.getByRole("link", { name: "All orders" })).toHaveAttribute("href", "/admin/orders");
    api.getAdminOrder.mockResolvedValue(orderDetail());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Order PRM-2026-000123" })).toBeInTheDocument();
  });

  it("a failed refresh keeps the order on screen with a warning", async () => {
    await ready();
    api.getAdminOrder.mockRejectedValueOnce(new Error("Offline"));
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText(/Offline.*last successful load/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });
});

describe("OrderDetail - fulfilment", () => {
  it("shows the four steps with the current one marked", async () => {
    api.getAdminOrder.mockResolvedValue(orderDetail({ status: "shipped", next_status: "delivered" }));
    await ready();
    const steps = within(screen.getByRole("list", { name: "Fulfilment steps" })).getAllByRole("listitem");
    expect(steps.map((s) => s.textContent)).toEqual(["Confirmed (done)", "Processing (done)", "Shipped (current step)", "Delivered (not yet)"]);
    expect(steps[2]).toHaveAttribute("aria-current", "step");
    expect(steps.filter((s) => s.hasAttribute("aria-current"))).toHaveLength(1);
  });

  it("offers exactly the step the server names", async () => {
    api.getAdminOrder.mockResolvedValue(orderDetail({ status: "processing", next_status: "shipped" }));
    await ready();
    expect(screen.getByRole("button", { name: "Mark as shipped" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark as processing" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Mark as delivered" })).toBeNull();
  });

  it("offers nothing when the server says it cannot advance, and says why", async () => {
    for (const [overrides, text] of [
      [{ status: "delivered", next_status: null, can_advance: false }, /delivered/],
      [{ status: "cancelled", next_status: null, can_advance: false, cancellation_reason: "customer" }, /was cancelled/],
      [{ status: "pending", payment_status: "pending", next_status: null, can_advance: false }, /not been paid/],
      // the server's word wins even if next_status is present
      [{ status: "confirmed", next_status: "processing", can_advance: false }, /cannot be moved forward/],
    ] as const) {
      api.getAdminOrder.mockResolvedValue(orderDetail(overrides as never));
      render(<OrderDetail id="o1" />);
      await screen.findByRole("heading", { level: 1 });
      expect(screen.queryByRole("button", { name: /^Mark as/ })).toBeNull();
      expect(screen.getByText(text)).toBeInTheDocument();
      cleanup();
    }
  });

  it("shows the step tracker only for an order on the fulfilment path", async () => {
    for (const overrides of [
      { status: "pending", payment_status: "pending", next_status: null, can_advance: false },
      { status: "cancelled", next_status: null, can_advance: false },
      { status: "refunded", payment_status: "refunded", next_status: null, can_advance: false },
    ]) {
      api.getAdminOrder.mockResolvedValue(orderDetail(overrides as never));
      render(<OrderDetail id="o1" />);
      await screen.findByRole("heading", { level: 1 });
      expect(screen.queryByRole("list", { name: "Fulfilment steps" })).toBeNull();
      cleanup();
    }
    api.getAdminOrder.mockResolvedValue(orderDetail());       // a paid, confirmed order is on the path
    await ready();
    expect(screen.getByRole("list", { name: "Fulfilment steps" })).toBeInTheDocument();
  });

  it("has no cancel, refund or mark-paid action anywhere", async () => {
    await ready();
    expect(screen.queryByRole("button", { name: /cancel order|refund|mark as paid|mark paid/i })).toBeNull();
  });

  it("asks first, with the warning and a note box, and sends nothing until confirmed", async () => {
    await ready();
    open();
    const dialog = screen.getByRole("dialog", { name: "Mark as processing?" });
    expect(dialog).toHaveTextContent(/cannot be undone/);
    expect(within(dialog).getByLabelText(/^Note/)).toBeInTheDocument();
    expect(api.advanceAdminOrder).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(api.advanceAdminOrder).not.toHaveBeenCalled();
  });

  it("confirms: sends the target and the trimmed note, then shows the server's copy", async () => {
    api.advanceAdminOrder.mockResolvedValue(orderDetail({ status: "processing", next_status: "shipped" }));
    await ready();
    open();
    fireEvent.change(screen.getByLabelText(/^Note/), { target: { value: "  Packed by Ravi  " } });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark as processing" }));
    await waitFor(() => expect(api.advanceAdminOrder).toHaveBeenCalledWith("o1", { status: "processing", note: "Packed by Ravi" }));
    expect(await screen.findByText("Order marked as processing.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Mark as shipped" })).toBeInTheDocument();
    expect(screen.getAllByText("Processing").length).toBeGreaterThan(0);
  });

  it("omits an empty note", async () => {
    api.advanceAdminOrder.mockResolvedValue(orderDetail({ status: "processing", next_status: "shipped" }));
    await ready();
    open();
    fireEvent.change(screen.getByLabelText(/^Note/), { target: { value: "   " } });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark as processing" }));
    await waitFor(() => expect(api.advanceAdminOrder).toHaveBeenCalledWith("o1", { status: "processing" }));
  });

  it("the note box starts empty each time", async () => {
    await ready();
    open();
    fireEvent.change(screen.getByLabelText(/^Note/), { target: { value: "old" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    open();
    expect(screen.getByLabelText(/^Note/)).toHaveValue("");
  });

  it("a refusal stays in the dialog and a 409 reloads the order", async () => {
    api.advanceAdminOrder.mockRejectedValue(rejection(409, "This order changed while you were updating it. Refresh and try again."));
    await ready();
    api.getAdminOrder.mockResolvedValue(orderDetail({ status: "processing", next_status: "shipped" }));
    open();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark as processing" }));
    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent(/changed while you were updating/);
    await waitFor(() => expect(api.getAdminOrder).toHaveBeenCalledTimes(2));
  });

  it("a non-409 failure does not reload, and a double click sends one request", async () => {
    let fail!: (e: unknown) => void;
    api.advanceAdminOrder.mockReturnValue(new Promise((_, reject) => (fail = reject)));
    await ready();
    open();
    const confirm = within(screen.getByRole("dialog")).getByRole("button", { name: "Mark as processing" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(api.advanceAdminOrder).toHaveBeenCalledTimes(1);
    fail(rejection(500, "Server error"));
    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("Server error");
    expect(api.getAdminOrder).toHaveBeenCalledTimes(1);
  });
});
