"use client";

import Link from "next/link";
import { PackageOpen } from "lucide-react";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { OrderStatusBadge } from "@/components/orders/OrderStatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAuth } from "@/context/AuthContext";
import { useDashboardOverview, type Section, type SectionKey } from "@/hooks/useDashboardOverview";
import { formatMoney } from "@/lib/money";
import { formatOrderDate } from "@/lib/order-format";
import type { OrderList } from "@/types/order";

const TEXT_LINK = "text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded";

interface StatTileProps {
  label: string;
  section: Section<number>;
  sectionKey: SectionKey;
  onRetry: (key: SectionKey) => void;
  href?: string;
}

function StatTile({ label, section, sectionKey, onRetry, href }: StatTileProps) {
  let value: React.ReactNode;
  if (section.status === "loading") {
    value = <span role="status" aria-label={`Loading ${label}`} className="block h-8 w-12 animate-pulse rounded-lg bg-muted" />;
  } else if (section.status === "error") {
    value = (
      <span className="flex flex-col items-start gap-1">
        <span role="alert" className="text-xs text-accent-dark">
          Couldn&apos;t load
        </span>
        <button type="button" className={TEXT_LINK} onClick={() => onRetry(sectionKey)} aria-label={`Retry ${label}`}>
          Retry
        </button>
      </span>
    );
  } else {
    value = <span className="font-display text-3xl font-semibold text-foreground">{section.data}</span>;
  }

  const body = (
    <>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="mt-2 min-h-8">{value}</div>
    </>
  );

  return <Card role="group" aria-label={label} className="p-5">{href && section.status !== "error" ? <Link href={href} className="block">{body}</Link> : body}</Card>;
}

function RecentOrders({ section, onRetry }: { section: Section<OrderList>; onRetry: (key: SectionKey) => void }) {
  let body: React.ReactNode;
  if (section.status === "loading") {
    body = (
      <div role="status" aria-label="Loading recent orders" className="flex flex-col gap-3">
        {[0, 1, 2].map((n) => (
          <div key={n} className="h-16 animate-pulse rounded-xl bg-muted" />
        ))}
      </div>
    );
  } else if (section.status === "error") {
    body = (
      <div className="flex flex-col items-start gap-3">
        <p role="alert" className="text-sm text-foreground">
          {section.message}
        </p>
        <Button type="button" variant="outline" size="sm" onClick={() => onRetry("orders")}>
          Try again
        </Button>
      </div>
    );
  } else if (section.data.pagination.total === 0) {
    body = (
      <div className="flex flex-col items-center gap-3 py-6 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-blob bg-primary-light text-primary">
          <PackageOpen className="h-6 w-6" aria-hidden="true" />
        </span>
        <p className="font-medium text-foreground">No orders yet</p>
        <p className="text-sm text-muted-foreground">When you place an order it will show up here.</p>
        <Button variant="primary" size="sm" asChild>
          <Link href="/shop">Start shopping</Link>
        </Button>
      </div>
    );
  } else {
    body = (
      <ul className="flex flex-col divide-y divide-border">
        {section.data.orders.map((order) => (
          <li key={order.id}>
            <Link
              href={`/orders/${order.id}`}
              className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-3 hover:text-primary"
            >
              <span className="flex flex-col">
                <span className="text-sm font-semibold text-foreground">{order.order_number ?? "Order"}</span>
                <span className="text-xs text-muted-foreground">{formatOrderDate(order.created_at)}</span>
              </span>
              <OrderStatusBadge
                status={order.status}
                paymentStatus={order.payment_status}
                cancellationReason={order.cancellation_reason}
                canPay={order.can_pay}
              />
              <span className="text-sm font-semibold text-foreground">{formatMoney(order.total)}</span>
            </Link>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <Card className="p-6">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-display text-xl font-semibold text-foreground">Recent orders</h2>
        <Link href="/orders" className={TEXT_LINK}>
          View all
        </Link>
      </div>
      {body}
    </Card>
  );
}

function OverviewContent() {
  const { user } = useAuth();
  const overview = useDashboardOverview();
  if (!user) return null;

  const ordersTotal: Section<number> =
    overview.orders.status === "ready"
      ? { status: "ready", data: overview.orders.data.pagination.total }
      : overview.orders.status === "error"
        ? { status: "error", message: overview.orders.message }
        : { status: "loading" };

  return (
    <DashboardShell title="Overview" description={`Welcome back, ${user.first_name}.`}>
      <div className="flex flex-col gap-6">
        <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
          <StatTile label="Orders" section={ordersTotal} sectionKey="orders" onRetry={overview.retry} href="/orders" />
          <StatTile label="Wishlist" section={overview.wishlist} sectionKey="wishlist" onRetry={overview.retry} href="/dashboard/wishlist" />
          <StatTile label="Saved addresses" section={overview.addresses} sectionKey="addresses" onRetry={overview.retry} href="/dashboard/addresses" />
          <StatTile label="Invoices" section={overview.invoices} sectionKey="invoices" onRetry={overview.retry} href="/dashboard/invoices" />
        </div>
        <RecentOrders section={overview.orders} onRetry={overview.retry} />
      </div>
    </DashboardShell>
  );
}

export default function DashboardPage() {
  return (
    <ProtectedRoute>
      <OverviewContent />
    </ProtectedRoute>
  );
}
