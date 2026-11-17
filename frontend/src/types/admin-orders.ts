/**
 * Types mirroring the admin order API (backend/app/schemas/admin_orders.py).
 * Money arrives as JSON numbers with two decimals. The only write is a fulfilment step.
 */

import type { SortOrder } from "@/types/admin-catalog";
import type { CancellationReason, OrderStatus, PaymentStatus } from "@/types/order";
import type { PaginationMeta } from "@/types/product";

export type FulfilmentTarget = "processing" | "shipped" | "delivered";
export type AdminOrderSort = "created_at" | "total" | "status" | "order_number";

export interface AdminOrderListItem {
  id: string;
  order_number: string | null;
  status: OrderStatus;
  payment_status: PaymentStatus;
  inventory_state: string;
  cancellation_reason: CancellationReason | null;
  customer_name: string;
  customer_email: string;
  customer_phone: string | null;
  item_count: number;
  total_amount: number;
  /** What an admin may set next, or null (the SERVER decides; the UI never works it out). */
  next_status: FulfilmentTarget | null;
  created_at: string;
}

export interface AdminOrderList {
  orders: AdminOrderListItem[];
  pagination: PaginationMeta;
}

export interface AdminOrderListParams {
  page?: number;
  page_size?: number;
  status?: OrderStatus;
  payment_status?: PaymentStatus;
  inventory_state?: string;
  search?: string;
  created_from?: string;
  created_to?: string;
  sort?: AdminOrderSort;
  order?: SortOrder;
}

export interface AdminOrderLine {
  product_id: string | null;
  name: string;
  sku: string;
  unit_price: number;
  quantity: number;
  subtotal: number;
}

export interface AdminOrderTotals {
  subtotal: number;
  discount: number;
  taxable_amount: number;
  gst_rate: number;
  gst: number;
  delivery_charge: number;
  total: number;
}

export interface AdminShippingAddress {
  full_name: string | null;
  phone_number: string | null;
  address_line_1: string | null;
  address_line_2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
}

export interface AdminPaymentAttempt {
  id: string;
  gateway: string;
  gateway_order_id: string | null;
  gateway_payment_id: string | null;
  status: string;
  amount: number;
  currency: string;
  failure_reason: string | null;
  /** The customer was charged but the order could not be completed: refund it in the gateway dashboard. */
  refund_required: boolean;
  paid_at: string | null;
  created_at: string;
}

export interface AdminOrderDetail {
  id: string;
  order_number: string | null;
  status: OrderStatus;
  payment_status: PaymentStatus;
  inventory_state: string;
  cancellation_reason: CancellationReason | null;
  customer: { id: string; name: string; email: string; phone_number: string | null };
  coupon_code: string | null;
  items: AdminOrderLine[];
  item_count: number;
  totals: AdminOrderTotals;
  shipping_address: AdminShippingAddress;
  payments: AdminPaymentAttempt[];
  reserved_units: number;
  next_status: FulfilmentTarget | null;
  can_advance: boolean;
  expires_at: string | null;
  created_at: string;
  cancelled_at: string | null;
  updated_at: string;
}

export interface OrderStatusInput {
  status: FulfilmentTarget;
  note?: string;
}
