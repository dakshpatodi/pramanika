import { Minus, Plus } from "lucide-react";

interface QuantityControlProps {
  value: number;
  /** Highest quantity the customer can choose (available stock). */
  max: number;
  disabled?: boolean;
  onChange: (next: number) => void;
  /** Product name, used in the buttons' accessible labels. */
  label: string;
}

/**
 * "- 2 +" stepper for a cart line. Purely presentational: it never
 * stores the quantity itself - the cart from the server is the truth, so
 * the number only changes once the server has accepted the new value.
 *
 * "-" stops at 1 (removing a line is a separate, explicit button), "+"
 * stops at `max` so the customer can't ask for more than is in stock.
 */
export function QuantityControl({ value, max, disabled = false, onChange, label }: QuantityControlProps) {
  const canDecrease = !disabled && value > 1;
  const canIncrease = !disabled && value < max;

  return (
    <div className="inline-flex items-center rounded-full border border-border bg-card">
      <button
        type="button"
        onClick={() => onChange(value - 1)}
        disabled={!canDecrease}
        className="flex h-9 w-9 items-center justify-center rounded-full text-foreground transition-colors hover:text-primary disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-foreground"
        aria-label={`Decrease quantity of ${label}`}
      >
        <Minus className="h-4 w-4" />
      </button>
      <span className="w-8 text-center text-sm font-semibold" aria-live="polite" aria-label={`Quantity of ${label}`}>
        {value}
      </span>
      <button
        type="button"
        onClick={() => onChange(value + 1)}
        disabled={!canIncrease}
        className="flex h-9 w-9 items-center justify-center rounded-full text-foreground transition-colors hover:text-primary disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-foreground"
        aria-label={`Increase quantity of ${label}`}
      >
        <Plus className="h-4 w-4" />
      </button>
    </div>
  );
}