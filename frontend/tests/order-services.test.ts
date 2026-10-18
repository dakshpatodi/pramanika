import { beforeEach, describe, expect, it, vi } from "vitest";

const { client } = vi.hoisted(() => ({
  client: { get: vi.fn(), post: vi.fn() },
}));
vi.mock("@/lib/axios", () => ({ apiClient: client }));

import { createAddress, listAddresses } from "@/services/addresses";
import { cancelOrder, getOrder, listOrders, placeOrder } from "@/services/orders";

beforeEach(() => {
  client.get.mockReset();
  client.post.mockReset();
});

describe("address service", () => {
  it("lists addresses from GET /api/addresses and unwraps the envelope", async () => {
    client.get.mockResolvedValue({ data: { success: true, message: "ok", data: [{ id: "a1" }] } });
    expect(await listAddresses()).toEqual([{ id: "a1" }]);
    expect(client.get).toHaveBeenCalledWith("/api/addresses");
  });

  it("creates an address with POST /api/addresses and sends exactly the input", async () => {
    client.post.mockResolvedValue({ data: { success: true, message: "ok", data: { id: "a2" } } });
    const input = {
      full_name: "Asha", phone_number: "9876543210", address_line_1: "1 MG Road",
      city: "Pune", state: "Maharashtra", postal_code: "411001",
    };
    expect(await createAddress(input)).toEqual({ id: "a2" });
    expect(client.post).toHaveBeenCalledWith("/api/addresses", input);
  });
});

describe("order service", () => {
  it("places an order with the Idempotency-Key header and reports 201 as created", async () => {
    client.post.mockResolvedValue({ status: 201, data: { success: true, message: "ok", data: { id: "o1" } } });
    const result = await placeOrder({ shipping_address_id: "a1", expected_total: 259 }, "chk-key-123456");
    expect(result).toEqual({ order: { id: "o1" }, created: true });
    expect(client.post).toHaveBeenCalledWith(
      "/api/orders",
      { shipping_address_id: "a1", expected_total: 259 },
      { headers: { "Idempotency-Key": "chk-key-123456" } }
    );
  });

  it("reports a 200 (the server recognised the key) as NOT newly created", async () => {
    client.post.mockResolvedValue({ status: 200, data: { success: true, message: "again", data: { id: "o1" } } });
    const result = await placeOrder({ shipping_address_id: "a1" }, "chk-key-123456");
    expect(result.created).toBe(false);
  });

  it("never sends prices, items or a user id - only what the input holds", async () => {
    client.post.mockResolvedValue({ status: 201, data: { data: { id: "o1" } } });
    await placeOrder({ shipping_address_id: "a1" }, "chk-key-123456");
    const body = client.post.mock.calls[0][1];
    expect(Object.keys(body)).toEqual(["shipping_address_id"]);
  });

  it("lists orders with page and page_size query params", async () => {
    client.get.mockResolvedValue({ data: { data: { orders: [], pagination: { total: 0 } } } });
    await listOrders(2, 5);
    expect(client.get).toHaveBeenCalledWith("/api/orders", { params: { page: 2, page_size: 5 } });
    await listOrders();
    expect(client.get).toHaveBeenLastCalledWith("/api/orders", { params: { page: 1, page_size: 10 } });
  });

  it("gets one order by id", async () => {
    client.get.mockResolvedValue({ data: { data: { id: "o9" } } });
    expect(await getOrder("o9")).toEqual({ id: "o9" });
    expect(client.get).toHaveBeenCalledWith("/api/orders/o9");
  });

  it("cancels with POST /api/orders/{id}/cancel", async () => {
    client.post.mockResolvedValue({ data: { data: { id: "o9", status: "cancelled" } } });
    expect(await cancelOrder("o9")).toEqual({ id: "o9", status: "cancelled" });
    expect(client.post).toHaveBeenCalledWith("/api/orders/o9/cancel");
  });
});