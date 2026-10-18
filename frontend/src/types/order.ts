/**
 * Types mirroring the backend's Phase 6 order schemas (app/schemas/order.py).
 * Keep in sync manually - there is no shared codegen between the two stacks.
 *
 * Every amount was calculated by the server; the frontend only displays
 * them. An order is PAID only when `payment_status` is "paid" - nothing
 * the browser sees (not even Razorpay's own "success") says otherwise.
 * `can_pay` and `can_cancel` are the server's verdicts; never work them out here.
 */

export type OrderStatus =
  | "pending"
  | "confirmed"
  | "processing"
  | "shipped"
  | "delivered"
  | "cancelled"
  | "refunded";

export type PaymentStatus = "pending" | "paid" | "failed" | "refunded";

export interface OrderItem {
  id: string;
  /** null if the product has since been deleted - the snapshot below still shows what was bought. */
  product_id: string | null;
  product_name: string;
  sku: string;
  /** Price per unit when the order was placed. */
  unit_price: number;
  quantity: number;
  line_total: number;
}

export interface OrderTotals {
  subtotal: number;
  discount: number;
  taxable_amount: number;
  gst_rate: number;
  gst: number;
  delivery_charge: number;
  total: number;
}

/** The delivery address as it was when the order was placed (a copy,
 * unaffected by later edits to the saved address). */
export interface OrderShippingAddress {
  full_name: string | null;
  phone_number: string | null;
  address_line_1: string | null;
  address_line_2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
}

/** Why a cancelled order was cancelled. */
export type CancellationReason = "customer" | "expired";

/** Status of the most recent payment attempt on an order. */
export type PaymentAttemptStatus = "initiated" | "authorized" | "failed" | "expired" | "captured" | "refunded";

/** What the customer may be told about the payment attempts. No gateway ids,
 * no bank wording. */
export interface OrderPaymentInfo {
  /** null if no payment was ever started. "failed" on a payable order means
   * the last try did not go through and can be repeated. */
  last_attempt: PaymentAttemptStatus | null;
  /** Money arrived after the order closed and is waiting to be refunded. */
  refund_pending: boolean;
}

export interface Order {
  id: string;
  order_number: string | null;
  status: OrderStatus;
  payment_status: PaymentStatus;
  /** Server's verdict - show the Cancel button only when true. */
  can_cancel: boolean;
  /** Server's verdict - show "Pay now" only when true (false once paid,
   * cancelled, expired, or past the payment deadline). */
  can_pay: boolean;
  /** When an unpaid order stops being payable and releases its stock. */
  expires_at: string | null;
  cancellation_reason: CancellationReason | null;
  payment: OrderPaymentInfo;
  coupon_code: string | null;
  items: OrderItem[];
  item_count: number;
  totals: OrderTotals;
  shipping_address: OrderShippingAddress;
  created_at: string;
  cancelled_at: string | null;
}

/** One row of the order history list. */
export interface OrderSummary {
  id: string;
  order_number: string | null;
  status: OrderStatus;
  payment_status: PaymentStatus;
  can_pay: boolean;
  expires_at: string | null;
  cancellation_reason: CancellationReason | null;
  total: number;
  /** Total units across all lines. */
  item_count: number;
  /** Number of different products in the order. */
  line_count: number;
  /** Up to the first three product names. */
  item_names: string[];
  created_at: string;
}

export interface PaginationMeta {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface OrderList {
  orders: OrderSummary[];
  pagination: PaginationMeta;
}

/** Body of POST /api/orders. The client says WHERE to deliver and which
 * total it was shown - never prices, items, discounts or a user id. */
export interface PlaceOrderInput {
  shipping_address_id: string;
  /** The total shown on screen. If the server's total differs, nothing is
   * ordered and the customer must review the new total. */
  expected_total?: number;
}

/** Result of POST /api/orders. */
export interface PlaceOrderResult {
  order: Order;
  /** false when the server recognised the Idempotency-Key and returned the
   * order from an earlier identical request instead of creating another. */
  created: boolean;
}
