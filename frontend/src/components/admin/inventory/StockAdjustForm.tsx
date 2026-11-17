"use client";

import { useRef, useState } from "react";
import { Check } from "lucide-react";
import axios from "axios";

import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { FormField } from "@/components/admin/catalog/FormField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { getApiErrorMessage } from "@/lib/errors";
import {
  EMPTY_STOCK,
  MAX_REASON,
  STOCK_MODES,
  resultingQuantity,
  stockUpdateInput,
  validateStock,
  type StockField,
  type StockFormValues,
  type StockMode,
} from "@/lib/admin-inventory-form";
import { updateAdminInventory } from "@/services/admin-inventory";
import type { AdminInventoryDetail } from "@/types/admin-inventory";

interface StockAdjustFormProps {
  item: AdminInventoryDetail;
  /** The server's copy after a change. */
  onUpdated: (item: AdminInventoryDetail) => void;
  /** The server said the stock moved or the request clashed with a sale: reload the figures. */
  onStale: () => void;
}

const AMOUNT_LABEL: Record<StockMode, string> = { add: "Units received", remove: "Units to remove", set: "Counted stock" };

/**
 * Receive, remove or count stock. Every change is confirmed first, showing the result. "Set" sends the
 * count the admin SAW so a sale in between is refused instead of overwritten; "add / remove" is applied
 * by the server on its current value, so two admins never undo each other. The server refuses anything
 * below the units open orders have reserved, and says why.
 */
export function StockAdjustForm({ item, onUpdated, onStale }: StockAdjustFormProps) {
  const [values, setValues] = useState<StockFormValues>(EMPTY_STOCK);
  const [errors, setErrors] = useState<Partial<Record<StockField, string>>>({});
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const busyRef = useRef(false);
  const amountRef = useRef<HTMLInputElement>(null);
  const reasonRef = useRef<HTMLInputElement>(null);

  function edit<K extends keyof StockFormValues>(field: K, value: StockFormValues[K]) {
    setValues((current) => ({ ...current, [field]: value }));
    if (field !== "mode" && field in errors) setErrors((current) => ({ ...current, [field]: undefined }));
    setDone(null);
  }

  function review(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validateStock(values);
    setErrors(found);
    if (found.amount) return void amountRef.current?.focus();
    if (found.reason) return void reasonRef.current?.focus();
    setRefusal(null);
    setConfirming(true);
  }

  async function apply() {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setRefusal(null);
    try {
      const updated = await updateAdminInventory(item.product_id, stockUpdateInput(values, item.quantity));
      setConfirming(false);
      setValues(EMPTY_STOCK);
      setDone(`Stock is now ${updated.quantity.toLocaleString("en-IN")} (${updated.available_quantity.toLocaleString("en-IN")} available).`);
      onUpdated(updated);
    } catch (failure) {
      setRefusal(getApiErrorMessage(failure, "We couldn't change the stock. Please try again."));
      if (axios.isAxiosError(failure) && failure.response?.status === 409) onStale();
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  const after = resultingQuantity(item.quantity, values);

  return (
    <form onSubmit={review} noValidate aria-label="Change stock" className="flex flex-col gap-4">
      <FormField id="stock-mode" label="What happened?">
        <Select value={values.mode} onChange={(e) => edit("mode", e.target.value as StockMode)}>
          {STOCK_MODES.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </Select>
      </FormField>
      <FormField
        id="stock-amount"
        label={AMOUNT_LABEL[values.mode]}
        required
        error={errors.amount}
        hint={values.mode === "set" ? `Stock was ${item.quantity.toLocaleString("en-IN")} when this page loaded.` : undefined}
      >
        <Input ref={amountRef} inputMode="numeric" autoComplete="off" value={values.amount} onChange={(e) => edit("amount", e.target.value)} />
      </FormField>
      <FormField id="stock-reason" label="Note (optional)" error={errors.reason} hint="Kept in the change history, e.g. “Supplier delivery 14 Nov”.">
        <Input ref={reasonRef} maxLength={MAX_REASON + 50} autoComplete="off" value={values.reason} onChange={(e) => edit("reason", e.target.value)} />
      </FormField>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" variant="primary">Review change</Button>
        {done ? (
          <p role="status" className="flex items-center gap-1.5 text-sm text-foreground">
            <Check className="h-4 w-4 text-primary" aria-hidden="true" />
            {done}
          </p>
        ) : null}
      </div>

      <ConfirmDialog
        open={confirming}
        title={`Change stock for "${item.name}"?`}
        description={
          <>
            Stock goes from <strong>{item.quantity.toLocaleString("en-IN")}</strong> to{" "}
            <strong>{after === null ? "?" : after.toLocaleString("en-IN")}</strong>
            {item.reserved_quantity > 0 ? `. ${item.reserved_quantity.toLocaleString("en-IN")} unit(s) stay reserved by open orders` : ""}.
            This is recorded in the change history.
          </>
        }
        confirmLabel="Change stock"
        busy={busy}
        error={refusal}
        onConfirm={apply}
        onCancel={() => setConfirming(false)}
      />
    </form>
  );
}
