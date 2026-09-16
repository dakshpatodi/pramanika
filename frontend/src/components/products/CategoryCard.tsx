import Link from "next/link";

import { getCategoryIcon } from "@/lib/category-icons";
import type { CategoryWithCount } from "@/types/product";

interface CategoryCardProps {
  category: CategoryWithCount;
}

/**
 * Built fresh for the real API shape - not the Phase 1 placeholder
 * CategoryCard in components/shared/, which stays untouched powering
 * the homepage's fake data. See Phase 4 design decision #6.
 *
 * Links to /shop?category=<slug> rather than a separate per-category
 * page - one listing page with a filter, not two places that both need
 * to implement "show products in a category". See design decision #7.
 */
export function CategoryCard({ category }: CategoryCardProps) {
  const Icon = getCategoryIcon(category.slug);

  return (
    <Link
      href={`/shop?category=${category.slug}`}
      className="group flex flex-col items-center gap-4 rounded-2xl border border-border bg-card p-6 text-center shadow-card transition-all duration-300 hover:-translate-y-1 hover:shadow-lift"
    >
      <span className="flex h-20 w-20 items-center justify-center rounded-blob bg-primary-light text-primary transition-transform duration-300 group-hover:scale-105 group-hover:rounded-2xl">
        <Icon className="h-9 w-9" strokeWidth={1.75} />
      </span>
      <span className="flex flex-col gap-1">
        <span className="font-display text-base font-semibold text-foreground">{category.name}</span>
        {category.description ? (
          <span className="text-xs text-muted-foreground">{category.description}</span>
        ) : null}
        <span className="text-xs font-medium text-primary">{category.product_count} products</span>
      </span>
    </Link>
  );
}