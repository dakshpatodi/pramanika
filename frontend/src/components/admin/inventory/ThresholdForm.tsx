"use client";

import { useRef, useState } from "react";
import { Check } from "lucide-react";

import { FormField } from "@/components/admin/catalog/FormField";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getApiErrorMessage } from "@/lib/errors";
import { thresholdUpdateInput, validateThreshold } from "@/lib/admin-inventory-form";
import { updateAdminInventory } from "@/services/admin-inventory";
import type { AdminInventoryDetail } from "@/types/admin-inventory";

/** The "low stock" warning level: a product at or below it is flagged Low stock. Does not change the stock itself. */
export function ThresholdForm({ item, onUpdated }: { item: AdminInventoryDetail; onUpdated: (item: AdminInventoryDetail) => void }) {
  const saved = item.low_stock_threshold === null ? "" : String(item.low_stock_threshold);
  const [value, setValue] = useState(saved);
  const [error, setError] = useState<string | undefined>();
  const [failure, setFailure] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const dirty = value.trim() !== saved;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (savingRef.current) return;
    const found = validateThreshold(value);
    setError(found);
    if (found) return void inputRef.current?.focus();
    if (!dirty) return;

    savingRef.current = true;
    setSaving(true);
    setFailure(null);
    setDone(false);
    try {
      const updated = await updateAdminInventory(item.product_id, thresholdUpdateInput(value));
      setValue(updated.low_stock_threshold === null ? "" : String(updated.low_stock_threshold));
      setDone(true);
      onUpdated(updated);
    } catch (caught) {
      setFailure(getApiErrorMessage(caught, "We couldn't save the warning level. Please try again."));
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate aria-label="Low-stock warning level" className="flex flex-col gap-4">
      <FormField
        id="stock-threshold"
        label="Warn when available stock is at or below"
        required
        error={error}
        hint="Products at or below this show as Low stock; at 0 they show as Out of stock."
      >
        <Input
          ref={inputRef}
          inputMode="numeric"
          autoComplete="off"
          disabled={saving}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setError(undefined);
            setDone(false);
          }}
        />
      </FormField>
      {failure ? <Banner>{failure}</Banner> : null}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" variant="primary" disabled={saving || !dirty}>
          {saving ? "Saving..." : "Save warning level"}
        </Button>
        {done ? (
          <p role="status" className="flex items-center gap-1.5 text-sm text-foreground">
            <Check className="h-4 w-4 text-primary" aria-hidden="true" />
            Saved.
          </p>
        ) : null}
      </div>
    </form>
  );
}
