"use client";

import { useEffect, useState } from "react";

import { listCategories } from "@/services/categories";
import type { CategoryWithCount } from "@/types/product";

interface CategoryFilterProps {
  value: string;
  onChange: (value: string) => void;
}

export function CategoryFilter({ value, onChange }: CategoryFilterProps) {
  const [categories, setCategories] = useState<CategoryWithCount[]>([]);

  useEffect(() => {
    let isMounted = true;
    listCategories()
      .then((data) => {
        if (isMounted) setCategories(data);
      })
      .catch(() => {
        // Filter options are non-critical - if this fails, the dropdown
        // just shows "All Categories" only, rather than blocking the page.
      });
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-11 rounded-xl border border-border bg-card px-4 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      <option value="">All Categories</option>
      {categories.map((category) => (
        <option key={category.slug} value={category.slug}>
          {category.name} ({category.product_count})
        </option>
      ))}
    </select>
  );
}