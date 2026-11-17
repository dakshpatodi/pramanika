import { beforeEach, describe, expect, it, vi } from "vitest";

const { client } = vi.hoisted(() => ({ client: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }));
vi.mock("@/lib/axios", () => ({ apiClient: client }));

import * as api from "@/services/admin-catalog";

const reply = (data: unknown) => ({ data: { success: true, message: "OK", data } });

beforeEach(() => {
  client.get.mockReset();
  client.post.mockReset();
  client.patch.mockReset();
});

describe("admin catalogue service", () => {
  it("lists categories with only the real filters (false is kept, blanks dropped)", async () => {
    client.get.mockResolvedValue(reply({ categories: [] }));
    await api.listAdminCategories({ page: 2, page_size: 20, search: "", is_active: false, sort: "name", order: "asc" });
    expect(client.get).toHaveBeenCalledWith("/api/admin/categories", { params: { page: 2, page_size: 20, is_active: false, sort: "name", order: "asc" } });
  });
  it("lists products with category, stock and status filters", async () => {
    client.get.mockResolvedValue(reply({ products: [] }));
    await api.listAdminProducts({ category_id: "c1", stock: "low", is_active: true, search: "oat", sort: "price", order: "desc", page: 1 });
    expect(client.get).toHaveBeenCalledWith("/api/admin/products", {
      params: { category_id: "c1", stock: "low", is_active: true, search: "oat", sort: "price", order: "desc", page: 1 },
    });
    await api.listAdminProducts();
    expect(client.get).toHaveBeenLastCalledWith("/api/admin/products", { params: {} });
  });
  it("gets one category / product by id (and escapes the id)", async () => {
    client.get.mockResolvedValue(reply({ id: "x" }));
    await expect(api.getAdminCategory("c 1/../x")).resolves.toEqual({ id: "x" });
    expect(client.get).toHaveBeenCalledWith("/api/admin/categories/c%201%2F..%2Fx");
    await api.getAdminProduct("p1");
    expect(client.get).toHaveBeenLastCalledWith("/api/admin/products/p1");
    await api.getAdminProduct("p 1/../x");
    expect(client.get).toHaveBeenLastCalledWith("/api/admin/products/p%201%2F..%2Fx");
  });
  it("creates with POST and sends exactly the input", async () => {
    client.post.mockResolvedValue(reply({ id: "n" }));
    const cat = { name: "A", is_active: true };
    await expect(api.createAdminCategory(cat)).resolves.toEqual({ id: "n" });
    expect(client.post).toHaveBeenCalledWith("/api/admin/categories", cat);
    const prod = { category_id: "c1", name: "M", sku: "S", price: "9.99", is_active: true, initial_quantity: 1, low_stock_threshold: 2 };
    await api.createAdminProduct(prod);
    expect(client.post).toHaveBeenLastCalledWith("/api/admin/products", prod);
  });
  it("edits with PATCH and sends only the changes", async () => {
    client.patch.mockResolvedValue(reply({ id: "u" }));
    await api.updateAdminCategory("c1", { name: "B" });
    expect(client.patch).toHaveBeenCalledWith("/api/admin/categories/c1", { name: "B" });
    await api.updateAdminProduct("p1", { price: "5.00", description: null });
    expect(client.patch).toHaveBeenLastCalledWith("/api/admin/products/p1", { price: "5.00", description: null });
  });
  it("activates and deactivates through the dedicated endpoints (no body)", async () => {
    client.post.mockResolvedValue(reply({ id: "a" }));
    await api.setAdminCategoryActive("c1", false);
    expect(client.post).toHaveBeenLastCalledWith("/api/admin/categories/c1/deactivate");
    await api.setAdminCategoryActive("c1", true);
    expect(client.post).toHaveBeenLastCalledWith("/api/admin/categories/c1/activate");
    await api.setAdminProductActive("p1", false);
    expect(client.post).toHaveBeenLastCalledWith("/api/admin/products/p1/deactivate");
    await api.setAdminProductActive("p1", true);
    expect(client.post).toHaveBeenLastCalledWith("/api/admin/products/p1/activate");
  });
  it("has no way to delete anything", () => {
    expect(Object.keys(api).some((name) => /delete|remove/i.test(name))).toBe(false);
  });
});
