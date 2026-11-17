import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "@/components/admin/ConfirmDialog";

afterEach(cleanup);

function setup(props: Partial<React.ComponentProps<typeof ConfirmDialog>> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <ConfirmDialog open title="Hide it?" description="Customers will not see it." confirmLabel="Hide" onConfirm={onConfirm} onCancel={onCancel} {...props} />
  );
  return { onConfirm, onCancel };
}

describe("ConfirmDialog", () => {
  it("draws a danger confirmation differently from a normal one", () => {
    setup({ tone: "danger" });
    const danger = screen.getByRole("button", { name: "Hide" }).className;
    cleanup();
    setup();
    expect(screen.getByRole("button", { name: "Hide" }).className).not.toBe(danger);
  });

  it("renders nothing while closed", () => {
    setup({ open: false });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("is a labelled, described, modal dialog", () => {
    setup();
    const dialog = screen.getByRole("dialog", { name: "Hide it?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleDescription("Customers will not see it.");
  });

  it("starts with focus on Cancel (the safe choice)", () => {
    setup();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });

  it("confirms and cancels through its buttons", () => {
    const { onConfirm, onCancel } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("Escape cancels; a click on the backdrop cancels; a click inside does not", () => {
    const { onCancel } = setup();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);
    fireEvent.mouseDown(screen.getByRole("dialog"));
    expect(onCancel).toHaveBeenCalledTimes(1);
    fireEvent.mouseDown(screen.getByRole("dialog").parentElement as HTMLElement);
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it("keeps Tab inside the dialog, in both directions", () => {
    setup();
    const cancel = screen.getByRole("button", { name: "Cancel" });
    const confirm = screen.getByRole("button", { name: "Hide" });
    confirm.focus();
    fireEvent.keyDown(confirm, { key: "Tab" });
    expect(cancel).toHaveFocus();
    fireEvent.keyDown(cancel, { key: "Tab", shiftKey: true });
    expect(confirm).toHaveFocus();
  });

  it("while busy: both buttons are disabled and nothing can dismiss it", () => {
    const { onCancel, onConfirm } = setup({ busy: true });
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Working..." })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    fireEvent.mouseDown(screen.getByRole("dialog").parentElement as HTMLElement);
    expect(onCancel).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("shows the server's refusal as an alert inside the dialog", () => {
    setup({ error: "Category still has active products." });
    expect(screen.getByRole("alert")).toHaveTextContent("Category still has active products.");
  });

  it("gives focus back to whatever had it when it closes", () => {
    function Host() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Open</button>
          <ConfirmDialog open={open} title="T" description="D" confirmLabel="Go" onConfirm={() => undefined} onCancel={() => setOpen(false)} />
        </>
      );
    }
    render(<Host />);
    const opener = screen.getByRole("button", { name: "Open" });
    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
  });
});
