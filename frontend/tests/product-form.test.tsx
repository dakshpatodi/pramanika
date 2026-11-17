import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { AxiosError } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { api, auth } = vi.hoisted(() => ({
  api: { createAdminProduct: vi.fn(), updateAdminProduct: vi.fn(), listAdminCategories: vi.fn() },
  auth: { user: { id: "u1" }, isLoading: false },
}));
vi.mock("@/services/admin-catalog", () => api);
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));

import { ProductForm } from "@/components/admin/catalog/ProductForm";
import { category, pagination, productDetail } from "./admin-fixtures";

beforeEach(() => {
  api.createAdminProduct.mockReset();
  api.updateAdminProduct.mockReset();
  api.listAdminCategories.mockReset();
  api.listAdminCategories.mockResolvedValue({
    categories: [category({ id: "c1", name: "Cereals" }), category({ id: "c2", name: "Snacks" })],
    pagination: pagination(),
  });
});
afterEach(cleanup);

const type = (label: RegExp | string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const submit = (name: string) => fireEvent.click(screen.getByRole("button", { name }));
const rejection = (status: number, data: unknown) =>
  new AxiosError("x", "ERR", undefined, undefined, { status, data, statusText: "", headers: {}, config: {} as never });

async function fillMinimum() {
  await screen.findByRole("option", { name: "Cereals" });
  type(/^Category/, "c1");
  type(/^Name/, "Muesli");
  type(/^SKU/, "mue-001");
  type(/^Price/, "249.50");
}

describe("ProductForm - create", () => {
  it("offers only active categories (asks the server for those)", async () => {
    render(<ProductForm />);
    await screen.findByRole("option", { name: "Cereals" });
    expect(api.listAdminCategories).toHaveBeenCalledWith({ is_active: true, page_size: 100, sort: "name", order: "asc" });
    expect(within(screen.getByLabelText(/^Category/)).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose a category", "Cereals", "Snacks"]);
  });

  it("lists every problem, focuses the first, and sends nothing", async () => {
    render(<ProductForm />);
    await screen.findByRole("option", { name: "Cereals" });
    submit("Create product");
    for (const message of ["Choose a category.", "Enter a name.", "Enter a SKU.", "Enter a price."]) {
      expect(screen.getByText(message)).toBeInTheDocument();
    }
    expect(screen.getByLabelText(/^Category/)).toHaveFocus();
    expect(api.createAdminProduct).not.toHaveBeenCalled();
  });

  it("sends money as text, the SKU in capitals and the opening stock as numbers", async () => {
    api.createAdminProduct.mockResolvedValue(productDetail({ id: "new1", name: "Muesli", sku: "MUE-001" }));
    render(<ProductForm />);
    await fillMinimum();
    type(/^Units in stock/, "20");
    type(/^Low-stock warning/, "5");
    type(/^Compare-at/, "299");
    type(/^Weight/, "500");
    type("Unit", "g");
    submit("Create product");
    await screen.findByText(/Product "Muesli" created \(MUE-001\)\./);
    expect(api.createAdminProduct).toHaveBeenCalledWith({
      category_id: "c1", name: "Muesli", sku: "MUE-001", price: "249.50", compare_at_price: "299", weight: "500", weight_unit: "g",
      is_active: true, initial_quantity: 20, low_stock_threshold: 5,
    });
    expect(screen.getByRole("link", { name: "Open it" })).toHaveAttribute("href", "/admin/products/new1");
  });

  it("a hidden product can be created", async () => {
    api.createAdminProduct.mockResolvedValue(productDetail());
    render(<ProductForm />);
    await fillMinimum();
    fireEvent.click(screen.getByLabelText("Show this product in the shop"));
    submit("Create product");
    await screen.findByText(/created/);
    expect(api.createAdminProduct.mock.calls[0][0]).toMatchObject({ is_active: false });
  });

  it("flags a weight without a unit and a compare-at price that is not higher", async () => {
    render(<ProductForm />);
    await fillMinimum();
    type(/^Weight/, "500");
    type(/^Compare-at/, "100");
    submit("Create product");
    expect(screen.getByText("Choose a unit for the weight.")).toBeInTheDocument();
    expect(screen.getByText("Must be higher than the price, or leave it empty.")).toBeInTheDocument();
    expect(api.createAdminProduct).not.toHaveBeenCalled();
  });

  it("marks the field the server refused (taken SKU) and keeps everything typed", async () => {
    api.createAdminProduct.mockRejectedValue(rejection(409, { success: false, message: "sku: that value is already in use." }));
    render(<ProductForm />);
    await fillMinimum();
    submit("Create product");
    expect(await screen.findByRole("alert")).toHaveTextContent("sku: that value is already in use.");
    expect(screen.getByLabelText(/^SKU/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText(/^SKU/)).toHaveFocus();
    expect(screen.getByLabelText(/^Name/)).toHaveValue("Muesli");
    expect(screen.getByLabelText(/^Price/)).toHaveValue("249.50");
  });

  it("uses the 422 errors list to mark a field", async () => {
    api.createAdminProduct.mockRejectedValue(
      rejection(422, { success: false, message: "price: x", errors: [{ loc: ["body", "price"], msg: "Value error, Too many decimals." }] })
    );
    render(<ProductForm />);
    await fillMinimum();
    submit("Create product");
    await screen.findByRole("alert");
    expect(screen.getByLabelText(/^Price/)).toHaveAccessibleDescription("Too many decimals.");
  });

  it("a double submit creates one product", async () => {
    let finish!: (v: unknown) => void;
    api.createAdminProduct.mockReturnValue(new Promise((r) => (finish = r)));
    render(<ProductForm />);
    await fillMinimum();
    const form = screen.getByRole("button", { name: "Create product" }).closest("form") as HTMLFormElement;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(api.createAdminProduct).toHaveBeenCalledTimes(1);
    finish(productDetail());
    await screen.findByText(/created/);
  });

  it("tells the admin when the categories could not load", async () => {
    api.listAdminCategories.mockRejectedValue(new Error("Categories unavailable"));
    render(<ProductForm />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Categories unavailable");
  });
});

describe("ProductForm - edit", () => {
  it("shows the saved values, money with two decimals, and the stock as read-only text", async () => {
    render(<ProductForm product={productDetail()} />);
    expect(screen.getByLabelText(/^Name/)).toHaveValue("Muesli");
    expect(screen.getByLabelText(/^Price/)).toHaveValue("249.00");
    expect(screen.getByLabelText(/^Compare-at/)).toHaveValue("299.00");
    expect(screen.getByLabelText(/^Weight/)).toHaveValue("500");
    expect(screen.getByLabelText("Unit")).toHaveValue("g");
    expect(screen.getByText(/45 available \(50 in stock, 5 reserved by open orders\)\. Stock is managed under Inventory/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Units in stock/)).toBeNull();
    expect(screen.queryByLabelText(/Show this product/)).toBeNull();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    await waitFor(() => expect(api.listAdminCategories).toHaveBeenCalled());
  });

  it("links to the inventory page of this product for stock changes", async () => {
    render(<ProductForm product={productDetail()} />);
    expect(screen.getByRole("link", { name: "Manage stock" })).toHaveAttribute("href", "/admin/inventory/p1");
    await waitFor(() => expect(api.listAdminCategories).toHaveBeenCalled());
  });

  it("includes the product's own category even when it is hidden", async () => {
    const hidden = productDetail({ category: { id: "c9", name: "Seasonal", slug: "seasonal", is_active: false } });
    render(<ProductForm product={hidden} />);
    await screen.findByRole("option", { name: "Snacks" });
    expect(screen.getByRole("option", { name: "Seasonal (inactive)" })).toBeInTheDocument();
    expect(screen.getByLabelText(/^Category/)).toHaveValue("c9");
  });

  it("sends only what changed", async () => {
    const updated = productDetail({ price: 259.5 });
    api.updateAdminProduct.mockResolvedValue(updated);
    const onSaved = vi.fn();
    render(<ProductForm product={productDetail()} onSaved={onSaved} />);
    type(/^Price/, "259.50");
    submit("Save changes");
    await screen.findByText("Saved.");
    expect(api.updateAdminProduct).toHaveBeenCalledWith("p1", { price: "259.50" });
    expect(onSaved).toHaveBeenCalledWith(updated);
    expect(screen.getByLabelText(/^Price/)).toHaveValue("259.50");
  });

  it("submitting an unchanged form (Enter key) sends nothing", () => {
    render(<ProductForm product={productDetail()} />);
    fireEvent.submit(screen.getByRole("button", { name: "Save changes" }).closest("form")!);
    expect(api.updateAdminProduct).not.toHaveBeenCalled();
  });

  it("retyping the same price in another form does not count as a change", () => {
    render(<ProductForm product={productDetail()} />);
    type(/^Price/, "249");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });

  it("moving to another category and clearing optional fields are sent", async () => {
    api.updateAdminProduct.mockResolvedValue(productDetail());
    render(<ProductForm product={productDetail()} />);
    await screen.findByRole("option", { name: "Snacks" });
    type(/^Category/, "c2");
    type(/^Compare-at/, "");
    type(/^Description/, "");
    submit("Save changes");
    await waitFor(() => expect(api.updateAdminProduct).toHaveBeenCalledWith("p1", { category_id: "c2", compare_at_price: null, description: null }));
  });

  it("changing the unit sends the weight with it", async () => {
    api.updateAdminProduct.mockResolvedValue(productDetail());
    render(<ProductForm product={productDetail()} />);
    type("Unit", "kg");
    submit("Save changes");
    await waitFor(() => expect(api.updateAdminProduct).toHaveBeenCalledWith("p1", { weight: "500", weight_unit: "kg" }));
  });

  it("keeps the edits and shows the server's message when the save is refused", async () => {
    api.updateAdminProduct.mockRejectedValue(rejection(409, { success: false, message: "slug: that value is already in use." }));
    render(<ProductForm product={productDetail()} />);
    type(/^Slug/, "taken");
    submit("Save changes");
    expect(await screen.findByRole("alert")).toHaveTextContent("slug: that value is already in use.");
    expect(screen.getByLabelText(/^Slug/)).toHaveValue("taken");
    expect(screen.getByLabelText(/^Slug/)).toHaveAttribute("aria-invalid", "true");
  });

  it("Discard restores the saved values", () => {
    render(<ProductForm product={productDetail()} />);
    type(/^Name/, "Changed");
    fireEvent.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(screen.getByLabelText(/^Name/)).toHaveValue("Muesli");
  });
});
