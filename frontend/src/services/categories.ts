/**
 * Thin wrapper around the category browsing endpoints.
 */

import { apiClient } from "@/lib/axios";
import type { ApiResponse } from "@/types/auth";
import type { Category, CategoryWithCount } from "@/types/product";

export async function listCategories(): Promise<CategoryWithCount[]> {
  const { data } = await apiClient.get<ApiResponse<CategoryWithCount[]>>("/api/categories");
  return data.data as CategoryWithCount[];
}

export async function getCategory(slug: string): Promise<Category> {
  const { data } = await apiClient.get<ApiResponse<Category>>(`/api/categories/${slug}`);
  return data.data as Category;
}