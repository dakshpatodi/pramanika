import type { AdminDashboard } from "@/types/admin";
import type { AdminCategory, AdminProduct, AdminProductDetail } from "@/types/admin-catalog";
import type { AdminAuditEvent, AdminInventoryDetail, AdminInventoryItem } from "@/types/admin-inventory";
import type { AdminOrderDetail, AdminOrderListItem } from "@/types/admin-orders";
import type { PaginationMeta } from "@/types/product";

export function dashboard(overrides: Partial<AdminDashboard> = {}): AdminDashboard {
  return {
    generated_at: "2026-10-26T10:30:00Z",
    orders: { total: 13, by_status: { pending: 2, confirmed: 5, shipped: 3, cancelled: 3 } },
    customers: { total: 40, new_last_30_days: 7 },
    products: { total: 30, active: 27, inactive: 3, low_stock: 4, out_of_stock: 2 },
    revenue: { currency: "INR", all_time: 125432.5, all_time_orders: 10, last_30_days: 20480, last_30_days_orders: 1 },
    recent_orders: [
      {
        id: "o1", order_number: "PRM-2026-000123", customer_name: "Asha Rao", customer_email: "asha@example.com",
        total_amount: 1049.5, status: "confirmed", payment_status: "paid", created_at: "2026-10-25T08:00:00Z",
      },
      {
        id: "o2", order_number: null, customer_name: "Ravi Iyer", customer_email: "ravi@example.com",
        total_amount: 200, status: "pending", payment_status: "pending", created_at: "2026-10-24T08:00:00Z",
      },
    ],
    ...overrides,
  };
}


export function pagination(overrides: Partial<PaginationMeta> = {}): PaginationMeta {
  return { total: 1, page: 1, page_size: 20, total_pages: 1, has_next: false, has_previous: false, ...overrides };
}

export function category(overrides: Partial<AdminCategory> = {}): AdminCategory {
  return {
    id: "c1", name: "Cereals", slug: "cereals", description: "Breakfast cereals", image_url: null, is_active: true,
    product_count: 5, active_product_count: 4, created_at: "2026-10-01T08:00:00Z", updated_at: "2026-10-02T08:00:00Z",
    ...overrides,
  };
}

export function product(overrides: Partial<AdminProduct> = {}): AdminProduct {
  return {
    id: "p1", name: "Muesli", slug: "muesli", sku: "MUE-001", price: 249, compare_at_price: 299, image_url: null,
    is_active: true, category: { id: "c1", name: "Cereals", slug: "cereals", is_active: true },
    quantity: 50, reserved_quantity: 5, available_quantity: 45, low_stock_threshold: 10, stock_status: "ok",
    created_at: "2026-10-01T08:00:00Z", updated_at: "2026-10-02T08:00:00Z",
    ...overrides,
  };
}

export function productDetail(overrides: Partial<AdminProductDetail> = {}): AdminProductDetail {
  return {
    ...product(), short_description: "Crunchy", description: "Whole grain muesli", weight: 500, weight_unit: "g",
    ingredients: "Oats, raisins", nutritional_information: "High fibre",
    ...overrides,
  };
}

export function inventoryItem(overrides: Partial<AdminInventoryItem> = {}): AdminInventoryItem {
  return {
    product_id: "p1", name: "Muesli", sku: "MUE-001", is_active: true,
    category: { id: "c1", name: "Cereals", slug: "cereals", is_active: true },
    quantity: 50, reserved_quantity: 5, available_quantity: 45, low_stock_threshold: 10, stock_status: "ok",
    updated_at: "2026-10-02T08:00:00Z",
    ...overrides,
  };
}

export function inventoryDetail(overrides: Partial<AdminInventoryDetail> = {}): AdminInventoryDetail {
  return { ...inventoryItem(), open_order_count: 2, open_order_units: 5, reservations_match: true, ...overrides };
}

export function auditEvent(overrides: Partial<AdminAuditEvent> = {}): AdminAuditEvent {
  return {
    id: "e1", admin_user_id: "a1", admin_email: "boss@example.com", action: "inventory.update", entity_type: "inventory",
    entity_id: "p1", before: { quantity: 50 }, after: { quantity: 45, method: "adjust", adjust_by: -5, reason: "Damaged in transit" },
    created_at: "2026-10-26T10:30:00Z",
    ...overrides,
  };
}

export function orderListItem(overrides: Partial<AdminOrderListItem> = {}): AdminOrderListItem {
  return {
    id: "o1", order_number: "PRM-2026-000123", status: "confirmed", payment_status: "paid", inventory_state: "consumed",
    cancellation_reason: null, customer_name: "Asha Rao", customer_email: "asha@example.com", customer_phone: "9876543210",
    item_count: 3, total_amount: 1049.5, next_status: "processing", created_at: "2026-10-25T08:00:00Z",
    ...overrides,
  };
}

export function orderDetail(overrides: Partial<AdminOrderDetail> = {}): AdminOrderDetail {
  return {
    id: "o1", order_number: "PRM-2026-000123", status: "confirmed", payment_status: "paid", inventory_state: "consumed",
    cancellation_reason: null,
    customer: { id: "u1", name: "Asha Rao", email: "asha@example.com", phone_number: "9876543210" },
    coupon_code: null,
    items: [
      { product_id: "p1", name: "Muesli", sku: "MUE-001", unit_price: 249, quantity: 2, subtotal: 498 },
      { product_id: null, name: "Retired Millet", sku: "MIL-009", unit_price: 100, quantity: 1, subtotal: 100 },
    ],
    item_count: 3,
    totals: { subtotal: 598, discount: 0, taxable_amount: 598, gst_rate: 5, gst: 29.9, delivery_charge: 0, total: 627.9 },
    shipping_address: {
      full_name: "Asha Rao", phone_number: "9876543210", address_line_1: "12 MG Road", address_line_2: null,
      city: "Pune", state: "Maharashtra", postal_code: "411001", country: "India",
    },
    payments: [
      {
        id: "pay1", gateway: "razorpay", gateway_order_id: "order_AAA", gateway_payment_id: "pay_BBB", status: "paid", amount: 627.9,
        currency: "INR", failure_reason: null, refund_required: false, paid_at: "2026-10-25T08:05:00Z", created_at: "2026-10-25T08:01:00Z",
      },
    ],
    reserved_units: 0, next_status: "processing", can_advance: true, expires_at: null,
    created_at: "2026-10-25T08:00:00Z", cancelled_at: null, updated_at: "2026-10-25T08:05:00Z",
    ...overrides,
  };
}
