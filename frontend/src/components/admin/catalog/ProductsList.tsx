"use client";

import Link from "next/link";
import { useState } from "react";
import { Plus, Search } from "lucide-react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ListEmpty, ListError, ListSkeleton } from "@/components/admin/ListStates";
import { ActiveToggle } from "@/components/admin/catalog/ActiveToggle";
import { ActiveBadge, StockBadge } from "@/components/admin/catalog/badges";
import { Pagination } from "@/components/products/Pagination";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useAdminQuery } from "@/hooks/useAdminQuery";
import { formatMoney } from "@/lib/money";
import { listAdminCategories, listAdminProducts } from "@/services/admin-catalog";
import type { ProductListParams, ProductSort, SortOrder, StockStatus } from "@/types/admin-catalog";

const PAGE_SIZE = 20;

const SORTS: Array<{ value: string; label: string; sort: ProductSort; order: SortOrder }> = [
  { value: "created_at-desc", label: "Newest first", sort: "created_at", order: "desc" },
  { value: "created_at-asc", label: "Oldest first", sort: "created_at", order: "asc" },
  { value: "name-asc", label: "Name: A to Z", sort: "name", order: "asc" },
  { value: "name-desc", label: "Name: Z to A", sort: "name", order: "desc" },
  { value: "sku-asc", label: "SKU: A to Z", sort: "sku", order: "asc" },
  { value: "price-asc", label: "Price: low to high", sort: "price", order: "asc" },
  { value: "price-desc", label: "Price: high to low", sort: "price", order: "desc" },
  { value: "available-asc", label: "Least stock first", sort: "available", order: "asc" },
  { value: "available-desc", label: "Most stock first", sort: "available", order: "desc" },
];

type StatusFilter = "all" | "active" | "inactive";
type StockFilter = "all" | StockStatus;

/** Every product (active or not), searchable, filterable by category / status / stock, sortable and paged. */
export function ProductsList() {
  const [searchText, setSearchText] = useState("");
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [stock, setStock] = useState<StockFilter>("all");
  const [sortKey, setSortKey] = useState(SORTS[0].value);
  const [page, setPage] = useState(1);

  const categories = useAdminQuery(
    "product-list-categories",
    () => listAdminCategories({ page_size: 100, sort: "name", order: "asc" }),
    { failure: "We couldn't load the categories." }
  );

  const chosen = SORTS.find((s) => s.value === sortKey) ?? SORTS[0];
  const params: ProductListParams = {
    page,
    page_size: PAGE_SIZE,
    search: search || undefined,
    category_id: categoryId || undefined,
    is_active: status === "all" ? undefined : status === "active",
    stock: stock === "all" ? undefined : stock,
    sort: chosen.sort,
    order: chosen.order,
  };
  const { data, loading, error, reload } = useAdminQuery(JSON.stringify(params), () => listAdminProducts(params), {
    failure: "We couldn't load the products.",
    keepPrevious: true,
  });
  const filtered = search !== "" || categoryId !== "" || status !== "all" || stock !== "all";

  const change = <T,>(set: (value: T) => void) => (value: T) => {
    set(value);
    setPage(1);
  };

  return (
    <>
      <AdminPageHeader
        title="Products"
        description="Everything in the catalogue, including hidden products."
        actions={
          <Button asChild variant="primary" size="sm">
            <Link href="/admin/products/new">
              <Plus aria-hidden="true" />
              New product
            </Link>
          </Button>
        }
      />

      <form
        role="search"
        aria-label="Filter products"
        className="mb-4 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          setSearch(searchText.trim());
          setPage(1);
        }}
      >
        <div className="flex min-w-48 flex-1 flex-col gap-1">
          <label htmlFor="product-search" className="text-xs font-medium text-muted-foreground">Search</label>
          <Input id="product-search" value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder="Name, SKU or slug" maxLength={100} />
        </div>
        <Button type="submit" variant="outline" size="md">
          <Search aria-hidden="true" />
          Search
        </Button>
        <div className="flex flex-col gap-1">
          <label htmlFor="product-category-filter" className="text-xs font-medium text-muted-foreground">Category</label>
          <Select id="product-category-filter" value={categoryId} onChange={(e) => change(setCategoryId)(e.target.value)}>
            <option value="">All categories</option>
            {(categories.data?.categories ?? []).map((c) => (
              <option key={c.id} value={c.id}>{c.is_active ? c.name : `${c.name} (inactive)`}</option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="product-status-filter" className="text-xs font-medium text-muted-foreground">Status</label>
          <Select id="product-status-filter" value={status} onChange={(e) => change(setStatus)(e.target.value as StatusFilter)}>
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="product-stock-filter" className="text-xs font-medium text-muted-foreground">Stock</label>
          <Select id="product-stock-filter" value={stock} onChange={(e) => change(setStock)(e.target.value as StockFilter)}>
            <option value="all">All</option>
            <option value="ok">In stock</option>
            <option value="low">Low stock</option>
            <option value="out">Out of stock</option>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="product-sort" className="text-xs font-medium text-muted-foreground">Sort by</label>
          <Select id="product-sort" value={sortKey} onChange={(e) => change(setSortKey)(e.target.value)}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </Select>
        </div>
      </form>

      {data && error ? (
        <div className="mb-4">
          <Banner>{error} Showing the last result.</Banner>
        </div>
      ) : null}

      {!data && loading ? (
        <ListSkeleton label="Loading products" />
      ) : !data && error ? (
        <ListError message={error} onRetry={reload} />
      ) : data ? (
        <Card className="p-4 sm:p-6" aria-busy={loading}>
          {data.products.length === 0 ? (
            filtered ? (
              <ListEmpty title="No products match" hint="Try a different search or filter." />
            ) : (
              <ListEmpty
                title="No products yet"
                hint="Add the first product to start selling."
                action={
                  <Button asChild variant="primary" size="sm">
                    <Link href="/admin/products/new">New product</Link>
                  </Button>
                }
              />
            )
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[52rem] text-left">
                <caption className="sr-only">Products</caption>
                <thead>
                  <tr className="text-xs uppercase tracking-wide text-muted-foreground">
                    <th scope="col" className="pb-2 pr-4 font-medium">Product</th>
                    <th scope="col" className="pb-2 pr-4 font-medium">Category</th>
                    <th scope="col" className="pb-2 pr-4 text-right font-medium">Price</th>
                    <th scope="col" className="pb-2 pr-4 font-medium">Stock</th>
                    <th scope="col" className="pb-2 pr-4 font-medium">Status</th>
                    <th scope="col" className="pb-2 font-medium"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data.products.map((product) => (
                    <tr key={product.id} className="border-t border-border/60 align-middle">
                      <td className="py-3 pr-4 text-sm">
                        <Link href={`/admin/products/${product.id}`} className="block font-semibold text-foreground hover:text-primary hover:underline">
                          {product.name}
                        </Link>
                        <span className="block text-xs text-muted-foreground">{product.sku}</span>
                      </td>
                      <td className="py-3 pr-4 text-sm text-foreground">
                        {product.category.name}
                        {product.category.is_active ? null : <span className="block text-xs text-muted-foreground">category inactive</span>}
                      </td>
                      <td className="py-3 pr-4 text-right text-sm font-semibold text-foreground">
                        {formatMoney(product.price)}
                        {product.compare_at_price !== null ? (
                          <span className="block text-xs font-normal text-muted-foreground line-through">{formatMoney(product.compare_at_price)}</span>
                        ) : null}
                      </td>
                      <td className="py-3 pr-4 text-sm">
                        <StockBadge status={product.stock_status} />
                        <span className="mt-1 block text-xs text-muted-foreground">{product.available_quantity.toLocaleString("en-IN")} available</span>
                      </td>
                      <td className="py-3 pr-4"><ActiveBadge active={product.is_active} /></td>
                      <td className="py-3">
                        <div className="flex items-center justify-end gap-2">
                          <Button asChild variant="outline" size="sm">
                            <Link href={`/admin/products/${product.id}`} aria-label={`Edit ${product.name}`}>Edit</Link>
                          </Button>
                          <ActiveToggle kind="product" id={product.id} name={product.name} active={product.is_active} onChanged={reload} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-4">
            <Pagination pagination={data.pagination} onPageChange={setPage} />
          </div>
        </Card>
      ) : null}
    </>
  );
}
