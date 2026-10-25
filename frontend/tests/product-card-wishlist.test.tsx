import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { auth, api } = vi.hoisted(() => ({
  auth: { user: null as null | { id: string }, isLoading: false },
  api: { getWishlistProductIds: vi.fn(), addToWishlist: vi.fn(), removeFromWishlist: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/services/wishlist", () => api);

import { ProductCard } from "@/components/products/ProductCard";
import { WishlistProvider } from "@/context/WishlistContext";
import type { ProductListItem } from "@/types/product";

const product = (over: Partial<ProductListItem> = {}): ProductListItem => ({
  id: "p1", slug: "ragi-flour", name: "Ragi Flour", sku: "RAGI-001", price: 120, compare_at_price: null, in_stock: true, low_stock: false, image_url: null, category: {id: "category-1",slug: "flours",name: "Flours",description: "", image_url: null,},
  ...over,
});

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset()); // block body: a returned function would be run by Vitest as a teardown
  api.getWishlistProductIds.mockResolvedValue([]);
  api.addToWishlist.mockResolvedValue({});
  auth.user = { id: "u1" };
  auth.isLoading = false;
});
afterEach(cleanup);

describe("ProductCard", () => {
  it("without a provider is exactly the plain card: one link, no heart", () => {
    render(<ProductCard product={product()} />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/shop/ragi-flour");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("keeps showing the product's details inside the link", () => {
    render(<ProductCard product={product({ compare_at_price: 150, low_stock: true })} />);
    const link = screen.getByRole("link");
    expect(within(link).getByRole("heading", { name: "Ragi Flour" })).toBeInTheDocument();
    expect(within(link).getByText("Flours")).toBeInTheDocument();
    expect(within(link).getByText(/₹120/)).toBeInTheDocument();
    expect(within(link).getByText(/₹150/)).toBeInTheDocument();
    expect(within(link).getByText("Sale")).toBeInTheDocument();
    expect(within(link).getByText("Low stock")).toBeInTheDocument();
  });

  it("shows an out-of-stock card with a heart too (saving for later is still useful)", async () => {
    render(<WishlistProvider><ProductCard product={product({ in_stock: false })} /></WishlistProvider>);
    expect(screen.getByText("Out of stock")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Save to wishlist: Ragi Flour" })).toBeInTheDocument();
  });

  it("puts the heart BESIDE the link, never inside it (no button or link nested in a link)", async () => {
    render(<WishlistProvider><ProductCard product={product()} /></WishlistProvider>);
    const heart = await screen.findByRole("button", { name: "Save to wishlist: Ragi Flour" });
    const link = screen.getByRole("link");
    expect(link.contains(heart)).toBe(false);
    expect(link.querySelector("a, button")).toBeNull();
    expect(heart.closest("a")).toBeNull();
  });

  it("clicking the heart saves THIS product and does not follow the card link", async () => {
    render(<WishlistProvider><ProductCard product={product({ id: "p-77" })} /></WishlistProvider>);
    const click = vi.fn();
    screen.getByRole("link").addEventListener("click", click);
    fireEvent.click(await screen.findByRole("button", { name: "Save to wishlist: Ragi Flour" }));
    expect(api.addToWishlist).toHaveBeenCalledWith("p-77");
    expect(click).not.toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "Remove from wishlist: Ragi Flour" })).toBeInTheDocument();
  });

  it("shows a saved product's heart as saved", async () => {
    api.getWishlistProductIds.mockResolvedValue(["p1"]);
    render(<WishlistProvider><ProductCard product={product()} /></WishlistProvider>);
    expect(await screen.findByRole("button", { name: "Remove from wishlist: Ragi Flour" })).toBeInTheDocument();
  });

  it("gives a guest a second link, to log in and come back to this product", () => {
    auth.user = null;
    render(<WishlistProvider><ProductCard product={product()} /></WishlistProvider>);
    const hrefs = screen.getAllByRole("link").map((l) => l.getAttribute("href"));
    expect(hrefs).toEqual(["/shop/ragi-flour", "/login?redirect=%2Fshop%2Fragi-flour"]);
  });

  it("hearts on different cards are independent", async () => {
    render(
      <WishlistProvider>
        <ProductCard product={product()} />
        <ProductCard product={product({ id: "p2", slug: "jowar", name: "Jowar" })} />
      </WishlistProvider>
    );
    fireEvent.click(await screen.findByRole("button", { name: "Save to wishlist: Jowar" }));
    await screen.findByRole("button", { name: "Remove from wishlist: Jowar" });
    expect(screen.getByRole("button", { name: "Save to wishlist: Ragi Flour" })).toBeInTheDocument();
    expect(api.addToWishlist).toHaveBeenCalledWith("p2");
  });
});
