"use client";

import { useEffect, useId, useRef } from "react";

import { Button } from "@/components/ui/button";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  /** "danger" draws the confirm button in the warning colour (hiding things, removing access). */
  tone?: "default" | "danger";
  /** True while the action runs: both buttons disable and Escape / backdrop do nothing. */
  busy?: boolean;
  /** The server's refusal, shown inside the dialog so the admin can read it and decide. */
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

const FOCUSABLE = "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled])";

/**
 * An accessible modal confirmation (no UI library): role="dialog" with a title and description,
 * focus starts on Cancel (the safe choice) and is trapped inside, Escape and a click outside
 * cancel, and focus returns to what had it before. While `busy` nothing can dismiss it, so a
 * request in flight is never orphaned.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  tone = "default",
  busy = false,
  error = null,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();
    return () => previous?.focus?.();
  }, [open]);

  if (!open) return null;

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.stopPropagation();
      if (!busy) onCancel();
      return;
    }
    if (event.key !== "Tab") return;
    const items = Array.from(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
    if (items.length === 0) {
      event.preventDefault();
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !panelRef.current?.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || !panelRef.current?.contains(active))) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-foreground/40 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        onKeyDown={onKeyDown}
        className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-card"
      >
        <h2 id={titleId} className="font-display text-xl font-semibold text-foreground">
          {title}
        </h2>
        <div id={descriptionId} className="mt-2 text-sm text-muted-foreground">
          {description}
        </div>
        {error ? (
          <p role="alert" className="mt-3 rounded-xl bg-accent-light px-3 py-2 text-sm text-foreground">
            {error}
          </p>
        ) : null}
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <Button ref={cancelRef} type="button" variant="outline" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button type="button" variant={tone === "danger" ? "accent" : "primary"} onClick={onConfirm} disabled={busy}>
            {busy ? "Working..." : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
