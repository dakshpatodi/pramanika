/**
 * Types mirroring the admin inventory API (backend/app/schemas/admin_inventory.py)
 * and the read-only audit trail (backend/app/schemas/admin.py).
 */

import type { AdminCategoryRef, SortOrder, StockStatus } from "@/types/admin-catalog";
import type { PaginationMeta } from "@/types/product";

export type InventorySort = "name" | "sku" | "available" | "quantity" | "updated_at";

export interface AdminInventoryItem {
  product_id: string;
  name: string;
  sku: string;
  is_active: boolean;
  category: AdminCategoryRef;
  quantity: number;
  reserved_quantity: number;
  available_quantity: number;
  low_stock_threshold: number | null;
  stock_status: StockStatus;
  updated_at: string;
}

export interface AdminInventoryDetail extends AdminInventoryItem {
  open_order_count: number;
  open_order_units: number;
  /** False when the units held by open orders differ from `reserved_quantity` (the books have drifted). */
  reservations_match: boolean;
}

export interface AdminInventoryList {
  items: AdminInventoryItem[];
  pagination: PaginationMeta;
}

export interface InventoryListParams {
  page?: number;
  page_size?: number;
  search?: string;
  category_id?: string;
  is_active?: boolean;
  stock?: StockStatus;
  sort?: InventorySort;
  order?: SortOrder;
}

/**
 * One stock change. Exactly one of: SET (`quantity` + `expected_quantity`, the value the admin saw),
 * ADJUST (`adjust_by`, applied on the database's current value), or just a new `low_stock_threshold`.
 * `reason` only goes with a stock change.
 */
export interface InventoryUpdateInput {
  quantity?: number;
  expected_quantity?: number;
  adjust_by?: number;
  low_stock_threshold?: number;
  reason?: string;
}

export interface AdminAuditEvent {
  id: string;
  admin_user_id: string | null;
  admin_email: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
}

export interface AdminAuditEventList {
  events: AdminAuditEvent[];
  pagination: PaginationMeta;
}

export interface AuditEventParams {
  page?: number;
  page_size?: number;
  entity_type?: string;
  entity_id?: string;
  action?: string;
}
