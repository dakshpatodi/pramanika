/**
 * Thin wrapper around the product browsing endpoints. Reuses the same
 * `apiClient` as the auth services (Milestone 6/7) even though these
 * routes need no auth - there's no reason for a second HTTP client
 * instance just because one set of routes happens to be public.
 */

import { apiClient } from "@/lib/axios";
import type { ApiResponse } from "@/types/auth";
import type { ProductDetail, ProductListResponse, ProductSort } from "@/types/product";

export interface ProductListParams {
  page?: number;
  page_size?: number;
  search?: string;
  category?: string;
  min_price?: number;
  max_price?: number;
  sort?: ProductSort;
}

export async function listProducts(params: ProductListParams = {}): Promise<ProductListResponse> {
  const { data } = await apiClient.get<ApiResponse<ProductListResponse>>("/api/products", { params });
  return data.data as ProductListResponse;
}

export async function getProduct(slug: string): Promise<ProductDetail> {
  const { data } = await apiClient.get<ApiResponse<ProductDetail>>(`/api/products/${slug}`);
  return data.data as ProductDetail;
}