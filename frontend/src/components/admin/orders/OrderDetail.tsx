"use client";

import Link from "next/link";
import { ArrowLeft, RefreshCw } from "lucide-react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ListError, ListSkeleton } from "@/components/admin/ListStates";
import { OrderFulfilment } from "@/components/admin/orders/OrderFulfilment";
import { OrderStatusBadge } from "@/components/orders/OrderStatusBadge";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAdminQuery } from "@/hooks/useAdminQuery";
import { addressLines } from "@/lib/admin-orders";
import { formatMoney } from "@/lib/money";
import { formatOrderDateTime } from "@/lib/order-format";
import { getAdminOrder } from "@/services/admin-orders";
import type { AdminOrderDetail } from "@/types/admin-orders";

function Totals({ order }: { order: AdminOrderDetail }) {
  const { totals } = order;
  const rows: Array<[string, string, boolean?]> = [
    ["Subtotal", formatMoney(totals.subtotal)],
    ...(totals.discount > 0 ? ([[order.coupon_code ? `Discount (${order.coupon_code})` : "Discount", `-${formatMoney(totals.discount)}`]] as Array<[string, string]>) : []),
    [`GST (${Number(totals.gst_rate)}%)`, formatMoney(totals.gst)],
    ["Delivery", totals.delivery_charge > 0 ? formatMoney(totals.delivery_charge) : "Free"],
    ["Total", formatMoney(totals.total), true],
  ];
  return (
    <dl className="ml-auto mt-4 w-full max-w-xs">
      {rows.map(([label, value, strong]) => (
        <div key={label} className={`flex items-baseline justify-between gap-4 py-1 text-sm ${strong ? "border-t border-border/60 pt-2 font-semibold text-foreground" : "text-muted-foreground"}`}>
          <dt>{label}</dt>
          <dd className={strong ? "" : "text-foreground"}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** One order in full, read-only apart from the fulfilment step. */
export function OrderDetail({ id }: { id: string }) {
  const { data, loading, error, reload, setData } = useAdminQuery(`order:${id}`, () => getAdminOrder(id), {
    failure: "We couldn't load this order.",
  });

  if (!data) {
    return (
      <>
        <AdminPageHeader title="Order" actions={<BackLink />} />
        {loading ? <ListSkeleton label="Loading the order" /> : <ListError message={error ?? "We couldn't load this order."} onRetry={reload} />}
      </>
    );
  }

  const order = data;
  const refundDue = order.payments.filter((p) => p.refund_required);
  const address = addressLines(order.shipping_address);

  return (
    <>
      <AdminPageHeader
        title={order.order_number ? `Order ${order.order_number}` : "Order"}
        description={`Placed ${formatOrderDateTime(order.created_at)}`}
        actions={
          <>
            <OrderStatusBadge status={order.status} paymentStatus={order.payment_status} cancellationReason={order.cancellation_reason} />
            <BackLink />
            <Button type="button" variant="outline" size="sm" onClick={reload} disabled={loading}>
              <RefreshCw className={loading ? "animate-spin" : undefined} aria-hidden="true" />
              {loading ? "Refreshing" : "Refresh"}
            </Button>
          </>
        }
      />

      {error ? (
        <div className="mb-4">
          <Banner>{error} What you see is from the last successful load.</Banner>
        </div>
      ) : null}
      {refundDue.length > 0 ? (
        <div className="mb-4">
          <Banner>
            A payment on this order needs a refund ({refundDue.map((p) => formatMoney(p.amount)).join(", ")}): the customer was charged but the order could not be completed.
            Refunds are made in the payment gateway dashboard, not here.
          </Banner>
        </div>
      ) : null}

      <div className="flex flex-col gap-6">
        <OrderFulfilment order={order} onAdvanced={setData} onStale={reload} />

        <div className="grid gap-6 md:grid-cols-2">
          <Card className="p-6">
            <h2 className="font-display text-xl font-semibold text-foreground">Customer</h2>
            <p className="mt-2 text-sm font-medium text-foreground">{order.customer.name}</p>
            <p className="break-all text-sm text-muted-foreground">
              <a href={`mailto:${order.customer.email}`} className="hover:text-primary hover:underline">{order.customer.email}</a>
            </p>
            {order.customer.phone_number ? <p className="text-sm text-muted-foreground">{order.customer.phone_number}</p> : null}
          </Card>
          <Card className="p-6">
            <h2 className="font-display text-xl font-semibold text-foreground">Ship to</h2>
            {address.length > 0 ? (
              <address className="mt-2 text-sm not-italic text-foreground">
                {address.map((line, index) => (
                  <span key={`${index}-${line}`} className="block">{line}</span>
                ))}
              </address>
            ) : (
              <p className="mt-2 text-sm text-muted-foreground">No address was recorded.</p>
            )}
          </Card>
        </div>

        <Card className="p-6">
          <h2 className="font-display text-xl font-semibold text-foreground">Items</h2>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[32rem] text-left">
              <caption className="sr-only">Items in this order</caption>
              <thead>
                <tr className="text-xs uppercase tracking-wide text-muted-foreground">
                  <th scope="col" className="pb-2 pr-4 font-medium">Product</th>
                  <th scope="col" className="pb-2 pr-4 text-right font-medium">Price</th>
                  <th scope="col" className="pb-2 pr-4 text-right font-medium">Qty</th>
                  <th scope="col" className="pb-2 text-right font-medium">Subtotal</th>
                </tr>
              </thead>
              <tbody>
                {order.items.map((line, index) => (
                  <tr key={`${line.sku}-${index}`} className="border-t border-border/60 align-top">
                    <td className="py-3 pr-4 text-sm">
                      {line.product_id ? (
                        <Link href={`/admin/products/${line.product_id}`} className="font-medium text-foreground hover:text-primary hover:underline">{line.name}</Link>
                      ) : (
                        <span className="font-medium text-foreground">{line.name}</span>
                      )}
                      <span className="block text-xs text-muted-foreground">{line.sku}</span>
                    </td>
                    <td className="py-3 pr-4 text-right text-sm text-foreground">{formatMoney(line.unit_price)}</td>
                    <td className="py-3 pr-4 text-right text-sm text-foreground">{line.quantity.toLocaleString("en-IN")}</td>
                    <td className="py-3 text-right text-sm font-semibold text-foreground">{formatMoney(line.subtotal)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Totals order={order} />
        </Card>

        <Card className="p-6">
          <h2 className="font-display text-xl font-semibold text-foreground">Payments</h2>
          {order.payments.length === 0 ? (
            <p className="mt-2 text-sm text-muted-foreground">No payment has been attempted.</p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[36rem] text-left">
                <caption className="sr-only">Payment attempts</caption>
                <thead>
                  <tr className="text-xs uppercase tracking-wide text-muted-foreground">
                    <th scope="col" className="pb-2 pr-4 font-medium">Attempt</th>
                    <th scope="col" className="pb-2 pr-4 font-medium">Status</th>
                    <th scope="col" className="pb-2 pr-4 text-right font-medium">Amount</th>
                    <th scope="col" className="pb-2 font-medium">Gateway reference</th>
                  </tr>
                </thead>
                <tbody>
                  {order.payments.map((payment) => (
                    <tr key={payment.id} className="border-t border-border/60 align-top">
                      <td className="whitespace-nowrap py-3 pr-4 text-sm text-foreground">{formatOrderDateTime(payment.created_at)}</td>
                      <td className="py-3 pr-4 text-sm">
                        <span className="font-medium capitalize text-foreground">{payment.status}</span>
                        {payment.paid_at ? <span className="block text-xs text-muted-foreground">Paid {formatOrderDateTime(payment.paid_at)}</span> : null}
                        {payment.failure_reason ? <span className="block text-xs text-muted-foreground">{payment.failure_reason}</span> : null}
                        {payment.refund_required ? <span className="block text-xs font-medium text-accent-dark">Refund required</span> : null}
                      </td>
                      <td className="py-3 pr-4 text-right text-sm text-foreground">{formatMoney(payment.amount)}</td>
                      <td className="break-all py-3 text-xs text-muted-foreground">
                        {payment.gateway_order_id ? <span className="block">Order {payment.gateway_order_id}</span> : null}
                        {payment.gateway_payment_id ? <span className="block">Payment {payment.gateway_payment_id}</span> : null}
                        {!payment.gateway_order_id && !payment.gateway_payment_id ? "—" : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card className="p-6">
          <h2 className="font-display text-xl font-semibold text-foreground">Timeline</h2>
          <dl className="mt-2 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
            <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Placed</dt><dd className="text-foreground">{formatOrderDateTime(order.created_at)}</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Last updated</dt><dd className="text-foreground">{formatOrderDateTime(order.updated_at)}</dd></div>
            {order.cancelled_at ? (
              <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Cancelled</dt><dd className="text-foreground">{formatOrderDateTime(order.cancelled_at)}</dd></div>
            ) : null}
            {order.status === "pending" && order.expires_at ? (
              <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Pay by</dt><dd className="text-foreground">{formatOrderDateTime(order.expires_at)}</dd></div>
            ) : null}
            {order.reserved_units > 0 ? (
              <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Stock held</dt><dd className="text-foreground">{order.reserved_units.toLocaleString("en-IN")} unit{order.reserved_units === 1 ? "" : "s"}</dd></div>
            ) : null}
          </dl>
        </Card>
      </div>
    </>
  );
}

function BackLink() {
  return (
    <Button asChild variant="outline" size="sm">
      <Link href="/admin/orders">
        <ArrowLeft aria-hidden="true" />
        All orders
      </Link>
    </Button>
  );
}
