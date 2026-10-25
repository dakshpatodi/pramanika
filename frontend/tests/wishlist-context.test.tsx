import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { auth, api } = vi.hoisted(() => ({
  auth: { user: null as null | { id: string }, isLoading: false },
  api: { getWishlistProductIds: vi.fn(), addToWishlist: vi.fn(), removeFromWishlist: vi.fn(), listWishlist: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/services/wishlist", () => api);

import { useWishlist, WishlistProvider } from "@/context/WishlistContext";

const wrapper = ({ children }: { children: React.ReactNode }) => <WishlistProvider>{children}</WishlistProvider>;
const apiError = (message: string) =>
  Object.assign(new Error("Request failed"), { isAxiosError: true, response: { status: 409, data: { success: false, message } } });
function deferred<T = void>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset()); // block body: a returned function would be run by Vitest as a teardown
  api.getWishlistProductIds.mockResolvedValue(["p1", "p2"]);
  api.addToWishlist.mockResolvedValue({});
  api.removeFromWishlist.mockResolvedValue(undefined);
  auth.user = { id: "u1" };
  auth.isLoading = false;
});

describe("WishlistProvider - loading", () => {
  it("loads the saved ids for a logged-in user", async () => {
    const { result } = renderHook(() => useWishlist(), { wrapper });
    expect(result.current.isAvailable).toBe(true);
    await waitFor(() => expect(result.current.isSaved("p1")).toBe(true));
    expect(result.current.isSaved("p2")).toBe(true);
    expect(result.current.isSaved("p3")).toBe(false);
    expect(result.current.count).toBe(2);
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.isLoading).toBe(false);
    expect(api.getWishlistProductIds).toHaveBeenCalledTimes(1);
  });

  it("is loading until the ids arrive", async () => {
    const d = deferred<string[]>();
    api.getWishlistProductIds.mockReturnValue(d.promise);
    const { result } = renderHook(() => useWishlist(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(true));
    await act(async () => { d.resolve(["p1"]); });
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isSaved("p1")).toBe(true);
  });

  it("asks for nothing for a guest", () => {
    auth.user = null;
    const { result } = renderHook(() => useWishlist(), { wrapper });
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.isLoading).toBe(false);
    expect(api.getWishlistProductIds).not.toHaveBeenCalled();
  });

  it("asks for nothing while the session itself is still loading, and reports loading", () => {
    auth.user = null;
    auth.isLoading = true;
    const { result } = renderHook(() => useWishlist(), { wrapper });
    expect(result.current.isLoading).toBe(true);
    expect(api.getWishlistProductIds).not.toHaveBeenCalled();
  });

  it("keeps the failure message, and refresh() can recover", async () => {
    api.getWishlistProductIds.mockRejectedValueOnce(apiError("Wishlist is down."));
    const { result } = renderHook(() => useWishlist(), { wrapper });
    await waitFor(() => expect(result.current.loadError).toBe("Wishlist is down."));
    expect(result.current.isLoading).toBe(false);
    await act(async () => { await result.current.refresh(); });
    expect(result.current.loadError).toBeNull();
    expect(result.current.isSaved("p1")).toBe(true);
  });

  it("throws away one user's ids when the user logs out or changes", async () => {
    const { result, rerender } = renderHook(() => useWishlist(), { wrapper });
    await waitFor(() => expect(result.current.isSaved("p1")).toBe(true));

    auth.user = null;
    rerender();
    await waitFor(() => expect(result.current.isSaved("p1")).toBe(false));
    expect(result.current.count).toBe(0);

    api.getWishlistProductIds.mockResolvedValue(["x"]);
    auth.user = { id: "u2" };
    rerender();
    await waitFor(() => expect(result.current.isSaved("x")).toBe(true));
    expect(result.current.isSaved("p1")).toBe(false);
  });

  it("ignores ids that arrive for a user who has already logged out", async () => {
    const d = deferred<string[]>();
    api.getWishlistProductIds.mockReturnValue(d.promise);
    const { result, rerender } = renderHook(() => useWishlist(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(true));
    auth.user = null;
    rerender();
    await act(async () => { d.resolve(["p1"]); });
    expect(result.current.isSaved("p1")).toBe(false);
    expect(result.current.isLoading).toBe(false);
  });

  it("a heart tapped while the ids were loading keeps its value", async () => {
    const d = deferred<string[]>();
    api.getWishlistProductIds.mockReturnValue(d.promise);
    const { result } = renderHook(() => useWishlist(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(true));
    const save = deferred();
    api.addToWishlist.mockReturnValue(save.promise);
    let toggled!: Promise<boolean>;
    act(() => { toggled = result.current.toggle("p9"); });
    await act(async () => { d.resolve(["p1"]); }); // the server list does not know p9 yet
    expect(result.current.isSaved("p9")).toBe(true);
    expect(result.current.isSaved("p1")).toBe(true);
    await act(async () => { save.resolve(); await toggled; });
    expect(result.current.isSaved("p9")).toBe(true);
  });
});

describe("WishlistProvider - saving and removing", () => {
  async function ready() {
    const hook = renderHook(() => useWishlist(), { wrapper });
    await waitFor(() => expect(hook.result.current.isSaved("p1")).toBe(true));
    return hook;
  }

  it("toggle on an unsaved product saves it: the heart flips before the server answers", async () => {
    const { result } = await ready();
    const d = deferred();
    api.addToWishlist.mockReturnValue(d.promise);
    let toggled!: Promise<boolean>;
    act(() => { toggled = result.current.toggle("p3"); });
    expect(result.current.isSaved("p3")).toBe(true);
    expect(result.current.isPending("p3")).toBe(true);
    expect(api.addToWishlist).toHaveBeenCalledWith("p3");
    await act(async () => { d.resolve(); });
    await expect(toggled).resolves.toBe(true);
    expect(result.current.isSaved("p3")).toBe(true);
    expect(result.current.isPending("p3")).toBe(false);
    expect(api.removeFromWishlist).not.toHaveBeenCalled();
  });

  it("toggle on a saved product removes it", async () => {
    const { result } = await ready();
    let saved: boolean | undefined;
    await act(async () => { saved = await result.current.toggle("p1"); });
    expect(saved).toBe(false);
    expect(api.removeFromWishlist).toHaveBeenCalledWith("p1");
    expect(api.addToWishlist).not.toHaveBeenCalled();
    expect(result.current.isSaved("p1")).toBe(false);
    expect(result.current.count).toBe(1);
  });

  it("puts the heart back and rejects with the server's error when saving fails", async () => {
    const { result } = await ready();
    const failure = apiError("Your wishlist is full.");
    api.addToWishlist.mockRejectedValue(failure);
    await act(async () => {
      await expect(result.current.toggle("p3")).rejects.toBe(failure);
    });
    expect(result.current.isSaved("p3")).toBe(false);
    expect(result.current.isPending("p3")).toBe(false);
    expect(result.current.count).toBe(2);
  });

  it("puts the heart back when removing fails", async () => {
    const { result } = await ready();
    api.removeFromWishlist.mockRejectedValue(apiError("nope"));
    await act(async () => {
      await expect(result.current.remove("p1")).rejects.toBeTruthy();
    });
    expect(result.current.isSaved("p1")).toBe(true);
    expect(result.current.isPending("p1")).toBe(false);
  });

  it("sends one request when the same heart is tapped twice quickly", async () => {
    const { result } = await ready();
    const d = deferred();
    api.addToWishlist.mockReturnValue(d.promise);
    let first!: Promise<boolean>;
    let second!: Promise<boolean>;
    act(() => {
      first = result.current.toggle("p3");
      second = result.current.toggle("p3");
    });
    await act(async () => { d.resolve(); });
    await expect(first).resolves.toBe(true);
    await expect(second).resolves.toBe(true); // reports the state it found, changes nothing
    expect(api.addToWishlist).toHaveBeenCalledTimes(1);
    expect(api.removeFromWishlist).not.toHaveBeenCalled();
    expect(result.current.isSaved("p3")).toBe(true);
  });

  it("add() and remove() on a product already in flight send nothing more", async () => {
    const { result } = await ready();
    const d = deferred();
    api.addToWishlist.mockReturnValue(d.promise);
    let first!: Promise<void>;
    act(() => {
      first = result.current.add("p3");
      void result.current.add("p3");
      void result.current.remove("p3"); // would flip it back and send a delete
    });
    await act(async () => { d.resolve(); await first; });
    expect(api.addToWishlist).toHaveBeenCalledTimes(1);
    expect(api.removeFromWishlist).not.toHaveBeenCalled();
    expect(result.current.isSaved("p3")).toBe(true);
  });

  it("different products do not block each other", async () => {
    const { result } = await ready();
    const d = deferred();
    api.addToWishlist.mockReturnValueOnce(d.promise);
    act(() => { void result.current.toggle("p3"); });
    await act(async () => { await result.current.toggle("p1"); });
    expect(api.removeFromWishlist).toHaveBeenCalledWith("p1");
    expect(result.current.isSaved("p1")).toBe(false);
    expect(result.current.isPending("p3")).toBe(true);
    await act(async () => { d.resolve(); });
  });

  it("add() and remove() are explicit: remove on a product that looks unsaved still asks the server", async () => {
    const { result } = await ready();
    await act(async () => { await result.current.remove("never-seen"); });
    expect(api.removeFromWishlist).toHaveBeenCalledWith("never-seen");
    await act(async () => { await result.current.add("p1"); });
    expect(api.addToWishlist).toHaveBeenCalledWith("p1");
    expect(result.current.isSaved("p1")).toBe(true);
  });

  it("does not put a failed save back for a user who has since logged out", async () => {
    const { result, rerender } = await ready();
    const d = deferred();
    api.addToWishlist.mockReturnValue(d.promise);
    let toggled!: Promise<boolean>;
    act(() => { toggled = result.current.toggle("p3"); });
    auth.user = { id: "u2" };
    api.getWishlistProductIds.mockResolvedValue(["p3"]);
    rerender();
    await waitFor(() => expect(result.current.isSaved("p3")).toBe(true)); // u2's own list
    await act(async () => {
      d.reject(apiError("nope"));
      await expect(toggled).rejects.toBeTruthy();
    });
    expect(result.current.isSaved("p3")).toBe(true); // u2's value was not clobbered
  });

  it("refuses for a guest without calling the server", async () => {
    auth.user = null;
    const { result } = renderHook(() => useWishlist(), { wrapper });
    await act(async () => {
      await expect(result.current.toggle("p1")).rejects.toThrow("log in");
    });
    expect(api.addToWishlist).not.toHaveBeenCalled();
    expect(result.current.isSaved("p1")).toBe(false);
  });

  it("setSaved records a change made elsewhere without a request", async () => {
    const { result } = await ready();
    act(() => result.current.setSaved("p1", false));
    expect(result.current.isSaved("p1")).toBe(false);
    act(() => result.current.setSaved("p7", true));
    expect(result.current.isSaved("p7")).toBe(true);
    expect(api.addToWishlist).not.toHaveBeenCalled();
    expect(api.removeFromWishlist).not.toHaveBeenCalled();
  });
});

describe("useWishlist outside a provider", () => {
  it("is inert instead of throwing", async () => {
    const { result } = renderHook(() => useWishlist());
    expect(result.current.isAvailable).toBe(false);
    expect(result.current.isSaved("p1")).toBe(false);
    expect(result.current.isPending("p1")).toBe(false);
    expect(result.current.count).toBe(0);
    await expect(result.current.toggle("p1")).rejects.toThrow();
    await expect(result.current.add("p1")).rejects.toThrow();
    await expect(result.current.remove("p1")).rejects.toThrow();
    expect(api.addToWishlist).not.toHaveBeenCalled();
  });
});
