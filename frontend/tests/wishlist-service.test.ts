import { beforeEach, describe, expect, it, vi } from "vitest";

const { client } = vi.hoisted(() => ({ client: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }));
vi.mock("@/lib/axios", () => ({ apiClient: client }));

import { addToWishlist, getWishlistProductIds, listWishlist, removeFromWishlist } from "@/services/wishlist";

beforeEach(() => {
  Object.values(client).forEach((fn) => fn.mockReset()); // block body: a returned function would be run by Vitest as a teardown
});

describe("wishlist service", () => {
  it("listWishlist asks for one page and unwraps the envelope", async () => {
    const payload = { items: [], pagination: { total: 0, page: 2, page_size: 5, total_pages: 0, has_next: false, has_previous: true } };
    client.get.mockResolvedValue({ data: { success: true, data: payload } });
    expect(await listWishlist(2, 5)).toBe(payload);
    expect(client.get).toHaveBeenCalledWith("/api/wishlist", { params: { page: 2, page_size: 5 } });
  });

  it("listWishlist defaults to the first page of 12", async () => {
    client.get.mockResolvedValue({ data: { data: {} } });
    await listWishlist();
    expect(client.get).toHaveBeenCalledWith("/api/wishlist", { params: { page: 1, page_size: 12 } });
  });

  it("getWishlistProductIds returns just the id list", async () => {
    client.get.mockResolvedValue({ data: { success: true, data: { product_ids: ["a", "b"] } } });
    expect(await getWishlistProductIds()).toEqual(["a", "b"]);
    expect(client.get).toHaveBeenCalledWith("/api/wishlist/product-ids");
  });

  it("addToWishlist posts only the product id (never a user id) and returns the item", async () => {
    const item = { product_id: "p1", name: "Millet" };
    client.post.mockResolvedValue({ data: { success: true, data: item } });
    expect(await addToWishlist("p1")).toBe(item);
    expect(client.post).toHaveBeenCalledWith("/api/wishlist/items", { product_id: "p1" });
  });

  it("removeFromWishlist deletes by product id, URL-encoded", async () => {
    client.delete.mockResolvedValue({ data: { success: true, data: null } });
    await removeFromWishlist("p1");
    expect(client.delete).toHaveBeenCalledWith("/api/wishlist/items/p1");
    await removeFromWishlist("a/b?c");
    expect(client.delete).toHaveBeenLastCalledWith("/api/wishlist/items/a%2Fb%3Fc");
  });

  it("lets a failed request reject so the caller can show the server's message", async () => {
    const failure = Object.assign(new Error("x"), { isAxiosError: true, response: { status: 409, data: { success: false, message: "Your wishlist is full." } } });
    client.post.mockRejectedValue(failure);
    await expect(addToWishlist("p1")).rejects.toBe(failure);
  });
});
