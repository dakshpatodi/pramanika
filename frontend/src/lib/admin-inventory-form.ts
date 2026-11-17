/**
 * Stock form helpers for the admin inventory page: light client-side checks (the SERVER stays the
 * authority: it refuses a change that would go below the reserved units, past the maximum, or on
 * stock that moved since it was loaded) and the exact request bodies. Values are strings while editing.
 */

import type { StockStatus } from "@/types/admin-catalog";
import type { AdminAuditEvent, InventoryUpdateInput } from "@/types/admin-inventory";

/** Narrows a `?stock=` value from the address bar to a filter the API accepts. */
export const isStockFilter = (value: unknown): value is StockStatus => value === "ok" || value === "low" || value === "out";

export const MAX_STOCK = 1_000_000;
export const MAX_REASON = 200;

export type StockMode = "add" | "remove" | "set";

export const STOCK_MODES: Array<{ value: StockMode; label: string }> = [
  { value: "add", label: "Add stock (received)" },
  { value: "remove", label: "Remove stock (damaged, lost)" },
  { value: "set", label: "Set the exact count (stock take)" },
];

const WHOLE = /^\d+$/;
const trimmed = (value: string) => value.trim();

export interface StockFormValues {
  mode: StockMode;
  amount: string;
  reason: string;
}
export type StockField = "amount" | "reason";

export const EMPTY_STOCK: StockFormValues = { mode: "add", amount: "", reason: "" };

export function validateStock(values: StockFormValues): Partial<Record<StockField, string>> {
  const errors: Partial<Record<StockField, string>> = {};
  const raw = trimmed(values.amount);
  const label = values.mode === "set" ? "the new count" : "how many units";
  if (!raw) errors.amount = `Enter ${label}.`;
  else if (!WHOLE.test(raw)) errors.amount = "Enter a whole number, no decimals or signs.";
  else {
    const n = Number(raw);
    if (n > MAX_STOCK) errors.amount = `Use at most ${MAX_STOCK.toLocaleString("en-IN")}.`;
    else if (n === 0 && values.mode !== "set") errors.amount = "Enter at least 1 unit.";
  }
  if (trimmed(values.reason).length > MAX_REASON) errors.reason = `Use at most ${MAX_REASON} characters.`;
  return errors;
}

/** The stock level this change would leave (display only: the server computes the real result). */
export function resultingQuantity(current: number, values: StockFormValues): number | null {
  const raw = trimmed(values.amount);
  if (!WHOLE.test(raw)) return null;
  const n = Number(raw);
  if (values.mode === "set") return n;
  return values.mode === "add" ? current + n : current - n;
}

/** SET sends the count the admin SAW as `expected_quantity`, so a sale in between is refused, not overwritten. */
export function stockUpdateInput(values: StockFormValues, loadedQuantity: number): InventoryUpdateInput {
  const n = Number(trimmed(values.amount));
  const input: InventoryUpdateInput =
    values.mode === "set"
      ? { quantity: n, expected_quantity: loadedQuantity }
      : { adjust_by: values.mode === "add" ? n : -n };
  const reason = trimmed(values.reason);
  if (reason) input.reason = reason;
  return input;
}

export function validateThreshold(value: string): string | undefined {
  const raw = trimmed(value);
  if (!raw) return "Enter a number (0 turns the low-stock warning off).";
  if (!WHOLE.test(raw)) return "Enter a whole number, no decimals or signs.";
  if (Number(raw) > MAX_STOCK) return `Use at most ${MAX_STOCK.toLocaleString("en-IN")}.`;
  return undefined;
}

export const thresholdUpdateInput = (value: string): InventoryUpdateInput => ({ low_stock_threshold: Number(trimmed(value)) });

// ------------------------------------------------------------------- history

const num = (value: unknown): number | null => (typeof value === "number" && Number.isFinite(value) ? value : null);

/** One audit row about a product's stock, in words. Unknown shapes fall back to the action name. */
export function describeStockEvent(event: Pick<AdminAuditEvent, "action" | "before" | "after">): { summary: string; reason: string | null } {
  const before = event.before ?? {};
  const after = event.after ?? {};
  const parts: string[] = [];

  const from = num(before.quantity);
  const to = num(after.quantity);
  if (to !== null) {
    const how =
      after.method === "set" ? "set by stock take" : num(after.adjust_by) !== null
        ? (num(after.adjust_by) as number) > 0 ? `added ${num(after.adjust_by)}` : `removed ${-(num(after.adjust_by) as number)}`
        : null;
    parts.push(`Stock ${from !== null ? `${from} → ${to}` : `now ${to}`}${how ? ` (${how})` : ""}`);
  }
  const thresholdFrom = num(before.low_stock_threshold);
  const thresholdTo = num(after.low_stock_threshold);
  if (thresholdTo !== null) {
    parts.push(`Low-stock warning at ${thresholdFrom !== null ? `${thresholdFrom} → ${thresholdTo}` : thresholdTo}`);
  }
  return {
    summary: parts.length > 0 ? parts.join("; ") : event.action,
    reason: typeof after.reason === "string" && after.reason ? after.reason : null,
  };
}
