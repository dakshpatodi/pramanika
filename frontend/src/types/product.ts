/**
 * Types mirroring the backend's Phase 4 schemas (app/schemas/product.py,
 * app/schemas/category.py). Keep these in sync manually when those
 * schemas change - there's no shared codegen between the two stacks.
 */

export interface Category {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  image_url: string | null;
}

/** Adds product_count - only returned by GET /api/categories (the list
 * endpoint), not GET /api/categories/{slug} (plain Category). */
export interface CategoryWithCount extends Category {
  product_count: number;
}

/** Matches backend/app/schemas/product.py's ProductSort enum exactly -
 * keep in sync if that whitelist ever changes. */
export type ProductSort = "newest" | "price_asc" | "price_desc" | "name_asc" | "name_desc";

export type WeightUnit = "g" | "kg" | "ml" | "l";

/** Lightweight shape from GET /api/products - matches ProductListItem
 * on the backend. No description/ingredients/nutritional_information -
 * those only exist on ProductDetail. */
export interface ProductListItem {
  id: string;
  name: string;
  slug: string;
  sku: string;
  price: number;
  compare_at_price: number | null;
  image_url: string | null;
  category: Category;
  in_stock: boolean;
  low_stock: boolean;
}

/** Full shape from GET /api/products/{slug}. */
export interface ProductDetail {
  id: string;
  name: string;
  slug: string;
  sku: string;
  short_description: string | null;
  description: string | null;
  price: number;
  compare_at_price: number | null;
  weight: number | null;
  weight_unit: WeightUnit | null;
  ingredients: string | null;
  nutritional_information: string | null;
  image_url: string | null;
  category: Category;
  in_stock: boolean;
  low_stock: boolean;
  created_at: string;
  related_products: ProductListItem[];
}

export interface PaginationMeta {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface ProductListResponse {
  products: ProductListItem[];
  pagination: PaginationMeta;
}