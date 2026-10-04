"use client";

import { useState } from "react";

import { CartLine } from "@/components/cart/CartLine";
import { Button } from "@/components/ui/button";
import type { CartItem } from "@/types/cart";

interface CartListProps {
  items: CartItem[];
  /** Units in the cart, for the heading. */
  itemCount: number;
  disabled: boolean;
  onQuantityChange: (item: CartItem, quantity: number) => void;
  onRemove: (item: CartItem) => void;
  onClear: () => void;
}

/** The list of cart lines, with a two-step "Clear cart". */
export function CartList({ items, itemCount, disabled, onQuantityChange, onRemove, onClear }: CartListProps) {
  const [confirmingClear, setConfirmingClear] = useState(false);

  return (
    <section aria-labelledby="cart-items-heading" className="rounded-2xl border border-border bg-card p-5 shadow-card sm:p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
        <h2 id="cart-items-heading" className="font-display text-lg font-semibold text-foreground">
          {itemCount} {itemCount === 1 ? "item" : "items"}
        </h2>

        {confirmingClear ? (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Remove everything?</span>
            <Button
              variant="accent"
              size="sm"
              disabled={disabled}
              onClick={() => {
                setConfirmingClear(false);
                onClear();
              }}
            >
              Yes, clear cart
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirmingClear(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmingClear(true)}
            disabled={disabled}
            className="text-sm font-medium text-muted-foreground transition-colors hover:text-accent-dark disabled:cursor-not-allowed disabled:opacity-50"
          >
            Clear cart
          </button>
        )}
      </div>

      <ul className="divide-y divide-border">
        {items.map((item) => (
          <CartLine
            key={item.id}
            item={item}
            disabled={disabled}
            onQuantityChange={onQuantityChange}
            onRemove={onRemove}
          />
        ))}
      </ul>
    </section>
  );
}