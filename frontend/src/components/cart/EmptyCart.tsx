import Link from "next/link";
import { ShoppingBasket } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Shown when the cart has no items. */
export function EmptyCart() {
  return (
    <div className="flex flex-col items-center gap-4 rounded-2xl border border-border bg-card px-6 py-20 text-center shadow-card">
      <span className="flex h-16 w-16 items-center justify-center rounded-blob bg-primary-light text-primary">
        <ShoppingBasket className="h-8 w-8" aria-hidden="true" />
      </span>
      <h2 className="font-display text-2xl font-semibold text-foreground">Your cart is empty</h2>
      <p className="max-w-sm text-muted-foreground">
        Looks like you haven&apos;t added anything yet. Browse our cereals, ready mixes and healthy foods to get started.
      </p>
      <Button variant="primary" asChild>
        <Link href="/shop">Start shopping</Link>
      </Button>
    </div>
  );
}