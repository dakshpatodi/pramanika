import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { auth } = vi.hoisted(() => ({ auth: { user: { id: "u1" } as { id: string } | null, isLoading: false } }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));

import { useAdminQuery } from "@/hooks/useAdminQuery";

beforeEach(() => {
  auth.user = { id: "u1" };
  auth.isLoading = false;
});
afterEach(cleanup);

const deferred = <T,>() => {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => ((resolve = res), (reject = rej)));
  return { promise, resolve, reject };
};
const OPTS = { failure: "Could not load." };

describe("useAdminQuery", () => {
  it("loads, and holds the data", async () => {
    const fetcher = vi.fn().mockResolvedValue("A");
    const { result } = renderHook(() => useAdminQuery("k", fetcher, OPTS));
    expect(result.current).toMatchObject({ data: null, loading: true, error: null });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBe("A");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("does not fetch for a null key, while the session restores, or when signed out", () => {
    const fetcher = vi.fn().mockResolvedValue("A");
    renderHook(() => useAdminQuery(null, fetcher, OPTS));
    auth.isLoading = true;
    renderHook(() => useAdminQuery("k", fetcher, OPTS));
    auth.isLoading = false;
    auth.user = null;
    renderHook(() => useAdminQuery("k", fetcher, OPTS));
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("re-fetches when the key changes, keeping the previous result meanwhile if asked", async () => {
    const second = deferred<string>();
    const fetcher = vi.fn().mockResolvedValueOnce("page1").mockReturnValueOnce(second.promise);
    const { result, rerender } = renderHook(({ k }) => useAdminQuery(k, fetcher, { ...OPTS, keepPrevious: true }), { initialProps: { k: "1" } });
    await waitFor(() => expect(result.current.data).toBe("page1"));
    rerender({ k: "2" });
    expect(result.current).toMatchObject({ data: "page1", loading: true });      // old page stays on screen
    await act(async () => second.resolve("page2"));
    expect(result.current).toMatchObject({ data: "page2", loading: false });
  });

  it("drops the previous result when keepPrevious is off (one item must not show another's data)", async () => {
    const second = deferred<string>();
    const fetcher = vi.fn().mockResolvedValueOnce("item1").mockReturnValueOnce(second.promise);
    const { result, rerender } = renderHook(({ k }) => useAdminQuery(k, fetcher, OPTS), { initialProps: { k: "1" } });
    await waitFor(() => expect(result.current.data).toBe("item1"));
    rerender({ k: "2" });
    expect(result.current).toMatchObject({ data: null, loading: true });
  });

  it("ignores a slow answer for an old key", async () => {
    const slow = deferred<string>();
    const fetcher = vi.fn().mockReturnValueOnce(slow.promise).mockResolvedValueOnce("fast");
    const { result, rerender } = renderHook(({ k }) => useAdminQuery(k, fetcher, OPTS), { initialProps: { k: "1" } });
    rerender({ k: "2" });
    await waitFor(() => expect(result.current.data).toBe("fast"));
    await act(async () => slow.resolve("slow"));
    expect(result.current.data).toBe("fast");
  });

  it("reports the failure message, keeps old data, and recovers on reload", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce("ok").mockRejectedValueOnce(new Error("Server said no")).mockResolvedValueOnce("again");
    const { result } = renderHook(() => useAdminQuery("k", fetcher, OPTS));
    await waitFor(() => expect(result.current.data).toBe("ok"));
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.error).toBe("Server said no"));
    expect(result.current.data).toBe("ok");
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.data).toBe("again"));
    expect(result.current.error).toBeNull();
  });

  it("falls back to the supplied message when the error has none", async () => {
    const fetcher = vi.fn().mockRejectedValue({});
    const { result } = renderHook(() => useAdminQuery("k", fetcher, OPTS));
    await waitFor(() => expect(result.current.error).toBe("Could not load."));
  });

  it("uses the latest fetcher without re-fetching", async () => {
    const first = vi.fn().mockResolvedValue("first");
    const second = vi.fn().mockResolvedValue("second");
    const { result, rerender } = renderHook(({ f }) => useAdminQuery("k", f, OPTS), { initialProps: { f: first } });
    await waitFor(() => expect(result.current.data).toBe("first"));
    rerender({ f: second });
    expect(second).not.toHaveBeenCalled();
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.data).toBe("second"));
  });

  it("forgets the data and ignores a late answer when the user changes or signs out", async () => {
    const late = deferred<string>();
    const fetcher = vi.fn().mockReturnValueOnce(late.promise).mockResolvedValueOnce("for-u2");
    const { result, rerender } = renderHook(() => useAdminQuery("k", fetcher, { ...OPTS, keepPrevious: true }));
    auth.user = { id: "u2" };
    rerender();
    await waitFor(() => expect(result.current.data).toBe("for-u2"));
    await act(async () => late.resolve("for-u1"));
    expect(result.current.data).toBe("for-u2");
    auth.user = null;
    rerender();
    await waitFor(() => expect(result.current.data).toBeNull());
  });

  it("setData replaces the data without a request", async () => {
    const fetcher = vi.fn().mockResolvedValue("old");
    const { result } = renderHook(() => useAdminQuery("k", fetcher, OPTS));
    await waitFor(() => expect(result.current.data).toBe("old"));
    act(() => result.current.setData("saved copy"));
    expect(result.current.data).toBe("saved copy");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
