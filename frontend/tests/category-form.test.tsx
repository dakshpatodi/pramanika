import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AxiosError } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { api } = vi.hoisted(() => ({ api: { createAdminCategory: vi.fn(), updateAdminCategory: vi.fn() } }));
vi.mock("@/services/admin-catalog", () => api);

import { CategoryForm } from "@/components/admin/catalog/CategoryForm";
import { category } from "./admin-fixtures";

beforeEach(() => {
  api.createAdminCategory.mockReset();
  api.updateAdminCategory.mockReset();
});
afterEach(cleanup);

const type = (label: RegExp | string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const submit = (name: string) => fireEvent.click(screen.getByRole("button", { name }));
const rejection = (status: number, data: unknown) =>
  new AxiosError("x", "ERR", undefined, undefined, { status, data, statusText: "", headers: {}, config: {} as never });

describe("CategoryForm - create", () => {
  it("shows what is wrong, focuses the first bad field, and sends nothing", () => {
    render(<CategoryForm />);
    submit("Create category");
    expect(screen.getByText("Enter a name.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Name/)).toHaveFocus();
    expect(screen.getByLabelText(/^Name/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText(/^Name/)).toHaveAccessibleDescription("Enter a name.");
    expect(api.createAdminCategory).not.toHaveBeenCalled();
  });

  it("sends the cleaned values and then offers next steps", async () => {
    api.createAdminCategory.mockResolvedValue(category({ id: "new1", name: "Grains" }));
    render(<CategoryForm />);
    type(/^Name/, "  Grains ");
    type(/^Slug/, "Whole-Grains");
    type(/^Description/, "  Good stuff ");
    submit("Create category");
    await screen.findByText(/Category "Grains" created\./);
    expect(api.createAdminCategory).toHaveBeenCalledWith({ name: "Grains", slug: "whole-grains", description: "Good stuff", is_active: true });
    expect(screen.getByRole("link", { name: "Open it" })).toHaveAttribute("href", "/admin/categories/new1");
    expect(screen.getByRole("link", { name: "Back to categories" })).toHaveAttribute("href", "/admin/categories");
  });

  it("can create a hidden category, and 'Add another' starts clean", async () => {
    api.createAdminCategory.mockResolvedValue(category({ name: "Draft" }));
    render(<CategoryForm />);
    type(/^Name/, "Draft");
    fireEvent.click(screen.getByLabelText("Show this category in the shop"));
    submit("Create category");
    await screen.findByText(/created\./);
    expect(api.createAdminCategory).toHaveBeenCalledWith({ name: "Draft", is_active: false });
    fireEvent.click(screen.getByRole("button", { name: "Add another" }));
    expect(screen.getByLabelText(/^Name/)).toHaveValue("");
    expect(screen.getByLabelText("Show this category in the shop")).toBeChecked();
  });

  it("marks the field the server complained about, keeps what was typed, and shows the message", async () => {
    api.createAdminCategory.mockRejectedValue(rejection(409, { success: false, message: "slug: that value is already in use." }));
    render(<CategoryForm />);
    type(/^Name/, "Cereals");
    type(/^Slug/, "cereals");
    submit("Create category");
    expect(await screen.findByRole("alert")).toHaveTextContent("slug: that value is already in use.");
    expect(screen.getByLabelText(/^Slug/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText(/^Slug/)).toHaveFocus();
    expect(screen.getByLabelText(/^Name/)).toHaveValue("Cereals");
    expect(screen.getByRole("button", { name: "Create category" })).toBeEnabled();
  });

  it("a double submit creates one category", async () => {
    let finish!: (v: unknown) => void;
    api.createAdminCategory.mockReturnValue(new Promise((r) => (finish = r)));
    render(<CategoryForm />);
    type(/^Name/, "Cereals");
    const form = screen.getByRole("button", { name: "Create category" }).closest("form") as HTMLFormElement;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(api.createAdminCategory).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Saving..." })).toBeDisabled();
    finish(category());
    await screen.findByText(/created\./);
  });

  it("editing a field clears that field's error", () => {
    render(<CategoryForm />);
    submit("Create category");
    expect(screen.getByText("Enter a name.")).toBeInTheDocument();
    type(/^Name/, "A");
    expect(screen.queryByText("Enter a name.")).toBeNull();
  });
});

describe("CategoryForm - edit", () => {
  it("starts with the saved values, Save disabled, and no active checkbox", () => {
    render(<CategoryForm category={category({ description: "Desc", image_url: "/a.png" })} />);
    expect(screen.getByLabelText(/^Name/)).toHaveValue("Cereals");
    expect(screen.getByLabelText(/^Slug/)).toHaveValue("cereals");
    expect(screen.getByLabelText(/^Description/)).toHaveValue("Desc");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(screen.queryByLabelText(/Show this category/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Discard changes" })).toBeNull();
  });

  it("sends only what changed, shows 'Saved.', and hands the server's copy to the page", async () => {
    const updated = category({ name: "Grains" });
    api.updateAdminCategory.mockResolvedValue(updated);
    const onSaved = vi.fn();
    render(<CategoryForm category={category()} onSaved={onSaved} />);
    type(/^Name/, "Grains");
    submit("Save changes");
    await screen.findByText("Saved.");
    expect(api.updateAdminCategory).toHaveBeenCalledWith("c1", { name: "Grains" });
    expect(onSaved).toHaveBeenCalledWith(updated);
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();     // nothing new to save
  });

  it("clearing the description sends null", async () => {
    api.updateAdminCategory.mockResolvedValue(category({ description: null }));
    render(<CategoryForm category={category({ description: "Old" })} />);
    type(/^Description/, "");
    submit("Save changes");
    await waitFor(() => expect(api.updateAdminCategory).toHaveBeenCalledWith("c1", { description: null }));
  });

  it("requires a slug when editing", () => {
    render(<CategoryForm category={category()} />);
    type(/^Slug/, "");
    submit("Save changes");
    expect(screen.getByText("Enter a slug.")).toBeInTheDocument();
    expect(api.updateAdminCategory).not.toHaveBeenCalled();
  });

  it("Discard puts the saved values back", () => {
    render(<CategoryForm category={category()} />);
    type(/^Name/, "Changed");
    fireEvent.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(screen.getByLabelText(/^Name/)).toHaveValue("Cereals");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });

  it("keeps the edits and shows the message when the save fails", async () => {
    api.updateAdminCategory.mockRejectedValue(rejection(422, { success: false, message: "Network trouble" }));
    render(<CategoryForm category={category()} />);
    type(/^Name/, "Grains");
    submit("Save changes");
    expect(await screen.findByRole("alert")).toHaveTextContent("Network trouble");
    expect(screen.getByLabelText(/^Name/)).toHaveValue("Grains");
    expect(screen.queryByText("Saved.")).toBeNull();
  });
});
