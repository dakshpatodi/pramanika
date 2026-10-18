import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import type { PaymentPhase } from "@/hooks/usePayment";
import { useTimeLeft } from "@/hooks/useTimeLeft";
import { formatMoney } from "@/lib/money";
import { formatTimeLeft } from "@/lib/order-format";
import type { Order } from "@/types/order";

interface OrderPaymentPanelProps {
  order: Pick<Order, "totals" | "expires_at" | "payment">;
  phase: PaymentPhase;
  /** Why the last attempt did not end in "paid", else null. */
  error: string | null;
  isBusy: boolean;
  onPay: () => void;
  /** Ask the server again about a payment Razorpay already reported. */
  onCheckPayment: () => void;
  /** Re-read the order from the server (nothing is re-sent to Razorpay). */
  onRefresh: () => void;
  /** The payment deadline passed on this device's clock: ask the server what happened. */
  onDeadlinePassed: () => void;
}

/**
 * "Pay now" for an order that already exists - shown only while the server
 * says the order can be paid (`can_pay`). Paying again after a failed or
 * abandoned attempt uses the SAME order: the server reuses the open Razorpay
 * order or opens a fresh one, and never creates a second Pramanika order.
 *
 * The amount shown is the order's own total; the amount charged is whatever
 * the server puts in the Razorpay order.
 */
export function OrderPaymentPanel({ order, phase, error, isBusy, onPay, onCheckPayment, onRefresh, onDeadlinePassed }: OrderPaymentPanelProps) {
  const left = useTimeLeft(order.expires_at, onDeadlinePassed);
  const amount = formatMoney(order.totals.total);
  const attempt = order.payment.last_attempt;
  const retrying = attempt === "failed" || phase === "dismissed" || phase === "failed";

  let body: React.ReactNode;
  switch (phase) {
    case "starting":
      body = <p role="status" className="text-sm text-muted-foreground">Starting your payment...</p>;
      break;
    case "awaiting":
      body = <p role="status" className="text-sm text-muted-foreground">Complete your payment in the Razorpay window.</p>;
      break;
    case "verifying":
      body = (
        <p role="status" className="text-sm text-muted-foreground">
          Confirming your payment with the bank. Please don&apos;t close this page...
        </p>
      );
      break;
    case "verify_failed":
      body = (
        <>
          <Banner>{error ?? "We couldn't confirm your payment yet."}</Banner>
          <Button variant="primary" onClick={onCheckPayment}>
            Check payment status
          </Button>
        </>
      );
      break;
    case "closed":
      body = <Banner>{error ?? "This order can no longer be paid."}</Banner>;
      break;
    default:
      body = (
        <>
          {error ? <Banner>{error}</Banner> : null}
          {phase === "idle" && attempt === "authorized" ? (
            <>
              <p className="text-sm text-muted-foreground">
                Your payment is being confirmed by the bank. This can take a minute. Please don&apos;t pay again.
              </p>
              <Button variant="outline" onClick={onRefresh}>
                Refresh status
              </Button>
            </>
          ) : (
            <Button variant="primary" size="lg" onClick={onPay}>
              {retrying ? `Try payment again - ${amount}` : `Pay ${amount} now`}
            </Button>
          )}
        </>
      );
  }

  return (
    <section aria-label="Payment" className="flex flex-col gap-3 rounded-xl border border-border bg-muted/40 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-foreground">Complete your payment</h2>
        {left !== null && left > 0 ? (
          <span className="text-sm text-muted-foreground">
            Time left to pay: <strong className="font-medium text-foreground">{formatTimeLeft(left)}</strong>
          </span>
        ) : null}
      </div>
      {body}
      <p className="text-xs text-muted-foreground">Payments are processed securely by Razorpay. We never see your card details.</p>
      {isBusy ? <span className="sr-only">Payment in progress</span> : null}
    </section>
  );
}
