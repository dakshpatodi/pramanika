/**
 * Admin inventory API calls (Phase 9 M4 backend, /api/admin/inventory) and the read-only audit
 * trail used for a product's stock history. The server decides who may call them and validates
 * every number; nothing here is a permission or validation boundary.
 */

import { apiClient } from "@/lib/axios";
import type { ApiResponse } from "@/types/auth";
import type {
  AdminAuditEventList,
  AdminInventoryDetail,
  AdminInventoryList,
  AuditEventParams,
  InventoryListParams,
  InventoryUpdateInput,
} from "@/types/admin-inventory";

function cleanParams(params: object): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    out[key] = value as string | number | boolean;
  }
  return out;
}

const unwrap = <T>(response: { data: ApiResponse<T> }): T => response.data.data as T;

export async function listAdminInventory(params: InventoryListParams = {}): Promise<AdminInventoryList> {
  return unwrap(await apiClient.get<ApiResponse<AdminInventoryList>>("/api/admin/inventory", { params: cleanParams(params) }));
}

export async function getAdminInventory(productId: string): Promise<AdminInventoryDetail> {
  return unwrap(await apiClient.get<ApiResponse<AdminInventoryDetail>>(`/api/admin/inventory/${encodeURIComponent(productId)}`));
}

export async function updateAdminInventory(productId: string, input: InventoryUpdateInput): Promise<AdminInventoryDetail> {
  return unwrap(
    await apiClient.patch<ApiResponse<AdminInventoryDetail>>(`/api/admin/inventory/${encodeURIComponent(productId)}`, input)
  );
}

export async function listAdminAuditEvents(params: AuditEventParams = {}): Promise<AdminAuditEventList> {
  return unwrap(await apiClient.get<ApiResponse<AdminAuditEventList>>("/api/admin/audit-events", { params: cleanParams(params) }));
}
