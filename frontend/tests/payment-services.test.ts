import { beforeEach, describe, expect, it, vi } from "vitest";

const { client } = vi.hoisted(() => ({ client: { get: vi.fn(), post: vi.fn() } }));
vi.mock("@/lib/axios", () => ({ apiClient: client }));

import { createPayment, verifyPayment } from "@/services/payments";

beforeEach(() => {
  client.get.mockReset();
  client.post.mockReset();
});

describe("payment service", () => {
  it("starts a payment with a body-less POST to the order's payment endpoint and unwraps the envelope", async () => {
    const intent = {
      order_id: "o1", order_number: "PRM-1", razorpay_order_id: "order_X", razorpay_key_id: "rzp_test_K",
      amount_paise: 40621, currency: "INR",
    };
    client.post.mockResolvedValue({ status: 201, data: { success: true, message: "ok", data: intent } });
    expect(await createPayment("o1")).toEqual(intent);
    // No body, no amount: the server prices the payment from the stored order.
    expect(client.post).toHaveBeenCalledTimes(1);
    expect(client.post.mock.calls[0]).toEqual(["/api/orders/o1/payment"]);
  });

  it("sends exactly the three Razorpay values to the verify endpoint", async () => {
    client.post.mockResolvedValue({ status: 200, data: { success: true, message: "ok", data: { id: "o1", payment_status: "paid" } } });
    const input = { razorpay_order_id: "order_X", razorpay_payment_id: "pay_Y", razorpay_signature: "sig" };
    expect(await verifyPayment("o1", input)).toEqual({ id: "o1", payment_status: "paid" });
    expect(client.post).toHaveBeenCalledWith("/api/orders/o1/payment/verify", input);
    expect(Object.keys(client.post.mock.calls[0][1]).sort()).toEqual(["razorpay_order_id", "razorpay_payment_id", "razorpay_signature"]);
  });

  it("lets errors through untouched so the caller can read the server's status and message", async () => {
    const failure = Object.assign(new Error("boom"), { response: { status: 409 } });
    client.post.mockRejectedValue(failure);
    await expect(createPayment("o1")).rejects.toBe(failure);
    await expect(verifyPayment("o1", { razorpay_order_id: "a", razorpay_payment_id: "b", razorpay_signature: "c" })).rejects.toBe(failure);
  });
});
