"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { CartSkeleton } from "@/components/cart/CartSkeleton";
import { CartSummary } from "@/components/cart/CartSummary";
import { AddressForm } from "@/components/checkout/AddressForm";
import { AddressSelector } from "@/components/checkout/AddressSelector";
import { PaymentStatusPanel } from "@/components/checkout/PaymentStatusPanel";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { useCart } from "@/context/CartContext";
import { useAddresses } from "@/hooks/useAddresses";
import { usePayment } from "@/hooks/usePayment";
import { usePlaceOrder } from "@/hooks/usePlaceOrder";
import { formatMoney } from "@/lib/money";
import type { AddressInput } from "@/types/address";

function Section({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section aria-label={title} className="rounded-2xl border border-border bg-card p-5 shadow-card sm:p-6">
      <div className="mb-4 flex items-center justify-between gap-3 border-b border-border pb-4">
        <h2 className="font-display text-lg font-semibold text-foreground">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function CheckoutContent() {
  const router = useRouter();
  const { cart, isLoading, loadError, refreshCart } = useCart();
  const { addresses, isLoading: addressesLoading, loadError: addressesError, reload, addAddress } = useAddresses();
  const { placeOrder, isPlacing, error, placedOrder, clearError } = usePlaceOrder();
  const { pay, retryVerification, phase: paymentPhase, error: paymentError } = usePayment();

  // The customer's own pick. The address actually selected is derived below,
  // so there is never a rendered frame with addresses but no selection.
  const [chosenId, setChosenId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [attemptedTotal, setAttemptedTotal] = useState<number | null>(null);

  // The customer's pick if it is still in the list, else the default address,
  // else the first one.
  const selectedId =
    addresses === null
      ? null
      : (addresses.find((a) => a.id === chosenId) ?? addresses.find((a) => a.is_default) ?? addresses[0])?.id ?? null;

  // Nothing to check out -> back to the cart. Not after an order was placed:
  // the server has just emptied the cart and we are on our way to the
  // confirmation page.
  const cartIsEmpty = cart !== null && cart.items.length === 0;
  useEffect(() => {
    if (cartIsEmpty && placedOrder === null) router.replace("/cart");
  }, [cartIsEmpty, placedOrder, router]);

  // The order exists (pending, stock held). From here on this page is about
  // paying for it; it only leaves once the BACKEND has verified the payment.
  if (placedOrder !== null) {
    const { order } = placedOrder;
    const settle = async (attempt: Promise<"paid" | "dismissed" | "failed" | "verify_failed" | "closed">) => {
      if ((await attempt) === "paid") router.replace(`/orders/${order.id}`);
    };
    return (
      <PaymentStatusPanel
        orderId={order.id}
        orderNumber={order.order_number}
        phase={paymentPhase}
        error={paymentError}
        amountLabel={attemptedTotal !== null ? formatMoney(attemptedTotal) : null}
        onRetryPayment={() => void settle(pay(order))}
        onRetryVerification={() => void settle(retryVerification(order))}
      />
    );
  }

  if (!cart && loadError) {
    return (
      <div className="container flex flex-col items-center gap-4 py-24 text-center">
        <p role="alert" className="max-w-sm text-foreground">
          {loadError}
        </p>
        <Button variant="primary" onClick={() => void refreshCart()} disabled={isLoading}>
          {isLoading ? "Retrying..." : "Try again"}
        </Button>
      </div>
    );
  }

  if (!cart || cartIsEmpty) {
    return (
      <div className="container py-12">
        <h1 className="mb-6 font-display text-3xl font-semibold text-foreground">Checkout</h1>
        <CartSkeleton />
      </div>
    );
  }

  const noAddresses = addresses !== null && addresses.length === 0;
  const formOpen = noAddresses || showForm;
  const canPlace = selectedId !== null && !cart.has_issues && !isPlacing;

  const handleAddAddress = async (input: AddressInput) => {
    const created = await addAddress(input);
    setChosenId(created.id);
    setShowForm(false);
  };

  const handlePlaceOrder = async () => {
    if (selectedId === null) return;
    clearError();
    setAttemptedTotal(cart.totals.total);
    try {
      const { order } = await placeOrder(selectedId, cart.totals.total);
      // Open Razorpay for the new order. `pay` never throws: how it ended is in
      // `paymentPhase` / `paymentError`, and the panel above shows it.
      if ((await pay(order)) === "paid") router.replace(`/orders/${order.id}`);
    } catch {
      // The hook keeps the message in `error` and refreshes the cart.
    }
  };

  const totalChanged = error !== null && attemptedTotal !== null && attemptedTotal !== cart.totals.total;

  const placeOrderAction = (
    <div className="flex flex-col gap-3">
      <Button variant="primary" size="lg" className="w-full" disabled={!canPlace} onClick={() => void handlePlaceOrder()}>
        {isPlacing ? "Placing your order..." : `Place order & pay - ${formatMoney(cart.totals.total)}`}
      </Button>
      {cart.has_issues ? (
        <p className="text-center text-xs text-muted-foreground">
          <Link href="/cart" className="font-medium text-primary hover:underline">
            Review your cart
          </Link>{" "}
          to fix the highlighted items first.
        </p>
      ) : selectedId === null ? (
        <p className="text-center text-xs text-muted-foreground">Choose or add a delivery address to continue.</p>
      ) : null}
      <p className="text-center text-xs text-muted-foreground">
        You&apos;ll pay securely with Razorpay right after placing your order. Your items are held for you while you pay.
      </p>
    </div>
  );

  return (
    <div className="container flex flex-col gap-6 py-12">
      <h1 className="font-display text-3xl font-semibold text-foreground">Checkout</h1>

      {cart.has_issues ? (
        <Banner>
          Some items in your cart need your attention, so we can&apos;t place this order yet.{" "}
          <Link href="/cart" className="font-medium underline">
            Review your cart
          </Link>
        </Banner>
      ) : null}
      {error ? (
        <Banner>
          {error}
          {totalChanged ? ` Your total is now ${formatMoney(cart.totals.total)} - review it and place your order again.` : ""}
        </Banner>
      ) : null}

      <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex flex-col gap-6">
          <Section
            title="Delivery address"
            action={
              addresses && addresses.length > 0 && !formOpen ? (
                <Button variant="ghost" size="sm" onClick={() => setShowForm(true)} disabled={isPlacing}>
                  <Plus aria-hidden="true" /> Add a new address
                </Button>
              ) : null
            }
          >
            {addressesError && addresses === null ? (
              <div className="flex flex-col items-start gap-3">
                <p role="alert" className="text-sm text-foreground">
                  {addressesError}
                </p>
                <Button variant="outline" size="sm" onClick={() => void reload()} disabled={addressesLoading}>
                  {addressesLoading ? "Retrying..." : "Try again"}
                </Button>
              </div>
            ) : addresses === null ? (
              <div role="status" aria-label="Loading your addresses" className="flex flex-col gap-3">
                <div className="h-20 animate-pulse rounded-xl bg-muted" />
                <div className="h-20 animate-pulse rounded-xl bg-muted" />
              </div>
            ) : (
              <div className="flex flex-col gap-5">
                {addresses.length > 0 ? (
                  <AddressSelector addresses={addresses} selectedId={selectedId} disabled={isPlacing} onSelect={setChosenId} />
                ) : (
                  <p className="text-sm text-muted-foreground">You don&apos;t have a saved address yet. Add one to continue.</p>
                )}
                {formOpen ? (
                  <div className="rounded-xl border border-border p-4">
                    <AddressForm
                      onSubmit={handleAddAddress}
                      onCancel={noAddresses ? undefined : () => setShowForm(false)}
                      offerDefault={!noAddresses}
                    />
                  </div>
                ) : null}
              </div>
            )}
          </Section>

          <Section
            title="Review items"
            action={
              <Link href="/cart" className="text-sm font-medium text-primary hover:underline">
                Edit cart
              </Link>
            }
          >
            <ul className="divide-y divide-border">
              {cart.items.map((item) => (
                <li key={item.id} className="flex items-start justify-between gap-4 py-3 text-sm">
                  <div className="flex flex-col gap-0.5">
                    <span className="font-medium text-foreground">{item.product.name}</span>
                    <span className="text-muted-foreground">
                      {item.quantity} x {formatMoney(item.unit_price)}
                    </span>
                    {item.issue ? <span className="text-accent-dark">{item.issue}</span> : null}
                  </div>
                  <span className="font-medium text-foreground">{formatMoney(item.line_subtotal)}</span>
                </li>
              ))}
            </ul>
          </Section>
        </div>

        <div className="lg:sticky lg:top-24">
          <CartSummary cart={cart} action={placeOrderAction} />
        </div>
      </div>
    </div>
  );
}

export default function CheckoutPage() {
  return (
    <ProtectedRoute>
      <CheckoutContent />
    </ProtectedRoute>
  );
}
