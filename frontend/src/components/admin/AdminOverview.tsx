"use client";

import Link from "next/link";
import { PackageOpen, RefreshCw } from "lucide-react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { AdminStatCard } from "@/components/admin/AdminStatCard";
import { OrderStatusBadge } from "@/components/orders/OrderStatusBadge";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAdminDashboard } from "@/hooks/useAdminDashboard";
import { formatMoney } from "@/lib/money";
import { ORDER_STATUS_LABEL, PAYMENT_STATUS_LABEL, formatOrderDateTime } from "@/lib/order-format";
import type { AdminDashboard, AdminRecentOrder } from "@/types/admin";
import type { OrderStatus, PaymentStatus } from "@/types/order";

const STATUS_ORDER = Object.keys(ORDER_STATUS_LABEL) as OrderStatus[];

const isOrderStatus = (value: string): value is OrderStatus => value in ORDER_STATUS_LABEL;
const isPaymentStatus = (value: string): value is PaymentStatus => value in PAYMENT_STATUS_LABEL;

function plural(count: number, one: string, many = `${one}s`): string {
  return `${count.toLocaleString("en-IN")} ${count === 1 ? one : many}`;
}

function Skeleton() {
  return (
    <div role="status" aria-label="Loading the dashboard" className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {[0, 1].map((n) => (
          <div key={n} className="h-28 animate-pulse rounded-2xl bg-muted" />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {[0, 1, 2, 3].map((n) => (
          <div key={n} className="h-28 animate-pulse rounded-2xl bg-muted" />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-2xl bg-muted" />
    </div>
  );
}

function StatusBreakdown({ byStatus, total }: { byStatus: Record<string, number>; total: number }) {
  const known = STATUS_ORDER.map((status) => [status, ORDER_STATUS_LABEL[status], byStatus[status] ?? 0] as const);
  const unknown = Object.entries(byStatus)
    .filter(([status]) => !isOrderStatus(status))
    .map(([status, count]) => [status, status, count] as const);
  const rows = [...known, ...unknown];

  return (
    <Card className="p-6">
      <h2 className="font-display text-xl font-semibold text-foreground">Orders by status</h2>
      {total === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">No orders yet.</p>
      ) : (
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3 lg:grid-cols-4">
          {rows.map(([status, label, count]) => (
            <div key={status} className="flex items-baseline justify-between gap-2 border-b border-border/60 py-1.5">
              <dt className="text-sm text-muted-foreground">
                {count > 0 && isOrderStatus(status) ? (
                  <Link href={`/admin/orders?status=${status}`} className="hover:text-primary hover:underline">{label}</Link>
                ) : (
                  label
                )}
              </dt>
              <dd className="text-sm font-semibold text-foreground">{count.toLocaleString("en-IN")}</dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}

function RecentOrderRow({ order }: { order: AdminRecentOrder }) {
  return (
    <tr className="border-t border-border/60 align-top">
      <td className="py-3 pr-4 text-sm font-semibold text-foreground">
        <Link href={`/admin/orders/${order.id}`} className="hover:text-primary hover:underline">{order.order_number ?? "Order"}</Link>
      </td>
      <td className="py-3 pr-4 text-sm">
        <span className="block text-foreground">{order.customer_name}</span>
        <span className="block break-all text-xs text-muted-foreground">{order.customer_email}</span>
      </td>
      <td className="py-3 pr-4">
        {isOrderStatus(order.status) && isPaymentStatus(order.payment_status) ? (
          <OrderStatusBadge status={order.status} paymentStatus={order.payment_status} />
        ) : (
          <span className="text-sm text-muted-foreground">
            {order.status} / {order.payment_status}
          </span>
        )}
      </td>
      <td className="py-3 pr-4 text-right text-sm font-semibold text-foreground">{formatMoney(order.total_amount)}</td>
      <td className="whitespace-nowrap py-3 text-sm text-muted-foreground">{formatOrderDateTime(order.created_at)}</td>
    </tr>
  );
}

function RecentOrders({ orders }: { orders: AdminRecentOrder[] }) {
  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-xl font-semibold text-foreground">Recent orders</h2>
        <Link href="/admin/orders" className="text-sm font-medium text-primary hover:underline">View all orders</Link>
      </div>
      {orders.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-8 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-blob bg-primary-light text-primary">
            <PackageOpen className="h-6 w-6" aria-hidden="true" />
          </span>
          <p className="font-medium text-foreground">No orders yet</p>
          <p className="text-sm text-muted-foreground">New orders will appear here as customers check out.</p>
        </div>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left">
            <caption className="sr-only">The ten most recent orders</caption>
            <thead>
              <tr className="text-xs uppercase tracking-wide text-muted-foreground">
                <th scope="col" className="pb-2 pr-4 font-medium">Order</th>
                <th scope="col" className="pb-2 pr-4 font-medium">Customer</th>
                <th scope="col" className="pb-2 pr-4 font-medium">Status</th>
                <th scope="col" className="pb-2 pr-4 text-right font-medium">Total</th>
                <th scope="col" className="pb-2 font-medium">Placed</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <RecentOrderRow key={order.id} order={order} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function Numbers({ data }: { data: AdminDashboard }) {
  const { revenue, orders, customers, products } = data;
  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <AdminStatCard
          label="Revenue, last 30 days"
          value={formatMoney(revenue.last_30_days)}
          hint={`${plural(revenue.last_30_days_orders, "paid order")}`}
        />
        <AdminStatCard
          label="Revenue, all time"
          value={formatMoney(revenue.all_time)}
          hint={`${plural(revenue.all_time_orders, "paid order")} · includes GST and delivery`}
        />
      </div>

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <AdminStatCard label="Orders" value={orders.total.toLocaleString("en-IN")} links={[{ href: "/admin/orders", label: "View orders" }]} />
        <AdminStatCard
          label="Customers"
          value={customers.total.toLocaleString("en-IN")}
          hint={`${customers.new_last_30_days.toLocaleString("en-IN")} new in the last 30 days`}
        />
        <AdminStatCard
          label="Products"
          value={products.total.toLocaleString("en-IN")}
          hint={`${products.active.toLocaleString("en-IN")} active, ${products.inactive.toLocaleString("en-IN")} inactive`}
          links={[{ href: "/admin/products", label: "View products" }]}
        />
        <AdminStatCard
          label="Stock alerts"
          value={(products.low_stock + products.out_of_stock).toLocaleString("en-IN")}
          tone={products.low_stock + products.out_of_stock > 0 ? "warning" : "default"}
          hint={`${products.low_stock.toLocaleString("en-IN")} low, ${products.out_of_stock.toLocaleString("en-IN")} out of stock`}
          links={[
            { href: "/admin/inventory?stock=low", label: "Low stock" },
            { href: "/admin/inventory?stock=out", label: "Out of stock" },
          ]}
        />
      </div>

      <StatusBreakdown byStatus={orders.by_status} total={orders.total} />
      <RecentOrders orders={data.recent_orders} />
    </div>
  );
}

/** The admin overview: real numbers from GET /api/admin/dashboard. */
export function AdminOverview() {
  const { data, loading, error, reload } = useAdminDashboard();

  const refresh = (
    <Button type="button" variant="outline" size="sm" onClick={reload} disabled={loading}>
      <RefreshCw className={loading ? "animate-spin" : undefined} aria-hidden="true" />
      {loading && data ? "Refreshing" : "Refresh"}
    </Button>
  );

  return (
    <>
      <AdminPageHeader
        title="Overview"
        description={data ? `Updated ${formatOrderDateTime(data.generated_at)}` : "How the shop is doing."}
        actions={data ? refresh : null}
      />

      {data && error ? (
        <div className="mb-4">
          <Banner>{error} The numbers below are from the last successful load.</Banner>
        </div>
      ) : null}

      {data ? (
        <Numbers data={data} />
      ) : error ? (
        <div className="flex flex-col items-start gap-3">
          <Banner>{error}</Banner>
          <Button type="button" variant="outline" onClick={reload}>
            Try again
          </Button>
        </div>
      ) : (
        <Skeleton />
      )}
    </>
  );
}
