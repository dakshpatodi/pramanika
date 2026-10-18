import { EXPIRED_LABEL, ORDER_STATUS_LABEL, PAYMENT_CLOSED_LABEL, PAYMENT_STATUS_LABEL, isExpiredOrder, isPaymentWindowClosed } from "@/lib/order-format";
import type { CancellationReason, OrderStatus, PaymentStatus } from "@/types/order";

const STATUS_STYLE: Record<OrderStatus, string> = {
  pending: "bg-secondary-light text-foreground",
  confirmed: "bg-primary-light text-primary-dark",
  processing: "bg-primary-light text-primary-dark",
  shipped: "bg-primary-light text-primary-dark",
  delivered: "bg-primary text-primary-foreground",
  cancelled: "bg-muted text-muted-foreground",
  refunded: "bg-muted text-muted-foreground",
};

const PAYMENT_STYLE: Record<PaymentStatus, string> = {
  pending: "bg-muted text-muted-foreground",
  paid: "bg-primary-light text-primary-dark",
  failed: "bg-accent-light text-accent-dark",
  refunded: "bg-muted text-muted-foreground",
};

const PILL = "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium";

interface OrderStatusBadgeProps {
  status: OrderStatus;
  paymentStatus: PaymentStatus;
  /** Lets a cancelled order read "Expired" instead of "Cancelled". */
  cancellationReason?: CancellationReason | null;
  /** The server's `can_pay`; false on a pending order means its payment deadline has passed. */
  canPay?: boolean;
}

/** Order status and payment status as two small pills. */
export function OrderStatusBadge({ status, paymentStatus, cancellationReason, canPay }: OrderStatusBadgeProps) {
  const expired = isExpiredOrder({ status, cancellation_reason: cancellationReason });
  const windowClosed = isPaymentWindowClosed({ status, payment_status: paymentStatus, can_pay: canPay });
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <span className={`${PILL} ${STATUS_STYLE[status]}`}>{expired ? EXPIRED_LABEL : ORDER_STATUS_LABEL[status]}</span>
      {/* A cancelled order's payment is irrelevant - don't show "Payment pending" next to "Cancelled". */}
      {status === "cancelled" ? null : windowClosed ? (
        <span className={`${PILL} ${PAYMENT_STYLE.failed}`}>{PAYMENT_CLOSED_LABEL}</span>
      ) : (
        <span className={`${PILL} ${PAYMENT_STYLE[paymentStatus]}`}>{PAYMENT_STATUS_LABEL[paymentStatus]}</span>
      )}
    </span>
  );
}
