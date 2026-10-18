import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { cart, orders } = vi.hoisted(() => ({
  cart: { refreshCart: vi.fn() },
  orders: { placeOrder: vi.fn() },
}));
vi.mock("@/context/CartContext", () => ({ useCart: () => cart }));
vi.mock("@/services/orders", () => orders);

import { usePlaceOrder } from "@/hooks/usePlaceOrder";
import { isValidIdempotencyKey } from "@/lib/idempotency";

// Types come from the hook itself, so this file imports nothing else from src.
type PlaceOrderResult = Awaited<ReturnType<ReturnType<typeof usePlaceOrder>["placeOrder"]>>;

const order = { id: "o1", order_number: "PRM-2026-000001" } as unknown as PlaceOrderResult["order"];
const created: PlaceOrderResult = { order, created: true };

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  orders.placeOrder.mockReset();
  cart.refreshCart.mockReset();
  cart.refreshCart.mockResolvedValue(undefined);
});

describe("usePlaceOrder - success", () => {
  it("sends the address and the displayed total with a valid idempotency key", async () => {
    orders.placeOrder.mockResolvedValue(created);
    const { result } = renderHook(() => usePlaceOrder());

    let returned: PlaceOrderResult | undefined;
    await act(async () => { returned = await result.current.placeOrder("addr-1", 259); });

    expect(returned).toEqual(created);
    const [input, key] = orders.placeOrder.mock.calls[0];
    expect(input).toEqual({ shipping_address_id: "addr-1", expected_total: 259 });
    expect(isValidIdempotencyKey(key)).toBe(true);
  });

  it("omits expected_total when none is given", async () => {
    orders.placeOrder.mockResolvedValue(created);
    const { result } = renderHook(() => usePlaceOrder());
    await act(async () => { await result.current.placeOrder("addr-1"); });
    expect(orders.placeOrder.mock.calls[0][0]).toEqual({ shipping_address_id: "addr-1" });
  });

  it("refreshes the cart, exposes the placed order, and ends with isPlacing false", async () => {
    orders.placeOrder.mockResolvedValue(created);
    const { result } = renderHook(() => usePlaceOrder());
    await act(async () => { await result.current.placeOrder("addr-1", 100); });

    expect(cart.refreshCart).toHaveBeenCalledTimes(1);
    expect(result.current.placedOrder).toEqual(created);
    expect(result.current.isPlacing).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("uses a fresh key for the next order after one was placed", async () => {
    orders.placeOrder.mockResolvedValue(created);
    const { result } = renderHook(() => usePlaceOrder());
    await act(async () => { await result.current.placeOrder("addr-1", 100); });
    await act(async () => { await result.current.placeOrder("addr-1", 100); });
    expect(orders.placeOrder.mock.calls[0][1]).not.toBe(orders.placeOrder.mock.calls[1][1]);
  });

  it("does not fail the order if refreshing the cart afterwards fails", async () => {
    orders.placeOrder.mockResolvedValue(created);
    cart.refreshCart.mockRejectedValue(new Error("network"));
    const { result } = renderHook(() => usePlaceOrder());
    let returned: PlaceOrderResult | undefined;
    await act(async () => { returned = await result.current.placeOrder("addr-1", 100); });
    expect(returned).toEqual(created);
    expect(result.current.error).toBeNull();
  });
});

describe("usePlaceOrder - double click", () => {
  it("returns the same promise and sends ONE request while one is in flight", async () => {
    const pending = deferred<PlaceOrderResult>();
    orders.placeOrder.mockReturnValue(pending.promise);
    const { result } = renderHook(() => usePlaceOrder());

    let first!: Promise<PlaceOrderResult>;
    let second!: Promise<PlaceOrderResult>;
    act(() => {
      first = result.current.placeOrder("addr-1", 100);
      second = result.current.placeOrder("addr-1", 100);
    });
    expect(second).toBe(first);
    expect(orders.placeOrder).toHaveBeenCalledTimes(1);
    expect(result.current.isPlacing).toBe(true);

    await act(async () => { pending.resolve(created); await first; });
    expect(orders.placeOrder).toHaveBeenCalledTimes(1);
    expect(result.current.isPlacing).toBe(false);
  });

  it("ignores a click with a different address while one is in flight", async () => {
    const pending = deferred<PlaceOrderResult>();
    orders.placeOrder.mockReturnValue(pending.promise);
    const { result } = renderHook(() => usePlaceOrder());
    let first!: Promise<PlaceOrderResult>;
    act(() => {
      first = result.current.placeOrder("addr-1", 100);
      void result.current.placeOrder("addr-2", 100);
    });
    expect(orders.placeOrder).toHaveBeenCalledTimes(1);
    expect(orders.placeOrder.mock.calls[0][0].shipping_address_id).toBe("addr-1");
    await act(async () => { pending.resolve(created); await first; });
  });
});

describe("usePlaceOrder - failure and retry", () => {
  it("surfaces the error message, rejects, and refreshes the cart to show what changed", async () => {
    orders.placeOrder.mockRejectedValue(new Error("Prices in your cart have changed."));
    const { result } = renderHook(() => usePlaceOrder());

    await act(async () => {
      await expect(result.current.placeOrder("addr-1", 100)).rejects.toThrow("Prices in your cart have changed.");
    });

    expect(result.current.error).toBe("Prices in your cart have changed.");
    expect(result.current.placedOrder).toBeNull();
    expect(result.current.isPlacing).toBe(false);
    expect(cart.refreshCart).toHaveBeenCalledTimes(1);
  });

  it("falls back to a friendly message when the error has none", async () => {
    orders.placeOrder.mockRejectedValue({});
    const { result } = renderHook(() => usePlaceOrder());
    await act(async () => { await expect(result.current.placeOrder("addr-1", 100)).rejects.toBeDefined(); });
    expect(result.current.error).toMatch(/couldn't place your order/i);
  });

  it("RETRYING the same request reuses the same key (an attempt that reached the server cannot duplicate)", async () => {
    orders.placeOrder.mockRejectedValueOnce(new Error("Network Error")).mockResolvedValueOnce({ order, created: false });
    const { result } = renderHook(() => usePlaceOrder());

    await act(async () => { await expect(result.current.placeOrder("addr-1", 100)).rejects.toThrow(); });
    await act(async () => { await result.current.placeOrder("addr-1", 100); });

    expect(orders.placeOrder.mock.calls[0][1]).toBe(orders.placeOrder.mock.calls[1][1]);
    expect(result.current.error).toBeNull();
    expect(result.current.placedOrder?.created).toBe(false);
  });

  it("a CHANGED request (new total after a price change) gets a NEW key", async () => {
    orders.placeOrder.mockRejectedValueOnce(new Error("Prices changed")).mockResolvedValueOnce(created);
    const { result } = renderHook(() => usePlaceOrder());

    await act(async () => { await expect(result.current.placeOrder("addr-1", 100)).rejects.toThrow(); });
    await act(async () => { await result.current.placeOrder("addr-1", 120); });

    expect(orders.placeOrder.mock.calls[0][1]).not.toBe(orders.placeOrder.mock.calls[1][1]);
  });

  it("a different address also gets a new key", async () => {
    orders.placeOrder.mockRejectedValueOnce(new Error("nope")).mockResolvedValueOnce(created);
    const { result } = renderHook(() => usePlaceOrder());
    await act(async () => { await expect(result.current.placeOrder("addr-1", 100)).rejects.toThrow(); });
    await act(async () => { await result.current.placeOrder("addr-2", 100); });
    expect(orders.placeOrder.mock.calls[0][1]).not.toBe(orders.placeOrder.mock.calls[1][1]);
  });

  it("clears the previous error when a new attempt starts, and via clearError", async () => {
    orders.placeOrder.mockRejectedValueOnce(new Error("boom"));
    const pending = deferred<PlaceOrderResult>();
    orders.placeOrder.mockReturnValueOnce(pending.promise);
    const { result } = renderHook(() => usePlaceOrder());

    await act(async () => { await expect(result.current.placeOrder("addr-1", 100)).rejects.toThrow(); });
    expect(result.current.error).toBe("boom");

    let attempt!: Promise<PlaceOrderResult>;
    act(() => { attempt = result.current.placeOrder("addr-1", 100); });
    expect(result.current.error).toBeNull();
    await act(async () => { pending.resolve(created); await attempt; });

    orders.placeOrder.mockRejectedValueOnce(new Error("again"));
    await act(async () => { await expect(result.current.placeOrder("addr-1", 100)).rejects.toThrow(); });
    expect(result.current.error).toBe("again");
    act(() => result.current.clearError());
    expect(result.current.error).toBeNull();
  });

  it("allows another attempt after a failure (no stuck in-flight state)", async () => {
    orders.placeOrder.mockRejectedValueOnce(new Error("x")).mockResolvedValueOnce(created);
    const { result } = renderHook(() => usePlaceOrder());
    await act(async () => { await expect(result.current.placeOrder("addr-1", 100)).rejects.toThrow(); });
    await waitFor(() => expect(result.current.isPlacing).toBe(false));
    await act(async () => { await result.current.placeOrder("addr-1", 100); });
    expect(orders.placeOrder).toHaveBeenCalledTimes(2);
  });
});
