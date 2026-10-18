import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Address } from "@/types/address";
import type { Cart, CartItem } from "@/types/cart";
import type { Order } from "@/types/order";

const { auth, cartCtx, router, addressApi, orderApi, paymentApi, razorpay } = vi.hoisted(() => ({
  auth: { user: null as null | { id: string }, isLoading: false, isAuthenticated: true },
  cartCtx: {} as Record<string, any>,
  router: { push: vi.fn(), replace: vi.fn() },
  addressApi: { listAddresses: vi.fn(), createAddress: vi.fn() },
  orderApi: { placeOrder: vi.fn(), getOrder: vi.fn() },
  paymentApi: { createPayment: vi.fn(), verifyPayment: vi.fn() },
  razorpay: { loadRazorpayScript: vi.fn(), openRazorpayCheckout: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/context/CartContext", () => ({ useCart: () => cartCtx }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/checkout" }));
vi.mock("@/services/addresses", () => addressApi);
vi.mock("@/services/orders", () => orderApi);
vi.mock("@/services/payments", () => paymentApi);
vi.mock("@/lib/razorpay", () => razorpay);

import CheckoutPage from "@/app/checkout/page";
import { formatMoney } from "@/lib/money";

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
const address = (id: string, over: Partial<Address> = {}): Address => ({
  id, full_name: `Person ${id}`, phone_number: "9876543210", address_line_1: `${id} MG Road`, address_line_2: null,
  city: "Pune", state: "Maharashtra", postal_code: "411001", country: "India", is_default: false, created_at: "2026-10-05T00:00:00Z", ...over,
});
const placedOrder = { id: "order-1", order_number: "PRM-2026-000001" } as Order;

function deferred<T>() {
  let resolve!: (v: T) => void; let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
// What the next refreshCart() "fetches" - lets a test change the server's cart mid-flow.
let cartAfterRefresh: Cart | null = null;
function setCart(over: Record<string, unknown> = {}) {
  cartAfterRefresh = null;
  Object.assign(cartCtx, {
    cart: makeCart(), itemCount: 3, isLoading: false, isMutating: false, loadError: null,
    refreshCart: vi.fn().mockImplementation(async () => {
      if (cartAfterRefresh !== null) cartCtx.cart = cartAfterRefresh;
    }),
    ...over,
  });
}
const placeButton = () => screen.getByRole("button", { name: /^Place order|^Placing your order/ }) as HTMLButtonElement;
async function renderReady(addresses: Address[] = [address("a1", { is_default: true }), address("a2")]) {
  addressApi.listAddresses.mockResolvedValue(addresses);
  render(<CheckoutPage />);
  if (addresses.length > 0) await screen.findAllByRole("radio");
  else await screen.findByRole("form", { name: "Add a delivery address" });
}
function fillForm(values: Record<string, string>) {
  for (const [name, value] of Object.entries(values)) {
    fireEvent.change(document.getElementById(`address-${name}`) as HTMLInputElement, { target: { value } });
  }
}
const goodAddress = {
  full_name: " Asha Rao ", phone_number: "9876543210", address_line_1: "12 MG Road", address_line_2: "",
  city: "Pune", state: "Maharashtra", postal_code: "411001",
};

beforeEach(() => {
  auth.user = { id: "u1" }; auth.isLoading = false; auth.isAuthenticated = true;
  router.push.mockReset(); router.replace.mockReset();
  addressApi.listAddresses.mockReset(); addressApi.createAddress.mockReset(); orderApi.placeOrder.mockReset();
  // By default the payment succeeds end to end (Razorpay popup pays, the backend verifies), so the
  // tests below that are about placing the order still end on the order page. Payment-specific
  // behaviour is covered in checkout-payment.test.tsx.
  paymentApi.createPayment.mockReset(); paymentApi.verifyPayment.mockReset();
  razorpay.loadRazorpayScript.mockReset(); razorpay.openRazorpayCheckout.mockReset();
  razorpay.loadRazorpayScript.mockResolvedValue(undefined);
  paymentApi.createPayment.mockResolvedValue({
    order_id: "order-1", order_number: "PRM-2026-000001", razorpay_order_id: "order_X1",
    razorpay_key_id: "rzp_test_FAKE", amount_paise: 72135, currency: "INR",
  });
  razorpay.openRazorpayCheckout.mockImplementation((_req: unknown, cb: any) =>
    queueMicrotask(() => cb.onSuccess({ razorpay_order_id: "order_X1", razorpay_payment_id: "pay_1", razorpay_signature: "sig" })));
  paymentApi.verifyPayment.mockResolvedValue({ id: "order-1", payment_status: "paid" });
  setCart();
});
afterEach(cleanup);

describe("/checkout - access and states", () => {
  it("renders nothing and redirects to login when logged out", () => {
    auth.user = null; auth.isAuthenticated = false;
    const { container } = render(<CheckoutPage />);
    expect(container.innerHTML).toBe("");
    expect(router.push).toHaveBeenCalledWith("/login?redirect=%2Fcheckout");
    expect(addressApi.listAddresses).not.toHaveBeenCalled();
  });

  it("shows a skeleton while the cart loads - no form, no redirect", () => {
    setCart({ cart: null, isLoading: true });
    addressApi.listAddresses.mockResolvedValue([]);
    render(<CheckoutPage />);
    expect(screen.getByRole("status", { name: "Loading your cart" })).toBeTruthy();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("offers a retry when the cart could not be loaded", () => {
    setCart({ cart: null, loadError: "We couldn't load your cart." });
    addressApi.listAddresses.mockResolvedValue([]);
    render(<CheckoutPage />);
    expect(screen.getByRole("alert").textContent).toContain("We couldn't load your cart.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(cartCtx.refreshCart).toHaveBeenCalled();
  });

  it("sends an empty cart back to /cart", async () => {
    setCart({ cart: makeCart({ items: [], item_count: 0 }) });
    addressApi.listAddresses.mockResolvedValue([address("a1")]);
    render(<CheckoutPage />);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/cart"));
    expect(screen.queryByRole("button", { name: /Place order/ })).toBeNull();
  });

  it("shows a loading state for addresses, then the list", async () => {
    const pending = deferred<Address[]>();
    addressApi.listAddresses.mockReturnValue(pending.promise);
    render(<CheckoutPage />);
    expect(screen.getByRole("status", { name: "Loading your addresses" })).toBeTruthy();
    expect(placeButton().disabled).toBe(true);
    pending.resolve([address("a1", { is_default: true })]);
    expect(await screen.findByRole("radio")).toBeTruthy();
  });

  it("shows an error with retry when addresses fail to load", async () => {
    addressApi.listAddresses.mockRejectedValueOnce(new Error("Address service is down"));
    render(<CheckoutPage />);
    expect((await screen.findByText("Address service is down"))).toBeTruthy();
    addressApi.listAddresses.mockResolvedValue([address("a1")]);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("radio")).toBeTruthy();
  });
});

describe("/checkout - address choice", () => {
  it("preselects the default address and shows the server total on the button", async () => {
    await renderReady([address("a1"), address("a2", { is_default: true })]);
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.find((r) => r.checked)?.value).toBe("a2");
    expect(placeButton().textContent).toContain(formatMoney(721.35));
    expect(placeButton().disabled).toBe(false);
  });

  it("preselects the first address when none is the default", async () => {
    await renderReady([address("a1"), address("a2")]);
    expect((screen.getAllByRole("radio") as HTMLInputElement[]).find((r) => r.checked)?.value).toBe("a1");
  });

  it("lets the customer pick another address, and orders to THAT one", async () => {
    orderApi.placeOrder.mockResolvedValue({ order: placedOrder, created: true });
    await renderReady([address("a1", { is_default: true }), address("a2")]);
    fireEvent.click(screen.getByRole("radio", { name: /Person a2/ }));
    fireEvent.click(placeButton());
    await waitFor(() => expect(orderApi.placeOrder).toHaveBeenCalled());
    expect(orderApi.placeOrder.mock.calls[0][0].shipping_address_id).toBe("a2");
  });

  it("opens the add form automatically when there are no addresses, and blocks ordering", async () => {
    await renderReady([]);
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
    expect(placeButton().disabled).toBe(true);
    expect(screen.getByText(/Choose or add a delivery address/)).toBeTruthy();
    expect(screen.queryByRole("checkbox", { name: /default/i })).toBeNull(); // the first address is always the default
    expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
  });
});

describe("/checkout - adding an address", () => {
  it("validates on the client and sends nothing when the form is wrong", async () => {
    await renderReady([]);
    fillForm({ ...goodAddress, postal_code: "12", phone_number: "abc", city: "  " });
    fireEvent.click(screen.getByRole("button", { name: "Save address" }));
    expect(await screen.findByText("Enter a valid 6-digit PIN code.")).toBeTruthy();
    expect(screen.getByText("Use digits only, optionally starting with +.")).toBeTruthy();
    expect(screen.getByText("Enter the city.")).toBeTruthy();
    expect(addressApi.createAddress).not.toHaveBeenCalled();
  });

  it("saves a valid address (trimmed), reloads the list, and selects the new address", async () => {
    await renderReady([]);
    addressApi.createAddress.mockResolvedValue(address("new1", { is_default: true, full_name: "Asha Rao" }));
    addressApi.listAddresses.mockResolvedValue([address("new1", { is_default: true, full_name: "Asha Rao" })]);

    fillForm(goodAddress);
    fireEvent.click(screen.getByRole("button", { name: "Save address" }));

    await waitFor(() => expect(screen.getAllByRole("radio")).toHaveLength(1));
    expect(addressApi.createAddress).toHaveBeenCalledWith({
      full_name: "Asha Rao", phone_number: "9876543210", address_line_1: "12 MG Road", address_line_2: null,
      city: "Pune", state: "Maharashtra", postal_code: "411001", is_default: false,
    });
    expect((screen.getByRole("radio") as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByRole("form", { name: "Add a delivery address" })).toBeNull();
    expect(placeButton().disabled).toBe(false);
  });

  it("shows the server's message in the form and keeps what was typed", async () => {
    await renderReady([]);
    addressApi.createAddress.mockRejectedValue(new Error("We don't deliver there yet."));
    fillForm(goodAddress);
    fireEvent.click(screen.getByRole("button", { name: "Save address" }));
    expect(await screen.findByText("We don't deliver there yet.")).toBeTruthy();
    expect((document.getElementById("address-city") as HTMLInputElement).value).toBe("Pune");
    expect((screen.getByRole("button", { name: "Save address" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("with existing addresses the form is opt-in, cancellable, and can set the default", async () => {
    await renderReady();
    expect(screen.queryByRole("form", { name: "Add a delivery address" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Add a new address/ }));
    expect(screen.getByRole("form", { name: "Add a delivery address" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form", { name: "Add a delivery address" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Add a new address/ }));
    addressApi.createAddress.mockResolvedValue(address("a3", { is_default: true }));
    addressApi.listAddresses.mockResolvedValue([address("a3", { is_default: true }), address("a1"), address("a2")]);
    fillForm(goodAddress);
    fireEvent.click(screen.getByRole("checkbox", { name: /default address/i }));
    fireEvent.click(screen.getByRole("button", { name: "Save address" }));

    await waitFor(() => expect(screen.getAllByRole("radio")).toHaveLength(3));
    expect(addressApi.createAddress.mock.calls[0][0].is_default).toBe(true);
    expect((screen.getAllByRole("radio") as HTMLInputElement[]).find((r) => r.checked)?.value).toBe("a3");
  });
});

describe("/checkout - placing the order", () => {
  it("sends the address, the DISPLAYED total and an idempotency key - never prices or items", async () => {
    orderApi.placeOrder.mockResolvedValue({ order: placedOrder, created: true });
    await renderReady();
    fireEvent.click(placeButton());

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/orders/order-1"));
    const [input, key] = orderApi.placeOrder.mock.calls[0];
    expect(input).toEqual({ shipping_address_id: "a1", expected_total: 721.35 });
    expect(key).toMatch(/^chk-/);
    expect(cartCtx.refreshCart).toHaveBeenCalled();
  });

  it("shows 'Order placed' and does NOT bounce to /cart when the server has just emptied the cart", async () => {
    orderApi.placeOrder.mockResolvedValue({ order: placedOrder, created: true });
    await renderReady();
    cartAfterRefresh = makeCart({ items: [], item_count: 0 }); // what the refresh after a successful order returns
    fireEvent.click(placeButton());

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/orders/order-1"));
    expect(screen.getByText("Order placed")).toBeTruthy();
    expect(cartCtx.cart.items).toHaveLength(0);
    expect(router.replace).not.toHaveBeenCalledWith("/cart");
  });

  it("disables the button and sends ONE request however often it is clicked", async () => {
    const pending = deferred<{ order: Order; created: boolean }>();
    orderApi.placeOrder.mockReturnValue(pending.promise);
    await renderReady();

    const button = placeButton();
    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);

    expect(orderApi.placeOrder).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(placeButton().textContent).toBe("Placing your order..."));
    expect(placeButton().disabled).toBe(true);
    // the address cannot be changed mid-request either
    expect(screen.getAllByRole("radio")[1].matches(":disabled")).toBe(true);

    pending.resolve({ order: placedOrder, created: true });
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/orders/order-1"));
    expect(orderApi.placeOrder).toHaveBeenCalledTimes(1);
  });

  it("shows the server's message when the order is refused, and lets the customer try again", async () => {
    orderApi.placeOrder.mockRejectedValueOnce(new Error("Only 1 unit is available in stock."));
    await renderReady();
    fireEvent.click(placeButton());

    expect(await screen.findByText(/Only 1 unit is available in stock\./)).toBeTruthy();
    expect(router.replace).not.toHaveBeenCalled(); // stays on the page: no redirect anywhere
    expect(placeButton().disabled).toBe(false);
    expect(cartCtx.refreshCart).toHaveBeenCalled(); // so the page shows what the server now sees
  });

  it("explains a changed total and uses a NEW key for the new total, but the SAME key for an identical retry", async () => {
    orderApi.placeOrder
      .mockRejectedValueOnce(new Error("Prices in your cart have changed."))
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockRejectedValueOnce(new Error("Network Error"));
    await renderReady();

    // The refresh after the failure brings a new total.
    cartAfterRefresh = makeCart({ totals: { ...makeCart().totals, total: 800 } });
    fireEvent.click(placeButton());
    expect(await screen.findByText(/Your total is now/)).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain(formatMoney(800));

    // Second attempt: new total -> new key.
    fireEvent.click(placeButton());
    await waitFor(() => expect(orderApi.placeOrder).toHaveBeenCalledTimes(2));
    expect(orderApi.placeOrder.mock.calls[1][0].expected_total).toBe(800);
    expect(orderApi.placeOrder.mock.calls[1][1]).not.toBe(orderApi.placeOrder.mock.calls[0][1]);

    // Third attempt: nothing changed -> the SAME key as the second.
    await waitFor(() => expect(placeButton().disabled).toBe(false));
    fireEvent.click(placeButton());
    await waitFor(() => expect(orderApi.placeOrder).toHaveBeenCalledTimes(3));
    expect(orderApi.placeOrder.mock.calls[2][1]).toBe(orderApi.placeOrder.mock.calls[1][1]);
  });

  it("never claims the order is paid before any payment has happened", async () => {
    await renderReady();
    expect(screen.getByText(/pay securely with Razorpay/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/\bpaid\b|payment (successful|received|complete)/i);
  });
});

describe("/checkout - cart problems", () => {
  it("blocks ordering while a line has an issue and points back to the cart", async () => {
    setCart({ cart: makeCart({ has_issues: true, items: [line({ id: "i1", name: "Poha", issue: "This product is currently out of stock." })] }) });
    await renderReady();
    expect(placeButton().disabled).toBe(true);
    expect(screen.getByText("This product is currently out of stock.")).toBeTruthy();
    expect(screen.getAllByRole("link", { name: "Review your cart" }).length).toBeGreaterThan(0);
    fireEvent.click(placeButton());
    expect(orderApi.placeOrder).not.toHaveBeenCalled();
  });
});

describe("/checkout - summary", () => {
  it("lists the items and shows the server's totals unchanged", async () => {
    setCart({
      cart: makeCart({
        coupon: { code: "WELCOME10", description: null, applied: true, message: null },
        totals: { ...makeCart().totals, discount: 68.7, total: 652.65 },
      }),
    });
    await renderReady();
    const items = within(screen.getByRole("region", { name: "Review items" }));
    expect(items.getByText("Multigrain Cereal")).toBeTruthy();
    expect(items.getByText(`2 x ${formatMoney(249)}`)).toBeTruthy();
    const totals = within(screen.getByRole("complementary", { name: "Order summary" }));
    expect(totals.getByText("Discount (WELCOME10)")).toBeTruthy();
    expect(totals.getByText("-₹68.70")).toBeTruthy();
    expect(totals.getAllByText("₹652.65").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Edit cart" }).getAttribute("href")).toBe("/cart");
  });
});
