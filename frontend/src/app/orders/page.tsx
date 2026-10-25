"use client";

import { useState } from "react";
import Link from "next/link";
import { PackageOpen } from "lucide-react";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { OrderStatusBadge } from "@/components/orders/OrderStatusBadge";
import { Button } from "@/components/ui/button";
import { useOrders } from "@/hooks/useOrders";
import { formatMoney } from "@/lib/money";
import { formatOrderDate } from "@/lib/order-format";

const PAGE_SIZE = 10;

function OrdersSkeleton() {
  return (
    <div role="status" aria-label="Loading your orders" className="flex flex-col gap-4">
      {[0, 1, 2].map((n) => (
        <div key={n} className="h-28 animate-pulse rounded-2xl bg-muted" />
      ))}
    </div>
  );
}

function OrdersContent() {
  const [page, setPage] = useState(1);
  const { data, isLoading, error, reload } = useOrders(page, PAGE_SIZE);

  let body: React.ReactNode;
  if (!data && error) {
    body = (
      <div className="flex flex-col items-center gap-4 rounded-2xl border border-border bg-card px-6 py-16 text-center shadow-card">
        <p role="alert" className="max-w-sm text-foreground">
          {error}
        </p>
        <Button variant="primary" onClick={() => void reload()} disabled={isLoading}>
          {isLoading ? "Retrying..." : "Try again"}
        </Button>
      </div>
    );
  } else if (!data) {
    body = <OrdersSkeleton />;
  } else if (data.pagination.total === 0) {
    body = (
      <div className="flex flex-col items-center gap-4 rounded-2xl border border-border bg-card px-6 py-20 text-center shadow-card">
        <span className="flex h-16 w-16 items-center justify-center rounded-blob bg-primary-light text-primary">
          <PackageOpen className="h-8 w-8" aria-hidden="true" />
        </span>
        <h2 className="font-display text-2xl font-semibold text-foreground">No orders yet</h2>
        <p className="max-w-sm text-muted-foreground">When you place an order it will show up here.</p>
        <Button variant="primary" asChild>
          <Link href="/shop">Start shopping</Link>
        </Button>
      </div>
    );
  } else {
    const { orders, pagination } = data;
    body = (
      <div className="flex flex-col gap-4">
        {error ? (
          <p role="alert" className="text-sm text-accent-dark">
            {error}
          </p>
        ) : null}
        <ul aria-busy={isLoading} className="flex flex-col gap-4">
          {orders.map((order) => (
            <li key={order.id}>
              <Link
                href={`/orders/${order.id}`}
                className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-5 shadow-card transition-colors hover:bg-muted sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex flex-col gap-1">
                  <span className="font-display text-base font-semibold text-foreground">
                    {order.order_number ?? "Order"}
                  </span>
                  <span className="text-sm text-muted-foreground">Placed on {formatOrderDate(order.created_at)}</span>
                  <span className="text-sm text-foreground">
                    {order.item_names.join(", ")}
                    {order.line_count > order.item_names.length ? ` and ${order.line_count - order.item_names.length} more` : ""}
                  </span>
                </div>
                <div className="flex flex-col items-start gap-2 sm:items-end">
                  <OrderStatusBadge
                    status={order.status}
                    paymentStatus={order.payment_status}
                    cancellationReason={order.cancellation_reason}
                    canPay={order.can_pay}
                  />
                  {order.can_pay ? <span className="text-xs font-medium text-primary">Complete payment</span> : null}
                  <span className="font-display text-lg font-semibold text-foreground">{formatMoney(order.total)}</span>
                  <span className="text-xs text-muted-foreground">
                    {order.item_count} {order.item_count === 1 ? "item" : "items"}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>

        {pagination.total_pages > 1 ? (
          <nav aria-label="Order pages" className="flex items-center justify-between gap-3">
            <Button
              variant="outline"
              size="sm"
              disabled={!pagination.has_previous || isLoading}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {pagination.page} of {pagination.total_pages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={!pagination.has_next || isLoading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </nav>
        ) : null}
      </div>
    );
  }

  return <DashboardShell title="Your orders">{body}</DashboardShell>;
}

export default function OrdersPage() {
  return (
    <ProtectedRoute>
      <OrdersContent />
    </ProtectedRoute>
  );
}
