"use client";

import { useRef, useState } from "react";

import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { getApiErrorMessage } from "@/lib/errors";
import { setAdminCategoryActive, setAdminProductActive } from "@/services/admin-catalog";

interface ActiveToggleProps {
  kind: "category" | "product";
  id: string;
  name: string;
  active: boolean;
  /** Called after the server accepted the change, so the page can reload. */
  onChanged: () => void;
}

const COPY = {
  product: {
    deactivate: {
      title: (name: string) => `Hide "${name}" from the shop?`,
      body: "Customers will no longer see it or be able to add it to a cart. Orders already placed are not affected. You can activate it again at any time.",
    },
    activate: {
      title: (name: string) => `Show "${name}" in the shop?`,
      body: "Customers will be able to see and buy it again. Its category must be active.",
    },
  },
  category: {
    deactivate: {
      title: (name: string) => `Hide the category "${name}"?`,
      body: "Customers will no longer see this category. This is refused while the category still has active products: hide or move them first.",
    },
    activate: {
      title: (name: string) => `Show the category "${name}"?`,
      body: "Customers will see this category in the shop again.",
    },
  },
} as const;

/** Activate / Deactivate for one category or product, behind a confirmation. A refusal from the server stays visible in the dialog. */
export function ActiveToggle({ kind, id, name, active, onChanged }: ActiveToggleProps) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false); // blocks a double click before React re-renders

  const action = active ? "deactivate" : "activate";
  const copy = COPY[kind][action];
  const verb = active ? "Deactivate" : "Activate";

  async function confirm() {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      await (kind === "product" ? setAdminProductActive(id, !active) : setAdminCategoryActive(id, !active));
      setOpen(false);
      onChanged();
    } catch (failure) {
      setError(getApiErrorMessage(failure, `We couldn't ${action} it. Please try again.`));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-label={`${verb} ${name}`}
        onClick={() => {
          setError(null);
          setOpen(true);
        }}
      >
        {verb}
      </Button>
      <ConfirmDialog
        open={open}
        title={copy.title(name)}
        description={copy.body}
        confirmLabel={verb}
        tone={active ? "danger" : "default"}
        busy={busy}
        error={error}
        onConfirm={confirm}
        onCancel={() => setOpen(false)}
      />
    </>
  );
}
