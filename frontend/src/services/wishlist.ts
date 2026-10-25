/**
 * Wishlist API calls (Phase 8 backend, /api/wishlist). Everything goes through
 * the shared `apiClient`, so the access token travels in the Authorization
 * header and an expired one is refreshed silently. The owner is always the
 * logged-in user: no call here takes a user id.
 */

import { apiClient } from "@/lib/axios";
import type { ApiResponse } from "@/types/auth";
import type { WishlistItem, WishlistList, WishlistProductIds } from "@/types/wishlist";

/** One page of the wishlist, most recently added first. */
export async function listWishlist(page: number = 1, pageSize: number = 12): Promise<WishlistList> {
  const { data } = await apiClient.get<ApiResponse<WishlistList>>("/api/wishlist", {
    params: { page, page_size: pageSize },
  });
  return data.data as WishlistList;
}

/** The ids of every saved product (at most 100): what the heart buttons need. */
export async function getWishlistProductIds(): Promise<string[]> {
  const { data } = await apiClient.get<ApiResponse<WishlistProductIds>>("/api/wishlist/product-ids");
  return (data.data as WishlistProductIds).product_ids;
}

/** Saves a product. Safe to repeat: saving one that is already saved succeeds. */
export async function addToWishlist(productId: string): Promise<WishlistItem> {
  const { data } = await apiClient.post<ApiResponse<WishlistItem>>("/api/wishlist/items", { product_id: productId });
  return data.data as WishlistItem;
}

/** Removes a product. Safe to repeat: removing one that is not there succeeds. */
export async function removeFromWishlist(productId: string): Promise<void> {
  await apiClient.delete(`/api/wishlist/items/${encodeURIComponent(productId)}`);
}
