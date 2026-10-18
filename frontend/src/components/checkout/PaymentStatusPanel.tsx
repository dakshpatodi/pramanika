import Link from "next/link";

import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import type { PaymentPhase } from "@/hooks/usePayment";

interface PaymentStatusPanelProps {
  orderId: string;
  orderNumber: string | null;
  phase: PaymentPhase;
  /** Why the last attempt did not end in "paid", else null. */
  error: string | null;
  /** Formatted amount for the retry button, e.g. "₹721.35"; omitted if unknown. */
  amountLabel?: string | null;
  onRetryPayment: () => void;
  onRetryVerification: () => void;
}

/**
 * Shown on /checkout once the order exists and until the payment is
 * confirmed. The order is SAVED at this point (its stock is held), so every
 * state links to it - nobody is ever stranded on a spinner.
 *
 * Only "paid" speaks of a received payment, and `phase` only becomes "paid"
 * after the backend verified it.
 */
export function PaymentStatusPanel({
  orderId,
  orderNumber,
  phase,
  error,
  amountLabel,
  onRetryPayment,
  onRetryVerification,
}: PaymentStatusPanelProps) {
  const orderLink = (
    <Link href={`/orders/${orderId}`} className="text-sm font-medium text-primary hover:underline">
      View my order
    </Link>
  );
  const reference = orderNumber ? ` (${orderNumber})` : "";

  let body: React.ReactNode;
  switch (phase) {
    case "paid":
      body = <p className="text-muted-foreground">Payment received - taking you to your order...</p>;
      break;
    case "verifying":
      body = <p className="text-muted-foreground">Confirming your payment with the bank. Please don&apos;t close this page...</p>;
      break;
    case "awaiting":
      body = <p className="text-muted-foreground">Complete your payment in the Razorpay window.</p>;
      break;
    case "dismissed":
    case "failed":
      body = (
        <>
          {error ? <Banner>{error}</Banner> : null}
          <Button variant="primary" size="lg" onClick={onRetryPayment}>
            {amountLabel ? `Pay ${amountLabel} now` : "Try payment again"}
          </Button>
          {orderLink}
        </>
      );
      break;
    case "verify_failed":
      body = (
        <>
          <Banner>{error ?? "We couldn't confirm your payment yet."}</Banner>
          <Button variant="primary" size="lg" onClick={onRetryVerification}>
            Check payment status
          </Button>
          {orderLink}
        </>
      );
      break;
    case "closed":
      body = (
        <>
          <Banner>{error ?? "This order can no longer be paid."}</Banner>
          {orderLink}
        </>
      );
      break;
    case "idle":
    case "starting":
    default:
      body = <p className="text-muted-foreground">Starting your payment...</p>;
  }

  return (
    <div className="container flex flex-col items-center gap-4 py-24 text-center" role="status" aria-live="polite">
      <h1 className="font-display text-2xl font-semibold text-foreground">Order placed</h1>
      <p className="text-sm text-muted-foreground">
        {phase === "paid" ? `Thank you${reference}.` : `Your order${reference} is saved and your items are held for you.`}
      </p>
      <div className="flex max-w-md flex-col items-center gap-4">{body}</div>
    </div>
  );
}
