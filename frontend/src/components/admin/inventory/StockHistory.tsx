"use client";

import { ListError } from "@/components/admin/ListStates";
import { Card } from "@/components/ui/card";
import { useAdminQuery } from "@/hooks/useAdminQuery";
import { describeStockEvent } from "@/lib/admin-inventory-form";
import { formatOrderDateTime } from "@/lib/order-format";
import { listAdminAuditEvents } from "@/services/admin-inventory";

const SHOWN = 10;

/** The latest stock changes for one product, from the admin audit trail (who, when, what, why). */
export function StockHistory({ productId, version }: { productId: string; version: number }) {
  const { data, loading, error, reload } = useAdminQuery(
    `stock-history:${productId}:${version}`,
    () => listAdminAuditEvents({ entity_type: "inventory", entity_id: productId, page_size: SHOWN }),
    { failure: "We couldn't load the change history.", keepPrevious: true }
  );

  return (
    <Card className="p-6" aria-busy={loading}>
      <h2 className="font-display text-xl font-semibold text-foreground">Change history</h2>
      {!data && loading ? (
        <p role="status" className="mt-3 text-sm text-muted-foreground">Loading the history…</p>
      ) : !data && error ? (
        <div className="mt-3">
          <ListError message={error} onRetry={reload} />
        </div>
      ) : data && data.events.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">No changes have been made here yet.</p>
      ) : data ? (
        <>
          <ol className="mt-3 flex flex-col divide-y divide-border/60">
            {data.events.map((event) => {
              const { summary, reason } = describeStockEvent(event);
              return (
                <li key={event.id} className="py-2.5 text-sm">
                  <p className="font-medium text-foreground">{summary}</p>
                  {reason ? <p className="text-muted-foreground">Note: {reason}</p> : null}
                  <p className="text-xs text-muted-foreground">
                    {event.admin_email} · {formatOrderDateTime(event.created_at)}
                  </p>
                </li>
              );
            })}
          </ol>
          {data.pagination.total > SHOWN ? (
            <p className="mt-2 text-xs text-muted-foreground">Showing the latest {SHOWN} of {data.pagination.total.toLocaleString("en-IN")} changes.</p>
          ) : null}
        </>
      ) : null}
    </Card>
  );
}
