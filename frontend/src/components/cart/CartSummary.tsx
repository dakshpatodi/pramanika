import { Button } from "@/components/ui/button";
import { formatMoney, formatPercent } from "@/lib/money";
import type { Cart } from "@/types/cart";

interface CartSummaryProps {
  cart: Cart;
  /** Rendered above the totals - the page puts the coupon box here. */
  children?: React.ReactNode;
}

function Row({ label, value, muted = false }: { label: string; value: React.ReactNode; muted?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={muted ? "font-medium text-primary" : "font-medium text-foreground"}>{value}</dd>
    </div>
  );
}

/**
 * Order summary. Every number comes straight from `cart.totals` as the
 * server calculated it - nothing here adds, multiplies or rounds, so the
 * page can never disagree with what checkout will charge.
 */
export function CartSummary({ cart, children }: CartSummaryProps) {
  const { totals, coupon } = cart;
  const couponApplied = coupon !== null && coupon.applied;

  return (
    <aside
      aria-labelledby="cart-summary-heading"
      className="flex flex-col gap-5 rounded-2xl border border-border bg-card p-5 shadow-card sm:p-6"
    >
      <h2 id="cart-summary-heading" className="font-display text-lg font-semibold text-foreground">
        Order summary
      </h2>

      {children}

      <dl className="flex flex-col gap-3 border-t border-border pt-5">
        <Row label="Subtotal" value={formatMoney(totals.subtotal)} />
        {totals.discount > 0 ? (
          <Row
            label={couponApplied ? `Discount (${coupon.code})` : "Discount"}
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
          <dt className="font-display text-base font-semibold text-foreground">Total</dt>
          <dd className="font-display text-2xl font-semibold text-foreground">{formatMoney(totals.total)}</dd>
        </div>
      </dl>

      {totals.amount_for_free_delivery > 0 ? (
        <p className="rounded-xl bg-secondary-light px-3 py-2 text-xs text-foreground">
          Add {formatMoney(totals.amount_for_free_delivery)} more to get free delivery.
        </p>
      ) : null}

      {/* Honest placeholder until Phase 6 builds checkout - same pattern as
          the disabled-with-explanation controls in earlier phases. */}
      <Button variant="primary" size="lg" disabled className="w-full">
        Checkout coming soon
      </Button>
    </aside>
  );
}