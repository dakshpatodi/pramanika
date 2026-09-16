import Link from "next/link";
import { AlertTriangle, XCircle } from "lucide-react";

import { getCategoryIcon } from "@/lib/category-icons";
import { formatPrice } from "@/lib/utils";
import type { ProductListItem } from "@/types/product";

interface ProductCardProps {
  product: ProductListItem;
}

/**
 * Built fresh for the real Phase 3/4 API shape - deliberately NOT the
 * Phase 1 placeholder ProductCard in components/shared/ (which still
 * powers the homepage's fake data and stays untouched). See Phase 4
 * design decision #6.
 *
 * The whole card is the "CTA to view product" (a Link wrapping
 * everything) rather than a separate button inside it - a nested
 * interactive element would be worse UX and is redundant when the
 * entire card already navigates on click.
 */
export function ProductCard({ product }: ProductCardProps) {
  const Icon = getCategoryIcon(product.category.slug);

  return (
    <Link
      href={`/shop/${product.slug}`}
      className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-card transition-all duration-300 hover:-translate-y-1 hover:shadow-lift"
    >
      <div className="relative flex aspect-square items-center justify-center bg-primary-light">
        {product.compare_at_price ? (
          <span className="absolute left-3 top-3 rounded-full bg-accent px-2.5 py-1 text-xs font-semibold text-accent-foreground">
            Sale
          </span>
        ) : null}
        {!product.in_stock ? (
          <span className="absolute right-3 top-3 flex items-center gap-1 rounded-full bg-foreground/80 px-2.5 py-1 text-xs font-semibold text-background">
            <XCircle className="h-3 w-3" /> Out of stock
          </span>
        ) : product.low_stock ? (
          <span className="absolute right-3 top-3 flex items-center gap-1 rounded-full bg-secondary px-2.5 py-1 text-xs font-semibold text-secondary-foreground">
            <AlertTriangle className="h-3 w-3" /> Low stock
          </span>
        ) : null}
        <Icon
          className="h-16 w-16 text-primary transition-transform duration-300 group-hover:scale-110"
          strokeWidth={1.5}
        />
      </div>

      <div className="flex flex-1 flex-col gap-2 p-4">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {product.category.name}
        </span>
        <h3 className="font-display text-base font-semibold text-foreground">{product.name}</h3>

        <div className="mt-auto flex items-baseline gap-2 pt-2">
          <span className="font-display text-lg font-semibold text-foreground">{formatPrice(product.price)}</span>
          {product.compare_at_price ? (
            <span className="text-sm text-muted-foreground line-through">
              {formatPrice(product.compare_at_price)}
            </span>
          ) : null}
        </div>
      </div>
    </Link>
  );
}