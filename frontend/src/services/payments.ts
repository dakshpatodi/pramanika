/**
 * Payment API calls (Phase 7 backend). Authenticated by the shared
 * `apiClient`; every call is scoped to the logged-in user by the server.
 */

import { apiClient } from "@/lib/axios";
import type { ApiResponse } from "@/types/auth";
import type { Order } from "@/types/order";
import type { PaymentIntent, PaymentVerificationInput } from "@/types/payment";

/**
 * Starts (or resumes) paying for one of the user's unpaid orders.
 *
 * There is no request body: the server prices the payment from the stored
 * order. Safe to call repeatedly - while the order has an open payment the
 * same Razorpay order comes back.
 */
export async function createPayment(orderId: string): Promise<PaymentIntent> {
  const { data } = await apiClient.post<ApiResponse<PaymentIntent>>(`/api/orders/${orderId}/payment`);
  return data.data as PaymentIntent;
}

/**
 * Asks the server to verify what Razorpay Checkout returned. The server
 * checks the signature (and that it belongs to this order's Razorpay order)
 * and answers with the order as it now stands. Repeating the call is safe.
 *
 * An order is only paid when the RETURNED order says `payment_status:
 * "paid"` - not because this request returned 200.
 */
export async function verifyPayment(orderId: string, input: PaymentVerificationInput): Promise<Order> {
  const { data } = await apiClient.post<ApiResponse<Order>>(`/api/orders/${orderId}/payment/verify`, input);
  return data.data as Order;
}
