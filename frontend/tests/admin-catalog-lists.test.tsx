import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { api, auth } = vi.hoisted(() => ({
  api: {
    listAdminCategories: vi.fn(), listAdminProducts: vi.fn(),
    setAdminCategoryActive: vi.fn(), setAdminProductActive: vi.fn(),
  },
  auth: { user: { id: "u1" }, isLoading: false },
}));
vi.mock("@/services/admin-catalog", () => api);
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));

import { CategoriesList } from "@/components/admin/catalog/CategoriesList";
import { ProductsList } from "@/components/admin/catalog/ProductsList";
import { category, pagination, product } from "./admin-fixtures";

const categoryPage = (categories = [category()], meta = {}) => ({ categories, pagination: pagination({ total: categories.length, ...meta }) });
const productPage = (products = [product()], meta = {}) => ({ products, pagination: pagination({ total: products.length, ...meta }) });
const lastParams = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls[fn.mock.calls.length - 1][0];

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.listAdminCategories.mockResolvedValue(categoryPage());
  api.listAdminProducts.mockResolvedValue(productPage());
});
afterEach(cleanup);

describe("CategoriesList", () => {
  it("shows a skeleton, then the categories with counts, status and links", async () => {
    render(<CategoriesList />);
    expect(screen.getByRole("status", { name: "Loading categories" })).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Categories" });
    const row = within(table).getAllByRole("row")[1];
    expect(within(row).getByRole("link", { name: "Cereals" })).toHaveAttribute("href", "/admin/categories/c1");
    expect(within(row).getByText("cereals")).toBeInTheDocument();
    expect(within(row).getByText(/4 active/)).toBeInTheDocument();
    expect(within(row).getByText("/ 5")).toBeInTheDocument();
    expect(within(row).getByText("Active")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Edit Cereals" })).toHaveAttribute("href", "/admin/categories/c1");
    expect(screen.getByRole("link", { name: /New category/ })).toHaveAttribute("href", "/admin/categories/new");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("asks for the first page, newest-name-first defaults, with no filters", async () => {
    render(<CategoriesList />);
    await screen.findByRole("table");
    expect(lastParams(api.listAdminCategories)).toEqual({ page: 1, page_size: 20, sort: "name", order: "asc" });
  });

  it("an error with nothing loaded offers Try again, which recovers", async () => {
    api.listAdminCategories.mockRejectedValueOnce(new Error("Server down"));
    render(<CategoriesList />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server down");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("empty shop vs. empty filter result are different messages", async () => {
    api.listAdminCategories.mockResolvedValue(categoryPage([]));
    render(<CategoriesList />);
    expect(await screen.findByText("No categories yet")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /New category/ }).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "zzz" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("No categories match")).toBeInTheDocument();
  });

  it("search is sent trimmed on submit and goes back to page 1", async () => {
    api.listAdminCategories.mockResolvedValue(categoryPage([category()], { total: 40, total_pages: 2, has_next: true }));
    render(<CategoriesList />);
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "2" }));
    await waitFor(() => expect(lastParams(api.listAdminCategories).page).toBe(2));
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "  oat  " } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(lastParams(api.listAdminCategories)).toMatchObject({ search: "oat", page: 1 }));
  });

  it("the status filter sends is_active true / false, and drops it for All", async () => {
    render(<CategoriesList />);
    await screen.findByRole("table");
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "inactive" } });
    await waitFor(() => expect(lastParams(api.listAdminCategories).is_active).toBe(false));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "active" } });
    await waitFor(() => expect(lastParams(api.listAdminCategories).is_active).toBe(true));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "all" } });
    await waitFor(() => expect("is_active" in lastParams(api.listAdminCategories) && lastParams(api.listAdminCategories).is_active !== undefined).toBe(false));
  });

  it("sorting maps to sort and order", async () => {
    render(<CategoriesList />);
    await screen.findByRole("table");
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "product_count-desc" } });
    await waitFor(() => expect(lastParams(api.listAdminCategories)).toMatchObject({ sort: "product_count", order: "desc" }));
  });

  it("paging asks for the chosen page and keeps the old rows visible while loading", async () => {
    api.listAdminCategories.mockResolvedValueOnce(categoryPage([category()], { total: 40, total_pages: 2, has_next: true }));
    let finish!: (v: unknown) => void;
    api.listAdminCategories.mockReturnValueOnce(new Promise((r) => (finish = r)));
    render(<CategoriesList />);
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByRole("link", { name: "Cereals" })).toBeInTheDocument();          // still there
    expect(screen.getByRole("table").closest("[aria-busy]")).toHaveAttribute("aria-busy", "true");
    finish(categoryPage([category({ id: "c2", name: "Snacks" })], { page: 2, total: 40, total_pages: 2, has_previous: true }));
    expect(await screen.findByRole("link", { name: "Snacks" })).toBeInTheDocument();
    expect(lastParams(api.listAdminCategories).page).toBe(2);
  });

  it("deactivating asks first, then reloads the list", async () => {
    api.setAdminCategoryActive.mockResolvedValue({});
    render(<CategoriesList />);
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Cereals" }));
    expect(api.setAdminCategoryActive).not.toHaveBeenCalled();
    const calls = api.listAdminCategories.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    await waitFor(() => expect(api.listAdminCategories.mock.calls.length).toBe(calls + 1));
    expect(api.setAdminCategoryActive).toHaveBeenCalledWith("c1", false);
  });

  it("a failed refresh keeps the last list and says so", async () => {
    render(<CategoriesList />);
    await screen.findByRole("table");
    api.listAdminCategories.mockRejectedValueOnce(new Error("Flaky network"));
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "active" } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/Flaky network.*last result/);
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});

describe("ProductsList", () => {
  beforeEach(() => {
    api.listAdminCategories.mockResolvedValue(categoryPage([category({ id: "c1", name: "Cereals" }), category({ id: "c2", name: "Seasonal", is_active: false })]));
  });

  it("shows products with SKU, category, price, was-price, stock and status", async () => {
    render(<ProductsList />);
    expect(screen.getByRole("status", { name: "Loading products" })).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Products" });
    const row = within(table).getAllByRole("row")[1];
    expect(within(row).getByRole("link", { name: "Muesli" })).toHaveAttribute("href", "/admin/products/p1");
    expect(within(row).getByText("MUE-001")).toBeInTheDocument();
    expect(within(row).getByText("Cereals")).toBeInTheDocument();
    expect(within(row).getByText("₹249.00")).toBeInTheDocument();
    expect(within(row).getByText("₹299.00")).toBeInTheDocument();
    expect(within(row).getByText("In stock")).toBeInTheDocument();
    expect(within(row).getByText("45 available")).toBeInTheDocument();
    expect(within(row).getByText("Active")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /New product/ })).toHaveAttribute("href", "/admin/products/new");
  });

  it("shows low / out of stock, inactive products and a hidden category in words", async () => {
    api.listAdminProducts.mockResolvedValue(productPage([
      product({ id: "a", name: "Low One", stock_status: "low", available_quantity: 3, compare_at_price: null }),
      product({ id: "b", name: "Gone", stock_status: "out", available_quantity: 0, is_active: false, category: { id: "c2", name: "Seasonal", slug: "s", is_active: false } }),
    ]));
    render(<ProductsList />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Low stock")).toBeInTheDocument();
    expect(within(table).getByText("Out of stock")).toBeInTheDocument();
    expect(within(table).getByText("Inactive")).toBeInTheDocument();
    expect(within(table).getByText("category inactive")).toBeInTheDocument();
  });

  it("starts unfiltered and sends each filter to the server", async () => {
    render(<ProductsList />);
    await screen.findByRole("table");
    expect(lastParams(api.listAdminProducts)).toEqual({ page: 1, page_size: 20, sort: "created_at", order: "desc" });
    await screen.findByRole("option", { name: "Cereals" });
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "c1" } });
    await waitFor(() => expect(lastParams(api.listAdminProducts).category_id).toBe("c1"));
    fireEvent.change(screen.getByLabelText("Stock"), { target: { value: "low" } });
    await waitFor(() => expect(lastParams(api.listAdminProducts).stock).toBe("low"));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "inactive" } });
    await waitFor(() => expect(lastParams(api.listAdminProducts).is_active).toBe(false));
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "price-asc" } });
    await waitFor(() => expect(lastParams(api.listAdminProducts)).toMatchObject({ sort: "price", order: "asc", category_id: "c1", stock: "low", is_active: false }));
  });

  it("the category filter lists hidden categories too, marked", async () => {
    render(<ProductsList />);
    expect(await screen.findByRole("option", { name: "Seasonal (inactive)" })).toBeInTheDocument();
    expect(api.listAdminCategories).toHaveBeenCalledWith({ page_size: 100, sort: "name", order: "asc" });
  });

  it("changing a filter returns to page 1", async () => {
    api.listAdminProducts.mockResolvedValue(productPage([product()], { total: 60, total_pages: 3, has_next: true }));
    render(<ProductsList />);
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    await waitFor(() => expect(lastParams(api.listAdminProducts).page).toBe(3));
    fireEvent.change(screen.getByLabelText("Stock"), { target: { value: "out" } });
    await waitFor(() => expect(lastParams(api.listAdminProducts)).toMatchObject({ page: 1, stock: "out" }));
  });

  it("a new search goes back to page 1", async () => {
    api.listAdminProducts.mockResolvedValue(productPage([product()], { total: 60, total_pages: 3, has_next: true }));
    render(<ProductsList />);
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    await waitFor(() => expect(lastParams(api.listAdminProducts).page).toBe(3));
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "oat" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(lastParams(api.listAdminProducts)).toMatchObject({ search: "oat", page: 1 }));
  });

  it("marks the table busy while another page loads", async () => {
    api.listAdminProducts.mockResolvedValueOnce(productPage([product()], { total: 60, total_pages: 3, has_next: true }));
    api.listAdminProducts.mockReturnValueOnce(new Promise(() => {}));
    render(<ProductsList />);
    await screen.findByRole("table");
    expect(screen.getByRole("table").closest("[aria-busy]")).toHaveAttribute("aria-busy", "false");
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByRole("table").closest("[aria-busy]")).toHaveAttribute("aria-busy", "true");
  });

  it("search is sent on submit", async () => {
    render(<ProductsList />);
    await screen.findByRole("table");
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: " MUE-0 " } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(lastParams(api.listAdminProducts).search).toBe("MUE-0"));
  });

  it("error with retry; empty catalogue; empty filter result", async () => {
    api.listAdminProducts.mockRejectedValueOnce(new Error("Products unavailable"));
    render(<ProductsList />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Products unavailable");
    api.listAdminProducts.mockResolvedValue(productPage([]));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No products yet")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Stock"), { target: { value: "low" } });
    expect(await screen.findByText("No products match")).toBeInTheDocument();
  });

  it("deactivating a product asks first, then reloads", async () => {
    api.setAdminProductActive.mockResolvedValue({});
    render(<ProductsList />);
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Muesli" }));
    const calls = api.listAdminProducts.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    await waitFor(() => expect(api.listAdminProducts.mock.calls.length).toBe(calls + 1));
    expect(api.setAdminProductActive).toHaveBeenCalledWith("p1", false);
  });
});
