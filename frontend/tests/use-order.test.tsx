import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Order } from "@/types/order";

const { api } = vi.hoisted(() => ({ api: { getOrder: vi.fn(), cancelOrder: vi.fn() } }));
vi.mock("@/services/orders", () => api);

import { useOrder } from "@/hooks/useOrder";

const order = (id: string, over: Partial<Order> = {}) => ({ id, status: "pending", can_cancel: true, ...over }) as Order;
function deferred<T>() {
  let resolve!: (v: T) => void; let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  api.getOrder.mockReset();
  api.cancelOrder.mockReset();
});

describe("useOrder - loading", () => {
  it("loads the order and reports loading in between", async () => {
    const pending = deferred<Order>();
    api.getOrder.mockReturnValue(pending.promise);
    const { result } = renderHook(() => useOrder("o1"));
    expect(result.current.isLoading).toBe(true);
    expect(result.current.order).toBeNull();
    await act(async () => { pending.resolve(order("o1")); await pending.promise; });
    expect(result.current.order?.id).toBe("o1");
    expect(result.current.isLoading).toBe(false);
    expect(api.getOrder).toHaveBeenCalledWith("o1");
  });

  it("reports the server's message when it cannot be loaded (e.g. not found / not yours) and can retry", async () => {
    api.getOrder.mockRejectedValueOnce(new Error("Order was not found."));
    const { result } = renderHook(() => useOrder("o1"));
    await waitFor(() => expect(result.current.error).toBe("Order was not found."));
    expect(result.current.order).toBeNull();

    api.getOrder.mockResolvedValue(order("o1"));
    await act(async () => { await result.current.reload(); });
    expect(result.current.error).toBeNull();
    expect(result.current.order?.id).toBe("o1");
  });

  it("starts over when the id changes and ignores a late response for the old id", async () => {
    const slow = deferred<Order>();
    api.getOrder.mockReturnValueOnce(slow.promise);
    const { result, rerender } = renderHook(({ id }) => useOrder(id), { initialProps: { id: "old" } });

    api.getOrder.mockResolvedValueOnce(order("new"));
    rerender({ id: "new" });
    await waitFor(() => expect(result.current.order?.id).toBe("new"));

    await act(async () => { slow.resolve(order("old")); await slow.promise; });
    expect(result.current.order?.id).toBe("new");
    expect(result.current.isLoading).toBe(false);
  });
});

describe("useOrder - cancel", () => {
  async function loaded() {
    api.getOrder.mockResolvedValue(order("o1"));
    const hook = renderHook(() => useOrder("o1"));
    await waitFor(() => expect(hook.result.current.order).not.toBeNull());
    return hook;
  }

  it("stores the cancelled order the server returns", async () => {
    const { result } = await loaded();
    api.cancelOrder.mockResolvedValue(order("o1", { status: "cancelled", can_cancel: false }));
    await act(async () => { await result.current.cancel(); });
    expect(api.cancelOrder).toHaveBeenCalledWith("o1");
    expect(result.current.order?.status).toBe("cancelled");
    expect(result.current.isCancelling).toBe(false);
    expect(result.current.cancelError).toBeNull();
  });

  it("sends one request however many times it is called while in flight", async () => {
    const { result } = await loaded();
    const pending = deferred<Order>();
    api.cancelOrder.mockReturnValue(pending.promise);

    let first!: Promise<Order>; let second!: Promise<Order>;
    act(() => { first = result.current.cancel(); second = result.current.cancel(); });
    expect(second).toBe(first);
    expect(api.cancelOrder).toHaveBeenCalledTimes(1);
    expect(result.current.isCancelling).toBe(true);

    await act(async () => { pending.resolve(order("o1", { status: "cancelled", can_cancel: false })); await first; });
    expect(result.current.isCancelling).toBe(false);
  });

  it("shows the server's message when cancelling is refused, rejects, and re-reads the order", async () => {
    const { result } = await loaded();
    api.cancelOrder.mockRejectedValue(new Error("An order that is paid can no longer be cancelled."));
    api.getOrder.mockResolvedValue(order("o1", { can_cancel: false, payment_status: "paid" } as Partial<Order>));

    await act(async () => { await expect(result.current.cancel()).rejects.toThrow("can no longer be cancelled"); });

    expect(result.current.cancelError).toBe("An order that is paid can no longer be cancelled.");
    expect(result.current.isCancelling).toBe(false);
    await waitFor(() => expect(result.current.order?.can_cancel).toBe(false));
    expect(api.getOrder).toHaveBeenCalledTimes(2);
  });

  it("allows another attempt after a failure, and clears the old error when it starts", async () => {
    const { result } = await loaded();
    api.cancelOrder.mockRejectedValueOnce(new Error("boom"));
    await act(async () => { await expect(result.current.cancel()).rejects.toThrow(); });
    expect(result.current.cancelError).toBe("boom");

    api.cancelOrder.mockResolvedValueOnce(order("o1", { status: "cancelled", can_cancel: false }));
    await act(async () => { await result.current.cancel(); });
    expect(result.current.cancelError).toBeNull();
    expect(result.current.order?.status).toBe("cancelled");
    expect(api.cancelOrder).toHaveBeenCalledTimes(2);
  });
});
