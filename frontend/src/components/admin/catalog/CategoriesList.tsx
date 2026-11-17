"use client";

import Link from "next/link";
import { useState } from "react";
import { Plus, Search } from "lucide-react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ListEmpty, ListError, ListSkeleton } from "@/components/admin/ListStates";
import { ActiveToggle } from "@/components/admin/catalog/ActiveToggle";
import { ActiveBadge } from "@/components/admin/catalog/badges";
import { Pagination } from "@/components/products/Pagination";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useAdminQuery } from "@/hooks/useAdminQuery";
import { listAdminCategories } from "@/services/admin-catalog";
import type { CategoryListParams, CategorySort, SortOrder } from "@/types/admin-catalog";

const PAGE_SIZE = 20;

const SORTS: Array<{ value: string; label: string; sort: CategorySort; order: SortOrder }> = [
  { value: "name-asc", label: "Name: A to Z", sort: "name", order: "asc" },
  { value: "name-desc", label: "Name: Z to A", sort: "name", order: "desc" },
  { value: "created_at-desc", label: "Newest first", sort: "created_at", order: "desc" },
  { value: "created_at-asc", label: "Oldest first", sort: "created_at", order: "asc" },
  { value: "product_count-desc", label: "Most products", sort: "product_count", order: "desc" },
  { value: "product_count-asc", label: "Fewest products", sort: "product_count", order: "asc" },
];

type StatusFilter = "all" | "active" | "inactive";

/** Every category (active or not), searchable, filterable, sortable and paged. */
export function CategoriesList() {
  const [searchText, setSearchText] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [sortKey, setSortKey] = useState(SORTS[0].value);
  const [page, setPage] = useState(1);

  const chosen = SORTS.find((s) => s.value === sortKey) ?? SORTS[0];
  const params: CategoryListParams = {
    page,
    page_size: PAGE_SIZE,
    search: search || undefined,
    is_active: status === "all" ? undefined : status === "active",
    sort: chosen.sort,
    order: chosen.order,
  };
  const query = useAdminQuery(JSON.stringify(params), () => listAdminCategories(params), {
    failure: "We couldn't load the categories.",
    keepPrevious: true,
  });
  const { data, loading, error, reload } = query;
  const filtered = search !== "" || status !== "all";

  return (
    <>
      <AdminPageHeader
        title="Categories"
        description="Group products for the shop. Hiding a category needs all its products hidden first."
        actions={
          <Button asChild variant="primary" size="sm">
            <Link href="/admin/categories/new">
              <Plus aria-hidden="true" />
              New category
            </Link>
          </Button>
        }
      />

      <form
        role="search"
        aria-label="Filter categories"
        className="mb-4 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          setSearch(searchText.trim());
          setPage(1);
        }}
      >
        <div className="flex min-w-48 flex-1 flex-col gap-1">
          <label htmlFor="category-search" className="text-xs font-medium text-muted-foreground">Search</label>
          <Input id="category-search" value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder="Name or slug" maxLength={100} />
        </div>
        <Button type="submit" variant="outline" size="md">
          <Search aria-hidden="true" />
          Search
        </Button>
        <div className="flex flex-col gap-1">
          <label htmlFor="category-status" className="text-xs font-medium text-muted-foreground">Status</label>
          <Select id="category-status" value={status} onChange={(e) => { setStatus(e.target.value as StatusFilter); setPage(1); }}>
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="category-sort" className="text-xs font-medium text-muted-foreground">Sort by</label>
          <Select id="category-sort" value={sortKey} onChange={(e) => { setSortKey(e.target.value); setPage(1); }}>
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
        <ListSkeleton label="Loading categories" />
      ) : !data && error ? (
        <ListError message={error} onRetry={reload} />
      ) : data ? (
        <Card className="p-4 sm:p-6" aria-busy={loading}>
          {data.categories.length === 0 ? (
            filtered ? (
              <ListEmpty title="No categories match" hint="Try a different search or filter." />
            ) : (
              <ListEmpty
                title="No categories yet"
                hint="Create the first one to start organising products."
                action={
                  <Button asChild variant="primary" size="sm">
                    <Link href="/admin/categories/new">New category</Link>
                  </Button>
                }
              />
            )
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[40rem] text-left">
                <caption className="sr-only">Categories</caption>
                <thead>
                  <tr className="text-xs uppercase tracking-wide text-muted-foreground">
                    <th scope="col" className="pb-2 pr-4 font-medium">Name</th>
                    <th scope="col" className="pb-2 pr-4 font-medium">Slug</th>
                    <th scope="col" className="pb-2 pr-4 text-right font-medium">Products</th>
                    <th scope="col" className="pb-2 pr-4 font-medium">Status</th>
                    <th scope="col" className="pb-2 font-medium"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data.categories.map((category) => (
                    <tr key={category.id} className="border-t border-border/60 align-middle">
                      <td className="py-3 pr-4 text-sm font-semibold text-foreground">
                        <Link href={`/admin/categories/${category.id}`} className="hover:text-primary hover:underline">
                          {category.name}
                        </Link>
                      </td>
                      <td className="py-3 pr-4 text-sm text-muted-foreground">{category.slug}</td>
                      <td className="py-3 pr-4 text-right text-sm text-foreground">
                        {category.active_product_count} active
                        <span className="text-muted-foreground"> / {category.product_count}</span>
                      </td>
                      <td className="py-3 pr-4"><ActiveBadge active={category.is_active} /></td>
                      <td className="py-3">
                        <div className="flex items-center justify-end gap-2">
                          <Button asChild variant="outline" size="sm">
                            <Link href={`/admin/categories/${category.id}`} aria-label={`Edit ${category.name}`}>Edit</Link>
                          </Button>
                          <ActiveToggle kind="category" id={category.id} name={category.name} active={category.is_active} onChanged={reload} />
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
