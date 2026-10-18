/**
 * Order API calls (Phase 6 backend, /api/orders).
 *
 * Every call is authenticated by the shared `apiClient` and scoped to the
 * logged-in user by the server: another customer's order id simply
 * answers "not found".
 */

import { apiClient } from "@/lib/axios";
import type { ApiResponse } from "@/types/auth";
import type { Order, OrderList, PlaceOrderInput, PlaceOrderResult } from "@/types/order";

/**
 * Places an order from the user's server-side cart.
 *
 * `idempotencyKey` is required: the server uses it to make a retry safe.
 * Sending the same key with the same body again (after a timeout, a
 * dropped connection, a double click) returns the original order with
 * `created: false` instead of creating a second one. Use
 * `usePlaceOrder` / `lib/idempotency` rather than inventing keys by hand.
 */
export async function placeOrder(input: PlaceOrderInput, idempotencyKey: string): Promise<PlaceOrderResult> {
  const response = await apiClient.post<ApiResponse<Order>>("/api/orders", input, {
    headers: { "Idempotency-Key": idempotencyKey },
  });
  return {
    order: response.data.data as Order,
    // 201 = created now, 200 = replay of an earlier identical request.
    created: response.status === 201,
  };
}

export async function listOrders(page: number = 1, pageSize: number = 10): Promise<OrderList> {
  const { data } = await apiClient.get<ApiResponse<OrderList>>("/api/orders", {
    params: { page, page_size: pageSize },
  });
  return data.data as OrderList;
}

export async function getOrder(orderId: string): Promise<Order> {
  const { data } = await apiClient.get<ApiResponse<Order>>(`/api/orders/${orderId}`);
  return data.data as Order;
}

/** Cancels an unpaid order. Safe to repeat: cancelling an already
 * cancelled order just returns it. */
export async function cancelOrder(orderId: string): Promise<Order> {
  const { data } = await apiClient.post<ApiResponse<Order>>(`/api/orders/${orderId}/cancel`);
  return data.data as Order;
}