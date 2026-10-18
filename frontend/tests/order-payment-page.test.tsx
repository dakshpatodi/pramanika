import { AxiosError } from "axios";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Order } from "@/types/order";

const { auth, router, nav, orderApi, paymentApi, razorpay } = vi.hoisted(() => ({
  auth: { user: { id: "u1" } as null | { id: string }, isLoading: false, isAuthenticated: true },
  router: { push: vi.fn(), replace: vi.fn() },
  nav: { params: { id: "order-1" } as Record<string, string | string[]> },
  orderApi: { getOrder: vi.fn(), cancelOrder: vi.fn(), listOrders: vi.fn(), placeOrder: vi.fn() },
  paymentApi: { createPayment: vi.fn(), verifyPayment: vi.fn() },
  razorpay: { loadRazorpayScript: vi.fn(), openRazorpayCheckout: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/orders/order-1", useParams: () => nav.params }));
vi.mock("@/services/orders", () => orderApi);
vi.mock("@/services/payments", () => paymentApi);
vi.mock("@/lib/razorpay", () => razorpay);

import OrderPage from "@/app/orders/[id]/page";

const TOTAL = 721.35;
const FAR = "2099-01-01T00:00:00Z";

function makeOrder(over: Partial<Order> = {}): Order {
  return {
    id: "order-1", order_number: "PRM-2026-000042", status: "pending", payment_status: "pending", can_cancel: true,
    can_pay: true, expires_at: FAR, cancellation_reason: null, payment: { last_attempt: null, refund_pending: false },
    coupon_code: null,
    items: [{ id: "it1", product_id: "p1", product_name: "Multigrain Cereal", sku: "S1", unit_price: 229, quantity: 3, line_total: 687 }],
    item_count: 3,
    totals: { subtotal: 687, discount: 0, taxable_amount: 687, gst_rate: 0.05, gst: 34.35, delivery_charge: 0, total: TOTAL },
    shipping_address: {
      full_name: "Asha Rao", phone_number: "9876543210", address_line_1: "12 MG Road", address_line_2: null,
      city: "Pune", state: "Maharashtra", postal_code: "411001", country: "India",
    },
    created_at: "2026-10-05T10:30:00Z", cancelled_at: null,
    ...over,
  };
}
const paidOrder = () => makeOrder({ status: "confirmed", payment_status: "paid", can_cancel: false, can_pay: false, payment: { last_attempt: "captured", refund_pending: false } });
const expiredOrder = () => makeOrder({
  status: "cancelled", can_cancel: false, can_pay: false, cancellation_reason: "expired", cancelled_at: "2026-10-05T11:00:00Z",
  payment: { last_attempt: "expired", refund_pending: false },
});

const intent = { order_id: "order-1", order_number: "PRM-2026-000042", razorpay_order_id: "order_SRV", razorpay_key_id: "rzp_test_KEY", amount_paise: 72135, currency: "INR" };
const reported = { razorpay_order_id: "order_SRV", razorpay_payment_id: "pay_1", razorpay_signature: "sig_1" };

type Callbacks = { onSuccess: (r: unknown) => void; onDismiss: () => void; onFailure: (d: string | null) => void };
let popup: { request: any; cb: Callbacks } | null;

function apiError(status: number, message: string) {
  return new AxiosError(message, "ERR_BAD_REQUEST", undefined, undefined, {
    status, statusText: "", headers: {}, config: {} as never, data: { success: false, message },
  } as never);
}
function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return { promise, resolve };
}

const payButton = () => screen.getByRole("button", { name: /^Pay .* now$|^Try payment again/ });
const queryPayButton = () => screen.queryByRole("button", { name: /^Pay .* now$|^Try payment again/ });

async function openPopup() {
  fireEvent.click(await screen.findByRole("button", { name: /^Pay .* now$|^Try payment again/ }));
  await waitFor(() => expect(popup).not.toBeNull());
}

beforeEach(() => {
  popup = null;
  auth.user = { id: "u1" };
  nav.params = { id: "order-1" };
  router.push.mockReset(); router.replace.mockReset();
  orderApi.getOrder.mockReset().mockResolvedValue(makeOrder());
  orderApi.cancelOrder.mockReset(); orderApi.placeOrder.mockReset();
  paymentApi.createPayment.mockReset().mockResolvedValue(intent);
  paymentApi.verifyPayment.mockReset().mockResolvedValue({ id: "order-1", payment_status: "paid" });
  razorpay.loadRazorpayScript.mockReset().mockResolvedValue(undefined);
  razorpay.openRazorpayCheckout.mockReset().mockImplementation((request: unknown, cb: Callbacks) => { popup = { request, cb }; });
});
afterEach(cleanup);

describe("/orders/[id] - who sees 'Pay now'", () => {
  it("shows it for a payable order, with the order's own total and the deadline", async () => {
    render(<OrderPage />);
    const button = await screen.findByRole("button", { name: "Pay ₹721.35 now" });
    expect(button).toBeEnabled();
    const panel = within(screen.getByRole("region", { name: "Payment" }));
    expect(panel.getByText(/Time left to pay/)).toBeTruthy();
    expect(panel.getByText(/processed securely by Razorpay/)).toBeTruthy();
  });

  it.each([
    ["paid", paidOrder],
    ["expired", expiredOrder],
    ["cancelled by the customer", () => makeOrder({ status: "cancelled", can_cancel: false, can_pay: false, cancellation_reason: "customer" })],
    ["past its deadline, expiry not yet run", () => makeOrder({ can_pay: false, expires_at: "2026-01-01T00:00:00Z" })],
  ])("hides it - and the whole payment panel - for an order that is %s", async (_name, make) => {
    orderApi.getOrder.mockResolvedValue(make());
    render(<OrderPage />);
    await screen.findByRole("heading", { name: "PRM-2026-000042" });
    expect(queryPayButton()).toBeNull();
    expect(screen.queryByRole("region", { name: "Payment" })).toBeNull();
  });

  it("trusts the server's can_pay, not its own reading of the order", async () => {
    // a pending, unpaid, far-from-expired order that the server says cannot be paid
    orderApi.getOrder.mockResolvedValue(makeOrder({ can_pay: false }));
    render(<OrderPage />);
    await screen.findByRole("heading", { name: "PRM-2026-000042" });
    expect(queryPayButton()).toBeNull();
  });
});

describe("/orders/[id] - paying", () => {
  it("opens Razorpay with what the SERVER returned, verifies, then shows the order as the server reports it", async () => {
    render(<OrderPage />);
    await openPopup();
    expect(paymentApi.createPayment).toHaveBeenCalledWith("order-1");
    expect(popup!.request).toMatchObject({ keyId: "rzp_test_KEY", amountPaise: 72135, currency: "INR", razorpayOrderId: "order_SRV" });
    expect(screen.getByText(/Complete your payment in the Razorpay window/)).toBeTruthy();

    orderApi.getOrder.mockResolvedValue(paidOrder());
    await act(async () => { popup!.cb.onSuccess(reported); });
    await waitFor(() => expect(paymentApi.verifyPayment).toHaveBeenCalledWith("order-1", reported));
    expect(await screen.findByText("Payment received. Thank you!")).toBeTruthy();
    expect(screen.getByText("Paid")).toBeTruthy();
    expect(screen.getByText(/Your payment has been received and your order is being prepared/)).toBeTruthy();
    expect(queryPayButton()).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancel order" })).toBeNull();
    expect(orderApi.getOrder).toHaveBeenCalledTimes(2);
  });

  it("Razorpay saying 'success' is not 'paid': until the SERVER says paid the page does not claim it", async () => {
    paymentApi.verifyPayment.mockResolvedValue({ id: "order-1", payment_status: "pending" }); // e.g. only authorized
    render(<OrderPage />);
    await openPopup();
    await act(async () => { popup!.cb.onSuccess(reported); });
    expect(await screen.findByRole("button", { name: "Check payment status" })).toBeTruthy();
    expect(screen.queryByText("Payment received. Thank you!")).toBeNull();
    expect(screen.queryByText("Paid")).toBeNull();
    expect(screen.getByText("Payment pending")).toBeTruthy();
  });

  it("'Check payment status' asks the server again about the SAME payment without reopening Razorpay", async () => {
    paymentApi.verifyPayment.mockResolvedValueOnce({ id: "order-1", payment_status: "pending" });
    render(<OrderPage />);
    await openPopup();
    await act(async () => { popup!.cb.onSuccess(reported); });
    const check = await screen.findByRole("button", { name: "Check payment status" });

    orderApi.getOrder.mockResolvedValue(paidOrder());
    fireEvent.click(check);
    expect(await screen.findByText("Payment received. Thank you!")).toBeTruthy();
    expect(paymentApi.verifyPayment).toHaveBeenCalledTimes(2);
    expect(paymentApi.verifyPayment).toHaveBeenLastCalledWith("order-1", reported);
    expect(razorpay.openRazorpayCheckout).toHaveBeenCalledTimes(1);
    expect(paymentApi.createPayment).toHaveBeenCalledTimes(1);
  });

  it("a double click on Pay opens ONE popup and creates ONE Razorpay order", async () => {
    const gate = deferred<typeof intent>();
    paymentApi.createPayment.mockReturnValue(gate.promise);
    render(<OrderPage />);
    const button = await screen.findByRole("button", { name: /^Pay .* now$/ });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(await screen.findByText(/Starting your payment/)).toBeTruthy();
    await act(async () => { gate.resolve(intent); });
    await waitFor(() => expect(popup).not.toBeNull());
    expect(paymentApi.createPayment).toHaveBeenCalledTimes(1);
    expect(razorpay.openRazorpayCheckout).toHaveBeenCalledTimes(1);
  });

  it("the cancel button is disabled while a payment is in progress", async () => {
    render(<OrderPage />);
    await openPopup();
    expect(screen.getByRole("button", { name: "Cancel order" })).toBeDisabled();
    await act(async () => { popup!.cb.onDismiss(); });
    await waitFor(() => expect(screen.getByRole("button", { name: "Cancel order" })).toBeEnabled());
  });
});

describe("/orders/[id] - retry", () => {
  it("closing the popup leaves the order payable and offers to try again on the SAME order", async () => {
    render(<OrderPage />);
    await openPopup();
    await act(async () => { popup!.cb.onDismiss(); });
    expect(await screen.findByText(/payment window was closed before paying/i)).toBeTruthy();

    popup = null;
    fireEvent.click(screen.getByRole("button", { name: "Try payment again - ₹721.35" }));
    await waitFor(() => expect(popup).not.toBeNull());
    expect(paymentApi.createPayment).toHaveBeenCalledTimes(2);
    expect(paymentApi.createPayment).toHaveBeenNthCalledWith(2, "order-1");  // never a new Pramanika order
    expect(orderApi.placeOrder).not.toHaveBeenCalled();
  });

  it("a declined payment says so, keeps the order payable, and a retry then succeeds", async () => {
    render(<OrderPage />);
    await openPopup();
    await act(async () => { popup!.cb.onFailure("Payment declined by your bank."); popup!.cb.onDismiss(); });
    const alert = await screen.findByText(/Payment declined by your bank/);
    expect(alert.textContent).toMatch(/Nothing was charged/);

    popup = null;
    fireEvent.click(screen.getByRole("button", { name: /^Try payment again/ }));
    await waitFor(() => expect(popup).not.toBeNull());
    orderApi.getOrder.mockResolvedValue(paidOrder());
    await act(async () => { popup!.cb.onSuccess(reported); });
    expect(await screen.findByText("Payment received. Thank you!")).toBeTruthy();
  });

  it("on arrival after an earlier failed attempt it already offers 'Try payment again' and explains", async () => {
    orderApi.getOrder.mockResolvedValue(makeOrder({ payment: { last_attempt: "failed", refund_pending: false } }));
    render(<OrderPage />);
    expect(await screen.findByRole("button", { name: "Try payment again - ₹721.35" })).toBeTruthy();
    expect(screen.getByText(/last payment attempt didn't go through/)).toBeTruthy();
    expect(screen.getByText("Payment pending")).toBeTruthy();
  });

  it("a payment the bank is still confirming offers a refresh, not a second payment", async () => {
    orderApi.getOrder.mockResolvedValue(makeOrder({ payment: { last_attempt: "authorized", refund_pending: false } }));
    render(<OrderPage />);
    await screen.findByText(/Please don't pay again/);
    expect(queryPayButton()).toBeNull();

    orderApi.getOrder.mockResolvedValue(paidOrder());
    fireEvent.click(screen.getByRole("button", { name: "Refresh status" }));
    expect(await screen.findByText("Paid")).toBeTruthy();
    expect(paymentApi.createPayment).not.toHaveBeenCalled();
  });

  it("if the order closed while the customer was away, starting a payment shows the server's reason and the closed order", async () => {
    paymentApi.createPayment.mockRejectedValue(apiError(409, "This order has expired and can no longer be paid. Please place a new order."));
    render(<OrderPage />);
    await screen.findByRole("button", { name: /^Pay .* now$/ });
    orderApi.getOrder.mockResolvedValue(expiredOrder()); // what the reload will see
    fireEvent.click(payButton());
    expect(await screen.findByText("Expired")).toBeTruthy();
    expect(screen.getByText(/expired because it wasn't paid in time/)).toBeTruthy();
    expect(queryPayButton()).toBeNull();
    expect(razorpay.openRazorpayCheckout).not.toHaveBeenCalled();
  });

  it("if it was paid in the meantime (another tab, the webhook), the page just shows Paid", async () => {
    paymentApi.createPayment.mockRejectedValue(apiError(409, "This order has already been paid."));
    render(<OrderPage />);
    await screen.findByRole("button", { name: /^Pay .* now$/ });
    orderApi.getOrder.mockResolvedValue(paidOrder());
    fireEvent.click(payButton());
    expect(await screen.findByText("Paid")).toBeTruthy();
    expect(queryPayButton()).toBeNull();
  });

  it("a failure starting the payment keeps the button, shows an alert, and never opens Razorpay", async () => {
    paymentApi.createPayment.mockRejectedValueOnce(apiError(502, "We could not start the payment. Nothing was charged. Please try again in a moment."));
    render(<OrderPage />);
    await screen.findByRole("button", { name: /^Pay .* now$/ });
    fireEvent.click(payButton());
    expect(await screen.findByText(/Nothing was charged/)).toBeTruthy();
    expect(payButton()).toBeEnabled();
    expect(razorpay.openRazorpayCheckout).not.toHaveBeenCalled();
    expect(screen.getByText("Payment pending")).toBeTruthy();
  });
});

describe("/orders/[id] - expiry", () => {
  it("shows an expired order as Expired, with no Cancel and no Pay", async () => {
    orderApi.getOrder.mockResolvedValue(expiredOrder());
    render(<OrderPage />);
    await screen.findByRole("heading", { name: "PRM-2026-000042" });
    expect(screen.getByText("Expired")).toBeTruthy();
    expect(screen.queryByText("Cancelled")).toBeNull();
    expect(screen.getByText("Total (expired)")).toBeTruthy();
    expect(screen.getByText(/expired because it wasn't paid in time/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cancel order" })).toBeNull();
    expect(queryPayButton()).toBeNull();
  });

  it("an order past its deadline (expiry not yet run) says the window closed and offers only Cancel", async () => {
    orderApi.getOrder.mockResolvedValue(makeOrder({ can_pay: false, expires_at: "2026-01-01T00:00:00Z" }));
    render(<OrderPage />);
    await screen.findByRole("heading", { name: "PRM-2026-000042" });
    expect(screen.getByText("Payment window closed")).toBeTruthy();
    expect(screen.getByText(/time to pay for this order has run out/)).toBeTruthy();
    expect(queryPayButton()).toBeNull();
    expect(screen.getByRole("button", { name: "Cancel order" })).toBeEnabled();
  });

  it("when the countdown reaches zero the page asks the server again and the panel goes away", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      orderApi.getOrder.mockResolvedValue(makeOrder({ expires_at: new Date(Date.now() + 2_000).toISOString() }));
      render(<OrderPage />);
      await screen.findByRole("button", { name: /^Pay .* now$/ });
      expect(orderApi.getOrder).toHaveBeenCalledTimes(1);

      orderApi.getOrder.mockResolvedValue(makeOrder({ can_pay: false, expires_at: new Date(Date.now() - 1).toISOString() }));
      await act(async () => { vi.advanceTimersByTime(3_000); });
      await waitFor(() => expect(orderApi.getOrder).toHaveBeenCalledTimes(2));
      await waitFor(() => expect(queryPayButton()).toBeNull());
      expect(screen.getByText("Payment window closed")).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  it("tells the customer when money arrived after the order closed and will be refunded", async () => {
    orderApi.getOrder.mockResolvedValue({ ...expiredOrder(), payment: { last_attempt: "captured", refund_pending: true } });
    render(<OrderPage />);
    expect(await screen.findByText(/received a payment for this order after it had closed/)).toBeTruthy();
    expect(screen.getByText(/refunded to you/)).toBeTruthy();
    expect(screen.queryByText("Paid")).toBeNull();
  });

  it("does not show the refund notice otherwise", async () => {
    render(<OrderPage />);
    await screen.findByRole("heading", { name: "PRM-2026-000042" });
    expect(screen.queryByText(/refunded to you/)).toBeNull();
  });
});
