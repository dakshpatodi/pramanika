import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WishlistList } from "@/types/wishlist";

const { api } = vi.hoisted(() => ({ api: { listWishlist: vi.fn() } }));
vi.mock("@/services/wishlist", () => api);

import { useWishlistItems } from "@/hooks/useWishlistItems";

const page = (n: number, totalPages = 3): WishlistList => ({
  items: [{ product_id: `p${n}`, name: `P${n}`, slug: `p${n}`, price: 10, compare_at_price: null, image_url: null, is_available: true, in_stock: true, low_stock: false, added_at: "2026-10-05T00:00:00Z" }],
  pagination: { total: totalPages * 12, page: n, page_size: 12, total_pages: totalPages, has_next: n < totalPages, has_previous: n > 1 },
});
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
beforeEach(() => {
  api.listWishlist.mockReset(); // block body: a returned function would be run by Vitest as a teardown
});

describe("useWishlistItems", () => {
  it("loads the requested page", async () => {
    api.listWishlist.mockResolvedValue(page(1));
    const { result } = renderHook(() => useWishlistItems(1, 12));
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.data?.items[0].product_id).toBe("p1"));
    expect(api.listWishlist).toHaveBeenCalledWith(1, 12);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("keeps the previous page on screen while the next one loads", async () => {
    api.listWishlist.mockResolvedValueOnce(page(1));
    const { result, rerender } = renderHook(({ p }) => useWishlistItems(p, 12), { initialProps: { p: 1 } });
    await waitFor(() => expect(result.current.data?.pagination.page).toBe(1));
    const next = deferred<WishlistList>();
    api.listWishlist.mockReturnValueOnce(next.promise);
    rerender({ p: 2 });
    expect(result.current.data?.pagination.page).toBe(1);
    expect(result.current.isLoading).toBe(true);
    await act(async () => { next.resolve(page(2)); });
    expect(result.current.data?.pagination.page).toBe(2);
    expect(result.current.isLoading).toBe(false);
  });

  it("ignores a slow response for a page the user has already left", async () => {
    const slow = deferred<WishlistList>();
    api.listWishlist.mockReturnValueOnce(slow.promise);
    const { result, rerender } = renderHook(({ p }) => useWishlistItems(p, 12), { initialProps: { p: 1 } });
    api.listWishlist.mockResolvedValueOnce(page(2));
    rerender({ p: 2 });
    await waitFor(() => expect(result.current.data?.pagination.page).toBe(2));
    await act(async () => { slow.resolve(page(1)); });
    expect(result.current.data?.pagination.page).toBe(2);
    expect(result.current.isLoading).toBe(false);
  });

  it("ignores a slow FAILURE for a page the user has already left", async () => {
    const slow = deferred<WishlistList>();
    api.listWishlist.mockReturnValueOnce(slow.promise);
    const { result, rerender } = renderHook(({ p }) => useWishlistItems(p, 12), { initialProps: { p: 1 } });
    api.listWishlist.mockResolvedValueOnce(page(2));
    rerender({ p: 2 });
    await waitFor(() => expect(result.current.data?.pagination.page).toBe(2));
    await act(async () => { slow.reject(new Error("late")); });
    expect(result.current.error).toBeNull();
  });

  it("reports a failure with the server's message and reload() recovers", async () => {
    api.listWishlist.mockRejectedValueOnce(Object.assign(new Error("x"), { isAxiosError: true, response: { data: { success: false, message: "Wishlist is down." } } }));
    const { result } = renderHook(() => useWishlistItems(1, 12));
    await waitFor(() => expect(result.current.error).toBe("Wishlist is down."));
    expect(result.current.data).toBeNull();
    expect(result.current.isLoading).toBe(false);
    api.listWishlist.mockResolvedValueOnce(page(1));
    await act(async () => { await result.current.reload(); });
    expect(result.current.error).toBeNull();
    expect(result.current.data?.pagination.page).toBe(1);
  });

  it("falls back to a generic message", async () => {
    api.listWishlist.mockRejectedValueOnce({});
    const { result } = renderHook(() => useWishlistItems(1, 12));
    await waitFor(() => expect(result.current.error).toBe("We couldn't load your wishlist. Please try again."));
  });

  it("a failed reload keeps the page that was already showing", async () => {
    api.listWishlist.mockResolvedValueOnce(page(1));
    const { result } = renderHook(() => useWishlistItems(1, 12));
    await waitFor(() => expect(result.current.data).not.toBeNull());
    api.listWishlist.mockRejectedValueOnce(new Error("offline"));
    await act(async () => { await result.current.reload(); });
    expect(result.current.error).toBe("offline");
    expect(result.current.data?.pagination.page).toBe(1);
  });
});
