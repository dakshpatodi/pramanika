"use client";

import { useCallback, useRef, useState } from "react";

import { useCart } from "@/context/CartContext";
import { getApiErrorMessage } from "@/lib/errors";
import { createIdempotencyKeyStore, normaliseTotal } from "@/lib/idempotency";
import * as ordersApi from "@/services/orders";
import type { PlaceOrderInput, PlaceOrderResult } from "@/types/order";

export interface UsePlaceOrder {
  /**
   * Place the order. Resolves with the result on success and REJECTS on
   * failure (the message is also in `error`). While a request is in
   * flight, calling it again - a double click - returns the SAME promise
   * instead of sending a second request.
   */
  placeOrder: (shippingAddressId: string, expectedTotal?: number) => Promise<PlaceOrderResult>;
  /** True while the request is in flight - disable the button. */
  isPlacing: boolean;
  /** Message from the last failed attempt, else null. */
  error: string | null;
  /** The order once it has been placed, else null. Pages use this to
   * avoid treating the now-empty cart as "nothing to check out" while
   * they navigate to the confirmation page. */
  placedOrder: PlaceOrderResult | null;
  clearError: () => void;
}

/**
 * Checkout data layer: idempotency key handling, double-click protection,
 * and keeping the cart in step with the server.
 *
 *  - The key follows the request: retrying the same address + total reuses
 *    it (so an attempt that reached the server cannot turn into a second
 *    order); changing either gets a new one; success forgets it.
 *  - On success the cart is refreshed (the server emptied it).
 *  - On failure the cart is refreshed too, so the page shows what the
 *    server now sees (a price changed, an item sold out, a coupon
 *    expired) and the customer can confirm the new total.
 */
export function usePlaceOrder(): UsePlaceOrder {
  const { refreshCart } = useCart();
  const [isPlacing, setIsPlacing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [placedOrder, setPlacedOrder] = useState<PlaceOrderResult | null>(null);

  const keys = useRef(createIdempotencyKeyStore());
  const inFlight = useRef<Promise<PlaceOrderResult> | null>(null);

  const placeOrder = useCallback(
    (shippingAddressId: string, expectedTotal?: number): Promise<PlaceOrderResult> => {
      if (inFlight.current !== null) return inFlight.current;

      const input: PlaceOrderInput = { shipping_address_id: shippingAddressId };
      const total = normaliseTotal(expectedTotal);
      if (total !== undefined) input.expected_total = total;

      const key = keys.current.keyFor(input);
      setError(null);
      setIsPlacing(true);

      const attempt = (async (): Promise<PlaceOrderResult> => {
        try {
          const result = await ordersApi.placeOrder(input, key);
          keys.current.reset();
          setPlacedOrder(result);
          await refreshCart().catch(() => undefined);
          return result;
        } catch (err) {
          setError(getApiErrorMessage(err, "We couldn't place your order. Please try again."));
          await refreshCart().catch(() => undefined);
          throw err;
        } finally {
          inFlight.current = null;
          setIsPlacing(false);
        }
      })();

      inFlight.current = attempt;
      return attempt;
    },
    [refreshCart]
  );

  const clearError = useCallback(() => setError(null), []);

  return { placeOrder, isPlacing, error, placedOrder, clearError };
}