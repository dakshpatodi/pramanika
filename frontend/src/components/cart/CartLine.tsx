import Link from "next/link";
import { AlertTriangle, Package, Trash2 } from "lucide-react";

import { QuantityControl } from "@/components/cart/QuantityControl";
import { cn } from "@/lib/utils";
import { formatMoney } from "@/lib/money";
import type { CartItem } from "@/types/cart";

/** The API rejects line quantities above this (CartItemUpdateRequest.le). */
const MAX_LINE_QUANTITY = 1000;

interface CartLineProps {
  item: CartItem;
  /** True while any cart request is in flight - freezes the controls. */
  disabled: boolean;
  onQuantityChange: (item: CartItem, quantity: number) => void;
  onRemove: (item: CartItem) => void;
}

/** One product row in the cart. */
export function CartLine({ item, disabled, onQuantityChange, onRemove }: CartLineProps) {
  const { product } = item;
  const hasIssue = item.issue !== null;
  const canReduceToStock = hasIssue && item.available_quantity > 0 && item.quantity > item.available_quantity;

  return (
    <li className="flex flex-col gap-3 py-5 first:pt-0 last:pb-0">
      <div className="flex gap-4">
        <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-primary-light">
          {product.image_url ? (
            // Plain <img>: product photos come from arbitrary hosts and
            // next/image would need each one allow-listed in next.config.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={product.image_url} alt={product.name} className="h-full w-full object-cover" />
          ) : (
            <Package className="h-8 w-8 text-primary" strokeWidth={1.5} aria-hidden="true" />
          )}
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <Link
            href={`/shop/${product.slug}`}
            className="font-display text-base font-semibold text-foreground hover:text-primary"
          >
            {product.name}
          </Link>
          <span className="text-sm text-muted-foreground">{formatMoney(item.unit_price)} each</span>

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
            <QuantityControl
              value={item.quantity}
              max={Math.min(item.available_quantity, MAX_LINE_QUANTITY)}
              disabled={disabled}
              onChange={(next) => onQuantityChange(item, next)}
              label={product.name}
            />
            <button
              type="button"
              onClick={() => onRemove(item)}
              disabled={disabled}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-accent-dark disabled:cursor-not-allowed disabled:opacity-50"
              aria-label={`Remove ${product.name} from cart`}
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" /> Remove
            </button>
          </div>
        </div>

        <div className="shrink-0 text-right">
          <span
            className={cn(
              "font-display text-base font-semibold",
              hasIssue ? "text-muted-foreground line-through" : "text-foreground"
            )}
          >
            {formatMoney(item.line_subtotal)}
          </span>
        </div>
      </div>

      {hasIssue ? (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl bg-accent-light px-4 py-3 text-sm text-foreground"
        >
          <AlertTriangle className="h-4 w-4 shrink-0 text-accent-dark" aria-hidden="true" />
          <span className="flex-1">
            {item.issue} <span className="text-muted-foreground">Not included in your total.</span>
          </span>
          {canReduceToStock ? (
            <button
              type="button"
              onClick={() => onQuantityChange(item, item.available_quantity)}
              disabled={disabled}
              className="rounded-full border border-border bg-card px-3 py-1 text-xs font-semibold text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
            >
              Set quantity to {item.available_quantity}
            </button>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}