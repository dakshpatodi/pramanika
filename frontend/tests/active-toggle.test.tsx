import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AxiosError } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { api } = vi.hoisted(() => ({ api: { setAdminProductActive: vi.fn(), setAdminCategoryActive: vi.fn() } }));
vi.mock("@/services/admin-catalog", () => api);

import { ActiveToggle } from "@/components/admin/catalog/ActiveToggle";

beforeEach(() => {
  api.setAdminProductActive.mockReset();
  api.setAdminCategoryActive.mockReset();
});
afterEach(cleanup);

const refusal = (message: string) =>
  new AxiosError("x", "ERR", undefined, undefined, { status: 409, data: { success: false, message }, statusText: "", headers: {}, config: {} as never });

const open = (name: string) => fireEvent.click(screen.getByRole("button", { name }));

describe("ActiveToggle", () => {
  it("asks before deactivating a product, and does nothing if cancelled", () => {
    render(<ActiveToggle kind="product" id="p1" name="Muesli" active onChanged={vi.fn()} />);
    open("Deactivate Muesli");
    expect(screen.getByRole("dialog", { name: 'Hide "Muesli" from the shop?' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(api.setAdminProductActive).not.toHaveBeenCalled();
  });

  it("deactivates a product after confirmation, closes, and tells the page", async () => {
    api.setAdminProductActive.mockResolvedValue({});
    const onChanged = vi.fn();
    render(<ActiveToggle kind="product" id="p1" name="Muesli" active onChanged={onChanged} />);
    open("Deactivate Muesli");
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(api.setAdminProductActive).toHaveBeenCalledWith("p1", false);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("activates an inactive product (and says what that means)", async () => {
    api.setAdminProductActive.mockResolvedValue({});
    render(<ActiveToggle kind="product" id="p1" name="Muesli" active={false} onChanged={vi.fn()} />);
    open("Activate Muesli");
    expect(screen.getByRole("dialog", { name: 'Show "Muesli" in the shop?' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Activate" }));
    await waitFor(() => expect(api.setAdminProductActive).toHaveBeenCalledWith("p1", true));
  });

  it("uses the category endpoint and category wording for a category", async () => {
    api.setAdminCategoryActive.mockResolvedValue({});
    render(<ActiveToggle kind="category" id="c1" name="Cereals" active onChanged={vi.fn()} />);
    open("Deactivate Cereals");
    expect(screen.getByRole("dialog")).toHaveAccessibleDescription(/refused while the category still has active products/i);
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    await waitFor(() => expect(api.setAdminCategoryActive).toHaveBeenCalledWith("c1", false));
    expect(api.setAdminProductActive).not.toHaveBeenCalled();
  });

  it("keeps the dialog open and shows the server's refusal; the page is not told", async () => {
    api.setAdminCategoryActive.mockRejectedValue(refusal("Category has 4 active products."));
    const onChanged = vi.fn();
    render(<ActiveToggle kind="category" id="c1" name="Cereals" active onChanged={onChanged} />);
    open("Deactivate Cereals");
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Category has 4 active products.");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Deactivate" })).toBeEnabled();     // can retry or cancel
  });

  it("a double click sends one request", async () => {
    let finish!: (v: unknown) => void;
    api.setAdminProductActive.mockReturnValue(new Promise((r) => (finish = r)));
    render(<ActiveToggle kind="product" id="p1" name="Muesli" active onChanged={vi.fn()} />);
    open("Deactivate Muesli");
    const confirm = screen.getByRole("button", { name: "Deactivate" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(api.setAdminProductActive).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Working..." })).toBeDisabled();
    finish({});
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("clears an old refusal when it is opened again", async () => {
    api.setAdminProductActive.mockRejectedValueOnce(refusal("Nope."));
    render(<ActiveToggle kind="product" id="p1" name="Muesli" active onChanged={vi.fn()} />);
    open("Deactivate Muesli");
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    open("Deactivate Muesli");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
