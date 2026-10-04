"use client";

import { useState } from "react";
import { AlertTriangle, BadgePercent, Check, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getApiErrorMessage } from "@/lib/errors";
import type { CartCoupon } from "@/types/cart";

interface CouponInputProps {
  /** The coupon currently attached to the cart, if any. */
  coupon: CartCoupon | null;
  /** True while any cart request is in flight. */
  disabled: boolean;
  /** Should reject with the API error (e.g. "Invalid coupon code.") on failure. */
  onApply: (code: string) => Promise<unknown>;
  onRemove: () => Promise<unknown>;
}

/**
 * Apply / remove a coupon code.
 *
 * Whether a code is valid is decided entirely by the server - this just
 * sends it and shows the server's message. An attached coupon that has
 * stopped qualifying (cart fell below its minimum, it expired...) comes
 * back with `applied: false` and a message, shown here in place of a
 * discount.
 */
export function CouponInput({ coupon, disabled, onApply, onRemove }: CouponInputProps) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isWorking, setIsWorking] = useState(false);

  const busy = disabled || isWorking;

  async function handleApply(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = code.trim();
    if (!trimmed) {
      setError("Enter a coupon code.");
      return;
    }
    setError(null);
    setIsWorking(true);
    try {
      await onApply(trimmed);
      setCode("");
    } catch (err) {
      setError(getApiErrorMessage(err, "We couldn't apply that coupon. Please try again."));
    } finally {
      setIsWorking(false);
    }
  }

  async function handleRemove() {
    setError(null);
    setIsWorking(true);
    try {
      await onRemove();
    } catch (err) {
      setError(getApiErrorMessage(err, "We couldn't remove the coupon. Please try again."));
    } finally {
      setIsWorking(false);
    }
  }

  if (coupon) {
    return (
      <div className="flex flex-col gap-2">
        <div
          className={`flex items-start gap-3 rounded-xl px-4 py-3 text-sm ${
            coupon.applied ? "bg-primary-light" : "bg-accent-light"
          }`}
        >
          {coupon.applied ? (
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          ) : (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-accent-dark" aria-hidden="true" />
          )}
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="font-semibold text-foreground">
              {coupon.code} {coupon.applied ? "applied" : "not applied"}
            </span>
            {coupon.applied ? (
              coupon.description ? <span className="text-muted-foreground">{coupon.description}</span> : null
            ) : coupon.message ? (
              <span className="text-foreground">{coupon.message}</span>
            ) : null}
          </div>
          <button
            type="button"
            onClick={handleRemove}
            disabled={busy}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-card hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
            aria-label={`Remove coupon ${coupon.code}`}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        {error ? (
          <p role="alert" className="text-sm text-accent-dark">
            {error}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <form onSubmit={handleApply} className="flex flex-col gap-2" noValidate>
      <label htmlFor="coupon-code" className="flex items-center gap-1.5 text-sm font-medium text-foreground">
        <BadgePercent className="h-4 w-4 text-primary" aria-hidden="true" /> Have a coupon?
      </label>
      <div className="flex gap-2">
        <Input
          id="coupon-code"
          value={code}
          onChange={(event) => {
            setCode(event.target.value);
            if (error) setError(null);
          }}
          placeholder="Enter code"
          autoComplete="off"
          maxLength={50}
          disabled={busy}
          invalid={error !== null}
          aria-describedby={error ? "coupon-error" : undefined}
          className="uppercase placeholder:normal-case"
        />
        <Button type="submit" variant="outline" disabled={busy}>
          {isWorking ? "Applying..." : "Apply"}
        </Button>
      </div>
      {error ? (
        <p id="coupon-error" role="alert" className="text-sm text-accent-dark">
          {error}
        </p>
      ) : null}
    </form>
  );
}