import { beforeEach, describe, expect, it, vi } from "vitest";

const { client } = vi.hoisted(() => ({ client: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }));
vi.mock("@/lib/axios", () => ({ apiClient: client }));

import { listInvoices } from "@/services/invoices";
import { updateProfile } from "@/services/profile";
import { listWishlist } from "@/services/wishlist";

beforeEach(() => {
  client.get.mockReset();
  client.patch.mockReset();
});

describe("profile service", () => {
  it("PATCHes /api/users/me with exactly the input and unwraps the user", async () => {
    client.patch.mockResolvedValue({ data: { success: true, message: "ok", data: { id: "u1", first_name: "Meera" } } });
    expect(await updateProfile({ first_name: "Meera" })).toEqual({ id: "u1", first_name: "Meera" });
    expect(client.patch).toHaveBeenCalledWith("/api/users/me", { first_name: "Meera" });
  });

  it("lets the server's error reach the caller untouched", async () => {
    const failure = Object.assign(new Error("409"), { isAxiosError: true });
    client.patch.mockRejectedValue(failure);
    await expect(updateProfile({ phone_number: "9876543210" })).rejects.toBe(failure);
  });
});

describe("wishlist and invoice list services", () => {
  it("asks for the page and page size by their API names", async () => {
    client.get.mockResolvedValue({ data: { success: true, message: "ok", data: { items: [], pagination: { total: 0 } } } });
    await listWishlist(2, 12);
    expect(client.get).toHaveBeenCalledWith("/api/wishlist", { params: { page: 2, page_size: 12 } });

    client.get.mockResolvedValue({ data: { success: true, message: "ok", data: { invoices: [], pagination: { total: 0 } } } });
    await listInvoices(1, 10);
    expect(client.get).toHaveBeenLastCalledWith("/api/invoices", { params: { page: 1, page_size: 10 } });
  });

  it("unwraps the envelope", async () => {
    client.get.mockResolvedValue({ data: { success: true, message: "ok", data: { items: [{ product_id: "p1" }], pagination: { total: 1 } } } });
    expect((await listWishlist()).items[0].product_id).toBe("p1");
  });
});
