"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "@/context/AuthContext";
import { getApiErrorMessage } from "@/lib/errors";
import * as cartApi from "@/services/cart";
import type { Cart } from "@/types/cart";

interface CartContextValue {
  /** The server-priced cart, or null when logged out / not loaded yet. */
  cart: Cart | null;
  /** Total units in the cart - 0 when logged out or not loaded. */
  itemCount: number;
  /** True while a cart fetch is in flight (initial load or refreshCart). */
  isLoading: boolean;
  /** True while any add/update/remove/clear/coupon request is in flight. */
  isMutating: boolean;
  /** Message from the last failed cart fetch, else null. */
  loadError: string | null;
  refreshCart: () => Promise<void>;
  /** The mutations below resolve to the updated cart and REJECT on failure
   * (stock, invalid coupon, ...) - callers show `getApiErrorMessage(err)`.
   * On failure the stored cart is left exactly as it was. */
  addItem: (productId: string, quantity?: number) => Promise<Cart>;
  updateItem: (itemId: string, quantity: number) => Promise<Cart>;
  removeItem: (itemId: string) => Promise<Cart>;
  clearCart: () => Promise<Cart>;
  applyCoupon: (code: string) => Promise<Cart>;
  removeCoupon: () => Promise<Cart>;
}

const CartContext = createContext<CartContextValue | undefined>(undefined);

/**
 * Owns the one authoritative copy of the cart on the client.
 *
 * Must sit INSIDE AuthProvider: it loads the cart when a user is logged
 * in, and throws it away the moment they log out (or a different user
 * logs in), so one person's cart can never show up for another.
 *
 * Responses are applied in the order the requests were MADE, not the
 * order they arrive: if the customer taps "+" twice quickly and the first
 * response lands after the second, the stale one is dropped instead of
 * overwriting the newer cart.
 */
export function CartProvider({ children }: { children: React.ReactNode }) {
  const { user, isLoading: isAuthLoading } = useAuth();
  const userId = user?.id ?? null;

  const [cart, setCart] = useState<Cart | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingMutations, setPendingMutations] = useState(0);

  const ownerRef = useRef<string | null>(null); // whose cart the in-flight requests are for
  const issuedRef = useRef(0); // last request number handed out
  const appliedRef = useRef(0); // highest request number already shown
  const loadRef = useRef(0); // latest fetch, so only it clears isLoading

  const run = useCallback(async (request: () => Promise<Cart>): Promise<Cart> => {
    const ticket = ++issuedRef.current;
    const owner = ownerRef.current;
    const next = await request();
    if (ownerRef.current === owner && ticket > appliedRef.current) {
      appliedRef.current = ticket;
      setCart(next);
    }
    return next;
  }, []);

  const fetchCart = useCallback(async () => {
    const load = ++loadRef.current;
    const owner = ownerRef.current;
    setIsLoading(true);
    setLoadError(null);
    try {
      await run(cartApi.getCart);
    } catch (error) {
      if (ownerRef.current === owner && loadRef.current === load) {
        setLoadError(getApiErrorMessage(error, "We couldn't load your cart. Please try again."));
      }
    } finally {
      if (loadRef.current === load) setIsLoading(false);
    }
  }, [run]);

  // Whenever the logged-in user changes (login, logout, switch): forget
  // everything about the previous user and, if someone is logged in, load
  // their cart. Bumping the counters makes any response still in flight
  // for the previous user get discarded.
  useEffect(() => {
    ownerRef.current = userId;
    issuedRef.current += 1;
    appliedRef.current = issuedRef.current;
    loadRef.current += 1;
    setCart(null);
    setLoadError(null);
    setIsLoading(false);

    if (isAuthLoading || userId === null) return;
    void fetchCart();
  }, [userId, isAuthLoading, fetchCart]);

  const mutate = useCallback(
    async (request: () => Promise<Cart>): Promise<Cart> => {
      setPendingMutations((n) => n + 1);
      try {
        return await run(request);
      } finally {
        setPendingMutations((n) => n - 1);
      }
    },
    [run]
  );

  const value = useMemo<CartContextValue>(
    () => ({
      cart,
      itemCount: cart?.item_count ?? 0,
      isLoading,
      isMutating: pendingMutations > 0,
      loadError,
      refreshCart: fetchCart,
      addItem: (productId, quantity = 1) => mutate(() => cartApi.addCartItem(productId, quantity)),
      updateItem: (itemId, quantity) => mutate(() => cartApi.updateCartItem(itemId, quantity)),
      removeItem: (itemId) => mutate(() => cartApi.removeCartItem(itemId)),
      clearCart: () => mutate(() => cartApi.clearCart()),
      applyCoupon: (code) => mutate(() => cartApi.applyCoupon(code)),
      removeCoupon: () => mutate(() => cartApi.removeCoupon()),
    }),
    [cart, isLoading, pendingMutations, loadError, fetchCart, mutate]
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartContextValue {
  const context = useContext(CartContext);
  if (context === undefined) {
    throw new Error("useCart must be used within a CartProvider.");
  }
  return context;
}