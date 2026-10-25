import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProductDetail } from "@/types/product";

const { auth, cartCtx, router, nav, products, api } = vi.hoisted(() => ({
  auth: { user: null as null | { id: string }, isLoading: false, isAuthenticated: true },
  cartCtx: { addItem: vi.fn() },
  router: { push: vi.fn() },
  nav: { slug: "multigrain-cereal", pathname: "/shop/multigrain-cereal" },
  products: { getProduct: vi.fn() },
  api: { getWishlistProductIds: vi.fn(), addToWishlist: vi.fn(), removeFromWishlist: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/context/CartContext", () => ({ useCart: () => cartCtx }));
vi.mock("@/services/products", () => products);
vi.mock("@/services/wishlist", () => api);
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => nav.pathname,
  useParams: () => ({ slug: nav.slug }),
}));

import ProductDetailPage from "@/app/shop/[slug]/page";
import { WishlistProvider } from "@/context/WishlistContext";

function product(over: Partial<ProductDetail> = {}): ProductDetail {
  return {
    id: "p-1", slug: "multigrain-cereal", name: "Multigrain Cereal", sku: "MG-1", price: 249, compare_at_price: null, created_at: "2026-01-01T00:00:00Z",
    short_description: null, description: null, ingredients: null, nutritional_information: null, weight: null, weight_unit: null,
    in_stock: true, low_stock: false, image_url: null, category: {id: "category-2",slug: "cereals", name: "Cereals", description: "", image_url: null,}, related_products: [], ...over,
  };
}
const related = (n: number) => ({
  id: `r-${n}`, slug: `related-${n}`, name: `Related ${n}`, sku: "TEST-SKU", image_url: null, price: 50 * n, compare_at_price: null,
  in_stock: true, low_stock: false, category: { id: "category-2",slug: "cereals",name: "Cereals",description: "",image_url: null, },
});
async function renderLoaded() {
  const utils = render(<WishlistProvider><ProductDetailPage /></WishlistProvider>);
  await screen.findByRole("heading", { name: "Multigrain Cereal" });
  return utils;
}

beforeEach(() => {
  auth.user = { id: "u1" }; auth.isAuthenticated = true; auth.isLoading = false;
  router.push.mockReset(); cartCtx.addItem.mockReset().mockResolvedValue({});
  Object.values(api).forEach((fn) => fn.mockReset());
  api.getWishlistProductIds.mockResolvedValue([]);
  api.addToWishlist.mockResolvedValue({});
  api.removeFromWishlist.mockResolvedValue(undefined);
  products.getProduct.mockReset().mockResolvedValue(product());
  nav.slug = "multigrain-cereal"; nav.pathname = "/shop/multigrain-cereal";
});
afterEach(cleanup);

describe("Product page - wishlist", () => {
  it("saves this product from a labelled button", async () => {
    await renderLoaded();
    fireEvent.click(await screen.findByRole("button", { name: "Save to wishlist" }));
    expect(api.addToWishlist).toHaveBeenCalledWith("p-1");
    expect(await screen.findByRole("button", { name: "Remove from wishlist" })).toBeInTheDocument();
  });

  it("removes it again when it was already saved", async () => {
    api.getWishlistProductIds.mockResolvedValue(["p-1"]);
    await renderLoaded();
    fireEvent.click(await screen.findByRole("button", { name: "Remove from wishlist" }));
    expect(api.removeFromWishlist).toHaveBeenCalledWith("p-1");
    expect(await screen.findByRole("button", { name: "Save to wishlist" })).toBeInTheDocument();
  });

  it("is offered for an out-of-stock product too", async () => {
    products.getProduct.mockResolvedValue(product({ in_stock: false }));
    await renderLoaded();
    expect(screen.getByText("Out of stock")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Save to wishlist" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add to Cart/ })).toBeNull();
  });

  it("sends a guest to log in and back to this product, and sends nothing", async () => {
    auth.user = null; auth.isAuthenticated = false;
    await renderLoaded();
    expect(screen.getByRole("link", { name: "Save to wishlist" })).toHaveAttribute("href", "/login?redirect=%2Fshop%2Fmultigrain-cereal");
    expect(api.addToWishlist).not.toHaveBeenCalled();
    expect(screen.getByText("Log in to add items to your cart.")).toBeInTheDocument();
  });

  it("shows a wishlist failure beside the button and leaves the cart alone", async () => {
    api.addToWishlist.mockRejectedValue(Object.assign(new Error("x"), { isAxiosError: true, response: { data: { success: false, message: "Your wishlist is full." } } }));
    await renderLoaded();
    fireEvent.click(await screen.findByRole("button", { name: "Save to wishlist" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Your wishlist is full.");
    expect(cartCtx.addItem).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Save to wishlist" })).toBeInTheDocument();
  });

  it("does not disturb Add to Cart: still one such button, and it still adds", async () => {
    await renderLoaded();
    const add = screen.getByRole("button", { name: /Add to Cart|Adding/ });
    fireEvent.click(add);
    await screen.findByText(/Added 1 .* Multigrain Cereal to your cart/);
    expect(cartCtx.addItem).toHaveBeenCalledWith("p-1", 1);
    expect(api.addToWishlist).not.toHaveBeenCalled();
  });

  it("related products get hearts that save the RELATED product, not the one on the page", async () => {
    products.getProduct.mockResolvedValue(
    product({ related_products: [related(1), related(2)] }));
    await renderLoaded();
    fireEvent.click(await screen.findByRole("button", { name: "Save to wishlist: Related 2" }));
    expect(api.addToWishlist).toHaveBeenCalledTimes(1);
    expect(api.addToWishlist).toHaveBeenCalledWith("r-2");
    const heading = screen.getByRole("heading", { name: "You might also like" });
    const grid = heading.parentElement as HTMLElement;
    expect(within(grid).getAllByRole("link").map((l) => l.getAttribute("href"))).toEqual(["/shop/related-1", "/shop/related-2"]);
    expect(await within(grid).findByRole("button", { name: "Remove from wishlist: Related 2" })).toBeInTheDocument();
    expect(within(grid).getByRole("button", { name: "Save to wishlist: Related 1" })).toBeInTheDocument();
  });
});
