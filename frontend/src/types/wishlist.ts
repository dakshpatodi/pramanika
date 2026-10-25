/** Mirrors app/schemas/wishlist.py (Phase 8). Keep in sync manually. */

import type { PaginationMeta } from "@/types/order";

export interface WishlistItem {
  product_id: string;
  name: string;
  slug: string;
  price: number;
  compare_at_price: number | null;
  image_url: string | null;
  /** False when the product has been withdrawn from sale. It stays listed so it can be removed. */
  is_available: boolean;
  in_stock: boolean;
  low_stock: boolean;
  added_at: string;
}

export interface WishlistList {
  items: WishlistItem[];
  pagination: PaginationMeta;
}

/** GET /api/wishlist/product-ids */
export interface WishlistProductIds {
  product_ids: string[];
}
