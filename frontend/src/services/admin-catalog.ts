/**
 * Admin category and product API calls (Phase 9 M3 backend, /api/admin/...).
 * The server decides who may call them (401/403) and validates every field;
 * nothing here is a permission or validation boundary.
 */

import { apiClient } from "@/lib/axios";
import type {
  AdminCategory,
  AdminCategoryList,
  AdminProductDetail,
  AdminProductList,
  CategoryCreateInput,
  CategoryListParams,
  CategoryUpdateInput,
  ProductCreateInput,
  ProductListParams,
  ProductUpdateInput,
} from "@/types/admin-catalog";
import type { ApiResponse } from "@/types/auth";

/** Drops undefined / empty values so the URL only carries real filters. */
function cleanParams(params: object): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    out[key] = value as string | number | boolean;
  }
  return out;
}

const unwrap = <T>(response: { data: ApiResponse<T> }): T => response.data.data as T;

// ---------------------------------------------------------------- categories

export async function listAdminCategories(params: CategoryListParams = {}): Promise<AdminCategoryList> {
  return unwrap(await apiClient.get<ApiResponse<AdminCategoryList>>("/api/admin/categories", { params: cleanParams(params) }));
}

export async function getAdminCategory(id: string): Promise<AdminCategory> {
  return unwrap(await apiClient.get<ApiResponse<AdminCategory>>(`/api/admin/categories/${encodeURIComponent(id)}`));
}

export async function createAdminCategory(input: CategoryCreateInput): Promise<AdminCategory> {
  return unwrap(await apiClient.post<ApiResponse<AdminCategory>>("/api/admin/categories", input));
}

export async function updateAdminCategory(id: string, changes: CategoryUpdateInput): Promise<AdminCategory> {
  return unwrap(await apiClient.patch<ApiResponse<AdminCategory>>(`/api/admin/categories/${encodeURIComponent(id)}`, changes));
}

export async function setAdminCategoryActive(id: string, active: boolean): Promise<AdminCategory> {
  const action = active ? "activate" : "deactivate";
  return unwrap(await apiClient.post<ApiResponse<AdminCategory>>(`/api/admin/categories/${encodeURIComponent(id)}/${action}`));
}

// ------------------------------------------------------------------ products

export async function listAdminProducts(params: ProductListParams = {}): Promise<AdminProductList> {
  return unwrap(await apiClient.get<ApiResponse<AdminProductList>>("/api/admin/products", { params: cleanParams(params) }));
}

export async function getAdminProduct(id: string): Promise<AdminProductDetail> {
  return unwrap(await apiClient.get<ApiResponse<AdminProductDetail>>(`/api/admin/products/${encodeURIComponent(id)}`));
}

export async function createAdminProduct(input: ProductCreateInput): Promise<AdminProductDetail> {
  return unwrap(await apiClient.post<ApiResponse<AdminProductDetail>>("/api/admin/products", input));
}

export async function updateAdminProduct(id: string, changes: ProductUpdateInput): Promise<AdminProductDetail> {
  return unwrap(await apiClient.patch<ApiResponse<AdminProductDetail>>(`/api/admin/products/${encodeURIComponent(id)}`, changes));
}

export async function setAdminProductActive(id: string, active: boolean): Promise<AdminProductDetail> {
  const action = active ? "activate" : "deactivate";
  return unwrap(await apiClient.post<ApiResponse<AdminProductDetail>>(`/api/admin/products/${encodeURIComponent(id)}/${action}`));
}
