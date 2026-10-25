import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Address } from "@/types/address";

const { auth, router, api } = vi.hoisted(() => ({
  auth: { user: null as null | { id: string; first_name: string }, isLoading: false, isAuthenticated: true },
  router: { push: vi.fn() },
  api: { listAddresses: vi.fn(), createAddress: vi.fn(), updateAddress: vi.fn(), setDefaultAddress: vi.fn(), deleteAddress: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/dashboard/addresses" }));
vi.mock("@/services/addresses", () => api);

import SavedAddressesPage from "@/app/dashboard/addresses/page";

const address = (id: string, isDefault = false, over: Partial<Address> = {}): Address => ({
  id, full_name: `Person ${id}`, phone_number: "9876543210", address_line_1: `${id} MG Road`, address_line_2: null,
  city: "Pune", state: "Maharashtra", postal_code: "411001", country: "India", is_default: isDefault, created_at: "2026-10-05T00:00:00Z", ...over,
});
function deferred<T>() {
  let resolve!: (v: T) => void; let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
const card = (id: string) => screen.getByRole("group", { name: `Address: Person ${id}, ${id} MG Road` });
const serverError = (message: string) =>
  Object.assign(new Error("x"), { isAxiosError: true, response: { data: { success: false, message } } });

async function open(list: Address[]) {
  api.listAddresses.mockResolvedValue(list);
  render(<SavedAddressesPage />);
  if (list.length) await screen.findAllByRole("group", { name: /^Address:/ });
  else await screen.findByText("No saved addresses yet");
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  router.push.mockReset();
  auth.user = { id: "u1", first_name: "Asha" };
  auth.isLoading = false;
  auth.isAuthenticated = true;
});
afterEach(cleanup);

describe("Saved addresses page - viewing", () => {
  it("lists the addresses with the default marked, inside the account frame", async () => {
    await open([address("a1", true), address("a2")]);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Saved addresses");
    expect(within(screen.getByRole("navigation", { name: "Account" })).getByRole("link", { name: "Saved addresses" })).toHaveAttribute("aria-current", "page");
    expect(within(card("a1")).getByText("Default")).toBeInTheDocument();
    expect(within(card("a2")).queryByText("Default")).toBeNull();
    expect(within(card("a2")).getByText("Pune, Maharashtra 411001")).toBeInTheDocument();
  });

  it("offers 'Make default' only on addresses that are not the default", async () => {
    await open([address("a1", true), address("a2")]);
    expect(within(card("a1")).queryByRole("button", { name: /make default/i })).toBeNull();
    expect(within(card("a2")).getByRole("button", { name: /make default/i })).toBeInTheDocument();
  });

  it("shows a loading placeholder, then a retry when loading fails", async () => {
    const user = userEvent.setup();
    api.listAddresses.mockReturnValueOnce(new Promise(() => {}));
    render(<SavedAddressesPage />);
    expect(screen.getByRole("status", { name: "Loading your addresses" })).toBeInTheDocument();
    cleanup();

    api.listAddresses.mockReset();
    api.listAddresses.mockRejectedValueOnce(serverError("Addresses are unavailable."));
    render(<SavedAddressesPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Addresses are unavailable.");
    api.listAddresses.mockResolvedValue([address("a1", true)]);
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("group", { name: /^Address:/ })).toBeInTheDocument();
  });

  it("with no addresses, asks for the first one straight away (no default checkbox, no cancel)", async () => {
    await open([]);
    expect(screen.getByRole("heading", { name: "Add your first address" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Add a delivery address" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Make this my default address")).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add address" })).toBeNull();
  });

  it("renders nothing for a visitor and never calls the API", () => {
    auth.user = null;
    auth.isAuthenticated = false;
    const { container } = render(<SavedAddressesPage />);
    expect(container).toBeEmptyDOMElement();
    expect(router.push).toHaveBeenCalledWith("/login?redirect=%2Fdashboard%2Faddresses");
    for (const fn of Object.values(api)) expect(fn).not.toHaveBeenCalled();
  });
});

describe("Saved addresses page - adding", () => {
  async function fill(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText("Full name"), "Meera Iyer");
    await user.type(screen.getByLabelText("Phone number"), "9811122233");
    await user.type(screen.getByLabelText("Address line 1"), "5 Lake View");
    await user.type(screen.getByLabelText("City"), "Delhi");
    await user.type(screen.getByLabelText("State"), "Delhi");
    await user.type(screen.getByLabelText("PIN code"), "110001");
  }

  it("adds an address, reloads the list and says so", async () => {
    const user = userEvent.setup();
    await open([address("a1", true)]);
    await user.click(screen.getByRole("button", { name: "Add address" }));
    expect(screen.getByRole("heading", { name: "Add a new address" })).toBeInTheDocument();
    await fill(user);
    api.createAddress.mockResolvedValue(address("a2"));
    api.listAddresses.mockResolvedValue([address("a1", true), address("a2", false, { full_name: "Meera Iyer", address_line_1: "5 Lake View" })]);
    await user.click(screen.getByRole("button", { name: "Save address" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Address added.");
    expect(api.createAddress).toHaveBeenCalledWith(expect.objectContaining({ full_name: "Meera Iyer", postal_code: "110001", is_default: false }));
    expect(screen.getByRole("group", { name: "Address: Meera Iyer, 5 Lake View" })).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Add a delivery address" })).toBeNull();
  });

  it("can ask for the new address to become the default", async () => {
    const user = userEvent.setup();
    await open([address("a1", true)]);
    await user.click(screen.getByRole("button", { name: "Add address" }));
    await fill(user);
    await user.click(screen.getByLabelText("Make this my default address"));
    api.createAddress.mockResolvedValue(address("a2", true));
    api.listAddresses.mockResolvedValue([address("a2", true), address("a1")]);
    await user.click(screen.getByRole("button", { name: "Save address" }));
    await screen.findByRole("status");
    expect(api.createAddress).toHaveBeenCalledWith(expect.objectContaining({ is_default: true }));
  });

  it("shows the server's reason inside the form and keeps what was typed", async () => {
    const user = userEvent.setup();
    await open([address("a1", true)]);
    await user.click(screen.getByRole("button", { name: "Add address" }));
    await fill(user);
    api.createAddress.mockRejectedValue(serverError("You can save up to 20 addresses."));
    await user.click(screen.getByRole("button", { name: "Save address" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You can save up to 20 addresses.");
    expect((screen.getByLabelText("City") as HTMLInputElement).value).toBe("Delhi");
  });

  it("cancel closes the form without saving", async () => {
    const user = userEvent.setup();
    await open([address("a1", true)]);
    await user.click(screen.getByRole("button", { name: "Add address" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form")).toBeNull();
    expect(api.createAddress).not.toHaveBeenCalled();
  });

  it("at the 20-address limit there is no Add button, only the reason", async () => {
    await open(Array.from({ length: 20 }, (_, n) => address(`a${n}`, n === 0)));
    expect(screen.queryByRole("button", { name: "Add address" })).toBeNull();
    expect(screen.getByText(/maximum of 20 addresses/)).toBeInTheDocument();
  });
});

describe("Saved addresses page - editing", () => {
  it("opens the form with the saved values and saves ONLY what changed", async () => {
    const user = userEvent.setup();
    await open([address("a1", true), address("a2")]);
    await user.click(screen.getByRole("button", { name: "Edit address: Person a2, a2 MG Road" }));
    const form = screen.getByRole("form", { name: "Edit address" });
    expect((within(form).getByLabelText("City") as HTMLInputElement).value).toBe("Pune");
    expect(within(form).getByLabelText("Full name")).toHaveFocus();
    expect(within(form).queryByLabelText("Make this my default address")).toBeNull();

    await user.clear(within(form).getByLabelText("City"));
    await user.type(within(form).getByLabelText("City"), "Mumbai");
    api.updateAddress.mockResolvedValue(address("a2", false, { city: "Mumbai" }));
    await user.click(within(form).getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Address updated.");
    expect(api.updateAddress).toHaveBeenCalledTimes(1);
    expect(api.updateAddress).toHaveBeenCalledWith("a2", { city: "Mumbai" });
    expect(within(card("a2")).getByText("Mumbai, Maharashtra 411001")).toBeInTheDocument();
    expect(api.listAddresses).toHaveBeenCalledTimes(1);
  });

  it("makes no request when nothing changed", async () => {
    const user = userEvent.setup();
    await open([address("a1", true)]);
    await user.click(screen.getByRole("button", { name: /^Edit address/ }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("status")).toHaveTextContent("No changes to save.");
    expect(api.updateAddress).not.toHaveBeenCalled();
  });

  it("shows the server's reason and stays in the form when saving fails", async () => {
    const user = userEvent.setup();
    await open([address("a1", true)]);
    await user.click(screen.getByRole("button", { name: /^Edit address/ }));
    await user.type(screen.getByLabelText("City"), "x");
    api.updateAddress.mockRejectedValue(serverError("Address was not found."));
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Address was not found.");
    expect(screen.getByRole("form", { name: "Edit address" })).toBeInTheDocument();
  });

  it("cancel returns to the card unchanged; opening another edit closes the first", async () => {
    const user = userEvent.setup();
    await open([address("a1", true), address("a2")]);
    await user.click(screen.getByRole("button", { name: "Edit address: Person a1, a1 MG Road" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Edit address: Person a1, a1 MG Road" }));
    await user.click(screen.getByRole("button", { name: "Edit address: Person a2, a2 MG Road" }));
    expect(screen.getAllByRole("form")).toHaveLength(1);
    expect(api.updateAddress).not.toHaveBeenCalled();
  });
});

describe("Saved addresses page - default and delete", () => {
  it("moves the default to the chosen address", async () => {
    const user = userEvent.setup();
    await open([address("a1", true), address("a2")]);
    api.setDefaultAddress.mockResolvedValue([address("a2", true), address("a1")]);
    await user.click(screen.getByRole("button", { name: "Make default: Person a2, a2 MG Road" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Default address updated.");
    expect(api.setDefaultAddress).toHaveBeenCalledWith("a2");
    expect(within(card("a2")).getByText("Default")).toBeInTheDocument();
    expect(within(card("a1")).queryByText("Default")).toBeNull();
    expect(screen.getAllByText("Default")).toHaveLength(1);
  });

  it("reports a failed default change and leaves the list alone", async () => {
    const user = userEvent.setup();
    await open([address("a1", true), address("a2")]);
    api.setDefaultAddress.mockRejectedValue(serverError("Address was not found."));
    await user.click(screen.getByRole("button", { name: /^Make default/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Address was not found.");
    expect(within(card("a1")).getByText("Default")).toBeInTheDocument();
  });

  it("asks before deleting, says past orders are safe, and keeps the address on 'Keep'", async () => {
    const user = userEvent.setup();
    await open([address("a1", true), address("a2")]);
    await user.click(screen.getByRole("button", { name: "Delete address: Person a2, a2 MG Road" }));
    expect(within(card("a2")).getByText(/Orders you have already placed keep their delivery details/)).toBeInTheDocument();
    expect(within(card("a2")).queryByText(/will become your default/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Keep address" }));
    expect(api.deleteAddress).not.toHaveBeenCalled();
    expect(card("a2")).toBeInTheDocument();
  });

  it("deletes after confirmation and shows what remains", async () => {
    const user = userEvent.setup();
    await open([address("a1", true), address("a2")]);
    api.deleteAddress.mockResolvedValue([address("a1", true)]);
    await user.click(screen.getByRole("button", { name: "Delete address: Person a2, a2 MG Road" }));
    await user.click(screen.getByRole("button", { name: "Yes, delete" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Address deleted.");
    expect(api.deleteAddress).toHaveBeenCalledWith("a2");
    expect(screen.queryByRole("group", { name: "Address: Person a2, a2 MG Road" })).toBeNull();
  });

  it("warns when the address being deleted is the default, and shows the promoted one", async () => {
    const user = userEvent.setup();
    await open([address("a1", true), address("a2")]);
    api.deleteAddress.mockResolvedValue([address("a2", true)]);
    await user.click(screen.getByRole("button", { name: "Delete address: Person a1, a1 MG Road" }));
    expect(within(card("a1")).getByText(/Another saved address will become your default/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Yes, delete" }));
    await screen.findByRole("status");
    expect(within(card("a2")).getByText("Default")).toBeInTheDocument();
  });

  it("deleting the last address returns to the add-your-first-address state", async () => {
    const user = userEvent.setup();
    await open([address("a1", true)]);
    api.deleteAddress.mockResolvedValue([]);
    await user.click(screen.getByRole("button", { name: /^Delete address/ }));
    await user.click(screen.getByRole("button", { name: "Yes, delete" }));
    expect(await screen.findByText("No saved addresses yet")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Add your first address" })).toBeInTheDocument();
  });

  it("reports a failed delete and keeps the address", async () => {
    const user = userEvent.setup();
    await open([address("a1", true), address("a2")]);
    api.deleteAddress.mockRejectedValue({});
    await user.click(screen.getByRole("button", { name: "Delete address: Person a2, a2 MG Road" }));
    await user.click(screen.getByRole("button", { name: "Yes, delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't delete this address. Please try again.");
    expect(card("a2")).toBeInTheDocument();
  });

  it("does one change at a time: a second click while one is saving is ignored", async () => {
    const user = userEvent.setup();
    await open([address("a1", true), address("a2"), address("a3")]);
    const pending = deferred<Address[]>();
    api.setDefaultAddress.mockReturnValue(pending.promise);
    await user.click(screen.getByRole("button", { name: "Make default: Person a2, a2 MG Road" }));
    expect(within(card("a2")).getByRole("button", { name: /make default/i })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Make default: Person a3, a3 MG Road" }));
    expect(api.setDefaultAddress).toHaveBeenCalledTimes(1);
    pending.resolve([address("a2", true), address("a1"), address("a3")]);
    await screen.findByRole("status");
  });
});
