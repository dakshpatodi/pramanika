import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { OrderList } from "@/types/order";

const { api } = vi.hoisted(() => ({ api: { listOrders: vi.fn() } }));
vi.mock("@/services/orders", () => api);

import { useOrders } from "@/hooks/useOrders";

const list = (page: number): OrderList => ({
  orders: [{ id: `o${page}` } as OrderList["orders"][number]],
  pagination: { total: 30, page, page_size: 10, total_pages: 3, has_next: page < 3, has_previous: page > 1 },
});
function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return { promise, resolve };
}

beforeEach(() => api.listOrders.mockReset());

describe("useOrders", () => {
  it("loads the requested page with the page size", async () => {
    api.listOrders.mockResolvedValue(list(1));
    const { result } = renderHook(() => useOrders(1, 10));
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.data?.orders[0].id).toBe("o1"));
    expect(api.listOrders).toHaveBeenCalledWith(1, 10);
    expect(result.current.isLoading).toBe(false);
  });

  it("keeps the previous page on screen while the next one loads", async () => {
    api.listOrders.mockResolvedValueOnce(list(1));
    const { result, rerender } = renderHook(({ page }) => useOrders(page), { initialProps: { page: 1 } });
    await waitFor(() => expect(result.current.data?.pagination.page).toBe(1));

    const next = deferred<OrderList>();
    api.listOrders.mockReturnValueOnce(next.promise);
    rerender({ page: 2 });
    await waitFor(() => expect(result.current.isLoading).toBe(true));
    expect(result.current.data?.pagination.page).toBe(1);

    await act(async () => { next.resolve(list(2)); await next.promise; });
    expect(result.current.data?.pagination.page).toBe(2);
    expect(result.current.isLoading).toBe(false);
  });

  it("ignores a late response for a page the user already left", async () => {
    const slow = deferred<OrderList>();
    api.listOrders.mockReturnValueOnce(slow.promise);
    const { result, rerender } = renderHook(({ page }) => useOrders(page), { initialProps: { page: 1 } });

    api.listOrders.mockResolvedValueOnce(list(2));
    rerender({ page: 2 });
    await waitFor(() => expect(result.current.data?.pagination.page).toBe(2));

    await act(async () => { slow.resolve(list(1)); await slow.promise; });
    expect(result.current.data?.pagination.page).toBe(2);
  });

  it("reports a failure and can reload", async () => {
    api.listOrders.mockRejectedValueOnce(new Error("Server down"));
    const { result } = renderHook(() => useOrders(1));
    await waitFor(() => expect(result.current.error).toBe("Server down"));
    expect(result.current.data).toBeNull();

    api.listOrders.mockResolvedValue(list(1));
    await act(async () => { await result.current.reload(); });
    expect(result.current.error).toBeNull();
    expect(result.current.data?.pagination.page).toBe(1);
  });
});
