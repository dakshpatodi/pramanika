import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AddressForm } from "@/components/checkout/AddressForm";
import type { Address } from "@/types/address";

const saved: Address = {
  id: "a1", full_name: "Asha Rao", phone_number: "9876543210", address_line_1: "12 MG Road", address_line_2: "Flat 4",
  city: "Pune", state: "Maharashtra", postal_code: "411001", country: "India", is_default: false, created_at: "2026-10-05T00:00:00Z",
};
afterEach(cleanup);

describe("AddressForm - add mode (unchanged behaviour used by checkout)", () => {
  it("is an empty 'Add a delivery address' form with a Save address button", () => {
    render(<AddressForm onSubmit={vi.fn()} offerDefault />);
    expect(screen.getByRole("form", { name: "Add a delivery address" })).toBeInTheDocument();
    expect((screen.getByLabelText("Full name") as HTMLInputElement).value).toBe("");
    expect(screen.getByRole("button", { name: "Save address" })).toBeInTheDocument();
    expect(screen.getByLabelText("Make this my default address")).toBeInTheDocument();
  });
});

describe("AddressForm - edit mode", () => {
  it("starts from the saved address, with its own names and no default checkbox", () => {
    render(<AddressForm onSubmit={vi.fn()} offerDefault={false} initial={saved} submitLabel="Save changes" ariaLabel="Edit address" />);
    expect(screen.getByRole("form", { name: "Edit address" })).toBeInTheDocument();
    expect((screen.getByLabelText("Full name") as HTMLInputElement).value).toBe("Asha Rao");
    expect((screen.getByLabelText("Address line 2 (optional)") as HTMLInputElement).value).toBe("Flat 4");
    expect((screen.getByLabelText("PIN code") as HTMLInputElement).value).toBe("411001");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Make this my default address")).toBeNull();
  });

  it("shows an empty second line when the saved address has none", () => {
    render(<AddressForm onSubmit={vi.fn()} offerDefault={false} initial={{ ...saved, address_line_2: null }} />);
    expect((screen.getByLabelText("Address line 2 (optional)") as HTMLInputElement).value).toBe("");
  });

  it("submits the edited values, with a cleared second line as null", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<AddressForm onSubmit={onSubmit} offerDefault={false} initial={saved} submitLabel="Save changes" />);
    await user.clear(screen.getByLabelText("Address line 2 (optional)"));
    await user.clear(screen.getByLabelText("City"));
    await user.type(screen.getByLabelText("City"), "Mumbai");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ city: "Mumbai", address_line_2: null, full_name: "Asha Rao", is_default: false });
  });

  it("still applies the PIN rule when editing", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<AddressForm onSubmit={onSubmit} offerDefault={false} initial={saved} />);
    await user.clear(screen.getByLabelText("PIN code"));
    await user.type(screen.getByLabelText("PIN code"), "012345");
    await user.click(screen.getByRole("button", { name: "Save address" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Enter a valid 6-digit PIN code.")).toBeInTheDocument();
  });

  it("puts the cursor in the first field when asked to", () => {
    render(<AddressForm onSubmit={vi.fn()} offerDefault={false} initial={saved} autoFocus />);
    expect(screen.getByLabelText("Full name")).toHaveFocus();
  });

  it("shows the server's message when saving fails and keeps the form", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockRejectedValue(new Error("That PIN code is not serviceable."));
    render(<AddressForm onSubmit={onSubmit} offerDefault={false} initial={saved} />);
    await user.type(screen.getByLabelText("City"), "x");
    await user.click(screen.getByRole("button", { name: "Save address" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That PIN code is not serviceable.");
    expect((screen.getByLabelText("City") as HTMLInputElement).value).toBe("Punex");
  });
});
