import { beforeEach, describe, expect, it, vi } from "vitest";

const { client } = vi.hoisted(() => ({ client: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }));
vi.mock("@/lib/axios", () => ({ apiClient: client }));

import * as inventory from "@/services/admin-inventory";
import * as orders from "@/services/admin-orders";

const reply = (data: unknown) => ({ data: { success: true, message: "OK", data } });

beforeEach(() => {
  client.get.mockReset();
  client.post.mockReset();
  client.patch.mockReset();
});

describe("admin inventory service", () => {
  it("lists with only the real filters (false kept, blanks dropped)", async () => {
    client.get.mockResolvedValue(reply({ items: [] }));
    await inventory.listAdminInventory({ page: 2, page_size: 20, search: "", category_id: "c1", is_active: false, stock: "low", sort: "available", order: "asc" });
    expect(client.get).toHaveBeenCalledWith("/api/admin/inventory", {
      params: { page: 2, page_size: 20, category_id: "c1", is_active: false, stock: "low", sort: "available", order: "asc" },
    });
    await inventory.listAdminInventory();
    expect(client.get).toHaveBeenLastCalledWith("/api/admin/inventory", { params: {} });
  });
  it("gets one product's stock by id, escaped", async () => {
    client.get.mockResolvedValue(reply({ product_id: "x" }));
    await expect(inventory.getAdminInventory("p 1/../x")).resolves.toEqual({ product_id: "x" });
    expect(client.get).toHaveBeenCalledWith("/api/admin/inventory/p%201%2F..%2Fx");
  });
  it("changes stock with PATCH and sends exactly the input", async () => {
    client.patch.mockResolvedValue(reply({ product_id: "p1" }));
    await inventory.updateAdminInventory("p1", { quantity: 5, expected_quantity: 7, reason: "Recount" });
    expect(client.patch).toHaveBeenCalledWith("/api/admin/inventory/p1", { quantity: 5, expected_quantity: 7, reason: "Recount" });
    await inventory.updateAdminInventory("p 1", { adjust_by: -2 });
    expect(client.patch).toHaveBeenLastCalledWith("/api/admin/inventory/p%201", { adjust_by: -2 });
  });
  it("reads the audit trail for one product", async () => {
    client.get.mockResolvedValue(reply({ events: [] }));
    await inventory.listAdminAuditEvents({ entity_type: "inventory", entity_id: "p1", page_size: 10 });
    expect(client.get).toHaveBeenCalledWith("/api/admin/audit-events", { params: { entity_type: "inventory", entity_id: "p1", page_size: 10 } });
  });
  it("has no way to write the reserved count or to delete", () => {
    expect(Object.keys(inventory).sort()).toEqual(["getAdminInventory", "listAdminAuditEvents", "listAdminInventory", "updateAdminInventory"]);
  });
});

describe("admin orders service", () => {
  it("lists with status, payment, dates and paging", async () => {
    client.get.mockResolvedValue(reply({ orders: [] }));
    await orders.listAdminOrders({
      status: "confirmed", payment_status: "paid", search: "asha", created_from: "2026-10-01T00:00:00+05:30", sort: "total", order: "desc", page: 3, page_size: 20,
    });
    expect(client.get).toHaveBeenCalledWith("/api/admin/orders", {
      params: { status: "confirmed", payment_status: "paid", search: "asha", created_from: "2026-10-01T00:00:00+05:30", sort: "total", order: "desc", page: 3, page_size: 20 },
    });
  });
  it("gets one order by id, escaped", async () => {
    client.get.mockResolvedValue(reply({ id: "o" }));
    await orders.getAdminOrder("o 1/x");
    expect(client.get).toHaveBeenCalledWith("/api/admin/orders/o%201%2Fx");
  });
  it("advances with POST to /status and sends the target (and note when given)", async () => {
    client.post.mockResolvedValue(reply({ id: "o1" }));
    await orders.advanceAdminOrder("o1", { status: "shipped", note: "AWB 123" });
    expect(client.post).toHaveBeenCalledWith("/api/admin/orders/o1/status", { status: "shipped", note: "AWB 123" });
    await orders.advanceAdminOrder("o 1", { status: "processing" });
    expect(client.post).toHaveBeenLastCalledWith("/api/admin/orders/o%201/status", { status: "processing" });
  });
  it("has no cancel, refund or mark-paid call", () => {
    expect(Object.keys(orders).sort()).toEqual(["advanceAdminOrder", "getAdminOrder", "listAdminOrders"]);
  });
});
