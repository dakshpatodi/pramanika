import { AxiosError } from "axios";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { api, auth } = vi.hoisted(() => ({
  api: { getAdminInventory: vi.fn(), updateAdminInventory: vi.fn(), listAdminAuditEvents: vi.fn() },
  auth: { user: { id: "u1" }, isLoading: false },
}));
vi.mock("@/services/admin-inventory", () => api);
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));

import { InventoryEditor } from "@/components/admin/inventory/InventoryEditor";
import { auditEvent, inventoryDetail, pagination } from "./admin-fixtures";

const rejection = (status: number, message: string) =>
  new AxiosError("x", "ERR", undefined, undefined, { status, data: { success: false, message }, statusText: "", headers: {}, config: {} as never });
const type = (label: RegExp | string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const events = (list = [auditEvent()]) => ({ events: list, pagination: pagination({ total: list.length }) });

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.getAdminInventory.mockResolvedValue(inventoryDetail());
  api.listAdminAuditEvents.mockResolvedValue(events());
});
afterEach(cleanup);

async function ready() {
  render(<InventoryEditor id="p1" />);
  await screen.findByRole("heading", { level: 1, name: "Muesli" });
}

describe("InventoryEditor - loading and figures", () => {
  it("loads by id and shows the figures, reservations and links", async () => {
    await ready();
    expect(api.getAdminInventory).toHaveBeenCalledWith("p1");
    expect(screen.getByText("SKU MUE-001 · Cereals")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "In stock" })).toHaveTextContent("50");
    expect(screen.getByRole("group", { name: "Reserved" })).toHaveTextContent("5");
    expect(screen.getByRole("group", { name: "Available to sell" })).toHaveTextContent("45");
    expect(screen.getByRole("group", { name: "Low-stock warning at" })).toHaveTextContent("10");
    expect(screen.getByText(/2 open orders hold 5 units/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Edit product" })).toHaveAttribute("href", "/admin/products/p1");
    expect(screen.getByRole("link", { name: "View pending orders" })).toHaveAttribute("href", "/admin/orders?status=pending");
    expect(screen.queryByText(/does not match/)).toBeNull();
  });

  it("draws the available figure as a warning only when stock is low or out", async () => {
    await ready();
    expect(screen.getByRole("group", { name: "Available to sell" }).querySelector("p.font-display")).not.toHaveClass("text-accent-dark");
    cleanup();
    api.getAdminInventory.mockResolvedValue(inventoryDetail({ stock_status: "low", available_quantity: 3 }));
    await ready();
    expect(screen.getByRole("group", { name: "Available to sell" }).querySelector("p.font-display")).toHaveClass("text-accent-dark");
  });

  it("warns, in words, when reservations do not match open orders", async () => {
    api.getAdminInventory.mockResolvedValue(inventoryDetail({ reserved_quantity: 8, open_order_units: 5, reservations_match: false }));
    await ready();
    expect(screen.getByRole("alert")).toHaveTextContent(/reserved count \(8 units\) does not match what open orders hold \(5 units\)/);
  });

  it("says so when nothing is reserved, and when no threshold is set", async () => {
    api.getAdminInventory.mockResolvedValue(inventoryDetail({ open_order_count: 0, open_order_units: 0, reserved_quantity: 0, low_stock_threshold: null }));
    await ready();
    expect(screen.getByText("No open orders are holding stock for this product.")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Low-stock warning at" })).toHaveTextContent("Not set");
  });

  it("shows the server's message and retries when it cannot load (e.g. not found)", async () => {
    api.getAdminInventory.mockRejectedValueOnce(new Error("Product not found."));
    render(<InventoryEditor id="nope" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Product not found.");
    api.getAdminInventory.mockResolvedValue(inventoryDetail());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Muesli" })).toBeInTheDocument();
  });

  it("Refresh reloads and a failed refresh keeps the figures with a warning", async () => {
    await ready();
    api.getAdminInventory.mockRejectedValueOnce(new Error("Offline"));
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText(/Offline.*last successful load/)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "In stock" })).toHaveTextContent("50");
  });
});

describe("InventoryEditor - changing stock", () => {
  it("add: asks first (showing the result), then sends a positive adjust_by and shows the server's figures", async () => {
    api.updateAdminInventory.mockResolvedValue(inventoryDetail({ quantity: 60, available_quantity: 55 }));
    await ready();
    type(/^Units received/, "10");
    type(/^Note/, "Supplier delivery");
    fireEvent.click(screen.getByRole("button", { name: "Review change" }));
    expect(api.updateAdminInventory).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(/from 50 to 60/);
    expect(dialog).toHaveTextContent(/5 unit\(s\) stay reserved/);
    fireEvent.click(within(dialog).getByRole("button", { name: "Change stock" }));
    await waitFor(() => expect(api.updateAdminInventory).toHaveBeenCalledWith("p1", { adjust_by: 10, reason: "Supplier delivery" }));
    expect(await screen.findByText("Stock is now 60 (55 available).")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "In stock" })).toHaveTextContent("60");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByLabelText(/^Units received/)).toHaveValue("");
  });

  it("remove sends a negative adjust_by", async () => {
    api.updateAdminInventory.mockResolvedValue(inventoryDetail({ quantity: 47 }));
    await ready();
    type("What happened?", "remove");
    type(/^Units to remove/, "3");
    fireEvent.click(screen.getByRole("button", { name: "Review change" }));
    expect(screen.getByRole("dialog")).toHaveTextContent(/from 50 to 47/);
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Change stock" }));
    await waitFor(() => expect(api.updateAdminInventory).toHaveBeenCalledWith("p1", { adjust_by: -3 }));
  });

  it("set sends the count seen as expected_quantity", async () => {
    api.updateAdminInventory.mockResolvedValue(inventoryDetail({ quantity: 42 }));
    await ready();
    type("What happened?", "set");
    expect(screen.getByText("Stock was 50 when this page loaded.")).toBeInTheDocument();
    type(/^Counted stock/, "42");
    fireEvent.click(screen.getByRole("button", { name: "Review change" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Change stock" }));
    await waitFor(() => expect(api.updateAdminInventory).toHaveBeenCalledWith("p1", { quantity: 42, expected_quantity: 50 }));
  });

  it("an invalid amount is marked, focused, and nothing is asked or sent", async () => {
    await ready();
    type(/^Units received/, "2.5");
    fireEvent.click(screen.getByRole("button", { name: "Review change" }));
    expect(screen.getByLabelText(/^Units received/)).toHaveAccessibleDescription("Enter a whole number, no decimals or signs.");
    expect(screen.getByLabelText(/^Units received/)).toHaveFocus();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(api.updateAdminInventory).not.toHaveBeenCalled();
  });

  it("cancelling the dialog sends nothing and keeps what was typed", async () => {
    await ready();
    type(/^Units received/, "10");
    fireEvent.click(screen.getByRole("button", { name: "Review change" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByLabelText(/^Units received/)).toHaveValue("10");
    expect(api.updateAdminInventory).not.toHaveBeenCalled();
  });

  it("a refusal stays in the dialog with the server's reason and nothing changes", async () => {
    api.updateAdminInventory.mockRejectedValue(rejection(409, "Cannot remove 48 unit(s): 5 of 50 are reserved by open orders, so at most 45 can be removed."));
    await ready();
    type("What happened?", "remove");
    type(/^Units to remove/, "48");
    fireEvent.click(screen.getByRole("button", { name: "Review change" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Change stock" }));
    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent(/at most 45 can be removed/);
    expect(screen.getByRole("group", { name: "In stock" })).toHaveTextContent("50");
  });

  it("a 409 also reloads the figures (stock moved under us)", async () => {
    api.updateAdminInventory.mockRejectedValue(rejection(409, "Stock changed since you loaded it (now 44, you expected 50). Refresh and try again."));
    await ready();
    api.getAdminInventory.mockResolvedValue(inventoryDetail({ quantity: 44, available_quantity: 39 }));
    type("What happened?", "set");
    type(/^Counted stock/, "42");
    fireEvent.click(screen.getByRole("button", { name: "Review change" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Change stock" }));
    expect(await screen.findByText(/now 44, you expected 50/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("group", { name: "In stock" })).toHaveTextContent("44"));
  });

  it("a non-409 failure does not reload", async () => {
    api.updateAdminInventory.mockRejectedValue(rejection(500, "Server error"));
    await ready();
    const loads = api.getAdminInventory.mock.calls.length;
    type(/^Units received/, "1");
    fireEvent.click(screen.getByRole("button", { name: "Review change" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Change stock" }));
    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("Server error");
    expect(api.getAdminInventory.mock.calls.length).toBe(loads);
  });

  it("a double click on the confirm button sends one request", async () => {
    let finish!: (v: unknown) => void;
    api.updateAdminInventory.mockReturnValue(new Promise((r) => (finish = r)));
    await ready();
    type(/^Units received/, "1");
    fireEvent.click(screen.getByRole("button", { name: "Review change" }));
    const confirm = within(screen.getByRole("dialog")).getByRole("button", { name: "Change stock" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(api.updateAdminInventory).toHaveBeenCalledTimes(1);
    finish(inventoryDetail({ quantity: 51 }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("InventoryEditor - low-stock warning level", () => {
  it("Save is off until the number changes, then sends only the threshold", async () => {
    api.updateAdminInventory.mockResolvedValue(inventoryDetail({ low_stock_threshold: 20 }));
    await ready();
    const save = screen.getByRole("button", { name: "Save warning level" });
    expect(save).toBeDisabled();
    type(/^Warn when/, "20");
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await screen.findByText("Saved.");
    expect(api.updateAdminInventory).toHaveBeenCalledWith("p1", { low_stock_threshold: 20 });
    expect(screen.getByRole("group", { name: "Low-stock warning at" })).toHaveTextContent("20");
  });

  it("submitting an unchanged value (Enter key) sends nothing", async () => {
    await ready();
    fireEvent.submit(screen.getByRole("form", { name: "Low-stock warning level" }));
    expect(api.updateAdminInventory).not.toHaveBeenCalled();
  });

  it("submitting twice while saving sends one request", async () => {
    let finish!: (v: unknown) => void;
    api.updateAdminInventory.mockReturnValue(new Promise((r) => (finish = r)));
    await ready();
    type(/^Warn when/, "20");
    const form = screen.getByRole("form", { name: "Low-stock warning level" });
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(api.updateAdminInventory).toHaveBeenCalledTimes(1);
    finish(inventoryDetail({ low_stock_threshold: 20 }));
    await screen.findByText("Saved.");
  });

  it("marks a bad number and sends nothing; shows a server refusal", async () => {
    await ready();
    type(/^Warn when/, "-4");
    fireEvent.submit(screen.getByRole("form", { name: "Low-stock warning level" }));
    expect(screen.getByLabelText(/^Warn when/)).toHaveAccessibleDescription(/whole number/);
    expect(api.updateAdminInventory).not.toHaveBeenCalled();
    api.updateAdminInventory.mockRejectedValue(rejection(422, "low_stock_threshold: too big"));
    type(/^Warn when/, "5");
    fireEvent.click(screen.getByRole("button", { name: "Save warning level" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("low_stock_threshold: too big");
  });
});

describe("InventoryEditor - change history", () => {
  it("asks the audit trail for this product's inventory changes and words each one", async () => {
    await ready();
    expect(await screen.findByText("Stock 50 → 45 (removed 5)")).toBeInTheDocument();
    expect(api.listAdminAuditEvents).toHaveBeenCalledWith({ entity_type: "inventory", entity_id: "p1", page_size: 10 });
    expect(screen.getByText("Note: Damaged in transit")).toBeInTheDocument();
    expect(screen.getByText(/boss@example.com/)).toBeInTheDocument();
  });

  it("says when there is no history, and when a long one is cut off", async () => {
    api.listAdminAuditEvents.mockResolvedValue({ events: [], pagination: pagination({ total: 0 }) });
    await ready();
    expect(await screen.findByText("No changes have been made here yet.")).toBeInTheDocument();
    cleanup();
    api.listAdminAuditEvents.mockResolvedValue({ events: [auditEvent()], pagination: pagination({ total: 25 }) });
    await ready();
    expect(await screen.findByText("Showing the latest 10 of 25 changes.")).toBeInTheDocument();
  });

  it("an error in the history does not hide the page, and can be retried", async () => {
    api.listAdminAuditEvents.mockRejectedValueOnce(new Error("History down"));
    await ready();
    expect(await screen.findByText("History down")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "In stock" })).toBeInTheDocument();
    api.listAdminAuditEvents.mockResolvedValue(events());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Stock 50 → 45 (removed 5)")).toBeInTheDocument();
  });

  it("is reloaded after a change", async () => {
    api.updateAdminInventory.mockResolvedValue(inventoryDetail({ quantity: 51 }));
    await ready();
    await screen.findByText("Stock 50 → 45 (removed 5)");
    const loads = api.listAdminAuditEvents.mock.calls.length;
    type(/^Units received/, "1");
    fireEvent.click(screen.getByRole("button", { name: "Review change" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Change stock" }));
    await waitFor(() => expect(api.listAdminAuditEvents.mock.calls.length).toBe(loads + 1));
  });
});
