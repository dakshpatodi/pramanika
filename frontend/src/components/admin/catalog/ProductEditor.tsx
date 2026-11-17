"use client";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ListError, ListSkeleton } from "@/components/admin/ListStates";
import { ActiveToggle } from "@/components/admin/catalog/ActiveToggle";
import { ProductForm } from "@/components/admin/catalog/ProductForm";
import { ActiveBadge, StockBadge } from "@/components/admin/catalog/badges";
import { useAdminQuery } from "@/hooks/useAdminQuery";
import { getAdminProduct } from "@/services/admin-catalog";

/** One product: its form, state, stock badge and activate / deactivate button. */
export function ProductEditor({ id }: { id: string }) {
  const { data, loading, error, reload, setData } = useAdminQuery(`product:${id}`, () => getAdminProduct(id), {
    failure: "We couldn't load this product.",
  });

  if (!data) {
    return (
      <>
        <AdminPageHeader title="Product" />
        {loading ? <ListSkeleton label="Loading the product" /> : <ListError message={error ?? "We couldn't load this product."} onRetry={reload} />}
      </>
    );
  }

  return (
    <>
      <AdminPageHeader
        title={data.name}
        description={`SKU ${data.sku}`}
        actions={
          <>
            <ActiveBadge active={data.is_active} />
            <StockBadge status={data.stock_status} />
            <ActiveToggle kind="product" id={data.id} name={data.name} active={data.is_active} onChanged={reload} />
          </>
        }
      />
      <ProductForm key={data.id} product={data} onSaved={setData} />
    </>
  );
}
