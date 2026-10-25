"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { InvoiceDownloadButton } from "@/components/invoices/InvoiceDownloadButton";
import { OrderPaymentPanel } from "@/components/orders/OrderPaymentPanel";
import { OrderStatusBadge } from "@/components/orders/OrderStatusBadge";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { useOrder } from "@/hooks/useOrder";
import { usePayment } from "@/hooks/usePayment";
import { formatMoney, formatPercent } from "@/lib/money";
import { describeOrder, formatOrderDateTime } from "@/lib/order-format";
import type { Order } from "@/types/order";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section aria-label={title} className="rounded-2xl border border-border bg-card p-5 shadow-card sm:p-6">
      <h2 className="mb-4 border-b border-border pb-4 font-display text-lg font-semibold text-foreground">{title}</h2>
      {children}
    </section>
  );
}

function Row({ label, value, muted = false }: { label: string; value: React.ReactNode; muted?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={muted ? "font-medium text-primary" : "font-medium text-foreground"}>{value}</dd>
    </div>
  );
}

function OrderSkeleton() {
  return (
    <div role="status" aria-label="Loading your order" className="flex flex-col gap-6">
      <div className="h-24 animate-pulse rounded-2xl bg-muted" />
      <div className="h-64 animate-pulse rounded-2xl bg-muted" />
    </div>
  );
}

function CancelControl({
  disabled,
  onConfirm,
}: {
  disabled: boolean;
  onConfirm: () => void;
}) {
  const [confirming, setConfirming] = useState(false);

  if (!confirming) {
    return (
      <Button variant="outline" onClick={() => setConfirming(true)} disabled={disabled}>
        Cancel order
      </Button>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      <span className="text-foreground">Cancel this order?</span>
      <Button
        variant="accent"
        size="sm"
        disabled={disabled}
        onClick={() => {
          setConfirming(false);
          onConfirm();
        }}
      >
        Yes, cancel order
      </Button>
      <Button variant="ghost" size="sm" disabled={disabled} onClick={() => setConfirming(false)}>
        Keep order
      </Button>
    </div>
  );
}

function OrderDetails({ order, isCancelling, cancelError, onCancel, onReload }: {
  order: Order;
  isCancelling: boolean;
  cancelError: string | null;
  onCancel: () => void;
  onReload: () => Promise<void>;
}) {
  const payment = usePayment();
  const paying = payment.isBusy;

  // Whatever happens at Razorpay, the page then shows what the SERVER says:
  // paid, still payable, or closed (cancelled / expired) in the meantime.
  const startPayment = () => {
    void payment.pay(order).then((outcome) => {
      if (outcome === "paid" || outcome === "closed") return onReload();
      return undefined;
    });
  };
  const checkPayment = () => {
    void payment.retryVerification(order).then((outcome) => {
      if (outcome === "paid" || outcome === "closed") return onReload();
      return undefined;
    });
  };

  const { totals, shipping_address: address } = order;
  const cancelled = order.status === "cancelled";

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-5 shadow-card sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm text-muted-foreground">Order</p>
            <h1 className="font-display text-2xl font-semibold text-foreground">{order.order_number ?? "Your order"}</h1>
            <p className="mt-1 text-sm text-muted-foreground">Placed on {formatOrderDateTime(order.created_at)}</p>
          </div>
          <OrderStatusBadge
            status={order.status}
            paymentStatus={order.payment_status}
            cancellationReason={order.cancellation_reason}
            canPay={order.can_pay}
          />
        </div>
        <p className="text-sm text-foreground">{describeOrder(order)}</p>

        {order.payment_status === "paid" && payment.phase === "paid" ? (
          <p role="status" className="text-sm font-medium text-primary">
            Payment received. Thank you!
          </p>
        ) : null}
        {order.payment.refund_pending ? (
          <Banner>
            We received a payment for this order after it had closed. It wasn&apos;t used for the order, and it will be
            refunded to you.
          </Banner>
        ) : null}
        {order.can_pay ? (
          <OrderPaymentPanel
            order={order}
            phase={payment.phase}
            error={payment.error}
            isBusy={paying}
            onPay={startPayment}
            onCheckPayment={checkPayment}
            onRefresh={() => void onReload()}
            onDeadlinePassed={() => void onReload()}
          />
        ) : null}

        {cancelError ? <Banner>{cancelError}</Banner> : null}
        {order.can_cancel ? <CancelControl disabled={isCancelling || paying} onConfirm={onCancel} /> : null}
        {isCancelling ? (
          <p role="status" className="text-sm text-muted-foreground">
            Cancelling your order...
          </p>
        ) : null}
      </header>

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <Section title="Items">
          <ul className="divide-y divide-border">
            {order.items.map((item) => (
              <li key={item.id} className="flex items-start justify-between gap-4 py-3 text-sm">
                <div className="flex flex-col gap-0.5">
                  <span className="font-medium text-foreground">{item.product_name}</span>
                  <span className="text-muted-foreground">
                    {item.quantity} x {formatMoney(item.unit_price)}
                  </span>
                </div>
                <span className="font-medium text-foreground">{formatMoney(item.line_total)}</span>
              </li>
            ))}
          </ul>
        </Section>

        <div className="flex flex-col gap-6">
          <Section title="Order total">
            <dl className="flex flex-col gap-3">
              <Row label="Subtotal" value={formatMoney(totals.subtotal)} />
              {totals.discount > 0 ? (
                <Row
                  label={order.coupon_code ? `Discount (${order.coupon_code})` : "Discount"}
                  value={`-${formatMoney(totals.discount)}`}
                  muted
                />
              ) : null}
              <Row label={`GST (${formatPercent(totals.gst_rate)})`} value={formatMoney(totals.gst)} />
              <Row
                label="Delivery"
                value={totals.delivery_charge > 0 ? formatMoney(totals.delivery_charge) : "Free"}
                muted={totals.delivery_charge === 0}
              />
              <div className="flex items-baseline justify-between gap-4 border-t border-border pt-4">
                <dt className="font-display text-base font-semibold text-foreground">
                  {cancelled ? (order.cancellation_reason === "expired" ? "Total (expired)" : "Total (cancelled)") : "Total"}
                </dt>
                <dd className="font-display text-2xl font-semibold text-foreground">{formatMoney(totals.total)}</dd>
              </div>
            </dl>
          </Section>

          <Section title="Delivery address">
            <address className="flex flex-col gap-0.5 text-sm not-italic text-foreground">
              <span className="font-medium">{address.full_name}</span>
              <span>
                {address.address_line_1}
                {address.address_line_2 ? `, ${address.address_line_2}` : ""}
              </span>
              <span>
                {address.city}, {address.state} {address.postal_code}
              </span>
              <span>{address.country}</span>
              <span className="text-muted-foreground">Phone: {address.phone_number}</span>
            </address>
          </Section>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <Button variant="primary" asChild>
          <Link href="/shop">Continue shopping</Link>
        </Button>
        {order.payment_status === "paid" ? (
          <InvoiceDownloadButton orderId={order.id} orderNumber={order.order_number} />
        ) : null}
        <Button variant="outline" asChild>
          <Link href="/orders">All orders</Link>
        </Button>
      </div>
    </div>
  );
}

function OrderContent() {
  const params = useParams<{ id: string }>();
  const orderId = Array.isArray(params.id) ? params.id[0] : params.id;
  const { order, isLoading, error, reload, cancel, isCancelling, cancelError } = useOrder(orderId);

  let body: React.ReactNode;
  if (order) {
    body = (
      <OrderDetails
        order={order}
        isCancelling={isCancelling}
        cancelError={cancelError}
        onCancel={() => void cancel().catch(() => undefined)}
        onReload={reload}
      />
    );
  } else if (error) {
    body = (
      <div className="flex flex-col items-center gap-4 rounded-2xl border border-border bg-card px-6 py-16 text-center shadow-card">
        <p role="alert" className="max-w-sm text-foreground">
          {error}
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Button variant="primary" onClick={() => void reload()} disabled={isLoading}>
            {isLoading ? "Retrying..." : "Try again"}
          </Button>
          <Button variant="outline" asChild>
            <Link href="/orders">All orders</Link>
          </Button>
        </div>
      </div>
    );
  } else {
    body = <OrderSkeleton />;
  }

  return <DashboardShell>{body}</DashboardShell>;
}

export default function OrderPage() {
  return (
    <ProtectedRoute>
      <OrderContent />
    </ProtectedRoute>
  );
}
