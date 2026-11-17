"use client";

import { useRef, useState } from "react";
import { Check } from "lucide-react";
import axios from "axios";

import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { FULFILMENT_STEPS, NEXT_ACTION_LABEL, confirmBody, stepIndex, whyNoNextStep } from "@/lib/admin-orders";
import { getApiErrorMessage } from "@/lib/errors";
import { ORDER_STATUS_LABEL } from "@/lib/order-format";
import { advanceAdminOrder } from "@/services/admin-orders";
import type { AdminOrderDetail } from "@/types/admin-orders";

interface OrderFulfilmentProps {
  order: AdminOrderDetail;
  /** The server's copy after the step. */
  onAdvanced: (order: AdminOrderDetail) => void;
  /** The server said the order changed under us (409): reload it. */
  onStale: () => void;
}

/**
 * The fulfilment tracker and the ONE action an admin has: move a paid order forward a step. The server
 * says which step is next (`next_status`) and whether it may move at all (`can_advance`); this component
 * only shows that, asks for confirmation with an optional note, and reports the server's refusal.
 */
export function OrderFulfilment({ order, onAdvanced, onStale }: OrderFulfilmentProps) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const busyRef = useRef(false);

  const current = stepIndex(order.status);
  const target = order.can_advance ? order.next_status : null;

  async function advance() {
    if (!target || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setRefusal(null);
    try {
      const trimmedNote = note.trim();
      const updated = await advanceAdminOrder(order.id, trimmedNote ? { status: target, note: trimmedNote } : { status: target });
      setOpen(false);
      setDone(`Order marked as ${ORDER_STATUS_LABEL[updated.status].toLowerCase()}.`);
      onAdvanced(updated);
    } catch (failure) {
      setRefusal(getApiErrorMessage(failure, "We couldn't update the order. Please try again."));
      if (axios.isAxiosError(failure) && failure.response?.status === 409) onStale();
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  return (
    <Card className="p-6">
      <h2 className="font-display text-xl font-semibold text-foreground">Fulfilment</h2>

      {current >= 0 ? (
        <ol aria-label="Fulfilment steps" className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {FULFILMENT_STEPS.map((step, index) => {
            const state = index < current ? "done" : index === current ? "current" : "todo";
            return (
              <li
                key={step.status}
                aria-current={state === "current" ? "step" : undefined}
                className={`rounded-xl border px-3 py-2 text-sm ${
                  state === "todo" ? "border-border text-muted-foreground" : "border-primary bg-primary-light text-primary-dark"
                } ${state === "current" ? "font-semibold" : ""}`}
              >
                <span className="flex items-center gap-1.5">
                  {state === "done" ? <Check className="h-4 w-4" aria-hidden="true" /> : null}
                  {step.label}
                </span>
                <span className="sr-only">{state === "done" ? " (done)" : state === "current" ? " (current step)" : " (not yet)"}</span>
              </li>
            );
          })}
        </ol>
      ) : null}

      <div className="mt-4">
        {target ? (
          <Button
            type="button"
            variant="primary"
            onClick={() => {
              setNote("");
              setRefusal(null);
              setDone(null);
              setOpen(true);
            }}
          >
            {NEXT_ACTION_LABEL[target]}
          </Button>
        ) : (
          <p className="text-sm text-muted-foreground">{whyNoNextStep(order)}</p>
        )}
        {done ? (
          <p role="status" className="mt-3 flex items-center gap-1.5 text-sm text-foreground">
            <Check className="h-4 w-4 text-primary" aria-hidden="true" />
            {done}
          </p>
        ) : null}
      </div>

      {target ? (
        <ConfirmDialog
          open={open}
          title={`${NEXT_ACTION_LABEL[target]}?`}
          description={
            <div className="flex flex-col gap-3">
              <p>{confirmBody(target)}</p>
              <div className="flex flex-col gap-1">
                <label htmlFor="fulfilment-note" className="text-xs font-medium text-muted-foreground">Note (optional, kept in the change history)</label>
                <Input id="fulfilment-note" value={note} maxLength={200} autoComplete="off" disabled={busy} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Courier tracking number" />
              </div>
            </div>
          }
          confirmLabel={NEXT_ACTION_LABEL[target]}
          busy={busy}
          error={refusal}
          onConfirm={advance}
          onCancel={() => setOpen(false)}
        />
      ) : null}
    </Card>
  );
}
