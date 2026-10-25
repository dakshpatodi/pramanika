import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Address } from "@/types/address";

const { auth, api } = vi.hoisted(() => ({
  auth: { user: null as null | { id: string }, isLoading: false },
  api: { listAddresses: vi.fn(), createAddress: vi.fn(), updateAddress: vi.fn(), setDefaultAddress: vi.fn(), deleteAddress: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/services/addresses", () => api);

import { useAddresses } from "@/hooks/useAddresses";

const address = (id: string, isDefault = false, over: Partial<Address> = {}): Address => ({
  id, full_name: "Asha", phone_number: "9876543210", address_line_1: `${id} MG Road`, address_line_2: null,
  city: "Pune", state: "Maharashtra", postal_code: "411001", country: "India", is_default: isDefault, created_at: "2026-10-05T00:00:00Z", ...over,
});
function deferred<T>() {
  let resolve!: (v: T) => void; let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
async function loaded(list: Address[]) {
  api.listAddresses.mockResolvedValue(list);
  const hook = renderHook(() => useAddresses());
  await waitFor(() => expect(hook.result.current.addresses).toEqual(list));
  return hook;
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  auth.user = { id: "u1" };
  auth.isLoading = false;
});

describe("useAddresses - managing", () => {
  it("replaces an edited address in place, without another list request", async () => {
    const { result } = await loaded([address("a1", true), address("a2")]);
    api.updateAddress.mockResolvedValue(address("a2", false, { city: "Mumbai" }));
    await act(async () => { await result.current.updateAddress("a2", { city: "Mumbai" }); });
    expect(api.updateAddress).toHaveBeenCalledWith("a2", { city: "Mumbai" });
    expect(result.current.addresses?.map((a) => [a.id, a.city])).toEqual([["a1", "Pune"], ["a2", "Mumbai"]]);
    expect(api.listAddresses).toHaveBeenCalledTimes(1);
  });

  it("shows the list the server returns after setting a default (default first)", async () => {
    const { result } = await loaded([address("a1", true), address("a2")]);
    api.setDefaultAddress.mockResolvedValue([address("a2", true), address("a1")]);
    await act(async () => { await result.current.makeDefault("a2"); });
    expect(result.current.addresses?.map((a) => [a.id, a.is_default])).toEqual([["a2", true], ["a1", false]]);
  });

  it("shows the remaining list after a delete, including a promoted default", async () => {
    const { result } = await loaded([address("a1", true), address("a2")]);
    api.deleteAddress.mockResolvedValue([address("a2", true)]);
    await act(async () => { await result.current.removeAddress("a1"); });
    expect(result.current.addresses?.map((a) => [a.id, a.is_default])).toEqual([["a2", true]]);
    expect(api.deleteAddress).toHaveBeenCalledWith("a1");
  });

  it("can end with no addresses at all", async () => {
    const { result } = await loaded([address("a1", true)]);
    api.deleteAddress.mockResolvedValue([]);
    await act(async () => { await result.current.removeAddress("a1"); });
    expect(result.current.addresses).toEqual([]);
  });

  it("rejects on failure and leaves the list as it was", async () => {
    const list = [address("a1", true), address("a2")];
    const { result } = await loaded(list);
    api.deleteAddress.mockRejectedValue(new Error("nope"));
    await act(async () => { await expect(result.current.removeAddress("a2")).rejects.toThrow("nope"); });
    api.setDefaultAddress.mockRejectedValue(new Error("nope2"));
    await act(async () => { await expect(result.current.makeDefault("a2")).rejects.toThrow("nope2"); });
    api.updateAddress.mockRejectedValue(new Error("nope3"));
    await act(async () => { await expect(result.current.updateAddress("a2", { city: "X" })).rejects.toThrow("nope3"); });
    expect(result.current.addresses).toEqual(list);
  });

  it("a change the server just confirmed beats an older list request still in flight", async () => {
    const { result } = await loaded([address("a1", true), address("a2")]);
    const stale = deferred<Address[]>();
    api.listAddresses.mockReturnValueOnce(stale.promise);
    act(() => { void result.current.reload(); });
    api.setDefaultAddress.mockResolvedValue([address("a2", true), address("a1")]);
    await act(async () => { await result.current.makeDefault("a2"); });
    await act(async () => { stale.resolve([address("a1", true), address("a2")]); });
    expect(result.current.addresses?.[0].id).toBe("a2");
    expect(result.current.isLoading).toBe(false);
  });

  it("ignores a confirmation that arrives after the user changed", async () => {
    const { result, rerender } = await loaded([address("a1", true)]);
    const slow = deferred<Address[]>();
    api.deleteAddress.mockReturnValue(slow.promise);
    let removal!: Promise<void>;
    act(() => { removal = result.current.removeAddress("a1"); });

    auth.user = { id: "u2" };
    api.listAddresses.mockResolvedValue([address("b1", true)]);
    rerender();
    await waitFor(() => expect(result.current.addresses?.[0].id).toBe("b1"));

    await act(async () => { slow.resolve([]); await removal; });
    expect(result.current.addresses?.map((a) => a.id)).toEqual(["b1"]);
  });

  it("still adds as before (adds, then reloads)", async () => {
    const { result } = await loaded([address("a1", true)]);
    api.createAddress.mockResolvedValue(address("a2"));
    api.listAddresses.mockResolvedValue([address("a1", true), address("a2")]);
    await act(async () => { await result.current.addAddress({} as never); });
    await waitFor(() => expect(result.current.addresses).toHaveLength(2));
  });
});
