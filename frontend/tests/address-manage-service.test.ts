import { beforeEach, describe, expect, it, vi } from "vitest";

const { client } = vi.hoisted(() => ({ client: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));
vi.mock("@/lib/axios", () => ({ apiClient: client }));

import { deleteAddress, setDefaultAddress, updateAddress } from "@/services/addresses";

beforeEach(() => Object.values(client).forEach((fn) => fn.mockReset()));

describe("address management service", () => {
  it("PATCHes only the given fields to the address's own path and unwraps the address", async () => {
    client.patch.mockResolvedValue({ data: { success: true, message: "ok", data: { id: "a1", city: "Mumbai" } } });
    expect(await updateAddress("a1", { city: "Mumbai" })).toEqual({ id: "a1", city: "Mumbai" });
    expect(client.patch).toHaveBeenCalledWith("/api/addresses/a1", { city: "Mumbai" });
  });

  it("sends a cleared second line as null", async () => {
    client.patch.mockResolvedValue({ data: { success: true, message: "ok", data: { id: "a1" } } });
    await updateAddress("a1", { address_line_2: null });
    expect(client.patch).toHaveBeenCalledWith("/api/addresses/a1", { address_line_2: null });
  });

  it("POSTs to the default endpoint with no body and resolves with the whole list", async () => {
    client.post.mockResolvedValue({ data: { success: true, message: "ok", data: [{ id: "a2" }, { id: "a1" }] } });
    expect(await setDefaultAddress("a2")).toEqual([{ id: "a2" }, { id: "a1" }]);
    expect(client.post).toHaveBeenCalledWith("/api/addresses/a2/default");
  });

  it("DELETEs the address and resolves with what remains", async () => {
    client.delete.mockResolvedValue({ data: { success: true, message: "ok", data: [{ id: "a1" }] } });
    expect(await deleteAddress("a2")).toEqual([{ id: "a1" }]);
    expect(client.delete).toHaveBeenCalledWith("/api/addresses/a2");
  });

  it("lets a refusal reach the caller untouched", async () => {
    const failure = Object.assign(new Error("404"), { isAxiosError: true });
    client.delete.mockRejectedValue(failure);
    await expect(deleteAddress("nope")).rejects.toBe(failure);
  });
});
