import { describe, expect, it } from "vitest";

import { describeOrder, formatOrderDate, formatOrderDateTime, ORDER_STATUS_LABEL, PAYMENT_STATUS_LABEL } from "@/lib/order-format";

describe("dates", () => {
  it("formats in India time regardless of the machine's time zone", () => {
    // 2026-10-05 20:00 UTC is already 6 Oct 01:30 in India.
    expect(formatOrderDate("2026-10-05T20:00:00Z")).toBe("6 Oct 2026");
    expect(formatOrderDateTime("2026-10-05T10:30:00Z")).toMatch(/^5 Oct 2026, 4:00\s?pm$/i);
  });
});

describe("labels", () => {
  it("has a label for every status", () => {
    expect(ORDER_STATUS_LABEL.pending).toBe("Pending");
    expect(ORDER_STATUS_LABEL.cancelled).toBe("Cancelled");
    expect(PAYMENT_STATUS_LABEL.pending).toBe("Payment pending");
    expect(PAYMENT_STATUS_LABEL.paid).toBe("Paid");
    expect(Object.keys(ORDER_STATUS_LABEL)).toHaveLength(7);
    expect(Object.keys(PAYMENT_STATUS_LABEL)).toHaveLength(4);
  });
});

describe("describeOrder", () => {
  const base = { status: "pending", payment_status: "pending", cancelled_at: null } as const;

  it("says nothing was paid for a pending, unpaid order", () => {
    const text = describeOrder(base);
    expect(text).toMatch(/No payment has been taken yet/);
    expect(text).not.toMatch(/\bpaid\b|received your payment|payment (successful|received)/i);
  });

  it("says the order was cancelled, with the date, and that stock was released", () => {
    const text = describeOrder({ ...base, status: "cancelled", cancelled_at: "2026-10-06T08:00:00Z" });
    expect(text).toMatch(/cancelled on 6 Oct 2026/);
    expect(text).toMatch(/released/);
    expect(describeOrder({ ...base, status: "cancelled" })).toMatch(/was cancelled\. The items .* released/);
  });

  it("only talks about payment having been received when the server says paid", () => {
    expect(describeOrder({ ...base, status: "confirmed", payment_status: "paid" })).toMatch(/payment has been received/i);
    expect(describeOrder({ ...base, status: "shipped", payment_status: "paid" })).toMatch(/on its way/);
    expect(describeOrder({ ...base, status: "delivered", payment_status: "paid" })).toMatch(/delivered/);
  });

  it("reports failed payments and refunds honestly", () => {
    expect(describeOrder({ ...base, payment_status: "failed" })).toMatch(/failed.*not been paid for/);
    expect(describeOrder({ ...base, status: "refunded", payment_status: "refunded" })).toMatch(/refunded/);
  });
});

import { EXPIRED_LABEL, PAYMENT_CLOSED_LABEL, formatOrderTime, formatTimeLeft, isExpiredOrder, isPaymentWindowClosed } from "@/lib/order-format";

describe("describeOrder - payment states (Milestone 9)", () => {
  const pending = {
    status: "pending", payment_status: "pending", cancelled_at: null, cancellation_reason: null, can_pay: true,
    expires_at: "2026-10-05T10:30:00Z", payment: { last_attempt: null, refund_pending: false },
  } as const;

  it("an expired order says it expired and that the items were released - not 'cancelled by you'", () => {
    const text = describeOrder({ ...pending, status: "cancelled", cancellation_reason: "expired", can_pay: false });
    expect(text).toMatch(/expired because it wasn't paid in time/);
    expect(text).toMatch(/released/);
    expect(text).not.toMatch(/was cancelled/);
  });

  it("a customer-cancelled order keeps the old wording", () => {
    expect(describeOrder({ ...pending, status: "cancelled", cancellation_reason: "customer", can_pay: false, cancelled_at: "2026-10-06T08:00:00Z" }))
      .toMatch(/cancelled on 6 Oct 2026/);
  });

  it("a payable order says when to pay by (India time) and that nothing was taken", () => {
    const text = describeOrder(pending);
    expect(text).toMatch(/No payment has been taken yet/);
    expect(text).toMatch(/pay before 4:00\s?pm/i);
    expect(text).not.toMatch(/payment (has been )?received/i);
  });

  it("after a failed attempt it invites another try on the same order", () => {
    const text = describeOrder({ ...pending, payment: { last_attempt: "failed", refund_pending: false } });
    expect(text).toMatch(/last payment attempt didn't go through/);
    expect(text).toMatch(/try again/);
  });

  it("while the bank is still confirming it does not say paid and does not invite a second payment", () => {
    const text = describeOrder({ ...pending, payment: { last_attempt: "authorized", refund_pending: false } });
    expect(text).toMatch(/being confirmed/);
    expect(text).toMatch(/isn't marked as paid until it is/);
    expect(text).not.toMatch(/try again/);
  });

  it("an order past its deadline says the time ran out and that nothing was charged", () => {
    const text = describeOrder({ ...pending, can_pay: false });
    expect(text).toMatch(/time to pay for this order has run out/);
    expect(text).toMatch(/haven't been charged/);
  });

  it("does not offer a deadline when the order can no longer be paid", () => {
    expect(describeOrder({ ...pending, can_pay: false, expires_at: null })).not.toMatch(/pay before/);
  });

  it("older callers that pass only the Phase 6 fields still get a sensible sentence", () => {
    expect(describeOrder({ status: "pending", payment_status: "pending", cancelled_at: null })).toMatch(/No payment has been taken yet/);
  });
});

describe("order state helpers", () => {
  it("isExpiredOrder is true only for a cancelled order cancelled by expiry", () => {
    expect(isExpiredOrder({ status: "cancelled", cancellation_reason: "expired" })).toBe(true);
    expect(isExpiredOrder({ status: "cancelled", cancellation_reason: "customer" })).toBe(false);
    expect(isExpiredOrder({ status: "cancelled", cancellation_reason: null })).toBe(false);
    expect(isExpiredOrder({ status: "pending", cancellation_reason: "expired" })).toBe(false);
  });

  it("isPaymentWindowClosed is true only for a pending, unpaid order the server says is not payable", () => {
    expect(isPaymentWindowClosed({ status: "pending", payment_status: "pending", can_pay: false })).toBe(true);
    expect(isPaymentWindowClosed({ status: "pending", payment_status: "pending", can_pay: true })).toBe(false);
    expect(isPaymentWindowClosed({ status: "pending", payment_status: "pending" })).toBe(false); // unknown is not 'closed'
    expect(isPaymentWindowClosed({ status: "confirmed", payment_status: "paid", can_pay: false })).toBe(false);
    expect(isPaymentWindowClosed({ status: "cancelled", payment_status: "pending", can_pay: false })).toBe(false);
  });

  it("has labels for the two new states", () => {
    expect(EXPIRED_LABEL).toBe("Expired");
    expect(PAYMENT_CLOSED_LABEL).toBe("Payment window closed");
  });

  it("formats a clock time in India time", () => {
    expect(formatOrderTime("2026-10-05T10:30:00Z")).toMatch(/^4:00\s?pm$/i);
  });
});

describe("formatTimeLeft", () => {
  it.each([
    [0, "0 sec"], [-5000, "0 sec"], [1, "1 sec"], [45_000, "45 sec"], [60_000, "1 min"], [125_000, "2 min 5 sec"],
    [299_000, "4 min 59 sec"], [300_000, "5 min"], [310_000, "5 min"], [29 * 60_000 + 59_000, "29 min"],
    [3_600_000, "1 hr"], [3_900_000, "1 hr 5 min"], [7_380_000, "2 hr 3 min"],
  ])("%d ms -> %s", (ms, text) => {
    expect(formatTimeLeft(ms)).toBe(text);
  });
});
