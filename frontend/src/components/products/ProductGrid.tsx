import { PackageSearch } from "lucide-react";

import { ProductCard } from "@/components/products/ProductCard";
import type { ProductListItem } from "@/types/product";

interface ProductGridProps {
  products: ProductListItem[];
  isLoading?: boolean;
}

export function ProductGrid({ products, isLoading }: ProductGridProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:gap-6 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, index) => (
          <div key={index} className="aspect-[3/4] animate-pulse rounded-2xl bg-muted" />
        ))}
      </div>
    );
  }

  if (products.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border py-16 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-blob bg-muted text-muted-foreground">
          <PackageSearch className="h-7 w-7" />
        </span>
        <p className="font-display text-lg font-semibold text-foreground">No products found</p>
        <p className="max-w-sm text-sm text-muted-foreground">
          Try adjusting your search or filters to find what you&apos;re looking for.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-4 sm:gap-6 lg:grid-cols-4">
      {products.map((product) => (
        <ProductCard key={product.id} product={product} />
      ))}
    </div>
  );
}