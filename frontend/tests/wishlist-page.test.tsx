import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { WishlistItem, WishlistList } from "@/types/wishlist";

const { auth, router, cart, api } = vi.hoisted(() => ({
  auth: { user: null as null | { id: string }, isLoading: false, isAuthenticated: true },
  router: { push: vi.fn() },
  cart: { addItem: vi.fn() },
  api: { listWishlist: vi.fn(), getWishlistProductIds: vi.fn(), addToWishlist: vi.fn(), removeFromWishlist: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/context/CartContext", () => ({ useCart: () => cart }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/dashboard/wishlist" }));
vi.mock("@/services/wishlist", () => api);

import WishlistPage from "@/app/dashboard/wishlist/page";
import { useWishlist, WishlistProvider } from "@/context/WishlistContext";

const item = (n: number, over: Partial<WishlistItem> = {}): WishlistItem => ({
  product_id: `p${n}`, name: `Product ${n}`, slug: `product-${n}`, price: 100 * n, compare_at_price: null, image_url: null,
  is_available: true, in_stock: true, low_stock: false, added_at: "2026-10-05T10:00:00Z", ...over,
});
const list = (items: WishlistItem[], page = 1, totalPages = 1, total = items.length): WishlistList => ({
  items, pagination: { total, page, page_size: 12, total_pages: totalPages, has_next: page < totalPages, has_previous: page > 1 },
});
const apiError = (message: string) =>
  Object.assign(new Error("Request failed"), { isAxiosError: true, response: { status: 409, data: { success: false, message } } });
function deferred<T = void>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

/** Shows what the heart buttons elsewhere would show, so the page can be checked against them. */
function Probe({ id }: { id: string }) {
  const { isSaved } = useWishlist();
  return <output aria-label={`saved ${id}`}>{isSaved(id) ? "yes" : "no"}</output>;
}
function mount(probeIds: string[] = []) {
  return render(
    <WishlistProvider>
      <WishlistPage />
      {probeIds.map((id) => <Probe key={id} id={id} />)}
    </WishlistProvider>
  );
}
const row = (name: string) => screen.getByRole("button", { name: `Remove ${name} from wishlist` }).closest("li") as HTMLElement;

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset()); // block body: a returned function would be run by Vitest as a teardown
  cart.addItem.mockReset().mockResolvedValue({});
  router.push.mockReset();
  api.getWishlistProductIds.mockResolvedValue(["p1", "p2"]);
  api.removeFromWishlist.mockResolvedValue(undefined);
  auth.user = { id: "u1" };
  auth.isLoading = false;
  auth.isAuthenticated = true;
});
afterEach(cleanup);

describe("Wishlist page", () => {
  it("lists the saved products inside the account frame", async () => {
    api.listWishlist.mockResolvedValue(list([item(2), item(1, { compare_at_price: 150 })]));
    mount();
    expect(await screen.findByText("Product 2")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Wishlist");
    expect(within(screen.getByRole("navigation", { name: "Account" })).getByRole("link", { name: "Wishlist" })).toHaveAttribute("aria-current", "page");
    expect(within(row("Product 2")).getByText(/₹200/)).toBeInTheDocument();
    expect(within(row("Product 1")).getByText(/₹150/)).toBeInTheDocument(); // compare-at price
    expect(within(row("Product 2")).getByRole("link", { name: "Product 2" })).toHaveAttribute("href", "/shop/product-2");
    expect(api.listWishlist).toHaveBeenCalledWith(1, 12);
  });

  it("shows a loading state, then an empty state that points to the shop", async () => {
    const d = deferred<WishlistList>();
    api.listWishlist.mockReturnValue(d.promise);
    mount();
    expect(screen.getByRole("status", { name: "Loading your wishlist" })).toBeInTheDocument();
    d.resolve(list([]));
    expect(await screen.findByRole("heading", { name: "Your wishlist is empty" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse the shop" })).toHaveAttribute("href", "/shop");
    expect(screen.queryByRole("button", { name: /from wishlist/ })).toBeNull();
  });

  it("shows the server's message when it cannot load, and Try again reloads", async () => {
    const user = userEvent.setup();
    api.listWishlist.mockRejectedValueOnce(apiError("Wishlist is down."));
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("Wishlist is down.");
    api.listWishlist.mockResolvedValue(list([item(1)]));
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Product 1")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  describe("availability", () => {
    it("a withdrawn product is not linked and cannot be bought, but can be removed", async () => {
      api.listWishlist.mockResolvedValue(list([item(1, { is_available: false, in_stock: false })]));
      mount();
      await screen.findByText("Product 1");
      const r = row("Product 1");
      expect(within(r).getByText("No longer available")).toBeInTheDocument();
      expect(within(r).queryByRole("link")).toBeNull();
      expect(within(r).queryByRole("button", { name: /Add .* to cart/ })).toBeNull();
      expect(within(r).getByRole("button", { name: "Remove Product 1 from wishlist" })).toBeEnabled();
    });

    it("an out-of-stock product is linked but cannot be added to the cart", async () => {
      api.listWishlist.mockResolvedValue(list([item(1, { in_stock: false })]));
      mount();
      await screen.findByText("Product 1");
      const r = row("Product 1");
      expect(within(r).getByText("Out of stock")).toBeInTheDocument();
      expect(within(r).getByRole("link", { name: "Product 1" })).toBeInTheDocument();
      expect(within(r).queryByRole("button", { name: /Add .* to cart/ })).toBeNull();
    });

    it("a low-stock product says so and can still be added", async () => {
      api.listWishlist.mockResolvedValue(list([item(1, { low_stock: true })]));
      mount();
      await screen.findByText("Product 1");
      expect(within(row("Product 1")).getByText("Only a few left")).toBeInTheDocument();
      expect(within(row("Product 1")).getByRole("button", { name: "Add Product 1 to cart" })).toBeEnabled();
    });
  });

  describe("add to cart", () => {
    it("adds one unit of that product, confirms, links to the cart, and keeps it on the wishlist", async () => {
      const user = userEvent.setup();
      api.listWishlist.mockResolvedValue(list([item(1), item(2)]));
      mount(["p1"]);
      await screen.findByText("Product 2");
      await user.click(within(row("Product 2")).getByRole("button", { name: "Add Product 2 to cart" }));
      expect(cart.addItem).toHaveBeenCalledTimes(1);
      expect(cart.addItem).toHaveBeenCalledWith("p2", 1);
      expect(await within(row("Product 2")).findByRole("status")).toHaveTextContent("Added Product 2 to your cart.");
      expect(within(row("Product 2")).getByRole("link", { name: "View cart" })).toHaveAttribute("href", "/cart");
      expect(within(row("Product 1")).queryByRole("status")).toBeNull();
      expect(api.removeFromWishlist).not.toHaveBeenCalled();
      expect(screen.getByText("Product 2")).toBeInTheDocument();
    });

    it("shows the server's reason when it is refused (e.g. stock) and lets the user try again", async () => {
      const user = userEvent.setup();
      api.listWishlist.mockResolvedValue(list([item(1)]));
      cart.addItem.mockRejectedValueOnce(apiError("Only 2 units are available in stock."));
      mount();
      await screen.findByText("Product 1");
      await user.click(screen.getByRole("button", { name: "Add Product 1 to cart" }));
      expect(await within(row("Product 1")).findByRole("alert")).toHaveTextContent("Only 2 units are available in stock.");
      expect(screen.getByRole("button", { name: "Add Product 1 to cart" })).toBeEnabled();
      const retry = deferred();
      cart.addItem.mockReturnValueOnce(retry.promise);
      await user.click(screen.getByRole("button", { name: "Add Product 1 to cart" }));
      expect(within(row("Product 1")).queryByRole("alert")).toBeNull(); // the old refusal is not left up while retrying
      retry.resolve();
      expect(await within(row("Product 1")).findByRole("status")).toBeInTheDocument();
      expect(within(row("Product 1")).queryByRole("alert")).toBeNull();
    });

    it("disables the row's buttons while the request is in flight, so it cannot be sent twice", async () => {
      const user = userEvent.setup();
      const d = deferred();
      cart.addItem.mockReturnValue(d.promise);
      api.listWishlist.mockResolvedValue(list([item(1)]));
      mount();
      await screen.findByText("Product 1");
      await user.click(screen.getByRole("button", { name: "Add Product 1 to cart" }));
      expect(screen.getByRole("button", { name: "Add Product 1 to cart" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Remove Product 1 from wishlist" })).toBeDisabled();
      expect(within(row("Product 1")).getByText("Adding...")).toBeInTheDocument();
      d.resolve();
      await waitFor(() => expect(screen.getByRole("button", { name: "Add Product 1 to cart" })).toBeEnabled());
      expect(cart.addItem).toHaveBeenCalledTimes(1);
    });
  });

  describe("remove", () => {
    it("removes it on the server, reloads the list, and updates every heart", async () => {
      const user = userEvent.setup();
      api.listWishlist.mockResolvedValueOnce(list([item(1), item(2)])).mockResolvedValue(list([item(2)]));
      mount(["p1", "p2"]);
      await screen.findByText("Product 1");
      await waitFor(() => expect(screen.getByLabelText("saved p1")).toHaveTextContent("yes"));
      await user.click(screen.getByRole("button", { name: "Remove Product 1 from wishlist" }));
      await waitFor(() => expect(screen.queryByText("Product 1")).toBeNull());
      expect(api.removeFromWishlist).toHaveBeenCalledWith("p1");
      expect(api.listWishlist).toHaveBeenCalledTimes(2);
      expect(screen.getByText("Product 2")).toBeInTheDocument();
      expect(screen.getByLabelText("saved p1")).toHaveTextContent("no");
      expect(screen.getByLabelText("saved p2")).toHaveTextContent("yes");
    });

    it("shows the empty state once the last product is removed", async () => {
      const user = userEvent.setup();
      api.listWishlist.mockResolvedValueOnce(list([item(1)])).mockResolvedValue(list([]));
      mount();
      await screen.findByText("Product 1");
      await user.click(screen.getByRole("button", { name: "Remove Product 1 from wishlist" }));
      expect(await screen.findByRole("heading", { name: "Your wishlist is empty" })).toBeInTheDocument();
    });

    it("keeps the row, says why, and leaves the heart saved when the server refuses", async () => {
      const user = userEvent.setup();
      api.listWishlist.mockResolvedValue(list([item(1)]));
      api.removeFromWishlist.mockRejectedValueOnce(apiError("Try again later."));
      mount(["p1"]);
      await screen.findByText("Product 1");
      await waitFor(() => expect(screen.getByLabelText("saved p1")).toHaveTextContent("yes"));
      await user.click(screen.getByRole("button", { name: "Remove Product 1 from wishlist" }));
      expect(await within(row("Product 1")).findByRole("alert")).toHaveTextContent("Try again later.");
      expect(screen.getByLabelText("saved p1")).toHaveTextContent("yes");
      expect(api.listWishlist).toHaveBeenCalledTimes(1);
      expect(screen.getByRole("button", { name: "Remove Product 1 from wishlist" })).toBeEnabled();
    });

    it("keeps what is on screen, with a message, if the refresh after removing fails", async () => {
      const user = userEvent.setup();
      api.listWishlist.mockResolvedValueOnce(list([item(1), item(2)])).mockRejectedValueOnce(apiError("Refresh failed."));
      mount();
      await screen.findByText("Product 1");
      await user.click(screen.getByRole("button", { name: "Remove Product 1 from wishlist" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("Refresh failed.");
      expect(screen.getByText("Product 2")).toBeInTheDocument();
    });
  });

  describe("pagination", () => {
    const many = Array.from({ length: 12 }, (_, i) => item(i + 1));

    it("moves between pages, asking the server for each", async () => {
      const user = userEvent.setup();
      api.listWishlist.mockImplementation(async (p: number) => (p === 1 ? list(many, 1, 2, 13) : list([item(13)], 2, 2, 13)));
      mount();
      await screen.findByText("Product 1");
      expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
      await user.click(screen.getByRole("button", { name: "Next" }));
      expect(await screen.findByText("Product 13")).toBeInTheDocument();
      expect(api.listWishlist).toHaveBeenLastCalledWith(2, 12);
      expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
      await user.click(screen.getByRole("button", { name: "Previous" }));
      expect(await screen.findByText("Product 1")).toBeInTheDocument();
      expect(api.listWishlist).toHaveBeenLastCalledWith(1, 12);
    });

    it("has no pager for a single page", async () => {
      api.listWishlist.mockResolvedValue(list([item(1)]));
      mount();
      await screen.findByText("Product 1");
      expect(screen.queryByRole("navigation", { name: "Wishlist pages" })).toBeNull();
    });

    it("steps back a page when removing the last product of the final page leaves it empty", async () => {
      const user = userEvent.setup();
      api.listWishlist.mockImplementation(async (p: number) => {
        if (p === 1) return list(many, 1, 1, 12);
        return list([item(13)], 2, 2, 13);
      });
      // first load of page 1 knows there are two pages; after the removal the server has only one
      api.listWishlist.mockResolvedValueOnce(list(many, 1, 2, 13));
      mount();
      await screen.findByText("Product 1");
      await user.click(screen.getByRole("button", { name: "Next" }));
      await screen.findByText("Product 13");
      // the reload for page 2 now comes back empty, with one page in total
      api.listWishlist.mockResolvedValueOnce({ items: [], pagination: { total: 12, page: 2, page_size: 12, total_pages: 1, has_next: false, has_previous: true } });
      await user.click(screen.getByRole("button", { name: "Remove Product 13 from wishlist" }));
      await waitFor(() => expect(api.listWishlist).toHaveBeenLastCalledWith(1, 12));
      expect(await screen.findByText("Product 1")).toBeInTheDocument();
      expect(screen.queryByText("Page 2 of 1")).toBeNull();
    });
  });

  it("renders nothing for a visitor and never calls the API", () => {
    auth.user = null;
    auth.isAuthenticated = false;
    const { container } = mount();
    expect(container).toBeEmptyDOMElement();
    expect(router.push).toHaveBeenCalledWith("/login?redirect=%2Fdashboard%2Fwishlist");
    expect(api.listWishlist).not.toHaveBeenCalled();
    expect(api.getWishlistProductIds).not.toHaveBeenCalled();
  });
});
