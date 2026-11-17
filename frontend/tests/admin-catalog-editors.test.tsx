import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { api, auth } = vi.hoisted(() => ({
  api: {
    getAdminCategory: vi.fn(), getAdminProduct: vi.fn(), updateAdminCategory: vi.fn(), updateAdminProduct: vi.fn(),
    listAdminCategories: vi.fn(), setAdminCategoryActive: vi.fn(), setAdminProductActive: vi.fn(),
  },
  auth: { user: { id: "u1" }, isLoading: false },
}));
vi.mock("@/services/admin-catalog", () => api);
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));

import { CategoryEditor } from "@/components/admin/catalog/CategoryEditor";
import { ProductEditor } from "@/components/admin/catalog/ProductEditor";
import { category, pagination, productDetail } from "./admin-fixtures";

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.listAdminCategories.mockResolvedValue({ categories: [category()], pagination: pagination() });
});
afterEach(cleanup);

describe("CategoryEditor", () => {
  it("loads the category by id, then shows its header and form", async () => {
    api.getAdminCategory.mockResolvedValue(category({ name: "Cereals", product_count: 5, active_product_count: 4 }));
    render(<CategoryEditor id="c1" />);
    expect(screen.getByRole("status", { name: "Loading the category" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1, name: "Cereals" })).toBeInTheDocument();
    expect(api.getAdminCategory).toHaveBeenCalledWith("c1");
    expect(screen.getByText("4 active of 5 products")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Name/)).toHaveValue("Cereals");
    expect(screen.getByRole("button", { name: "Deactivate Cereals" })).toBeInTheDocument();
  });

  it("shows the server's message with a retry when it cannot be loaded (e.g. not found)", async () => {
    api.getAdminCategory.mockRejectedValueOnce(new Error("Category not found."));
    render(<CategoryEditor id="nope" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Category not found.");
    expect(screen.queryByLabelText(/^Name/)).toBeNull();
    api.getAdminCategory.mockResolvedValue(category());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByLabelText(/^Name/)).toBeInTheDocument();
  });

  it("after a save the heading shows the new name", async () => {
    api.getAdminCategory.mockResolvedValue(category());
    api.updateAdminCategory.mockResolvedValue(category({ name: "Grains" }));
    render(<CategoryEditor id="c1" />);
    await screen.findByRole("heading", { level: 1, name: "Cereals" });
    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: "Grains" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Grains" })).toBeInTheDocument();
  });

  it("deactivating reloads the category and flips the badge and button", async () => {
    api.getAdminCategory.mockResolvedValueOnce(category()).mockResolvedValueOnce(category({ is_active: false }));
    api.setAdminCategoryActive.mockResolvedValue({});
    render(<CategoryEditor id="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Cereals" }));
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(await screen.findByRole("button", { name: "Activate Cereals" })).toBeInTheDocument();
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });

  it("opening a different category does not show the previous one's data", async () => {
    api.getAdminCategory.mockResolvedValueOnce(category({ id: "c1", name: "Cereals" }));
    let finish!: (v: unknown) => void;
    api.getAdminCategory.mockReturnValueOnce(new Promise((r) => (finish = r)));
    const { rerender } = render(<CategoryEditor id="c1" />);
    await screen.findByRole("heading", { name: "Cereals" });
    rerender(<CategoryEditor id="c2" />);
    expect(screen.queryByRole("heading", { name: "Cereals" })).toBeNull();
    finish(category({ id: "c2", name: "Snacks" }));
    expect(await screen.findByRole("heading", { name: "Snacks" })).toBeInTheDocument();
  });
});

describe("ProductEditor", () => {
  it("loads the product by id and shows header, badges, stock note and form", async () => {
    api.getAdminProduct.mockResolvedValue(productDetail());
    render(<ProductEditor id="p1" />);
    expect(screen.getByRole("status", { name: "Loading the product" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1, name: "Muesli" })).toBeInTheDocument();
    expect(api.getAdminProduct).toHaveBeenCalledWith("p1");
    expect(screen.getByText("SKU MUE-001")).toBeInTheDocument();
    expect(screen.getByText("In stock")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Price/)).toHaveValue("249.00");
    expect(screen.getByRole("button", { name: "Deactivate Muesli" })).toBeInTheDocument();
  });

  it("explains a load failure and can retry", async () => {
    api.getAdminProduct.mockRejectedValueOnce(new Error("Product not found."));
    render(<ProductEditor id="nope" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Product not found.");
    api.getAdminProduct.mockResolvedValue(productDetail());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Muesli" })).toBeInTheDocument();
  });

  it("saving updates the header, and deactivating reloads the badges", async () => {
    api.getAdminProduct.mockResolvedValueOnce(productDetail()).mockResolvedValueOnce(productDetail({ name: "Muesli Deluxe", is_active: false }));
    api.updateAdminProduct.mockResolvedValue(productDetail({ name: "Muesli Deluxe" }));
    api.setAdminProductActive.mockResolvedValue({});
    render(<ProductEditor id="p1" />);
    await screen.findByRole("heading", { level: 1, name: "Muesli" });
    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: "Muesli Deluxe" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Muesli Deluxe" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Muesli Deluxe" }));
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Activate Muesli Deluxe" })).toBeInTheDocument());
    expect(api.setAdminProductActive).toHaveBeenCalledWith("p1", false);
  });
});
