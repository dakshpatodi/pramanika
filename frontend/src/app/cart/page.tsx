"use client";

import { useCallback, useState } from "react";
import { AlertTriangle } from "lucide-react";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { CartList } from "@/components/cart/CartList";
import { CartSkeleton } from "@/components/cart/CartSkeleton";
import { CartSummary } from "@/components/cart/CartSummary";
import { CouponInput } from "@/components/cart/CouponInput";
import { EmptyCart } from "@/components/cart/EmptyCart";
import { Button } from "@/components/ui/button";
import { useCart } from "@/context/CartContext";
import { getApiErrorMessage } from "@/lib/errors";
import type { CartItem } from "@/types/cart";

function Banner({ children }: { children: React.ReactNode }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl bg-accent-light px-4 py-3 text-sm text-foreground">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-accent-dark" aria-hidden="true" />
      <div className="flex-1">{children}</div>
    </div>
  );
}

function CartContent() {
  const { cart, isLoading, isMutating, loadError, refreshCart, updateItem, removeItem, clearCart, applyCoupon, removeCoupon } =
    useCart();
  const [actionError, setActionError] = useState<string | null>(null);

  // Runs a line/cart action. On failure, shows the server's message (e.g.
  // "Only 3 units are available in stock.") and re-fetches the cart so
  // what's on screen matches the server again - the stored cart is never
  // changed by a failed request, but stock may have moved underneath us.
  const act = useCallback(
    async (action: () => Promise<unknown>) => {
      setActionError(null);
      try {
        await action();
      } catch (error) {
        setActionError(getApiErrorMessage(error, "We couldn't update your cart. Please try again."));
        void refreshCart();
      }
    },
    [refreshCart]
  );

  const handleQuantityChange = useCallback(
    (item: CartItem, quantity: number) => void act(() => updateItem(item.id, quantity)),
    [act, updateItem]
  );
  const handleRemove = useCallback((item: CartItem) => void act(() => removeItem(item.id)), [act, removeItem]);
  const handleClear = useCallback(() => void act(() => clearCart()), [act, clearCart]);

  let body: React.ReactNode;
  if (!cart && loadError) {
    body = (
      <div className="flex flex-col items-center gap-4 rounded-2xl border border-border bg-card px-6 py-16 text-center shadow-card">
        <p role="alert" className="max-w-sm text-foreground">
          {loadError}
        </p>
        <Button variant="primary" onClick={() => void refreshCart()} disabled={isLoading}>
          {isLoading ? "Retrying..." : "Try again"}
        </Button>
      </div>
    );
  } else if (!cart) {
    // Covers the first fetch, and the single render between "logged in"
    // and "fetch started" - never flash "empty" before we actually know.
    body = <CartSkeleton />;
  } else if (cart.items.length === 0) {
    body = <EmptyCart />;
  } else {
    body = (
      <div className="flex flex-col gap-4">
        {cart.has_issues ? (
          <Banner>Some items need your attention. They aren&apos;t included in your total until you fix or remove them.</Banner>
        ) : null}
        {actionError ? <Banner>{actionError}</Banner> : null}
        {loadError ? <Banner>{loadError}</Banner> : null}

        <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <CartList
            items={cart.items}
            itemCount={cart.item_count}
            disabled={isMutating}
            onQuantityChange={handleQuantityChange}
            onRemove={handleRemove}
            onClear={handleClear}
          />
          <div className="lg:sticky lg:top-24">
            <CartSummary cart={cart}>
              <CouponInput coupon={cart.coupon} disabled={isMutating} onApply={applyCoupon} onRemove={removeCoupon} />
            </CartSummary>
          </div>
        </div>
      </div>
    );
  }

  // Errors raised while the cart is empty/loading (e.g. clearing the last
  // item failed) still need to be visible.
  const showStandaloneError = actionError && !(cart && cart.items.length > 0);

  return (
    <div className="container flex flex-col gap-6 py-12">
      <h1 className="font-display text-3xl font-semibold text-foreground">Your cart</h1>
      {showStandaloneError ? <Banner>{actionError}</Banner> : null}
      {body}
    </div>
  );
}

export default function CartPage() {
  return (
    <ProtectedRoute>
      <CartContent />
    </ProtectedRoute>
  );
}