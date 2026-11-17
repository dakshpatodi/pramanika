"use client";

import Link from "next/link";
import { useState } from "react";
import { Search } from "lucide-react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ListEmpty, ListError, ListSkeleton } from "@/components/admin/ListStates";
import { ActiveBadge, StockBadge } from "@/components/admin/catalog/badges";
import { Pagination } from "@/components/products/Pagination";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useAdminQuery } from "@/hooks/useAdminQuery";
import { formatOrderDate } from "@/lib/order-format";
import { listAdminCategories } from "@/services/admin-catalog";
import { listAdminInventory } from "@/services/admin-inventory";
import type { SortOrder, StockStatus } from "@/types/admin-catalog";
import type { InventoryListParams, InventorySort } from "@/types/admin-inventory";

const PAGE_SIZE = 20;

const SORTS: Array<{ value: string; label: string; sort: InventorySort; order: SortOrder }> = [
  { value: "name-asc", label: "Name: A to Z", sort: "name", order: "asc" },
  { value: "name-desc", label: "Name: Z to A", sort: "name", order: "desc" },
  { value: "sku-asc", label: "SKU: A to Z", sort: "sku", order: "asc" },
  { value: "available-asc", label: "Least available first", sort: "available", order: "asc" },
  { value: "available-desc", label: "Most available first", sort: "available", order: "desc" },
  { value: "quantity-asc", label: "Fewest in stock first", sort: "quantity", order: "asc" },
  { value: "updated_at-desc", label: "Recently changed", sort: "updated_at", order: "desc" },
];

type StatusFilter = "all" | "active" | "inactive";
type StockFilter = "all" | StockStatus;

/** Stock for every product, filterable (low / out of stock first), sortable and paged. `initialStock` lets a link open it pre-filtered. */
export function InventoryList({ initialStock }: { initialStock?: StockStatus }) {
  const [searchText, setSearchText] = useState("");
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [stock, setStock] = useState<StockFilter>(initialStock ?? "all");
  const [sortKey, setSortKey] = useState(initialStock ? "available-asc" : SORTS[0].value);
  const [page, setPage] = useState(1);

  const categories = useAdminQuery(
    "inventory-list-categories",
    () => listAdminCategories({ page_size: 100, sort: "name", order: "asc" }),
    { failure: "We couldn't load the categories." }
  );

  const chosen = SORTS.find((s) => s.value === sortKey) ?? SORTS[0];
  const params: InventoryListParams = {
    page,
    page_size: PAGE_SIZE,
    search: search || undefined,
    category_id: categoryId || undefined,
    is_active: status === "all" ? undefined : status === "active",
    stock: stock === "all" ? undefined : stock,
    sort: chosen.sort,
    order: chosen.order,
  };
  const { data, loading, error, reload } = useAdminQuery(JSON.stringify(params), () => listAdminInventory(params), {
    failure: "We couldn't load the stock levels.",
    keepPrevious: true,
  });
  const filtered = search !== "" || categoryId !== "" || status !== "all" || stock !== "all";

  const change = <T,>(set: (value: T) => void) => (value: T) => {
    set(value);
    setPage(1);
  };

  return (
    <>
      <AdminPageHeader title="Inventory" description="Stock on hand, what open orders have reserved, and what is left to sell." />

      <form
        role="search"
        aria-label="Filter stock"
        className="mb-4 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          setSearch(searchText.trim());
          setPage(1);
        }}
      >
        <div className="flex min-w-48 flex-1 flex-col gap-1">
          <label htmlFor="inventory-search" className="text-xs font-medium text-muted-foreground">Search</label>
          <Input id="inventory-search" value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder="Name, SKU or slug" maxLength={100} />
        </div>
        <Button type="submit" variant="outline" size="md">
          <Search aria-hidden="true" />
          Search
        </Button>
        <div className="flex flex-col gap-1">
          <label htmlFor="inventory-category-filter" className="text-xs font-medium text-muted-foreground">Category</label>
          <Select id="inventory-category-filter" value={categoryId} onChange={(e) => change(setCategoryId)(e.target.value)}>
            <option value="">All categories</option>
            {(categories.data?.categories ?? []).map((c) => (
              <option key={c.id} value={c.id}>{c.is_active ? c.name : `${c.name} (inactive)`}</option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="inventory-stock-filter" className="text-xs font-medium text-muted-foreground">Stock</label>
          <Select id="inventory-stock-filter" value={stock} onChange={(e) => change(setStock)(e.target.value as StockFilter)}>
            <option value="all">All</option>
            <option value="ok">In stock</option>
            <option value="low">Low stock</option>
            <option value="out">Out of stock</option>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="inventory-status-filter" className="text-xs font-medium text-muted-foreground">Status</label>
          <Select id="inventory-status-filter" value={status} onChange={(e) => change(setStatus)(e.target.value as StatusFilter)}>
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="inventory-sort" className="text-xs font-medium text-muted-foreground">Sort by</label>
          <Select id="inventory-sort" value={sortKey} onChange={(e) => change(setSortKey)(e.target.value)}>
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
        <ListSkeleton label="Loading stock levels" />
      ) : !data && error ? (
        <ListError message={error} onRetry={reload} />
      ) : data ? (
        <Card className="p-4 sm:p-6" aria-busy={loading}>
          {data.items.length === 0 ? (
            filtered ? (
              <ListEmpty title="No products match" hint="Try a different search or filter." />
            ) : (
              <ListEmpty title="No products yet" hint="Stock appears here once products are added." />
            )
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[52rem] text-left">
                <caption className="sr-only">Stock levels</caption>
                <thead>
                  <tr className="text-xs uppercase tracking-wide text-muted-foreground">
                    <th scope="col" className="pb-2 pr-4 font-medium">Product</th>
                    <th scope="col" className="pb-2 pr-4 font-medium">Category</th>
                    <th scope="col" className="pb-2 pr-4 text-right font-medium">In stock</th>
                    <th scope="col" className="pb-2 pr-4 text-right font-medium">Reserved</th>
                    <th scope="col" className="pb-2 pr-4 text-right font-medium">Available</th>
                    <th scope="col" className="pb-2 pr-4 font-medium">Status</th>
                    <th scope="col" className="pb-2 font-medium"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <tr key={item.product_id} className="border-t border-border/60 align-middle">
                      <td className="py-3 pr-4 text-sm">
                        <Link href={`/admin/inventory/${item.product_id}`} className="block font-semibold text-foreground hover:text-primary hover:underline">
                          {item.name}
                        </Link>
                        <span className="block text-xs text-muted-foreground">{item.sku}</span>
                      </td>
                      <td className="py-3 pr-4 text-sm text-foreground">{item.category.name}</td>
                      <td className="py-3 pr-4 text-right text-sm text-foreground">{item.quantity.toLocaleString("en-IN")}</td>
                      <td className="py-3 pr-4 text-right text-sm text-foreground">{item.reserved_quantity.toLocaleString("en-IN")}</td>
                      <td className="py-3 pr-4 text-right text-sm font-semibold text-foreground">{item.available_quantity.toLocaleString("en-IN")}</td>
                      <td className="py-3 pr-4 text-sm">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <StockBadge status={item.stock_status} />
                          {item.is_active ? null : <ActiveBadge active={false} />}
                        </div>
                        <span className="mt-1 block text-xs text-muted-foreground">Changed {formatOrderDate(item.updated_at)}</span>
                      </td>
                      <td className="py-3">
                        <div className="flex justify-end">
                          <Button asChild variant="outline" size="sm">
                            <Link href={`/admin/inventory/${item.product_id}`} aria-label={`Adjust stock for ${item.name}`}>Adjust</Link>
                          </Button>
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
