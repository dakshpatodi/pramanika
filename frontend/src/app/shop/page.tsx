"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { CategoryFilter } from "@/components/products/CategoryFilter";
import { Pagination } from "@/components/products/Pagination";
import { PriceRangeFilter } from "@/components/products/PriceRangeFilter";
import { ProductGrid } from "@/components/products/ProductGrid";
import { SearchBar } from "@/components/products/SearchBar";
import { SortSelect } from "@/components/products/SortSelect";
import { Button } from "@/components/ui/button";
import { listProducts } from "@/services/products";
import type { PaginationMeta, ProductListItem, ProductSort } from "@/types/product";

const PAGE_SIZE = 12;

function ShopContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const search = searchParams.get("search") ?? "";
  const category = searchParams.get("category") ?? "";
  const minPrice = searchParams.get("min_price") ?? "";
  const maxPrice = searchParams.get("max_price") ?? "";
  const sort = (searchParams.get("sort") as ProductSort) || "newest";
  const page = Number(searchParams.get("page") ?? "1");

  const [products, setProducts] = useState<ProductListItem[]>([]);
  const [pagination, setPagination] = useState<PaginationMeta | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const updateParams = useCallback(
    (updates: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value === null || value === "") {
          next.delete(key);
        } else {
          next.set(key, value);
        }
      }
      // Any change other than the page number itself resets back to
      // page 1 - staying on page 5 of a brand-new filtered result set
      // would very often just land on an empty page.
      if (!("page" in updates)) {
        next.delete("page");
      }
      router.push(`/shop?${next.toString()}`);
    },
    [router, searchParams]
  );

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    listProducts({
      page,
      page_size: PAGE_SIZE,
      search: search || undefined,
      category: category || undefined,
      min_price: minPrice ? Number(minPrice) : undefined,
      max_price: maxPrice ? Number(maxPrice) : undefined,
      sort,
    })
      .then((data) => {
        if (!isMounted) return;
        setProducts(data.products);
        setPagination(data.pagination);
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, [page, search, category, minPrice, maxPrice, sort]);

  const hasActiveFilters = useMemo(
    () => Boolean(search || category || minPrice || maxPrice || sort !== "newest"),
    [search, category, minPrice, maxPrice, sort]
  );

  return (
    <div className="container flex flex-col gap-8 py-12">
      <div className="flex flex-col gap-2">
        <h1 className="font-display text-3xl font-semibold text-foreground">Shop</h1>
        <p className="text-muted-foreground">
          {pagination ? `${pagination.total} product${pagination.total === 1 ? "" : "s"}` : "Loading..."}
        </p>
      </div>

      <div className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-4 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="w-full sm:max-w-xs">
          <SearchBar value={search} onChange={(value) => updateParams({ search: value || null })} />
        </div>
        <CategoryFilter value={category} onChange={(value) => updateParams({ category: value || null })} />
        <PriceRangeFilter
          minPrice={minPrice}
          maxPrice={maxPrice}
          onApply={(min, max) => updateParams({ min_price: min || null, max_price: max || null })}
        />
        <div className="sm:ml-auto">
          <SortSelect value={sort} onChange={(value) => updateParams({ sort: value })} />
        </div>
        {hasActiveFilters ? (
          <Button variant="ghost" size="sm" onClick={() => router.push("/shop")}>
            Clear filters
          </Button>
        ) : null}
      </div>

      <ProductGrid products={products} isLoading={isLoading} />

      {pagination ? (
        <Pagination pagination={pagination} onPageChange={(newPage) => updateParams({ page: String(newPage) })} />
      ) : null}
    </div>
  );
}

function ShopFallback() {
  return (
    <div className="container flex flex-col gap-8 py-12">
      <div className="h-9 w-32 animate-pulse rounded-lg bg-muted" />
      <div className="grid grid-cols-2 gap-4 sm:gap-6 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, index) => (
          <div key={index} className="aspect-[3/4] animate-pulse rounded-2xl bg-muted" />
        ))}
      </div>
    </div>
  );
}

export default function ShopPage() {
  // useSearchParams() requires a Suspense boundary in the App Router -
  // same reason as /login's redirect param (Milestone 8).
  return (
    <Suspense fallback={<ShopFallback />}>
      <ShopContent />
    </Suspense>
  );
}