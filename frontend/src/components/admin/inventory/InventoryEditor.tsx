"use client";

import Link from "next/link";
import { useState } from "react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { AdminStatCard } from "@/components/admin/AdminStatCard";
import { ListError, ListSkeleton } from "@/components/admin/ListStates";
import { ActiveBadge, StockBadge } from "@/components/admin/catalog/badges";
import { StockAdjustForm } from "@/components/admin/inventory/StockAdjustForm";
import { StockHistory } from "@/components/admin/inventory/StockHistory";
import { ThresholdForm } from "@/components/admin/inventory/ThresholdForm";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAdminQuery } from "@/hooks/useAdminQuery";
import { getAdminInventory } from "@/services/admin-inventory";

const units = (n: number) => `${n.toLocaleString("en-IN")} unit${n === 1 ? "" : "s"}`;

/** One product's stock: figures, what holds the reservation, change forms and history. */
export function InventoryEditor({ id }: { id: string }) {
  const { data, loading, error, reload, setData } = useAdminQuery(`inventory:${id}`, () => getAdminInventory(id), {
    failure: "We couldn't load this product's stock.",
  });
  const [version, setVersion] = useState(0);

  if (!data) {
    return (
      <>
        <AdminPageHeader title="Stock" />
        {loading ? <ListSkeleton label="Loading the stock" /> : <ListError message={error ?? "We couldn't load this product's stock."} onRetry={reload} />}
      </>
    );
  }

  const updated = (next: typeof data) => {
    setData(next);
    setVersion((v) => v + 1);
  };

  return (
    <>
      <AdminPageHeader
        title={data.name}
        description={`SKU ${data.sku} · ${data.category.name}`}
        actions={
          <>
            <StockBadge status={data.stock_status} />
            {data.is_active ? null : <ActiveBadge active={false} />}
            <Button asChild variant="outline" size="sm">
              <Link href={`/admin/products/${data.product_id}`}>Edit product</Link>
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={reload} disabled={loading}>
              {loading ? "Refreshing" : "Refresh"}
            </Button>
          </>
        }
      />

      {error ? (
        <div className="mb-4">
          <Banner>{error} The figures below are from the last successful load.</Banner>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <AdminStatCard label="In stock" value={data.quantity.toLocaleString("en-IN")} />
        <AdminStatCard label="Reserved" value={data.reserved_quantity.toLocaleString("en-IN")} hint="Held by open, unpaid orders" />
        <AdminStatCard
          label="Available to sell"
          value={data.available_quantity.toLocaleString("en-IN")}
          tone={data.stock_status === "ok" ? "default" : "warning"}
        />
        <AdminStatCard label="Low-stock warning at" value={data.low_stock_threshold === null ? "Not set" : data.low_stock_threshold.toLocaleString("en-IN")} />
      </div>

      <Card className="mt-6 p-6">
        <h2 className="font-display text-xl font-semibold text-foreground">Reservations</h2>
        {data.open_order_count === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">No open orders are holding stock for this product.</p>
        ) : (
          <p className="mt-2 text-sm text-foreground">
            {data.open_order_count.toLocaleString("en-IN")} open order{data.open_order_count === 1 ? "" : "s"} hold {units(data.open_order_units)} until the
            customer pays or the order expires.{" "}
            <Link href="/admin/orders?status=pending" className="font-medium text-primary hover:underline">View pending orders</Link>
          </p>
        )}
        {!data.reservations_match ? (
          <div className="mt-3">
            <Banner>
              The reserved count ({units(data.reserved_quantity)}) does not match what open orders hold ({units(data.open_order_units)}). Nothing was
              changed automatically. Check the pending orders before adjusting stock.
            </Banner>
          </div>
        ) : null}
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <h2 className="font-display text-xl font-semibold text-foreground">Change stock</h2>
          <p className="mb-4 mt-1 text-sm text-muted-foreground">Stock can never go below what open orders have reserved.</p>
          <StockAdjustForm key={data.product_id} item={data} onUpdated={updated} onStale={reload} />
        </Card>
        <Card className="p-6">
          <h2 className="font-display text-xl font-semibold text-foreground">Low-stock warning</h2>
          <p className="mb-4 mt-1 text-sm text-muted-foreground">Decide when this product should be flagged for restocking.</p>
          <ThresholdForm key={data.product_id} item={data} onUpdated={updated} />
        </Card>
      </div>

      <div className="mt-6">
        <StockHistory productId={data.product_id} version={version} />
      </div>
    </>
  );
}
