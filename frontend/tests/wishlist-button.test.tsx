import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { auth, api } = vi.hoisted(() => ({
  auth: { user: null as null | { id: string }, isLoading: false },
  api: { getWishlistProductIds: vi.fn(), addToWishlist: vi.fn(), removeFromWishlist: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/services/wishlist", () => api);

import { WishlistProvider } from "@/context/WishlistContext";
import { WishlistButton } from "@/components/wishlist/WishlistButton";

const apiError = (message: string) =>
  Object.assign(new Error("Request failed"), { isAxiosError: true, response: { status: 409, data: { success: false, message } } });
function deferred<T = void>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

type Variant = "icon" | "text";
function mount(variant: Variant = "icon", withProvider = true) {
  const button = <WishlistButton productId="p1" productName="Ragi Flour" variant={variant} redirectTo="/shop/ragi-flour" />;
  return render(withProvider ? <WishlistProvider>{button}</WishlistProvider> : button);
}
const nameOf = (variant: Variant, saved: boolean) =>
  variant === "icon"
    ? `${saved ? "Remove from wishlist" : "Save to wishlist"}: Ragi Flour`
    : saved ? "Remove from wishlist" : "Save to wishlist";

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset()); // block body: a returned function would be run by Vitest as a teardown
  api.getWishlistProductIds.mockResolvedValue([]);
  api.addToWishlist.mockResolvedValue({});
  api.removeFromWishlist.mockResolvedValue(undefined);
  auth.user = { id: "u1" };
  auth.isLoading = false;
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("WishlistButton", () => {
  it("renders nothing outside a WishlistProvider", () => {
    const { container } = mount("icon", false);
    expect(container).toBeEmptyDOMElement();
  });

  describe.each<Variant>(["icon", "text"])("%s variant, logged in", (variant) => {
    it("offers to save an unsaved product", async () => {
      mount(variant);
      const button = await screen.findByRole("button", { name: nameOf(variant, false) });
      expect(button).not.toHaveAttribute("aria-disabled");
      expect(button.querySelector("svg")).not.toHaveClass("fill-current");
    });

    it("offers to remove a saved product, with a filled heart", async () => {
      api.getWishlistProductIds.mockResolvedValue(["p1"]);
      mount(variant);
      const button = await screen.findByRole("button", { name: nameOf(variant, true) });
      expect(button.querySelector("svg")).toHaveClass("fill-current");
    });

    it("flips at once on click, before the server answers, and announces the result", async () => {
      const d = deferred();
      api.addToWishlist.mockReturnValue(d.promise);
      mount(variant);
      fireEvent.click(await screen.findByRole("button", { name: nameOf(variant, false) }));
      const button = screen.getByRole("button", { name: nameOf(variant, true) });
      expect(button).toHaveAttribute("aria-disabled", "true");
      expect(api.addToWishlist).toHaveBeenCalledWith("p1");
      await act(async () => { d.resolve(); });
      expect(screen.getByRole("status")).toHaveTextContent("Ragi Flour saved to your wishlist.");
      expect(screen.getByRole("button", { name: nameOf(variant, true) })).not.toHaveAttribute("aria-disabled");
      expect(screen.queryByRole("alert")).toBeNull();
    });

    it("removes a saved product and announces it", async () => {
      api.getWishlistProductIds.mockResolvedValue(["p1"]);
      mount(variant);
      fireEvent.click(await screen.findByRole("button", { name: nameOf(variant, true) }));
      await screen.findByRole("button", { name: nameOf(variant, false) });
      expect(api.removeFromWishlist).toHaveBeenCalledWith("p1");
      await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Ragi Flour removed from your wishlist."));
    });

    it("puts the heart back and shows the server's message when it fails", async () => {
      api.addToWishlist.mockRejectedValue(apiError("Your wishlist is full."));
      mount(variant);
      fireEvent.click(await screen.findByRole("button", { name: nameOf(variant, false) }));
      expect(await screen.findByRole("alert")).toHaveTextContent("Your wishlist is full.");
      expect(screen.getByRole("button", { name: nameOf(variant, false) })).toBeInTheDocument();
      expect(screen.getByRole("status")).toHaveTextContent("");
    });

    it("falls back to a generic message for an unknown failure", async () => {
      api.addToWishlist.mockRejectedValue({});
      mount(variant);
      fireEvent.click(await screen.findByRole("button", { name: nameOf(variant, false) }));
      expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't update your wishlist. Please try again.");
    });

    it("clears the failure message on the next attempt", async () => {
      api.addToWishlist.mockRejectedValueOnce(apiError("Boom."));
      mount(variant);
      fireEvent.click(await screen.findByRole("button", { name: nameOf(variant, false) }));
      await screen.findByRole("alert");
      fireEvent.click(screen.getByRole("button", { name: nameOf(variant, false) }));
      await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
      await screen.findByRole("button", { name: nameOf(variant, true) });
    });

    it("sends one request however many times it is clicked while in flight", async () => {
      const d = deferred();
      api.addToWishlist.mockReturnValue(d.promise);
      mount(variant);
      const button = await screen.findByRole("button", { name: nameOf(variant, false) });
      fireEvent.click(button);
      fireEvent.click(screen.getByRole("button", { name: nameOf(variant, true) }));
      fireEvent.click(screen.getByRole("button", { name: nameOf(variant, true) }));
      await act(async () => { d.resolve(); });
      expect(api.addToWishlist).toHaveBeenCalledTimes(1);
      expect(api.removeFromWishlist).not.toHaveBeenCalled();
    });

    it("ignores clicks until the saved ids have loaded (it cannot know the state yet)", async () => {
      const d = deferred<string[]>();
      api.getWishlistProductIds.mockReturnValue(d.promise);
      mount(variant);
      const button = await screen.findByRole("button", { name: nameOf(variant, false) });
      expect(button).toHaveAttribute("aria-disabled", "true");
      fireEvent.click(button);
      expect(api.addToWishlist).not.toHaveBeenCalled();
      await act(async () => { d.resolve(["p1"]); });
      expect(await screen.findByRole("button", { name: nameOf(variant, true) })).not.toHaveAttribute("aria-disabled");
    });
  });

  it("the failure message of an icon heart clears itself after a few seconds", async () => {
    vi.useFakeTimers();
    api.addToWishlist.mockRejectedValue(apiError("Boom."));
    mount("icon");
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    fireEvent.click(screen.getByRole("button", { name: nameOf("icon", false) }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByRole("alert")).toHaveTextContent("Boom.");
    await act(async () => { await vi.advanceTimersByTimeAsync(4900); });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(200); });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  describe("guests", () => {
    beforeEach(() => {
      auth.user = null;
    });

    it("the icon is a link to log in that returns to the product, and nothing is sent", () => {
      mount("icon");
      const link = screen.getByRole("link", { name: "Log in to save to wishlist: Ragi Flour" });
      expect(link).toHaveAttribute("href", "/login?redirect=%2Fshop%2Fragi-flour");
      expect(screen.queryByRole("button")).toBeNull();
      expect(api.getWishlistProductIds).not.toHaveBeenCalled();
      expect(api.addToWishlist).not.toHaveBeenCalled();
    });

    it("the text button is a link to log in too", () => {
      mount("text");
      expect(screen.getByRole("link", { name: "Save to wishlist" })).toHaveAttribute("href", "/login?redirect=%2Fshop%2Fragi-flour");
      expect(screen.queryByRole("button")).toBeNull();
    });
  });

  it("while the session is still loading shows a disabled button, not a login link", () => {
    auth.user = null;
    auth.isLoading = true;
    mount("icon");
    expect(screen.queryByRole("link")).toBeNull();
    const button = screen.getByRole("button", { name: nameOf("icon", false) });
    expect(button).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(button);
    expect(api.addToWishlist).not.toHaveBeenCalled();
  });
});
