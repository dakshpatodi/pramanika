import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Address } from "@/types/address";

const { auth, api } = vi.hoisted(() => ({
  auth: { user: null as null | { id: string }, isLoading: false },
  api: { listAddresses: vi.fn(), createAddress: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/services/addresses", () => api);

import { useAddresses } from "@/hooks/useAddresses";

const address = (id: string, isDefault = false): Address => ({
  id, full_name: "Asha", phone_number: "9876543210", address_line_1: "1 MG Road", address_line_2: null,
  city: "Pune", state: "Maharashtra", postal_code: "411001", country: "India", is_default: isDefault, created_at: "2026-10-05T00:00:00Z",
});
function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return { promise, resolve };
}

beforeEach(() => {
  api.listAddresses.mockReset();
  api.createAddress.mockReset();
  auth.user = null;
  auth.isLoading = false;
});

describe("useAddresses", () => {
  it("does nothing while logged out or while the session is being restored", () => {
    const { result, rerender } = renderHook(() => useAddresses());
    expect(api.listAddresses).not.toHaveBeenCalled();
    expect(result.current.addresses).toBeNull();

    auth.isLoading = true;
    auth.user = { id: "u1" };
    rerender();
    expect(api.listAddresses).not.toHaveBeenCalled();
  });

  it("loads the addresses for the logged-in user", async () => {
    auth.user = { id: "u1" };
    api.listAddresses.mockResolvedValue([address("a1", true)]);
    const { result } = renderHook(() => useAddresses());
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.addresses).toEqual([address("a1", true)]));
    expect(result.current.isLoading).toBe(false);
    expect(result.current.loadError).toBeNull();
  });

  it("reports a failed load and can reload", async () => {
    auth.user = { id: "u1" };
    api.listAddresses.mockRejectedValueOnce(new Error("Server down"));
    const { result } = renderHook(() => useAddresses());
    await waitFor(() => expect(result.current.loadError).toBe("Server down"));
    expect(result.current.addresses).toBeNull();

    api.listAddresses.mockResolvedValue([address("a1")]);
    await act(async () => { await result.current.reload(); });
    expect(result.current.loadError).toBeNull();
    expect(result.current.addresses).toHaveLength(1);
  });

  it("adds an address, resolves with it, and reloads the list (default flags may have moved)", async () => {
    auth.user = { id: "u1" };
    api.listAddresses.mockResolvedValueOnce([address("a1", true)]);
    const { result } = renderHook(() => useAddresses());
    await waitFor(() => expect(result.current.addresses).toHaveLength(1));

    api.createAddress.mockResolvedValue(address("a2", true));
    api.listAddresses.mockResolvedValueOnce([address("a2", true), address("a1", false)]);
    let created: Address | undefined;
    await act(async () => {
      created = await result.current.addAddress({
        full_name: "Asha", phone_number: "9876543210", address_line_1: "2 MG Road",
        city: "Pune", state: "Maharashtra", postal_code: "411001", is_default: true,
      });
    });

    expect(created?.id).toBe("a2");
    expect(result.current.addresses?.map((a) => a.id)).toEqual(["a2", "a1"]);
    expect(api.createAddress).toHaveBeenCalledTimes(1);
  });

  it("rejects with the server's message when adding fails and leaves the list alone", async () => {
    auth.user = { id: "u1" };
    api.listAddresses.mockResolvedValue([address("a1", true)]);
    const { result } = renderHook(() => useAddresses());
    await waitFor(() => expect(result.current.addresses).toHaveLength(1));

    api.createAddress.mockRejectedValue(new Error("PIN code must be 6 digits"));
    await act(async () => {
      await expect(
        result.current.addAddress({
          full_name: "A", phone_number: "9876543210", address_line_1: "x", city: "Pune", state: "MH", postal_code: "12",
        })
      ).rejects.toThrow("PIN code must be 6 digits");
    });
    expect(result.current.addresses).toHaveLength(1);
    expect(api.listAddresses).toHaveBeenCalledTimes(1);
  });

  it("forgets the previous user's addresses on logout", async () => {
    auth.user = { id: "u1" };
    api.listAddresses.mockResolvedValue([address("a1")]);
    const { result, rerender } = renderHook(() => useAddresses());
    await waitFor(() => expect(result.current.addresses).toHaveLength(1));

    auth.user = null;
    rerender();
    await waitFor(() => expect(result.current.addresses).toBeNull());
  });

  it("drops a slow response that belonged to the previous user", async () => {
    const slow = deferred<Address[]>();
    auth.user = { id: "u1" };
    api.listAddresses.mockReturnValueOnce(slow.promise);
    const { result, rerender } = renderHook(() => useAddresses());

    auth.user = { id: "u2" };
    api.listAddresses.mockResolvedValueOnce([address("mine")]);
    rerender();
    await waitFor(() => expect(result.current.addresses?.map((a) => a.id)).toEqual(["mine"]));

    await act(async () => { slow.resolve([address("someone-elses")]); await slow.promise; });
    expect(result.current.addresses?.map((a) => a.id)).toEqual(["mine"]);
  });
});
