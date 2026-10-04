/**
 * Cart API calls (Phase 5 backend, /api/cart/*).
 *
 * Reuses the shared `apiClient`, which already attaches the access token
 * and silently refreshes it on a 401 - so every function here is
 * authenticated with no extra code, and the user is always the one in the
 * token (there is deliberately no user id anywhere in these requests).
 *
 * Every endpoint returns the complete, freshly priced cart, so each
 * function resolves to a `Cart` the caller can store as-is.
 */

import { apiClient } from "@/lib/axios";
import type { ApiResponse } from "@/types/auth";
import type { Cart } from "@/types/cart";

export async function getCart(): Promise<Cart> {
  const { data } = await apiClient.get<ApiResponse<Cart>>("/api/cart");
  return data.data as Cart;
}

/** Adds `quantity` units; if the product is already in the cart the
 * quantity is added to the existing line. */
export async function addCartItem(productId: string, quantity: number = 1): Promise<Cart> {
  const { data } = await apiClient.post<ApiResponse<Cart>>("/api/cart/items", {
    product_id: productId,
    quantity,
  });
  return data.data as Cart;
}

/** Sets a line's quantity to exactly `quantity`. */
export async function updateCartItem(itemId: string, quantity: number): Promise<Cart> {
  const { data } = await apiClient.patch<ApiResponse<Cart>>(`/api/cart/items/${itemId}`, { quantity });
  return data.data as Cart;
}

export async function removeCartItem(itemId: string): Promise<Cart> {
  const { data } = await apiClient.delete<ApiResponse<Cart>>(`/api/cart/items/${itemId}`);
  return data.data as Cart;
}

/** Removes every item and any coupon. */
export async function clearCart(): Promise<Cart> {
  const { data } = await apiClient.delete<ApiResponse<Cart>>("/api/cart");
  return data.data as Cart;
}

export async function applyCoupon(code: string): Promise<Cart> {
  const { data } = await apiClient.post<ApiResponse<Cart>>("/api/cart/coupon", { code });
  return data.data as Cart;
}

export async function removeCoupon(): Promise<Cart> {
  const { data } = await apiClient.delete<ApiResponse<Cart>>("/api/cart/coupon");
  return data.data as Cart;
}