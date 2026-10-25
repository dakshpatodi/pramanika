import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { User } from "@/types/auth";

const { auth, api } = vi.hoisted(() => ({
  auth: { user: null as unknown, updateUser: vi.fn() },
  api: { updateProfile: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/services/profile", () => api);

import { ProfileForm } from "@/components/dashboard/ProfileForm";

const saved = (over: Partial<User> = {}): User => ({
  id: "u1", first_name: "Asha", last_name: "Rao", email: "asha@example.com", phone_number: "+919876543210",
  role: "customer", is_active: true, is_verified: false, last_login: null, created_at: "2026-01-01T00:00:00Z", ...over,
});
function deferred<T>() {
  let resolve!: (v: T) => void; let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
const saveButton = () => screen.getByRole("button", { name: /save changes|saving/i });

beforeEach(() => {
  api.updateProfile.mockReset();
  auth.updateUser.mockReset();
  auth.user = saved();
});
afterEach(cleanup);

describe("ProfileForm", () => {
  it("starts with the saved values, the email locked, and nothing to save", () => {
    render(<ProfileForm />);
    expect(field("First name").value).toBe("Asha");
    expect(field("Last name").value).toBe("Rao");
    expect(field("Phone number").value).toBe("+919876543210");
    const email = field("Email");
    expect(email.value).toBe("asha@example.com");
    expect(email).toHaveAttribute("readonly");
    expect(saveButton()).toBeDisabled();
    expect(screen.queryByRole("button", { name: /discard/i })).toBeNull();
  });

  it("renders nothing without a user", () => {
    auth.user = null;
    const { container } = render(<ProfileForm />);
    expect(container).toBeEmptyDOMElement();
  });

  it("has no inputs for protected fields", () => {
    render(<ProfileForm />);
    const names = Array.from(document.querySelectorAll("input")).map((i) => i.getAttribute("name") ?? i.id);
    for (const forbidden of ["role", "is_active", "is_verified", "password", "id"]) expect(names).not.toContain(forbidden);
  });

  it("enables Save once something changes, and offers to discard", async () => {
    const user = userEvent.setup();
    render(<ProfileForm />);
    await user.type(field("First name"), "x");
    expect(saveButton()).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /discard/i }));
    expect(field("First name").value).toBe("Asha");
    expect(saveButton()).toBeDisabled();
  });

  it("does not count whitespace-only edits as a change", async () => {
    const user = userEvent.setup();
    render(<ProfileForm />);
    await user.type(field("First name"), "   ");
    expect(saveButton()).toBeDisabled();
  });

  it("sends only the changed fields, trimmed, and updates the signed-in user with the server's copy", async () => {
    const user = userEvent.setup();
    const fresh = saved({ first_name: "Meera" });
    api.updateProfile.mockResolvedValue(fresh);
    render(<ProfileForm />);
    await user.clear(field("First name"));
    await user.type(field("First name"), "  Meera ");
    await user.click(saveButton());

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Profile updated."));
    expect(api.updateProfile).toHaveBeenCalledTimes(1);
    expect(api.updateProfile).toHaveBeenCalledWith({ first_name: "Meera" });
    expect(auth.updateUser).toHaveBeenCalledWith(fresh);
    expect(field("First name").value).toBe("Meera");
  });

  it("sends all three when all three changed", async () => {
    const user = userEvent.setup();
    api.updateProfile.mockResolvedValue(saved());
    render(<ProfileForm />);
    for (const [label, value] of [["First name", "Meera"], ["Last name", "Iyer"], ["Phone number", "9811122233"]]) {
      await user.clear(field(label));
      await user.type(field(label), value);
    }
    await user.click(saveButton());
    await waitFor(() => expect(api.updateProfile).toHaveBeenCalled());
    expect(api.updateProfile).toHaveBeenCalledWith({ first_name: "Meera", last_name: "Iyer", phone_number: "9811122233" });
  });

  it("shows field errors, focuses the first bad field and sends nothing", async () => {
    const user = userEvent.setup();
    render(<ProfileForm />);
    await user.clear(field("First name"));
    await user.clear(field("Phone number"));
    await user.type(field("Phone number"), "abc");
    await user.click(saveButton());

    expect(api.updateProfile).not.toHaveBeenCalled();
    expect(screen.getByText("Enter your first name.")).toBeInTheDocument();
    expect(screen.getByText("Use digits only, optionally starting with +.")).toBeInTheDocument();
    expect(field("First name")).toHaveAttribute("aria-invalid", "true");
    expect(field("First name")).toHaveAccessibleDescription("Enter your first name.");
    expect(field("First name")).toHaveFocus();
  });

  it("clears a field's error as soon as the user edits that field", async () => {
    const user = userEvent.setup();
    render(<ProfileForm />);
    await user.clear(field("First name"));
    await user.click(saveButton());
    expect(screen.getByText("Enter your first name.")).toBeInTheDocument();
    await user.type(field("First name"), "M");
    expect(screen.queryByText("Enter your first name.")).toBeNull();
  });

  it("shows the server's message when it refuses (e.g. phone already used) and keeps what was typed", async () => {
    const user = userEvent.setup();
    api.updateProfile.mockRejectedValue(Object.assign(new Error("x"), {
      isAxiosError: true, response: { status: 409, data: { success: false, message: "That phone number is already registered." } },
    }));
    render(<ProfileForm />);
    await user.clear(field("Phone number"));
    await user.type(field("Phone number"), "9811122233");
    await user.click(saveButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("That phone number is already registered.");
    expect(field("Phone number").value).toBe("9811122233");
    expect(auth.updateUser).not.toHaveBeenCalled();
    expect(saveButton()).toBeEnabled(); // can fix and retry
  });

  it("falls back to a plain message when the failure has no server message (network down)", async () => {
    const user = userEvent.setup();
    api.updateProfile.mockRejectedValue({});
    render(<ProfileForm />);
    await user.type(field("First name"), "x");
    await user.click(saveButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't save your changes. Please try again.");
  });

  it("locks the form while saving and ignores a second submit", async () => {
    const user = userEvent.setup();
    const pending = deferred<User>();
    api.updateProfile.mockReturnValue(pending.promise);
    render(<ProfileForm />);
    await user.type(field("First name"), "x");
    await user.click(saveButton());

    expect(screen.getByRole("button", { name: "Saving..." })).toBeDisabled();
    expect(field("First name")).toBeDisabled();
    fireEvent.submit(screen.getByRole("form", { name: "Edit profile" })); // Enter key / scripted double submit
    expect(api.updateProfile).toHaveBeenCalledTimes(1);

    pending.resolve(saved({ first_name: "Ashax" }));
    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());
    expect(field("First name")).toBeEnabled();
  });

  it("drops the success note when the user starts editing again", async () => {
    const user = userEvent.setup();
    api.updateProfile.mockResolvedValue(saved({ first_name: "Meera" }));
    render(<ProfileForm />);
    await user.type(field("First name"), "x");
    await user.click(saveButton());
    await screen.findByRole("status");
    await user.type(field("Last name"), "y");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("drops an old error when the user starts editing again", async () => {
    const user = userEvent.setup();
    api.updateProfile.mockRejectedValue({});
    render(<ProfileForm />);
    await user.type(field("First name"), "x");
    await user.click(saveButton());
    await screen.findByRole("alert");
    await user.type(field("First name"), "y");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
