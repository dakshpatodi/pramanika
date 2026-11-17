"use client";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ListError, ListSkeleton } from "@/components/admin/ListStates";
import { ActiveToggle } from "@/components/admin/catalog/ActiveToggle";
import { CategoryForm } from "@/components/admin/catalog/CategoryForm";
import { ActiveBadge } from "@/components/admin/catalog/badges";
import { useAdminQuery } from "@/hooks/useAdminQuery";
import { getAdminCategory } from "@/services/admin-catalog";

/** One category: its form, state and activate / deactivate button. */
export function CategoryEditor({ id }: { id: string }) {
  const { data, loading, error, reload, setData } = useAdminQuery(`category:${id}`, () => getAdminCategory(id), {
    failure: "We couldn't load this category.",
  });

  if (!data) {
    return (
      <>
        <AdminPageHeader title="Category" />
        {loading ? <ListSkeleton label="Loading the category" /> : <ListError message={error ?? "We couldn't load this category."} onRetry={reload} />}
      </>
    );
  }

  return (
    <>
      <AdminPageHeader
        title={data.name}
        description={`${data.active_product_count} active of ${data.product_count} products`}
        actions={
          <>
            <ActiveBadge active={data.is_active} />
            <ActiveToggle kind="category" id={data.id} name={data.name} active={data.is_active} onChanged={reload} />
          </>
        }
      />
      <CategoryForm key={data.id} category={data} onSaved={setData} />
    </>
  );
}
