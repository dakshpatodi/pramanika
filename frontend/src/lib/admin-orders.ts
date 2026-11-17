/**
 * Display and request helpers for the admin order pages. Nothing here decides whether an order may
 * move: the server says so (`next_status`, `can_advance`) and refuses everything else. These helpers
 * only word what the server said.
 */

import type { AdminOrderDetail, AdminShippingAddress, FulfilmentTarget } from "@/types/admin-orders";
import type { OrderStatus } from "@/types/order";

/** The path a paid order walks, in order. */
export const FULFILMENT_STEPS: Array<{ status: Extract<OrderStatus, "confirmed" | "processing" | "shipped" | "delivered">; label: string }> = [
  { status: "confirmed", label: "Confirmed" },
  { status: "processing", label: "Processing" },
  { status: "shipped", label: "Shipped" },
  { status: "delivered", label: "Delivered" },
];

export const NEXT_ACTION_LABEL: Record<FulfilmentTarget, string> = {
  processing: "Mark as processing",
  shipped: "Mark as shipped",
  delivered: "Mark as delivered",
};

const CONFIRM_BODY: Record<FulfilmentTarget, string> = {
  processing: "The customer will see this order as Processing.",
  shipped: "The customer will see this order as Shipped. Only mark it once it has left you.",
  delivered: "The customer will see this order as Delivered. This is the last step.",
};
export const confirmBody = (target: FulfilmentTarget) =>
  `${CONFIRM_BODY[target]} An order can only move forward, so this cannot be undone.`;

/** Index of the order's step on the fulfilment path, or -1 when it is not on it (pending, cancelled, ...). */
export function stepIndex(status: OrderStatus): number {
  return FULFILMENT_STEPS.findIndex((step) => step.status === status);
}

/** Why an order has no next step, in words (shown only when the server says it cannot advance). */
export function whyNoNextStep(order: Pick<AdminOrderDetail, "status" | "payment_status" | "cancellation_reason">): string {
  if (order.status === "delivered") return "This order is delivered. There is nothing further to do.";
  if (order.status === "cancelled") {
    return order.cancellation_reason === "expired"
      ? "This order expired because it was not paid in time, so it cannot be fulfilled."
      : "This order was cancelled, so it cannot be fulfilled.";
  }
  if (order.status === "refunded") return "This order was refunded, so it cannot be fulfilled.";
  if (order.payment_status !== "paid") return "This order has not been paid yet. It can be fulfilled once payment is confirmed.";
  return "This order cannot be moved forward right now.";
}

/** The shipping address as printable lines, skipping empty parts. */
export function addressLines(address: AdminShippingAddress): string[] {
  const cityLine = [address.city, address.state, address.postal_code].filter(Boolean).join(", ");
  return [address.full_name, address.address_line_1, address.address_line_2, cityLine, address.country, address.phone_number]
    .map((line) => (line ?? "").trim())
    .filter(Boolean);
}

const DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * "Placed from" / "to" dates (day pickers) as the ISO instants the API takes, covering whole days in
 * India time, which is how the pages show dates. A blank or malformed day is left out.
 */
export function dayRangeParams(from: string, to: string): { created_from?: string; created_to?: string } {
  const out: { created_from?: string; created_to?: string } = {};
  if (DATE.test(from)) out.created_from = `${from}T00:00:00+05:30`;
  if (DATE.test(to)) out.created_to = `${to}T23:59:59.999+05:30`;
  return out;
}

/** True when both days are set and the end is before the start. */
export const dayRangeBackwards = (from: string, to: string) => DATE.test(from) && DATE.test(to) && to < from;

const ORDER_STATUSES: readonly string[] = ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled", "refunded"];

/** Narrows a `?status=` value from the address bar to a status the API accepts. */
export const isOrderStatusFilter = (value: unknown): value is OrderStatus => typeof value === "string" && ORDER_STATUSES.includes(value);
