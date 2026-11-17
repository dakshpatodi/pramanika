"use client";

import Link from "next/link";
import { useState } from "react";
import { Search } from "lucide-react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ListEmpty, ListError, ListSkeleton } from "@/components/admin/ListStates";
import { OrderStatusBadge } from "@/components/orders/OrderStatusBadge";
import { Pagination } from "@/components/products/Pagination";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useAdminQuery } from "@/hooks/useAdminQuery";
import { NEXT_ACTION_LABEL, dayRangeBackwards, dayRangeParams } from "@/lib/admin-orders";
import { formatMoney } from "@/lib/money";
import { ORDER_STATUS_LABEL, PAYMENT_STATUS_LABEL, formatOrderDateTime } from "@/lib/order-format";
import { listAdminOrders } from "@/services/admin-orders";
import type { SortOrder } from "@/types/admin-catalog";
import type { AdminOrderListParams, AdminOrderSort } from "@/types/admin-orders";
import type { OrderStatus, PaymentStatus } from "@/types/order";

const PAGE_SIZE = 20;

const SORTS: Array<{ value: string; label: string; sort: AdminOrderSort; order: SortOrder }> = [
  { value: "created_at-desc", label: "Newest first", sort: "created_at", order: "desc" },
  { value: "created_at-asc", label: "Oldest first", sort: "created_at", order: "asc" },
  { value: "total-desc", label: "Total: high to low", sort: "total", order: "desc" },
  { value: "total-asc", label: "Total: low to high", sort: "total", order: "asc" },
  { value: "order_number-asc", label: "Order number", sort: "order_number", order: "asc" },
];

const STATUSES = Object.keys(ORDER_STATUS_LABEL) as OrderStatus[];
const PAYMENTS = Object.keys(PAYMENT_STATUS_LABEL) as PaymentStatus[];

/** Every order, searchable, filterable by status / payment / placed date, sortable and paged. `initialStatus` lets a link open it pre-filtered. */
export function OrdersList({ initialStatus }: { initialStatus?: OrderStatus }) {
  const [searchText, setSearchText] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<"" | OrderStatus>(initialStatus ?? "");
  const [payment, setPayment] = useState<"" | PaymentStatus>("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [sortKey, setSortKey] = useState(SORTS[0].value);
  const [page, setPage] = useState(1);

  const backwards = dayRangeBackwards(from, to);
  const chosen = SORTS.find((s) => s.value === sortKey) ?? SORTS[0];
  const params: AdminOrderListParams = {
    page,
    page_size: PAGE_SIZE,
    search: search || undefined,
    status: status || undefined,
    payment_status: payment || undefined,
    ...(backwards ? {} : dayRangeParams(from, to)),
    sort: chosen.sort,
    order: chosen.order,
  };
  const { data, loading, error, reload } = useAdminQuery(JSON.stringify(params), () => listAdminOrders(params), {
    failure: "We couldn't load the orders.",
    keepPrevious: true,
  });
  const filtered = search !== "" || status !== "" || payment !== "" || from !== "" || to !== "";

  const change = <T,>(set: (value: T) => void) => (value: T) => {
    set(value);
    setPage(1);
  };

  return (
    <>
      <AdminPageHeader title="Orders" description="Every order. Open one to see the details and move a paid order forward." />

      <form
        role="search"
        aria-label="Filter orders"
        className="mb-4 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          setSearch(searchText.trim());
          setPage(1);
        }}
      >
        <div className="flex min-w-48 flex-1 flex-col gap-1">
          <label htmlFor="order-search" className="text-xs font-medium text-muted-foreground">Search</label>
          <Input id="order-search" value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder="Order number, customer name, email or phone" maxLength={100} />
        </div>
        <Button type="submit" variant="outline" size="md">
          <Search aria-hidden="true" />
          Search
        </Button>
        <div className="flex flex-col gap-1">
          <label htmlFor="order-status-filter" className="text-xs font-medium text-muted-foreground">Status</label>
          <Select id="order-status-filter" value={status} onChange={(e) => change(setStatus)(e.target.value as "" | OrderStatus)}>
            <option value="">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{ORDER_STATUS_LABEL[s]}</option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="order-payment-filter" className="text-xs font-medium text-muted-foreground">Payment</label>
          <Select id="order-payment-filter" value={payment} onChange={(e) => change(setPayment)(e.target.value as "" | PaymentStatus)}>
            <option value="">All</option>
            {PAYMENTS.map((p) => (
              <option key={p} value={p}>{PAYMENT_STATUS_LABEL[p]}</option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="order-from" className="text-xs font-medium text-muted-foreground">Placed from</label>
          <Input id="order-from" type="date" value={from} max={to || undefined} onChange={(e) => change(setFrom)(e.target.value)} invalid={backwards} aria-describedby={backwards ? "order-dates-error" : undefined} />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="order-to" className="text-xs font-medium text-muted-foreground">Placed to</label>
          <Input id="order-to" type="date" value={to} min={from || undefined} onChange={(e) => change(setTo)(e.target.value)} invalid={backwards} aria-describedby={backwards ? "order-dates-error" : undefined} />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="order-sort" className="text-xs font-medium text-muted-foreground">Sort by</label>
          <Select id="order-sort" value={sortKey} onChange={(e) => change(setSortKey)(e.target.value)}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </Select>
        </div>
        {backwards ? (
          <p id="order-dates-error" className="w-full text-xs text-accent-dark">
            “Placed to” is before “Placed from”, so the dates are not applied. Fix one of them.
          </p>
        ) : null}
      </form>

      {data && error ? (
        <div className="mb-4">
          <Banner>{error} Showing the last result.</Banner>
        </div>
      ) : null}

      {!data && loading ? (
        <ListSkeleton label="Loading orders" />
      ) : !data && error ? (
        <ListError message={error} onRetry={reload} />
      ) : data ? (
        <Card className="p-4 sm:p-6" aria-busy={loading}>
          {data.orders.length === 0 ? (
            filtered ? (
              <ListEmpty title="No orders match" hint="Try a different search, status or date range." />
            ) : (
              <ListEmpty title="No orders yet" hint="Orders appear here as customers check out." />
            )
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[56rem] text-left">
                <caption className="sr-only">Orders</caption>
                <thead>
                  <tr className="text-xs uppercase tracking-wide text-muted-foreground">
                    <th scope="col" className="pb-2 pr-4 font-medium">Order</th>
                    <th scope="col" className="pb-2 pr-4 font-medium">Customer</th>
                    <th scope="col" className="pb-2 pr-4 font-medium">Status</th>
                    <th scope="col" className="pb-2 pr-4 text-right font-medium">Items</th>
                    <th scope="col" className="pb-2 pr-4 text-right font-medium">Total</th>
                    <th scope="col" className="pb-2 pr-4 font-medium">Placed</th>
                    <th scope="col" className="pb-2 font-medium"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data.orders.map((order) => (
                    <tr key={order.id} className="border-t border-border/60 align-middle">
                      <td className="py-3 pr-4 text-sm">
                        <Link href={`/admin/orders/${order.id}`} className="font-semibold text-foreground hover:text-primary hover:underline">
                          {order.order_number ?? "Order"}
                        </Link>
                      </td>
                      <td className="py-3 pr-4 text-sm">
                        <span className="block text-foreground">{order.customer_name}</span>
                        <span className="block break-all text-xs text-muted-foreground">{order.customer_email}</span>
                      </td>
                      <td className="py-3 pr-4 text-sm">
                        <OrderStatusBadge status={order.status} paymentStatus={order.payment_status} cancellationReason={order.cancellation_reason} />
                        {order.next_status ? (
                          <span className="mt-1 block text-xs text-muted-foreground">Next: {NEXT_ACTION_LABEL[order.next_status].replace("Mark as ", "")}</span>
                        ) : null}
                      </td>
                      <td className="py-3 pr-4 text-right text-sm text-foreground">{order.item_count.toLocaleString("en-IN")}</td>
                      <td className="py-3 pr-4 text-right text-sm font-semibold text-foreground">{formatMoney(order.total_amount)}</td>
                      <td className="whitespace-nowrap py-3 pr-4 text-sm text-muted-foreground">{formatOrderDateTime(order.created_at)}</td>
                      <td className="py-3">
                        <div className="flex justify-end">
                          <Button asChild variant="outline" size="sm">
                            <Link href={`/admin/orders/${order.id}`} aria-label={`View order ${order.order_number ?? order.id}`}>View</Link>
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
