import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { api, auth } = vi.hoisted(() => ({
  api: { listAdminInventory: vi.fn(), listAdminCategories: vi.fn() },
  auth: { user: { id: "u1" }, isLoading: false },
}));
vi.mock("@/services/admin-inventory", () => ({ listAdminInventory: api.listAdminInventory }));
vi.mock("@/services/admin-catalog", () => ({ listAdminCategories: api.listAdminCategories }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));

import { InventoryList } from "@/components/admin/inventory/InventoryList";
import { category, inventoryItem, pagination } from "./admin-fixtures";

const page = (items = [inventoryItem()], meta = {}) => ({ items, pagination: pagination({ total: items.length, ...meta }) });
const last = () => api.listAdminInventory.mock.calls[api.listAdminInventory.mock.calls.length - 1][0];

beforeEach(() => {
  api.listAdminInventory.mockReset();
  api.listAdminCategories.mockReset();
  api.listAdminInventory.mockResolvedValue(page());
  api.listAdminCategories.mockResolvedValue({ categories: [category(), category({ id: "c2", name: "Seasonal", is_active: false })], pagination: pagination() });
});
afterEach(cleanup);

describe("InventoryList", () => {
  it("shows a skeleton, then stock rows with figures, badge and links", async () => {
    render(<InventoryList />);
    expect(screen.getByRole("status", { name: "Loading stock levels" })).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Stock levels" });
    const row = within(table).getAllByRole("row")[1];
    expect(within(row).getByRole("link", { name: "Muesli" })).toHaveAttribute("href", "/admin/inventory/p1");
    expect(within(row).getByText("MUE-001")).toBeInTheDocument();
    expect(within(row).getByText("Cereals")).toBeInTheDocument();
    expect(within(row).getByText("50")).toBeInTheDocument();
    expect(within(row).getByText("5")).toBeInTheDocument();
    expect(within(row).getByText("45")).toBeInTheDocument();
    expect(within(row).getByText("In stock")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Adjust stock for Muesli" })).toHaveAttribute("href", "/admin/inventory/p1");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("says Low / Out of stock and flags an inactive product in words", async () => {
    api.listAdminInventory.mockResolvedValue(page([
      inventoryItem({ product_id: "a", name: "Low One", stock_status: "low" }),
      inventoryItem({ product_id: "b", name: "Gone", stock_status: "out", quantity: 0, reserved_quantity: 0, available_quantity: 0, is_active: false }),
    ]));
    render(<InventoryList />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Low stock")).toBeInTheDocument();
    expect(within(table).getByText("Out of stock")).toBeInTheDocument();
    expect(within(table).getByText("Inactive")).toBeInTheDocument();
  });

  it("starts unfiltered, name A to Z", async () => {
    render(<InventoryList />);
    await screen.findByRole("table");
    expect(last()).toEqual({ page: 1, page_size: 20, sort: "name", order: "asc" });
  });

  it("opens pre-filtered from a link (?stock=low), least available first", async () => {
    render(<InventoryList initialStock="low" />);
    await screen.findByRole("table");
    expect(last()).toMatchObject({ stock: "low", sort: "available", order: "asc" });
    expect(screen.getByLabelText("Stock")).toHaveValue("low");
  });

  it("sends each filter and the sort to the server and returns to page 1", async () => {
    api.listAdminInventory.mockResolvedValue(page([inventoryItem()], { total: 60, total_pages: 3, has_next: true }));
    render(<InventoryList />);
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    await waitFor(() => expect(last().page).toBe(3));
    await screen.findByRole("option", { name: "Cereals" });
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "c1" } });
    await waitFor(() => expect(last()).toMatchObject({ category_id: "c1", page: 1 }));
    fireEvent.change(screen.getByLabelText("Stock"), { target: { value: "out" } });
    await waitFor(() => expect(last().stock).toBe("out"));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "inactive" } });
    await waitFor(() => expect(last().is_active).toBe(false));
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "quantity-asc" } });
    await waitFor(() => expect(last()).toMatchObject({ sort: "quantity", order: "asc", category_id: "c1", stock: "out", is_active: false, page: 1 }));
  });

  it("search is sent trimmed on submit and goes back to page 1", async () => {
    api.listAdminInventory.mockResolvedValue(page([inventoryItem()], { total: 60, total_pages: 3, has_next: true }));
    render(<InventoryList />);
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "2" }));
    await waitFor(() => expect(last().page).toBe(2));
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "  MUE  " } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(last()).toMatchObject({ search: "MUE", page: 1 }));
  });

  it("error then retry; empty vs. filtered-empty", async () => {
    api.listAdminInventory.mockRejectedValueOnce(new Error("Stock unavailable"));
    render(<InventoryList />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Stock unavailable");
    api.listAdminInventory.mockResolvedValue(page([]));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No products yet")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Stock"), { target: { value: "low" } });
    expect(await screen.findByText("No products match")).toBeInTheDocument();
  });

  it("keeps the old rows (busy) while the next page loads, and warns if a refresh fails", async () => {
    api.listAdminInventory.mockResolvedValueOnce(page([inventoryItem()], { total: 60, total_pages: 3, has_next: true }));
    api.listAdminInventory.mockReturnValueOnce(new Promise(() => {}));
    render(<InventoryList />);
    await screen.findByRole("table");
    expect(screen.getByRole("table").closest("[aria-busy]")).toHaveAttribute("aria-busy", "false");
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByRole("link", { name: "Muesli" })).toBeInTheDocument();
    expect(screen.getByRole("table").closest("[aria-busy]")).toHaveAttribute("aria-busy", "true");
  });

  it("a failed refresh keeps the last list and says so", async () => {
    render(<InventoryList />);
    await screen.findByRole("table");
    api.listAdminInventory.mockRejectedValueOnce(new Error("Flaky network"));
    fireEvent.change(screen.getByLabelText("Stock"), { target: { value: "low" } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/Flaky network.*last result/);
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});
