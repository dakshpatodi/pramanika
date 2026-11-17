/**
 * Types mirroring the admin catalogue API (backend/app/schemas/admin_catalog.py).
 * Money arrives as JSON numbers; it is SENT as strings ("19.99") so no float
 * ever rounds it.
 */

import type { PaginationMeta } from "@/types/product";

export type SortOrder = "asc" | "desc";
export type StockStatus = "ok" | "low" | "out";
export type WeightUnit = "g" | "kg" | "ml" | "l";

export const WEIGHT_UNITS: WeightUnit[] = ["g", "kg", "ml", "l"];

// ---------------------------------------------------------------- categories

export type CategorySort = "name" | "created_at" | "product_count";

export interface AdminCategory {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  image_url: string | null;
  is_active: boolean;
  product_count: number;
  active_product_count: number;
  created_at: string;
  updated_at: string;
}

export interface AdminCategoryList {
  categories: AdminCategory[];
  pagination: PaginationMeta;
}

export interface CategoryListParams {
  page?: number;
  page_size?: number;
  search?: string;
  is_active?: boolean;
  sort?: CategorySort;
  order?: SortOrder;
}

export interface CategoryCreateInput {
  name: string;
  slug?: string;
  description?: string | null;
  image_url?: string | null;
  is_active: boolean;
}

/** Only the fields that changed. `null` clears an optional field. */
export interface CategoryUpdateInput {
  name?: string;
  slug?: string;
  description?: string | null;
  image_url?: string | null;
}

// ------------------------------------------------------------------ products

export type ProductSort = "created_at" | "updated_at" | "name" | "sku" | "price" | "available";

export interface AdminCategoryRef {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
}

export interface AdminProduct {
  id: string;
  name: string;
  slug: string;
  sku: string;
  price: number;
  compare_at_price: number | null;
  image_url: string | null;
  is_active: boolean;
  category: AdminCategoryRef;
  quantity: number;
  reserved_quantity: number;
  available_quantity: number;
  low_stock_threshold: number | null;
  stock_status: StockStatus;
  created_at: string;
  updated_at: string;
}

export interface AdminProductDetail extends AdminProduct {
  short_description: string | null;
  description: string | null;
  weight: number | null;
  weight_unit: WeightUnit | null;
  ingredients: string | null;
  nutritional_information: string | null;
}

export interface AdminProductList {
  products: AdminProduct[];
  pagination: PaginationMeta;
}

export interface ProductListParams {
  page?: number;
  page_size?: number;
  search?: string;
  category_id?: string;
  is_active?: boolean;
  stock?: StockStatus;
  sort?: ProductSort;
  order?: SortOrder;
}

export interface ProductCreateInput {
  category_id: string;
  name: string;
  slug?: string;
  sku: string;
  price: string;
  compare_at_price?: string | null;
  short_description?: string | null;
  description?: string | null;
  weight?: string | null;
  weight_unit?: WeightUnit | null;
  ingredients?: string | null;
  nutritional_information?: string | null;
  image_url?: string | null;
  is_active: boolean;
  initial_quantity: number;
  low_stock_threshold: number;
}

/** Only the fields that changed. No stock and no is_active: those have their own endpoints. */
export type ProductUpdateInput = Partial<
  Omit<ProductCreateInput, "is_active" | "initial_quantity" | "low_stock_threshold">
>;
