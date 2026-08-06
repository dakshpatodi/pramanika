import { ShoppingCart, Star } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatPrice } from "@/lib/utils";
import { productPlaceholderIconMap } from "@/lib/icon-map";
import type { Product } from "@/types";

interface ProductCardProps {
  product: Product;
}

const badgeStyles: Record<NonNullable<Product["badge"]>, string> = {
  New: "bg-primary text-primary-foreground",
  Bestseller: "bg-secondary text-secondary-foreground",
  Sale: "bg-accent text-accent-foreground",
};

/**
 * Product tile used in the Featured Products grid.
 *
 * The "Add to Cart" button is presentational only in Phase 1 - it has no
 * click handler yet, since cart state/logic is out of scope until a
 * later phase.
 */
export function ProductCard({ product }: ProductCardProps) {
  const PlaceholderIcon = productPlaceholderIconMap[product.image] ?? productPlaceholderIconMap.oats;

  return (
    <div className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-card transition-all duration-300 hover:-translate-y-1 hover:shadow-lift">
      <div className="relative flex aspect-square items-center justify-center bg-primary-light">
        {product.badge ? (
          <span
            className={`absolute left-3 top-3 rounded-full px-2.5 py-1 text-xs font-semibold ${badgeStyles[product.badge]}`}
          >
            {product.badge}
          </span>
        ) : null}
        <PlaceholderIcon
          className="h-16 w-16 text-primary transition-transform duration-300 group-hover:scale-110"
          strokeWidth={1.5}
        />
      </div>

      <div className="flex flex-1 flex-col gap-2 p-4">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {product.category}
        </span>
        <h3 className="font-display text-base font-semibold text-foreground">{product.name}</h3>

        <div className="flex items-center gap-1 text-sm">
          <Star className="h-4 w-4 fill-secondary text-secondary" />
          <span className="font-medium text-foreground">{product.rating}</span>
          <span className="text-muted-foreground">({product.reviewCount})</span>
        </div>

        <div className="mt-auto flex items-center justify-between pt-2">
          <div className="flex items-baseline gap-2">
            <span className="font-display text-lg font-semibold text-foreground">
              {formatPrice(product.price)}
            </span>
            {product.compareAtPrice ? (
              <span className="text-sm text-muted-foreground line-through">
                {formatPrice(product.compareAtPrice)}
              </span>
            ) : null}
          </div>
          <Button size="icon" variant="primary" aria-label={`Add ${product.name} to cart`}>
            <ShoppingCart />
          </Button>
        </div>
      </div>
    </div>
  );
}
