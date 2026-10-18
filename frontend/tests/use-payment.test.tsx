import { AxiosError } from "axios";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { razorpay, payments, orders } = vi.hoisted(() => ({
  razorpay: { loadRazorpayScript: vi.fn(), openRazorpayCheckout: vi.fn() },
  payments: { createPayment: vi.fn(), verifyPayment: vi.fn() },
  orders: { getOrder: vi.fn() },
}));
vi.mock("@/lib/razorpay", () => razorpay);
vi.mock("@/services/payments", () => payments);
vi.mock("@/services/orders", () => orders);

import { usePayment } from "@/hooks/usePayment";

const order = { id: "o1", order_number: "PRM-2026-000001" };
const intent = {
  order_id: "o1", order_number: "PRM-2026-000001", razorpay_order_id: "order_SRV", razorpay_key_id: "rzp_test_KEY",
  amount_paise: 40621, currency: "INR",
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
  let resolve!: (v: T) => void; let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
/** Start paying and wait until the popup has been "opened". `done` is the flow's outcome. */
async function startPaying(result: { current: ReturnType<typeof usePayment> }) {
  let done!: Promise<string>;
  act(() => { done = result.current.pay(order); });
  await waitFor(() => expect(popup).not.toBeNull());
  return { done };
}

beforeEach(() => {
  popup = null;
  razorpay.loadRazorpayScript.mockReset().mockResolvedValue(undefined);
  razorpay.openRazorpayCheckout.mockReset().mockImplementation((request: unknown, cb: Callbacks) => { popup = { request, cb }; });
  payments.createPayment.mockReset().mockResolvedValue(intent);
  payments.verifyPayment.mockReset().mockResolvedValue({ id: "o1", payment_status: "paid" });
  orders.getOrder.mockReset();
});

describe("usePayment - the happy path", () => {
  it("opens Razorpay with the SERVER's values, then succeeds only after the backend verified", async () => {
    const { result } = renderHook(() => usePayment());
    await waitFor(() => expect(result.current.phase).toBe("idle"));

    const { done: outcome } = await startPaying(result);
    await waitFor(() => expect(result.current.phase).toBe("awaiting"));
    expect(razorpay.loadRazorpayScript).toHaveBeenCalledTimes(1);
    expect(payments.createPayment).toHaveBeenCalledWith("o1");
    expect(popup!.request).toEqual({
      keyId: "rzp_test_KEY", amountPaise: 40621, currency: "INR", razorpayOrderId: "order_SRV", description: "Order PRM-2026-000001",
    });
    await waitFor(() => expect(result.current.isBusy).toBe(true));

    const verification = deferred<{ id: string; payment_status: string }>();
    payments.verifyPayment.mockReturnValue(verification.promise);
    act(() => popup!.cb.onSuccess(paidResponse));

    // The popup said "success", but nothing is paid until the server says so.
    await waitFor(() => expect(result.current.phase).toBe("verifying"));
    await waitFor(() => expect(result.current.phase).not.toBe("paid"));
    expect(payments.verifyPayment).toHaveBeenCalledWith("o1", paidResponse);

    await act(async () => verification.resolve({ id: "o1", payment_status: "paid" }));
    expect(await outcome).toBe("paid");
    await waitFor(() => expect(result.current.phase).toBe("paid"));
    await waitFor(() => expect(result.current.error).toBeNull());
    await waitFor(() => expect(result.current.isBusy).toBe(false));
  });

  it("sends exactly the three Razorpay fields to the backend - nothing extra, no amount", async () => {
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => popup!.cb.onSuccess({ ...paidResponse, amount: 1, razorpay_extra: "x" }));
    await outcome;
    expect(Object.keys(payments.verifyPayment.mock.calls[0][1]).sort()).toEqual([
      "razorpay_order_id", "razorpay_payment_id", "razorpay_signature",
    ]);
  });

  it("is NOT paid when the server answers OK but says the order is not paid", async () => {
    payments.verifyPayment.mockResolvedValue({ id: "o1", payment_status: "pending" });
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => popup!.cb.onSuccess(paidResponse));
    expect(await outcome).toBe("verify_failed");
    await waitFor(() => expect(result.current.phase).toBe("verify_failed"));
  });

  it("is NOT paid when the server returns no order at all", async () => {
    payments.verifyPayment.mockResolvedValue(undefined);
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => popup!.cb.onSuccess(paidResponse));
    expect(await outcome).toBe("verify_failed");
  });
});

describe("usePayment - verification problems", () => {
  it("keeps the payment details and lets the customer re-check without paying again", async () => {
    payments.verifyPayment.mockRejectedValueOnce(new Error("Network Error"));
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => popup!.cb.onSuccess(paidResponse));

    expect(await outcome).toBe("verify_failed");
    await waitFor(() => expect(result.current.phase).toBe("verify_failed"));
    await waitFor(() => expect(result.current.error).toMatch(/don't pay again/i));

    payments.verifyPayment.mockResolvedValueOnce({ id: "o1", payment_status: "paid" });
    let again!: string;
    await act(async () => { again = await result.current.retryVerification(order); });
    expect(again).toBe("paid");
    await waitFor(() => expect(result.current.phase).toBe("paid"));
    expect(payments.verifyPayment).toHaveBeenCalledTimes(2);
    expect(payments.verifyPayment.mock.calls[1]).toEqual(["o1", paidResponse]); // the same values
    expect(payments.createPayment).toHaveBeenCalledTimes(1); // no new Razorpay order, no new popup
    expect(razorpay.openRazorpayCheckout).toHaveBeenCalledTimes(1);
  });

  it("shows the server's own explanation when it rejects the verification", async () => {
    payments.verifyPayment.mockRejectedValue(apiError(400, "We could not verify this payment."));
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => popup!.cb.onSuccess(paidResponse));
    expect(await outcome).toBe("verify_failed");
    await waitFor(() => expect(result.current.error).toBe("We could not verify this payment."));
  });

  it("a payment that arrived after the order closed (409) is 'closed' with the server's message - not something to re-check", async () => {
    const late = "Your payment was received after this order had been closed, so the order was not placed. The amount will be refunded to you.";
    payments.verifyPayment.mockRejectedValue(apiError(409, late));
    orders.getOrder.mockResolvedValue({ id: "o1", payment_status: "pending", status: "cancelled" });
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => popup!.cb.onSuccess(paidResponse));
    expect(await outcome).toBe("closed");
    await waitFor(() => expect(result.current.phase).toBe("closed"));
    await waitFor(() => expect(result.current.error).toBe(late));

    // and there is nothing left to re-check
    payments.verifyPayment.mockClear();
    let again!: string;
    await act(async () => { again = await result.current.retryVerification(order); });
    expect(again).toBe("failed");
    expect(payments.verifyPayment).not.toHaveBeenCalled();
  });

  it("a 409 from verify for an order the server says is paid is simply paid", async () => {
    payments.verifyPayment.mockRejectedValue(apiError(409, "This order has already been paid."));
    orders.getOrder.mockResolvedValue({ id: "o1", payment_status: "paid" });
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => popup!.cb.onSuccess(paidResponse));
    expect(await outcome).toBe("paid");
    await waitFor(() => expect(result.current.phase).toBe("paid"));
  });

  it("a 409 from verify is still 'closed' if the order cannot be re-read", async () => {
    payments.verifyPayment.mockRejectedValue(apiError(409, "This order has already been paid."));
    orders.getOrder.mockRejectedValue(new Error("Network Error"));
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => popup!.cb.onSuccess(paidResponse));
    expect(await outcome).toBe("closed");
    await waitFor(() => expect(result.current.error).toBe("This order has already been paid."));
  });

  it("treats an incomplete Razorpay response as unverified and sends nothing", async () => {
    for (const bad of [{}, { ...paidResponse, razorpay_signature: "" }, { ...paidResponse, razorpay_payment_id: undefined }, null]) {
      payments.verifyPayment.mockClear();
      popup = null;
      const { result } = renderHook(() => usePayment());
      const { done: outcome } = await startPaying(result);
      act(() => popup!.cb.onSuccess(bad));
      expect(await outcome).toBe("verify_failed");
      expect(payments.verifyPayment).not.toHaveBeenCalled();
    }
  });

  it("verifies only once even if Razorpay calls the success handler twice", async () => {
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => { popup!.cb.onSuccess(paidResponse); popup!.cb.onSuccess(paidResponse); });
    await outcome;
    expect(payments.verifyPayment).toHaveBeenCalledTimes(1);
  });

  it("re-checking with nothing to check is refused locally", async () => {
    const { result } = renderHook(() => usePayment());
    let outcome!: string;
    await act(async () => { outcome = await result.current.retryVerification(order); });
    expect(outcome).toBe("failed");
    expect(payments.verifyPayment).not.toHaveBeenCalled();
  });

  it("forgets the payment details once the order is paid, and when a new payment starts", async () => {
    const { result } = renderHook(() => usePayment());
    const { done } = await startPaying(result);
    act(() => popup!.cb.onSuccess(paidResponse));
    await done;
    payments.verifyPayment.mockClear();
    let outcome!: string;
    await act(async () => { outcome = await result.current.retryVerification(order); });
    expect(outcome).toBe("failed"); // nothing left to re-check
    expect(payments.verifyPayment).not.toHaveBeenCalled();
  });

  it("a new payment attempt discards the details of an earlier unconfirmed one", async () => {
    payments.verifyPayment.mockRejectedValueOnce(new Error("Network Error"));
    const { result } = renderHook(() => usePayment());
    const first = await startPaying(result);
    act(() => popup!.cb.onSuccess(paidResponse));
    await first.done; // verify_failed: the details are kept for a re-check

    popup = null;
    const second = await startPaying(result); // the customer chose to pay afresh
    act(() => popup!.cb.onDismiss());
    await second.done;

    payments.verifyPayment.mockClear();
    let outcome!: string;
    await act(async () => { outcome = await result.current.retryVerification(order); });
    expect(outcome).toBe("failed"); // the old payment's details are gone
    expect(payments.verifyPayment).not.toHaveBeenCalled();
  });

  it("closing the popup after paying does not undo the success", async () => {
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => { popup!.cb.onSuccess(paidResponse); popup!.cb.onDismiss(); });
    expect(await outcome).toBe("paid");
    await waitFor(() => expect(result.current.phase).toBe("paid"));
  });
});

describe("usePayment - the customer does not pay", () => {
  it("reports a closed popup as dismissed, keeps the order, and can be retried", async () => {
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => popup!.cb.onDismiss());
    expect(await outcome).toBe("dismissed");
    await waitFor(() => expect(result.current.phase).toBe("dismissed"));
    await waitFor(() => expect(result.current.error).toMatch(/order is saved/i));
    expect(payments.verifyPayment).not.toHaveBeenCalled();
    await waitFor(() => expect(result.current.isBusy).toBe(false));

    // Retry: asks the server again (which hands back the same Razorpay order) and opens the popup again.
    popup = null;
    const { done: retry } = await startPaying(result);
    await waitFor(() => expect(result.current.phase).toBe("awaiting"));
    expect(payments.createPayment).toHaveBeenCalledTimes(2);
    act(() => popup!.cb.onSuccess(paidResponse));
    expect(await retry).toBe("paid");
  });

  it("reports a failed attempt (with the bank's reason) when the customer then gives up", async () => {
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => { popup!.cb.onFailure("Your card was declined."); });
    expect(result.current.phase).toBe("awaiting"); // the popup is still open: they may try another method
    act(() => popup!.cb.onDismiss());
    expect(await outcome).toBe("failed");
    await waitFor(() => expect(result.current.phase).toBe("failed"));
    await waitFor(() => expect(result.current.error).toContain("Your card was declined."));
    await waitFor(() => expect(result.current.error).toMatch(/nothing was charged/i));
    expect(payments.verifyPayment).not.toHaveBeenCalled();
  });

  it("a failed attempt followed by a successful one in the same popup is a success", async () => {
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => popup!.cb.onFailure("Insufficient funds."));
    act(() => popup!.cb.onSuccess(paidResponse));
    expect(await outcome).toBe("paid");
    await waitFor(() => expect(result.current.error).toBeNull());
  });

  it("a failure without a reason still ends as 'failed' with a safe message", async () => {
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => { popup!.cb.onFailure(null); popup!.cb.onDismiss(); });
    expect(await outcome).toBe("failed");
    await waitFor(() => expect(result.current.error).toMatch(/didn't go through/));
  });
});

describe("usePayment - could not start", () => {
  it("does not ask the server for a Razorpay order if the script cannot load", async () => {
    razorpay.loadRazorpayScript.mockRejectedValue(new Error("We couldn't load the payment window. Check your connection and try again."));
    const { result } = renderHook(() => usePayment());
    let outcome!: string;
    await act(async () => { outcome = await result.current.pay(order); });
    expect(outcome).toBe("failed");
    await waitFor(() => expect(result.current.error).toMatch(/couldn't load the payment window/));
    expect(payments.createPayment).not.toHaveBeenCalled();
    expect(razorpay.openRazorpayCheckout).not.toHaveBeenCalled();
  });

  it("explains a server or network failure and allows a retry", async () => {
    for (const failure of [apiError(502, "We could not start the payment. Nothing was charged. Please try again in a moment."), new Error("Network Error")]) {
      payments.createPayment.mockRejectedValueOnce(failure);
      const { result } = renderHook(() => usePayment());
      let outcome!: string;
      await act(async () => { outcome = await result.current.pay(order); });
      expect(outcome).toBe("failed");
      await waitFor(() => expect(result.current.phase).toBe("failed"));
      await waitFor(() => expect(result.current.error).toBeTruthy());
      await waitFor(() => expect(result.current.isBusy).toBe(false));
    }
    expect(razorpay.openRazorpayCheckout).not.toHaveBeenCalled();
  });

  it("shows the server's message for a 502", async () => {
    payments.createPayment.mockRejectedValue(apiError(502, "We could not start the payment. Nothing was charged. Please try again in a moment."));
    const { result } = renderHook(() => usePayment());
    await act(async () => { await result.current.pay(order); });
    await waitFor(() => expect(result.current.error).toBe("We could not start the payment. Nothing was charged. Please try again in a moment."));
  });

  it("fails cleanly if the Razorpay popup itself cannot open", async () => {
    razorpay.openRazorpayCheckout.mockImplementation(() => { throw new Error("The payment window is not available. Please try again."); });
    const { result } = renderHook(() => usePayment());
    let outcome!: string;
    await act(async () => { outcome = await result.current.pay(order); });
    expect(outcome).toBe("failed");
    await waitFor(() => expect(result.current.error).toMatch(/not available/));
    await waitFor(() => expect(result.current.isBusy).toBe(false));
  });
});

describe("usePayment - orders that cannot be paid", () => {
  it("an already-paid order (409 + the server says paid) is simply paid - no popup", async () => {
    payments.createPayment.mockRejectedValue(apiError(409, "This order has already been paid."));
    orders.getOrder.mockResolvedValue({ id: "o1", payment_status: "paid" });
    const { result } = renderHook(() => usePayment());
    let outcome!: string;
    await act(async () => { outcome = await result.current.pay(order); });
    expect(outcome).toBe("paid");
    await waitFor(() => expect(result.current.phase).toBe("paid"));
    expect(orders.getOrder).toHaveBeenCalledWith("o1");
    expect(razorpay.openRazorpayCheckout).not.toHaveBeenCalled();
  });

  it("a 409 for an order that is NOT paid (expired / cancelled) is 'closed' with the server's message and no retry", async () => {
    payments.createPayment.mockRejectedValue(apiError(409, "This order has expired and can no longer be paid. Please place a new order."));
    orders.getOrder.mockResolvedValue({ id: "o1", payment_status: "pending", status: "cancelled" });
    const { result } = renderHook(() => usePayment());
    let outcome!: string;
    await act(async () => { outcome = await result.current.pay(order); });
    expect(outcome).toBe("closed");
    await waitFor(() => expect(result.current.phase).toBe("closed"));
    await waitFor(() => expect(result.current.error).toMatch(/expired/));
    expect(razorpay.openRazorpayCheckout).not.toHaveBeenCalled();
  });

  it("a 409 is still 'closed' if the order cannot be re-read", async () => {
    payments.createPayment.mockRejectedValue(apiError(409, "This order was cancelled and can no longer be paid."));
    orders.getOrder.mockRejectedValue(new Error("Network Error"));
    const { result } = renderHook(() => usePayment());
    await act(async () => { await result.current.pay(order); });
    await waitFor(() => expect(result.current.phase).toBe("closed"));
    await waitFor(() => expect(result.current.error).toMatch(/cancelled/));
  });

  it("a 404 is 'closed'", async () => {
    payments.createPayment.mockRejectedValue(apiError(404, "Order was not found."));
    const { result } = renderHook(() => usePayment());
    await act(async () => { await result.current.pay(order); });
    await waitFor(() => expect(result.current.phase).toBe("closed"));
    await waitFor(() => expect(result.current.error).toBe("Order was not found."));
  });
});

describe("usePayment - duplicate clicks", () => {
  it("runs ONE flow however often pay is called while it is in progress", async () => {
    const intentPending = deferred<typeof intent>();
    payments.createPayment.mockReturnValue(intentPending.promise);
    const { result } = renderHook(() => usePayment());

    let a!: Promise<string>, b!: Promise<string>, c!: Promise<string>;
    act(() => { a = result.current.pay(order); b = result.current.pay(order); c = result.current.pay(order); });
    expect(b).toBe(a);
    expect(c).toBe(a);

    await act(async () => intentPending.resolve(intent));
    await waitFor(() => expect(popup).not.toBeNull());
    // Still in progress (popup open): another click is still the same flow.
    let d!: Promise<string>;
    act(() => { d = result.current.pay(order); });
    expect(d).toBe(a);

    act(() => popup!.cb.onSuccess(paidResponse));
    expect(await a).toBe("paid");
    expect(payments.createPayment).toHaveBeenCalledTimes(1);
    expect(razorpay.openRazorpayCheckout).toHaveBeenCalledTimes(1);
    expect(payments.verifyPayment).toHaveBeenCalledTimes(1);
  });

  it("allows a new flow once the previous one has ended", async () => {
    const { result } = renderHook(() => usePayment());
    const { done: first } = await startPaying(result);
    act(() => popup!.cb.onDismiss());
    await first;
    popup = null;
    const { done: second } = await startPaying(result);
    expect(second).not.toBe(first);
    act(() => popup!.cb.onDismiss());
    await second;
    expect(razorpay.openRazorpayCheckout).toHaveBeenCalledTimes(2);
  });

  it("a double click on 'check payment status' verifies once", async () => {
    payments.verifyPayment.mockRejectedValueOnce(new Error("Network Error"));
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => popup!.cb.onSuccess(paidResponse));
    await outcome;

    const pending = deferred<{ id: string; payment_status: string }>();
    payments.verifyPayment.mockReturnValue(pending.promise);
    let a!: Promise<string>, b!: Promise<string>;
    act(() => { a = result.current.retryVerification(order); b = result.current.retryVerification(order); });
    expect(b).toBe(a);
    await act(async () => pending.resolve({ id: "o1", payment_status: "paid" }));
    await a;
    expect(payments.verifyPayment).toHaveBeenCalledTimes(2); // the original + ONE re-check
  });
});

describe("usePayment - hygiene", () => {
  it("never writes the signature or payment id to the console", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((m) => vi.spyOn(console, m).mockImplementation(() => undefined));
    payments.verifyPayment.mockRejectedValueOnce(new Error("Network Error"));
    const { result } = renderHook(() => usePayment());
    const { done: outcome } = await startPaying(result);
    act(() => popup!.cb.onSuccess(paidResponse));
    await outcome;
    const printed = spies.flatMap((s) => s.mock.calls).flat().map(String).join(" ");
    expect(printed).not.toContain("sig_1");
    expect(printed).not.toContain("pay_1");
    spies.forEach((s) => s.mockRestore());
  });
});
