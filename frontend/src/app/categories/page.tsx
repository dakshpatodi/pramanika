"use client";

import { useEffect, useState } from "react";

import { CategoryCard } from "@/components/products/CategoryCard";
import { listCategories } from "@/services/categories";
import type { CategoryWithCount } from "@/types/product";

export default function CategoriesPage() {
  const [categories, setCategories] = useState<CategoryWithCount[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    listCategories()
      .then((data) => {
        if (isMounted) setCategories(data);
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="container flex flex-col gap-8 py-12">
      <div className="flex flex-col gap-2 text-center">
        <h1 className="font-display text-3xl font-semibold text-foreground">Shop by Category</h1>
        <p className="text-muted-foreground">Browse our full range of wholesome staples.</p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="aspect-square animate-pulse rounded-2xl bg-muted" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {categories.map((category) => (
            <CategoryCard key={category.id} category={category} />
          ))}
        </div>
      )}
    </div>
  );
}