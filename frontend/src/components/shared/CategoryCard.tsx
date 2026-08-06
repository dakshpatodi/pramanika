import { iconMap } from "@/lib/icon-map";
import type { Category } from "@/types";

interface CategoryCardProps {
  category: Category;
}

/**
 * A single shop-by-category tile. The icon sits inside a "blob" shaped
 * badge (an organic, hand-drawn-feeling border radius rather than a
 * plain circle or square) - this shape recurs across the homepage as
 * the visual signature tying back to "whole, natural foods."
 */
export function CategoryCard({ category }: CategoryCardProps) {
  const Icon = iconMap[category.icon] ?? iconMap.Wheat;

  return (
    <button
      type="button"
      className="group flex w-full shrink-0 snap-start flex-col items-center gap-4 rounded-2xl border border-border bg-card p-6 text-center shadow-card transition-all duration-300 hover:-translate-y-1 hover:shadow-lift sm:w-auto"
    >
      <span className="flex h-20 w-20 items-center justify-center rounded-blob bg-primary-light text-primary transition-transform duration-300 group-hover:scale-105 group-hover:rounded-2xl">
        <Icon className="h-9 w-9" strokeWidth={1.75} />
      </span>
      <span className="flex flex-col gap-0.5">
        <span className="font-display text-base font-semibold text-foreground">
          {category.name}
        </span>
        <span className="text-xs text-muted-foreground">{category.productCount} products</span>
      </span>
    </button>
  );
}
