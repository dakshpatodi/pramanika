import { AxiosError } from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Address } from "@/types/address";
import type { Cart } from "@/types/cart";
import type { Order } from "@/types/order";

const { auth, cartCtx, router, addressApi, orderApi, paymentApi, razorpay } = vi.hoisted(() => ({
  auth: { user: { id: "u1" } as null | { id: string }, isLoading: false, isAuthenticated: true },
  cartCtx: {} as Record<string, any>,
  router: { push: vi.fn(), replace: vi.fn() },
  addressApi: { listAddresses: vi.fn(), createAddress: vi.fn() },
  orderApi: { placeOrder: vi.fn(), getOrder: vi.fn() },
  paymentApi: { createPayment: vi.fn(), verifyPayment: vi.fn() },
  razorpay: { loadRazorpayScript: vi.fn(), openRazorpayCheckout: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/context/CartContext", () => ({ useCart: () => cartCtx }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/checkout" }));
vi.mock("@/services/addresses", () => addressApi);
vi.mock("@/services/orders", () => orderApi);
vi.mock("@/services/payments", () => paymentApi);
vi.mock("@/lib/razorpay", () => razorpay);

import CheckoutPage from "@/app/checkout/page";

const TOTAL = 721.35;
const cart = (over: Partial<Cart> = {}): Cart => ({
  id: "c1",
  items: [{
    id: "i1", product: { id: "p1", name: "Multigrain Cereal", slug: "mc", sku: "S1", image_url: null },
    quantity: 3, unit_price: 229, line_subtotal: 687, available_quantity: 10, issue: null,
  }],
  item_count: 3, has_issues: false, coupon: null,
  totals: { subtotal: 687, discount: 0, taxable_amount: 687, gst_rate: 0.05, gst: 34.35, delivery_charge: 0, amount_for_free_delivery: 0, total: TOTAL, currency: "INR" },
  ...over,
});
const address: Address = {
  id: "a1", full_name: "Asha Rao", phone_number: "9876543210", address_line_1: "1 MG Road", address_line_2: null,
  city: "Pune", state: "Maharashtra", postal_code: "411001", country: "India", is_default: true, created_at: "2026-10-05T00:00:00Z",
};
const placed = { id: "order-1", order_number: "PRM-2026-000001" } as Order;
const intent = {
  order_id: "order-1", order_number: "PRM-2026-000001", razorpay_order_id: "order_SRV", razorpay_key_id: "rzp_test_KEY",
  amount_paise: 72135, currency: "INR",
};
const paidResponse = { razorpay_order_id: "order_SRV", razorpay_payment_id: "pay_1", razorpay_signature: "sig_1" };

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

/** Render, place the order (the cart empties, as on the real server), wait for the popup. */
async function placeAndOpenPopup() {
  render(<CheckoutPage />);
  await screen.findAllByRole("radio");
  fireEvent.click(screen.getByRole("button", { name: /^Place order/ }));
  await waitFor(() => expect(popup).not.toBeNull());
}
const retryButton = () => screen.getByRole("button", { name: /^Pay .* now$|^Try payment again$/ });

beforeEach(() => {
  popup = null;
  auth.user = { id: "u1" };
  router.push.mockReset(); router.replace.mockReset();
  addressApi.listAddresses.mockReset().mockResolvedValue([address]);
  orderApi.placeOrder.mockReset().mockResolvedValue({ order: placed, created: true });
  orderApi.getOrder.mockReset();
  paymentApi.createPayment.mockReset().mockResolvedValue(intent);
  paymentApi.verifyPayment.mockReset().mockResolvedValue({ id: "order-1", payment_status: "paid" });
  razorpay.loadRazorpayScript.mockReset().mockResolvedValue(undefined);
  razorpay.openRazorpayCheckout.mockReset().mockImplementation((request: unknown, cb: Callbacks) => { popup = { request, cb }; });
  // The server empties the cart once the order exists.
  Object.assign(cartCtx, {
    cart: cart(), itemCount: 3, isLoading: false, isMutating: false, loadError: null,
    refreshCart: vi.fn().mockImplementation(async () => { cartCtx.cart = cart({ items: [], item_count: 0 }); }),
  });
});
afterEach(cleanup);

describe("/checkout - paying after placing the order", () => {
  it("places the order, opens Razorpay for the SERVER's amount, and leaves only after the backend verified", async () => {
    await placeAndOpenPopup();

    expect(orderApi.placeOrder).toHaveBeenCalledTimes(1);
    expect(paymentApi.createPayment).toHaveBeenCalledWith("order-1");
    expect(popup!.request).toMatchObject({ keyId: "rzp_test_KEY", amountPaise: 72135, currency: "INR", razorpayOrderId: "order_SRV" });
    expect(screen.getByText("Order placed")).toBeTruthy();
    expect(screen.getByText(/Complete your payment in the Razorpay window/)).toBeTruthy();
    expect(router.replace).not.toHaveBeenCalled(); // not leaving just because the order exists
    expect(router.replace).not.toHaveBeenCalledWith("/cart"); // the emptied cart must not bounce us away

    const verification = deferred<{ id: string; payment_status: string }>();
    paymentApi.verifyPayment.mockReturnValue(verification.promise);
    popup!.cb.onSuccess(paidResponse);

    expect(await screen.findByText(/Confirming your payment/)).toBeTruthy();
    expect(paymentApi.verifyPayment).toHaveBeenCalledWith("order-1", paidResponse);
    expect(document.body.textContent).not.toMatch(/Payment received/);
    expect(router.replace).not.toHaveBeenCalled(); // the popup said "success", the server has not

    verification.resolve({ id: "order-1", payment_status: "paid" });
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/orders/order-1"));
    expect(screen.getByText(/Payment received/)).toBeTruthy();
  });

  it("a Place order double click makes one order and one Razorpay order", async () => {
    render(<CheckoutPage />);
    await screen.findAllByRole("radio");
    const button = screen.getByRole("button", { name: /^Place order/ });
    fireEvent.click(button); fireEvent.click(button); fireEvent.click(button);
    await waitFor(() => expect(popup).not.toBeNull());
    expect(orderApi.placeOrder).toHaveBeenCalledTimes(1);
    expect(paymentApi.createPayment).toHaveBeenCalledTimes(1);
    expect(razorpay.openRazorpayCheckout).toHaveBeenCalledTimes(1);
  });

  it("when the order is refused nothing is paid and no payment flow starts", async () => {
    orderApi.placeOrder.mockRejectedValue(new Error("Only 1 unit is available in stock."));
    cartCtx.refreshCart = vi.fn().mockResolvedValue(undefined); // a refused order leaves the cart as it was
    render(<CheckoutPage />);
    await screen.findAllByRole("radio");
    fireEvent.click(screen.getByRole("button", { name: /^Place order/ }));
    expect(await screen.findByText(/Only 1 unit is available/)).toBeTruthy();
    expect(paymentApi.createPayment).not.toHaveBeenCalled();
    expect(razorpay.openRazorpayCheckout).not.toHaveBeenCalled();
  });
});

describe("/checkout - the customer closes the popup", () => {
  it("keeps the saved order, explains, and lets them pay again WITHOUT creating another order", async () => {
    await placeAndOpenPopup();
    popup!.cb.onDismiss();

    expect(await screen.findByText(/payment window was closed/i)).toBeTruthy();
    expect(screen.getByText("Order placed")).toBeTruthy();
    expect(screen.getByRole("link", { name: "View my order" }).getAttribute("href")).toBe("/orders/order-1");
    expect(router.replace).not.toHaveBeenCalled();
    expect(retryButton().textContent).toBe("Pay ₹721.35 now");

    popup = null;
    fireEvent.click(retryButton());
    await waitFor(() => expect(popup).not.toBeNull());
    expect(paymentApi.createPayment).toHaveBeenCalledTimes(2);
    expect(orderApi.placeOrder).toHaveBeenCalledTimes(1); // the same order, not a new one

    popup!.cb.onSuccess(paidResponse);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/orders/order-1"));
  });

  it("does not leave the page when a retry ends without a payment either", async () => {
    await placeAndOpenPopup();
    popup!.cb.onDismiss();
    await screen.findByText(/payment window was closed/i);
    popup = null;
    fireEvent.click(retryButton());
    await waitFor(() => expect(popup).not.toBeNull());
    popup!.cb.onDismiss(); // closed again
    await waitFor(() => expect(retryButton()).toBeTruthy());
    await new Promise((r) => setTimeout(r, 20));
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("clicking the retry button twice opens one popup", async () => {
    await placeAndOpenPopup();
    popup!.cb.onDismiss();
    await screen.findByText(/payment window was closed/i);
    popup = null;
    const button = retryButton();
    fireEvent.click(button); fireEvent.click(button);
    await waitFor(() => expect(popup).not.toBeNull());
    expect(razorpay.openRazorpayCheckout).toHaveBeenCalledTimes(2); // the first popup + exactly one more
  });
});

describe("/checkout - the payment fails", () => {
  it("shows the bank's reason once the customer gives up, and offers another try", async () => {
    await placeAndOpenPopup();
    popup!.cb.onFailure("Your card was declined.");
    popup!.cb.onDismiss();
    expect(await screen.findByText(/Your card was declined\./)).toBeTruthy();
    expect(screen.getByText(/Nothing was charged/)).toBeTruthy();
    expect(retryButton()).toBeTruthy();
    expect(router.replace).not.toHaveBeenCalled();
    expect(paymentApi.verifyPayment).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toMatch(/Payment received|Thank you/);
  });

  it("explains a Razorpay/server outage and offers a retry", async () => {
    paymentApi.createPayment.mockRejectedValueOnce(apiError(502, "We could not start the payment. Nothing was charged. Please try again in a moment."));
    render(<CheckoutPage />);
    await screen.findAllByRole("radio");
    fireEvent.click(screen.getByRole("button", { name: /^Place order/ }));
    expect(await screen.findByText(/We could not start the payment/)).toBeTruthy();
    expect(razorpay.openRazorpayCheckout).not.toHaveBeenCalled();

    fireEvent.click(retryButton());
    await waitFor(() => expect(popup).not.toBeNull());
    expect(orderApi.placeOrder).toHaveBeenCalledTimes(1);
  });

  it("explains a script that would not load and offers a retry", async () => {
    razorpay.loadRazorpayScript.mockRejectedValueOnce(new Error("We couldn't load the payment window. Check your connection and try again."));
    render(<CheckoutPage />);
    await screen.findAllByRole("radio");
    fireEvent.click(screen.getByRole("button", { name: /^Place order/ }));
    expect(await screen.findByText(/couldn't load the payment window/)).toBeTruthy();
    expect(paymentApi.createPayment).not.toHaveBeenCalled();
    fireEvent.click(retryButton());
    await waitFor(() => expect(popup).not.toBeNull());
  });
});

describe("/checkout - the backend cannot confirm the payment", () => {
  it("says so, warns against paying twice, and re-checks without reopening the popup", async () => {
    paymentApi.verifyPayment.mockRejectedValueOnce(new Error("Network Error"));
    await placeAndOpenPopup();
    popup!.cb.onSuccess(paidResponse);

    expect(await screen.findByText(/don't pay again/i)).toBeTruthy();
    expect(router.replace).not.toHaveBeenCalled(); // NOT treated as paid
    expect(document.body.textContent).not.toMatch(/Payment received/);
    expect(screen.getByRole("link", { name: "View my order" }).getAttribute("href")).toBe("/orders/order-1");
    expect(screen.queryByRole("button", { name: /^Pay .* now$/ })).toBeNull(); // paying again is not offered

    fireEvent.click(screen.getByRole("button", { name: "Check payment status" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/orders/order-1"));
    expect(paymentApi.verifyPayment).toHaveBeenCalledTimes(2);
    expect(paymentApi.verifyPayment.mock.calls[1]).toEqual(["order-1", paidResponse]);
    expect(razorpay.openRazorpayCheckout).toHaveBeenCalledTimes(1);
    expect(paymentApi.createPayment).toHaveBeenCalledTimes(1);
  });

  it("stays on the page while a re-check still cannot confirm the payment", async () => {
    paymentApi.verifyPayment.mockRejectedValue(new Error("Network Error"));
    await placeAndOpenPopup();
    popup!.cb.onSuccess(paidResponse);
    fireEvent.click(await screen.findByRole("button", { name: "Check payment status" }));
    await waitFor(() => expect(paymentApi.verifyPayment).toHaveBeenCalledTimes(2));
    await screen.findByRole("button", { name: "Check payment status" });
    await new Promise((r) => setTimeout(r, 20));
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("a payment that arrived after the order closed explains it, offers no retry and does not claim success", async () => {
    const late = "Your payment was received after this order had been closed, so the order was not placed. The amount will be refunded to you.";
    paymentApi.verifyPayment.mockRejectedValue(apiError(409, late));
    orderApi.getOrder.mockResolvedValue({ id: "order-1", payment_status: "pending", status: "cancelled" });
    await placeAndOpenPopup();
    popup!.cb.onSuccess(paidResponse);
    expect(await screen.findByText(late)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Check payment status" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Pay .* now$|^Try payment again$/ })).toBeNull();
    expect(screen.getByRole("link", { name: "View my order" }).getAttribute("href")).toBe("/orders/order-1");
    expect(router.replace).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toMatch(/Payment received - taking you/);
  });

  it("shows the server's reason when it rejects the payment", async () => {
    paymentApi.verifyPayment.mockRejectedValue(apiError(400, "We could not verify this payment."));
    await placeAndOpenPopup();
    popup!.cb.onSuccess(paidResponse);
    expect(await screen.findByText("We could not verify this payment.")).toBeTruthy();
    expect(router.replace).not.toHaveBeenCalled();
  });
});

describe("/checkout - orders that cannot be paid", () => {
  it("an order that was already paid goes straight to the order page", async () => {
    paymentApi.createPayment.mockRejectedValue(apiError(409, "This order has already been paid."));
    orderApi.getOrder.mockResolvedValue({ id: "order-1", payment_status: "paid" });
    render(<CheckoutPage />);
    await screen.findAllByRole("radio");
    fireEvent.click(screen.getByRole("button", { name: /^Place order/ }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/orders/order-1"));
    expect(razorpay.openRazorpayCheckout).not.toHaveBeenCalled();
  });

  it("an expired or cancelled order shows the reason, links to the order, and offers no payment", async () => {
    paymentApi.createPayment.mockRejectedValue(apiError(409, "This order has expired and can no longer be paid. Please place a new order."));
    orderApi.getOrder.mockResolvedValue({ id: "order-1", payment_status: "pending", status: "cancelled" });
    render(<CheckoutPage />);
    await screen.findAllByRole("radio");
    fireEvent.click(screen.getByRole("button", { name: /^Place order/ }));
    expect(await screen.findByText(/has expired/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Pay .* now$|^Try payment again$/ })).toBeNull();
    expect(screen.getByRole("link", { name: "View my order" }).getAttribute("href")).toBe("/orders/order-1");
    expect(router.replace).not.toHaveBeenCalled();
    expect(razorpay.openRazorpayCheckout).not.toHaveBeenCalled();
  });
});
