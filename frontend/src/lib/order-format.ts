/**
 * Display helpers for orders. Formatting only - nothing here decides
 * anything about an order: the server says whether it can be paid
 * (`can_pay`), cancelled (`can_cancel`), or is paid (`payment_status`).
 */

import type { CancellationReason, Order, OrderStatus, PaymentStatus } from "@/types/order";

export const ORDER_STATUS_LABEL: Record<OrderStatus, string> = {
  pending: "Pending",
  confirmed: "Confirmed",
  processing: "Processing",
  shipped: "Shipped",
  delivered: "Delivered",
  cancelled: "Cancelled",
  refunded: "Refunded",
};

export const PAYMENT_STATUS_LABEL: Record<PaymentStatus, string> = {
  pending: "Payment pending",
  paid: "Paid",
  failed: "Payment failed",
  refunded: "Refunded",
};

export const EXPIRED_LABEL = "Expired";
export const PAYMENT_CLOSED_LABEL = "Payment window closed";

const dateFormat = new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeZone: "Asia/Kolkata" });
const dateTimeFormat = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Kolkata",
});
const timeFormat = new Intl.DateTimeFormat("en-IN", { timeStyle: "short", timeZone: "Asia/Kolkata" });

/** "2026-10-05T10:30:00Z" -> "5 Oct 2026" (India time). */
export function formatOrderDate(iso: string): string {
  return dateFormat.format(new Date(iso));
}

/** "2026-10-05T10:30:00Z" -> "5 Oct 2026, 4:00 pm" (India time). */
export function formatOrderDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso));
}

/** "2026-10-05T10:30:00Z" -> "4:00 pm" (India time). */
export function formatOrderTime(iso: string): string {
  return timeFormat.format(new Date(iso));
}

/** 125_000 -> "2 min 5 sec"; 3_900_000 -> "1 hr 5 min"; <= 0 -> "0 sec". Display only. */
export function formatTimeLeft(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) return minutes > 0 ? `${hours} hr ${minutes} min` : `${hours} hr`;
  if (minutes > 0) return seconds > 0 && minutes < 5 ? `${minutes} min ${seconds} sec` : `${minutes} min`;
  return `${seconds} sec`;
}

type OrderFacts = Pick<Order, "status" | "payment_status" | "cancelled_at"> &
  Partial<Pick<Order, "cancellation_reason" | "can_pay" | "expires_at" | "payment">>;

/** True for an order the system cancelled because it was not paid in time. */
export function isExpiredOrder(order: { status: OrderStatus; cancellation_reason?: CancellationReason | null }): boolean {
  return order.status === "cancelled" && order.cancellation_reason === "expired";
}

/** True for an unpaid order whose payment deadline has passed but which the
 * expiry job has not cancelled yet (the server says it can no longer be paid). */
export function isPaymentWindowClosed(order: {
  status: OrderStatus;
  payment_status: PaymentStatus;
  can_pay?: boolean;
}): boolean {
  return order.status === "pending" && order.payment_status === "pending" && order.can_pay === false;
}

/** One-line description of where the order stands. Says "paid" ONLY when
 * the server says the payment is paid. */
export function describeOrder(order: OrderFacts): string {
  if (order.status === "cancelled") {
    if (order.cancellation_reason === "expired") {
      return "This order expired because it wasn't paid in time. The items we were holding for you have been released.";
    }
    return order.cancelled_at
      ? `This order was cancelled on ${formatOrderDate(order.cancelled_at)}. The items we were holding for you have been released.`
      : "This order was cancelled. The items we were holding for you have been released.";
  }
  if (order.status === "refunded") return "This order has been refunded.";
  if (order.payment_status === "paid") {
    if (order.status === "shipped") return "Your order has been paid for and is on its way.";
    if (order.status === "delivered") return "Your order has been delivered.";
    return "Your payment has been received and your order is being prepared.";
  }
  if (order.payment_status === "failed") return "The payment for this order failed. Your order has not been paid for.";

  if (isPaymentWindowClosed(order as Parameters<typeof isPaymentWindowClosed>[0])) {
    return "The time to pay for this order has run out. It will be cancelled shortly and your items released. You haven't been charged.";
  }
  const attempt = order.payment?.last_attempt ?? null;
  const until = order.can_pay && order.expires_at ? ` Please pay before ${formatOrderTime(order.expires_at)} to keep this order.` : "";
  if (attempt === "authorized") {
    return "Your payment is being confirmed by the bank. Your order isn't marked as paid until it is.";
  }
  if (attempt === "failed" && order.can_pay) {
    return `Your last payment attempt didn't go through. We're still holding your items, so you can try again.${until}`;
  }
  if (order.can_pay === false) {
    return "We've received your order. No payment has been taken.";
  }
  return `We've received your order and are holding your items. No payment has been taken yet.${until}`;
}
