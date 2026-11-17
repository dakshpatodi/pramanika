/**
 * Admin order API calls (Phase 9 M5 backend, /api/admin/orders): two reads and ONE write, a
 * fulfilment step. There is no cancel, refund or mark-paid call, on purpose.
 */

import { apiClient } from "@/lib/axios";
import type { ApiResponse } from "@/types/auth";
import type { AdminOrderDetail, AdminOrderList, AdminOrderListParams, OrderStatusInput } from "@/types/admin-orders";

function cleanParams(params: object): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    out[key] = value as string | number | boolean;
  }
  return out;
}

const unwrap = <T>(response: { data: ApiResponse<T> }): T => response.data.data as T;

export async function listAdminOrders(params: AdminOrderListParams = {}): Promise<AdminOrderList> {
  return unwrap(await apiClient.get<ApiResponse<AdminOrderList>>("/api/admin/orders", { params: cleanParams(params) }));
}

export async function getAdminOrder(id: string): Promise<AdminOrderDetail> {
  return unwrap(await apiClient.get<ApiResponse<AdminOrderDetail>>(`/api/admin/orders/${encodeURIComponent(id)}`));
}

export async function advanceAdminOrder(id: string, input: OrderStatusInput): Promise<AdminOrderDetail> {
  return unwrap(await apiClient.post<ApiResponse<AdminOrderDetail>>(`/api/admin/orders/${encodeURIComponent(id)}/status`, input));
}
