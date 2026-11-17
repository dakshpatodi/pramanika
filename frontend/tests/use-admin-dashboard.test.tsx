import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { auth, getAdminDashboard } = vi.hoisted(() => ({
  auth: { user: { id: "u1" } as { id: string } | null, isLoading: false },
  getAdminDashboard: vi.fn(),
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/services/admin", () => ({ getAdminDashboard }));

import { useAdminDashboard } from "@/hooks/useAdminDashboard";
import { dashboard } from "./admin-fixtures";

beforeEach(() => {
  auth.user = { id: "u1" };
  auth.isLoading = false;
  getAdminDashboard.mockReset();
});
afterEach(cleanup);

const deferred = <T,>() => {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => ((resolve = res), (reject = rej)));
  return { promise, resolve, reject };
};

describe("useAdminDashboard", () => {
  it("loads once, then holds the data", async () => {
    getAdminDashboard.mockResolvedValue(dashboard());
    const { result } = renderHook(() => useAdminDashboard());
    expect(result.current).toMatchObject({ data: null, loading: true, error: null });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data?.orders.total).toBe(13);
    expect(getAdminDashboard).toHaveBeenCalledTimes(1);
  });

  it("does not call the API while the session is restoring or nobody is signed in", () => {
    auth.isLoading = true;
    renderHook(() => useAdminDashboard());
    auth.isLoading = false;
    auth.user = null;
    renderHook(() => useAdminDashboard());
    expect(getAdminDashboard).not.toHaveBeenCalled();
  });

  it("reports a failure with the server's message and recovers on reload", async () => {
    getAdminDashboard.mockRejectedValueOnce(new Error("Dashboard exploded"));
    const { result } = renderHook(() => useAdminDashboard());
    await waitFor(() => expect(result.current.error).toBe("Dashboard exploded"));
    expect(result.current).toMatchObject({ data: null, loading: false });
    getAdminDashboard.mockResolvedValueOnce(dashboard());
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.data).not.toBeNull());
    expect(result.current.error).toBeNull();
  });

  it("keeps the previous numbers while refreshing, and when the refresh fails", async () => {
    getAdminDashboard.mockResolvedValueOnce(dashboard());
    const { result } = renderHook(() => useAdminDashboard());
    await waitFor(() => expect(result.current.data).not.toBeNull());

    const second = deferred<ReturnType<typeof dashboard>>();
    getAdminDashboard.mockReturnValueOnce(second.promise);
    act(() => result.current.reload());
    expect(result.current.loading).toBe(true);
    expect(result.current.data?.orders.total).toBe(13);          // still there
    await act(async () => second.reject(new Error("later failure")));
    expect(result.current).toMatchObject({ loading: false, error: "later failure" });
    expect(result.current.data?.orders.total).toBe(13);          // still there
  });

  it("uses only the newest request when two overlap", async () => {
    const first = deferred<ReturnType<typeof dashboard>>();
    const second = deferred<ReturnType<typeof dashboard>>();
    getAdminDashboard.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { result } = renderHook(() => useAdminDashboard());
    act(() => result.current.reload());
    await act(async () => second.resolve(dashboard({ customers: { total: 2, new_last_30_days: 1 } })));
    await act(async () => first.resolve(dashboard({ customers: { total: 999, new_last_30_days: 9 } })));
    expect(result.current.data?.customers.total).toBe(2);
  });

  it("forgets the numbers and ignores a late answer when the signed-in user changes", async () => {
    const late = deferred<ReturnType<typeof dashboard>>();
    getAdminDashboard.mockReturnValueOnce(late.promise);
    const { result, rerender } = renderHook(() => useAdminDashboard());
    auth.user = { id: "u2" };
    getAdminDashboard.mockResolvedValueOnce(dashboard({ customers: { total: 5, new_last_30_days: 0 } }));
    rerender();
    await waitFor(() => expect(result.current.data?.customers.total).toBe(5));
    await act(async () => late.resolve(dashboard({ customers: { total: 777, new_last_30_days: 0 } })));
    expect(result.current.data?.customers.total).toBe(5);
  });

  it("clears the data when the user signs out", async () => {
    getAdminDashboard.mockResolvedValue(dashboard());
    const { result, rerender } = renderHook(() => useAdminDashboard());
    await waitFor(() => expect(result.current.data).not.toBeNull());
    auth.user = null;
    rerender();
    await waitFor(() => expect(result.current.data).toBeNull());
  });
});
