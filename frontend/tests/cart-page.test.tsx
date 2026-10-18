import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Cart, CartItem } from "@/types/cart";

const { auth, cartCtx, router } = vi.hoisted(() => ({
  auth: { user: null as null | { id: string }, isLoading: false, isAuthenticated: true },
  cartCtx: {} as Record<string, any>,
  router: { push: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/context/CartContext", () => ({ useCart: () => cartCtx }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/cart" }));

import CartPage from "@/app/cart/page";
import { formatMoney, formatPercent } from "@/lib/money";

function line(over: Partial<CartItem> & { id: string; name: string }): CartItem {
  const { id, name, ...rest } = over;
  return {
    id,
    product: { id: `p-${id}`, name, slug: name.toLowerCase().replace(/ /g, "-"), sku: `SKU-${id}`, image_url: null },
    quantity: 2, unit_price: 249, line_subtotal: 498, available_quantity: 10, issue: null, ...rest,
  };
}
function makeCart(over: Partial<Cart> = {}): Cart {
  return {
    id: "c1",
    items: [line({ id: "i1", name: "Multigrain Cereal" }), line({ id: "i2", name: "Poha", quantity: 1, unit_price: 189, line_subtotal: 189 })],
    item_count: 3, has_issues: false, coupon: null,
    totals: { subtotal: 687, discount: 0, taxable_amount: 687, gst_rate: 0.05, gst: 34.35, delivery_charge: 0, amount_for_free_delivery: 0, total: 721.35, currency: "INR" },
    ...over,
  };
}

function setCtx(over: Record<string, unknown> = {}) {
  Object.assign(cartCtx, {
    cart: makeCart(), itemCount: 3, isLoading: false, isMutating: false, loadError: null,
    refreshCart: vi.fn().mockResolvedValue(undefined),
    addItem: vi.fn(),
    updateItem: vi.fn().mockResolvedValue(makeCart()),
    removeItem: vi.fn().mockResolvedValue(makeCart()),
    clearCart: vi.fn().mockResolvedValue(makeCart()),
    applyCoupon: vi.fn().mockResolvedValue(makeCart()),
    removeCoupon: vi.fn().mockResolvedValue(makeCart()),
    ...over,
  });
}

beforeEach(() => {
  auth.user = { id: "u1" }; auth.isLoading = false; auth.isAuthenticated = true;
  router.push.mockReset();
  setCtx();
});
afterEach(cleanup);

describe("formatting helpers", () => {
  it("always shows two decimals", () => {
    expect(formatMoney(522.9)).toBe("₹522.90");
    expect(formatMoney(1234567)).toBe("₹12,34,567.00");
  });
  it("avoids float noise in percentages", () => {
    expect(formatPercent(0.05)).toBe("5%");
    expect(formatPercent(0.07)).toBe("7%");
    expect(formatPercent(0.125)).toBe("12.5%");
  });
});

describe("/cart page - access and states", () => {
  it("renders nothing and redirects when logged out", () => {
    auth.user = null; auth.isAuthenticated = false;
    const { container } = render(<CartPage />);
    expect(container.innerHTML).toBe("");
    expect(router.push).toHaveBeenCalledWith("/login?redirect=%2Fcart");
  });

  it("shows a skeleton - never 'empty' - until the first load finishes", () => {
    setCtx({ cart: null, isLoading: true });
    render(<CartPage />);
    expect(screen.getByRole("status", { name: "Loading your cart" })).toBeTruthy();
    expect(screen.queryByText("Your cart is empty")).toBeNull();
  });

  it("also shows the skeleton in the render before the fetch starts", () => {
    setCtx({ cart: null, isLoading: false, loadError: null });
    render(<CartPage />);
    expect(screen.getByRole("status", { name: "Loading your cart" })).toBeTruthy();
    expect(screen.queryByText("Your cart is empty")).toBeNull();
  });

  it("shows the load error with a working retry", () => {
    setCtx({ cart: null, loadError: "We couldn't load your cart. Please try again." });
    render(<CartPage />);
    expect(screen.getByRole("alert").textContent).toContain("couldn't load your cart");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(cartCtx.refreshCart).toHaveBeenCalledTimes(1);
  });

  it("shows the empty state with a link to the shop", () => {
    setCtx({ cart: makeCart({ items: [], item_count: 0 }) });
    render(<CartPage />);
    expect(screen.getByText("Your cart is empty")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Start shopping" }).getAttribute("href")).toBe("/shop");
  });
});

describe("/cart page - lines and totals", () => {
  it("shows lines and the server's numbers verbatim", () => {
    render(<CartPage />);
    expect(screen.getByRole("link", { name: "Multigrain Cereal" }).getAttribute("href")).toBe("/shop/multigrain-cereal");
    expect(screen.getByText("₹498.00")).toBeTruthy();
    expect(screen.getByText("₹189.00")).toBeTruthy();
    expect(screen.getByText("3 items")).toBeTruthy();
    const totals = within(screen.getByRole("complementary", { name: "Order summary" }));
    expect(totals.getByText("₹687.00")).toBeTruthy(); // subtotal
    expect(totals.getByText("GST (5%)")).toBeTruthy();
    expect(totals.getByText("₹34.35")).toBeTruthy();
    expect(totals.getByText("Free")).toBeTruthy();
    expect(totals.getByText("₹721.35")).toBeTruthy(); // total
    expect(totals.queryByText(/Discount/)).toBeNull();
    expect(totals.queryByText(/more to get free delivery/)).toBeNull();
  });

  it("uses singular 'item' for one unit", () => {
    setCtx({ cart: makeCart({ items: [line({ id: "i1", name: "Poha", quantity: 1 })], item_count: 1 }) });
    render(<CartPage />);
    expect(screen.getByText("1 item")).toBeTruthy();
  });

  it("shows a delivery charge and the free-delivery hint", () => {
    setCtx({ cart: makeCart({ totals: { ...makeCart().totals, delivery_charge: 49, amount_for_free_delivery: 151, total: 770.35 } }) });
    render(<CartPage />);
    const totals = within(screen.getByRole("complementary", { name: "Order summary" }));
    expect(totals.getByText("₹49.00")).toBeTruthy();
    expect(totals.getByText("Add ₹151.00 more to get free delivery.")).toBeTruthy();
    expect(totals.queryByText("Free")).toBeNull();
  });

  it("shows the discount row with the coupon code", () => {
    setCtx({
      cart: makeCart({
        coupon: { code: "WELCOME10", description: "10% off", applied: true, message: null },
        totals: { ...makeCart().totals, discount: 68.7 },
      }),
    });
    render(<CartPage />);
    const totals = within(screen.getByRole("complementary", { name: "Order summary" }));
    expect(totals.getByText("Discount (WELCOME10)")).toBeTruthy();
    expect(totals.getByText("-₹68.70")).toBeTruthy();
  });

  it("links to /checkout", () => {
    render(<CartPage />);
    const link = screen.getByRole("link", { name: "Proceed to checkout" });
    expect(link.getAttribute("href")).toBe("/checkout");
    expect(screen.queryByText("Checkout coming soon")).toBeNull();
  });

  it("does not offer checkout while a line has an issue", () => {
    setCtx({ cart: makeCart({ has_issues: true, items: [line({ id: "i1", name: "Poha", issue: "This product is currently out of stock." })] }) });
    render(<CartPage />);
    expect(screen.queryByRole("link", { name: "Proceed to checkout" })).toBeNull();
    expect((screen.getByRole("button", { name: "Fix items to continue" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("/cart page - line actions", () => {
  it("increments and decrements via updateItem with the absolute quantity", () => {
    render(<CartPage />);
    fireEvent.click(screen.getByRole("button", { name: "Increase quantity of Multigrain Cereal" }));
    expect(cartCtx.updateItem).toHaveBeenLastCalledWith("i1", 3);
    fireEvent.click(screen.getByRole("button", { name: "Decrease quantity of Multigrain Cereal" }));
    expect(cartCtx.updateItem).toHaveBeenLastCalledWith("i1", 1);
  });

  it("cannot go below 1 or above available stock", () => {
    setCtx({ cart: makeCart({ items: [line({ id: "i1", name: "Poha", quantity: 1, available_quantity: 1 })], item_count: 1 }) });
    render(<CartPage />);
    expect((screen.getByRole("button", { name: "Decrease quantity of Poha" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Increase quantity of Poha" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("removes a line", () => {
    render(<CartPage />);
    fireEvent.click(screen.getByRole("button", { name: "Remove Poha from cart" }));
    expect(cartCtx.removeItem).toHaveBeenCalledWith("i2");
  });

  it("freezes every control while a request is in flight", () => {
    setCtx({ isMutating: true });
    render(<CartPage />);
    for (const b of screen.getAllByRole("button")) {
      expect((b as HTMLButtonElement).disabled, b.getAttribute("aria-label") ?? b.textContent ?? "").toBe(true);
    }
  });

  it("shows the server message and re-syncs when an update fails", async () => {
    setCtx({ updateItem: vi.fn().mockRejectedValue(new Error("Only 3 units are available in stock.")) });
    render(<CartPage />);
    fireEvent.click(screen.getByRole("button", { name: "Increase quantity of Multigrain Cereal" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Only 3 units are available in stock."));
    expect(cartCtx.refreshCart).toHaveBeenCalledTimes(1);
  });

  it("clears the previous error on the next action", async () => {
    setCtx({ updateItem: vi.fn().mockRejectedValueOnce(new Error("boom")).mockResolvedValue(makeCart()) });
    render(<CartPage />);
    const plus = screen.getByRole("button", { name: "Increase quantity of Multigrain Cereal" });
    fireEvent.click(plus);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("boom"));
    fireEvent.click(plus);
    await waitFor(() => expect(screen.queryByText("boom")).toBeNull());
  });

  it("clear cart needs a confirmation and can be cancelled", () => {
    render(<CartPage />);
    fireEvent.click(screen.getByRole("button", { name: "Clear cart" }));
    expect(cartCtx.clearCart).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(cartCtx.clearCart).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Clear cart" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear cart" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, clear cart" }));
    expect(cartCtx.clearCart).toHaveBeenCalledTimes(1);
  });
});

describe("/cart page - lines with issues", () => {
  const issueCart = () =>
    makeCart({
      has_issues: true,
      items: [
        line({ id: "i1", name: "Ragi Dosa Mix", quantity: 12, available_quantity: 8, line_subtotal: 2100, issue: "Only 8 units available - please reduce the quantity." }),
        line({ id: "i2", name: "Golden Raisins", quantity: 1, available_quantity: 0, issue: "This product is currently out of stock." }),
      ],
      item_count: 13,
    });

  it("shows each issue, the page banner and excludes nothing silently", () => {
    setCtx({ cart: issueCart() });
    render(<CartPage />);
    expect(screen.getByText(/Only 8 units available - please reduce the quantity\./)).toBeTruthy();
    expect(screen.getByText(/This product is currently out of stock\./)).toBeTruthy();
    expect(screen.getAllByText(/Not included in your total/).length).toBe(2);
    expect(screen.getByText(/Some items need your attention/)).toBeTruthy();
  });

  it("offers 'Set quantity to N' only when stock exists but is below the quantity", () => {
    setCtx({ cart: issueCart() });
    render(<CartPage />);
    const buttons = screen.getAllByRole("button", { name: /Set quantity to/ });
    expect(buttons.length).toBe(1);
    fireEvent.click(buttons[0]);
    expect(cartCtx.updateItem).toHaveBeenCalledWith("i1", 8);
  });

  it("does not allow increasing an over-limit line", () => {
    setCtx({ cart: issueCart() });
    render(<CartPage />);
    expect((screen.getByRole("button", { name: "Increase quantity of Ragi Dosa Mix" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Decrease quantity of Ragi Dosa Mix" }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("/cart page - coupons", () => {
  it("applies a trimmed code and clears the box", async () => {
    render(<CartPage />);
    const input = screen.getByLabelText("Have a coupon?") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "  welcome10 " } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(cartCtx.applyCoupon).toHaveBeenCalledWith("welcome10"));
    await waitFor(() => expect(input.value).toBe(""));
  });

  it("does not call the API for an empty code", () => {
    render(<CartPage />);
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(cartCtx.applyCoupon).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toBe("Enter a coupon code.");
  });

  it("shows the server's rejection and keeps the typed code", async () => {
    setCtx({ applyCoupon: vi.fn().mockRejectedValue(new Error("A minimum order of Rs.500 is required to use this coupon.")) });
    render(<CartPage />);
    const input = screen.getByLabelText("Have a coupon?") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "FLAT100" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("minimum order of Rs.500"));
    expect(input.value).toBe("FLAT100");
    expect(input.getAttribute("aria-invalid")).toBe("true");
  });

  it("shows an applied coupon and removes it", () => {
    setCtx({ cart: makeCart({ coupon: { code: "WELCOME10", description: "10% off your order", applied: true, message: null } }) });
    render(<CartPage />);
    expect(screen.getByText("WELCOME10 applied")).toBeTruthy();
    expect(screen.getByText("10% off your order")).toBeTruthy();
    expect(screen.queryByLabelText("Have a coupon?")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Remove coupon WELCOME10" }));
    expect(cartCtx.removeCoupon).toHaveBeenCalledTimes(1);
  });

  it("explains an attached coupon that no longer qualifies", () => {
    setCtx({
      cart: makeCart({ coupon: { code: "FLAT100", description: null, applied: false, message: "A minimum order of Rs.500 is required to use this coupon." } }),
    });
    render(<CartPage />);
    expect(screen.getByText("FLAT100 not applied")).toBeTruthy();
    expect(screen.getByText(/minimum order of Rs.500/)).toBeTruthy();
  });

  it("shows an error if removing the coupon fails", async () => {
    setCtx({
      cart: makeCart({ coupon: { code: "WELCOME10", description: null, applied: true, message: null } }),
      removeCoupon: vi.fn().mockRejectedValue(new Error("nope")),
    });
    render(<CartPage />);
    fireEvent.click(screen.getByRole("button", { name: "Remove coupon WELCOME10" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("nope"));
  });
});
