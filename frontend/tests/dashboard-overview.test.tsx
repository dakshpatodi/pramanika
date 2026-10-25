import { act, cleanup, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { OrderList, OrderSummary } from "@/types/order";

const { auth, router, api } = vi.hoisted(() => ({
  auth: { user: null as null | { id: string; first_name: string }, isLoading: false, isAuthenticated: true },
  router: { push: vi.fn() },
  api: { listOrders: vi.fn(), listWishlist: vi.fn(), listAddresses: vi.fn(), listInvoices: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/dashboard" }));
vi.mock("@/services/orders", () => ({ listOrders: api.listOrders }));
vi.mock("@/services/wishlist", () => ({ listWishlist: api.listWishlist }));
vi.mock("@/services/addresses", () => ({ listAddresses: api.listAddresses }));
vi.mock("@/services/invoices", () => ({ listInvoices: api.listInvoices }));

import DashboardPage from "@/app/dashboard/page";
import { useDashboardOverview } from "@/hooks/useDashboardOverview";

const pagination = (total: number) => ({ total, page: 1, page_size: 3, total_pages: total ? 1 : 0, has_next: false, has_previous: false });
function order(n: number, over: Partial<OrderSummary> = {}): OrderSummary {
  return {
    id: `order-${n}`, order_number: `PRM-2026-00000${n}`, status: "confirmed", payment_status: "paid", can_pay: false, expires_at: null,
    cancellation_reason: null, total: 100 * n, item_count: 1, line_count: 1, item_names: ["Oats"], created_at: "2026-10-05T10:30:00Z", ...over,
  };
}
const orderList = (orders: OrderSummary[], total = orders.length): OrderList => ({ orders, pagination: pagination(total) });
function deferred<T>() {
  let resolve!: (v: T) => void; let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
function happy() {
  api.listOrders.mockResolvedValue(orderList([order(3), order(2), order(1)], 7));
  api.listWishlist.mockResolvedValue({ items: [], pagination: pagination(4) });
  api.listAddresses.mockResolvedValue([{ id: "a1" }, { id: "a2" }]);
  api.listInvoices.mockResolvedValue({ invoices: [], pagination: pagination(5) });
}
const tile = (label: string) => screen.getByRole("group", { name: label });

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  router.push.mockReset();
  auth.user = { id: "u1", first_name: "Asha" };
  auth.isLoading = false;
  auth.isAuthenticated = true;
});
afterEach(cleanup);

describe("Dashboard overview page", () => {
  it("greets the user and shows the real counts from the APIs", async () => {
    happy();
    render(<DashboardPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Overview");
    expect(screen.getByText("Welcome back, Asha.")).toBeInTheDocument();
    await waitFor(() => expect(within(tile("Orders")).getByText("7")).toBeInTheDocument());
    expect(within(tile("Wishlist")).getByText("4")).toBeInTheDocument();
    expect(within(tile("Saved addresses")).getByText("2")).toBeInTheDocument();
    expect(within(tile("Invoices")).getByText("5")).toBeInTheDocument();
  });

  it("links the tiles to their pages but never a tile that failed to load", async () => {
    happy();
    api.listInvoices.mockRejectedValue({});
    render(<DashboardPage />);
    await waitFor(() => expect(within(tile("Saved addresses")).getByText("2")).toBeInTheDocument());
    await waitFor(() => expect(within(tile("Wishlist")).getByText("4")).toBeInTheDocument());
    expect(within(tile("Orders")).getByRole("link")).toHaveAttribute("href", "/orders");
    expect(within(tile("Saved addresses")).getByRole("link")).toHaveAttribute("href", "/dashboard/addresses");
    expect(within(tile("Wishlist")).getByRole("link")).toHaveAttribute("href", "/dashboard/wishlist");
    await waitFor(() => expect(within(tile("Invoices")).getByRole("alert")).toBeInTheDocument());
    expect(within(tile("Invoices")).queryByRole("link")).toBeNull();
  });

  it("links the Invoices tile to its page once it has loaded", async () => {
    happy();
    render(<DashboardPage />);
    await waitFor(() => expect(within(tile("Invoices")).getByText("5")).toBeInTheDocument());
    expect(within(tile("Invoices")).getByRole("link")).toHaveAttribute("href", "/dashboard/invoices");
  });

  it("asks each API for only what it needs", async () => {
    happy();
    render(<DashboardPage />);
    await screen.findByText("PRM-2026-000003");
    expect(api.listOrders).toHaveBeenCalledWith(1, 3);
    expect(api.listWishlist).toHaveBeenCalledWith(1, 1);
    expect(api.listInvoices).toHaveBeenCalledWith(1, 1);
    expect(api.listAddresses).toHaveBeenCalledTimes(1);
  });

  it("lists the recent orders as links to their detail pages, with status and total", async () => {
    happy();
    render(<DashboardPage />);
    const link = (await screen.findByText("PRM-2026-000003")).closest("a")!;
    expect(link).toHaveAttribute("href", "/orders/order-3");
    expect(within(link).getByText("₹300.00")).toBeInTheDocument();
    expect(within(link).getByText("Paid")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /PRM-2026/ })).toHaveLength(3);
    expect(screen.getByRole("link", { name: "View all" })).toHaveAttribute("href", "/orders");
  });

  it("shows loading placeholders first", () => {
    api.listOrders.mockReturnValue(new Promise(() => {}));
    api.listWishlist.mockReturnValue(new Promise(() => {}));
    api.listAddresses.mockReturnValue(new Promise(() => {}));
    api.listInvoices.mockReturnValue(new Promise(() => {}));
    render(<DashboardPage />);
    expect(screen.getByRole("status", { name: "Loading recent orders" })).toBeInTheDocument();
    for (const label of ["Orders", "Wishlist", "Saved addresses", "Invoices"]) {
      expect(screen.getByRole("status", { name: `Loading ${label}` })).toBeInTheDocument();
    }
  });

  it("shows an empty state for a user with no orders, and zeros elsewhere", async () => {
    api.listOrders.mockResolvedValue(orderList([]));
    api.listWishlist.mockResolvedValue({ items: [], pagination: pagination(0) });
    api.listAddresses.mockResolvedValue([]);
    api.listInvoices.mockResolvedValue({ invoices: [], pagination: pagination(0) });
    render(<DashboardPage />);
    expect(await screen.findByText("No orders yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start shopping" })).toHaveAttribute("href", "/shop");
    expect(within(tile("Wishlist")).getByText("0")).toBeInTheDocument();
  });

  it("one failing section does not blank the others, and retry reloads only that section", async () => {
    const user = userEvent.setup();
    happy();
    api.listWishlist.mockRejectedValue(Object.assign(new Error("x"), { isAxiosError: true, response: { data: { success: false, message: "Wishlist is down." } } }));
    render(<DashboardPage />);

    await waitFor(() => expect(within(tile("Orders")).getByText("7")).toBeInTheDocument());
    expect(within(tile("Saved addresses")).getByText("2")).toBeInTheDocument();
    expect(within(tile("Wishlist")).getByRole("alert")).toHaveTextContent("Couldn't load");

    api.listWishlist.mockResolvedValue({ items: [], pagination: pagination(9) });
    await user.click(screen.getByRole("button", { name: "Retry Wishlist" }));
    await waitFor(() => expect(within(tile("Wishlist")).getByText("9")).toBeInTheDocument());
    expect(api.listWishlist).toHaveBeenCalledTimes(2);
    expect(api.listOrders).toHaveBeenCalledTimes(1);
    expect(api.listAddresses).toHaveBeenCalledTimes(1);
    expect(api.listInvoices).toHaveBeenCalledTimes(1);
  });

  it("shows the server's message and a retry when the orders fail", async () => {
    const user = userEvent.setup();
    happy();
    api.listOrders.mockRejectedValue(Object.assign(new Error("x"), { isAxiosError: true, response: { data: { success: false, message: "Orders are unavailable." } } }));
    render(<DashboardPage />);
    expect(await screen.findByText("Orders are unavailable.")).toBeInTheDocument();
    expect(within(tile("Orders")).getByRole("alert")).toBeInTheDocument();

    api.listOrders.mockResolvedValue(orderList([order(1)], 1));
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("PRM-2026-000001")).toBeInTheDocument();
  });

  it("never reaches the APIs for a visitor who is not signed in", () => {
    auth.user = null;
    auth.isAuthenticated = false;
    const { container } = render(<DashboardPage />);
    expect(container).toBeEmptyDOMElement();
    expect(router.push).toHaveBeenCalledWith("/login?redirect=%2Fdashboard");
    for (const fn of Object.values(api)) expect(fn).not.toHaveBeenCalled();
  });
});

describe("useDashboardOverview", () => {
  it("does nothing until the session is restored", () => {
    auth.isLoading = true;
    renderHook(() => useDashboardOverview());
    for (const fn of Object.values(api)) expect(fn).not.toHaveBeenCalled();
  });

  it("ignores a response that arrives after the user changed", async () => {
    const slow = deferred<OrderList>();
    happy();
    api.listOrders.mockReturnValueOnce(slow.promise);
    const { result, rerender } = renderHook(() => useDashboardOverview());
    await waitFor(() => expect(result.current.wishlist.status).toBe("ready"));

    auth.user = { id: "u2", first_name: "Other" };
    api.listOrders.mockResolvedValue(orderList([order(9)], 1));
    rerender();
    await waitFor(() => expect(result.current.orders.status).toBe("ready"));

    await act(async () => { slow.resolve(orderList([order(1)], 99)); });
    const orders = result.current.orders;
    expect(orders.status === "ready" && orders.data.pagination.total).toBe(1); // not the stale 99
  });

  it("ignores an older response for the same block when a retry is already in flight", async () => {
    happy();
    const first = deferred<OrderList>();
    api.listOrders.mockReturnValueOnce(first.promise);
    const { result } = renderHook(() => useDashboardOverview());
    await waitFor(() => expect(result.current.wishlist.status).toBe("ready"));

    api.listOrders.mockResolvedValue(orderList([order(2)], 2));
    act(() => result.current.retry("orders"));
    await waitFor(() => expect(result.current.orders.status).toBe("ready"));

    await act(async () => { first.resolve(orderList([order(1)], 50)); });
    const orders = result.current.orders;
    expect(orders.status === "ready" && orders.data.pagination.total).toBe(2);
  });

  it("forgets the previous user's numbers when the user logs out", async () => {
    happy();
    const { result, rerender } = renderHook(() => useDashboardOverview());
    await waitFor(() => expect(result.current.invoices.status).toBe("ready"));
    auth.user = null;
    rerender();
    expect(result.current.invoices.status).toBe("loading");
    expect(result.current.orders.status).toBe("loading");
  });
});
