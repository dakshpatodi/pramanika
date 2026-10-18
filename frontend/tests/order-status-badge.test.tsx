import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { OrderStatusBadge } from "@/components/orders/OrderStatusBadge";

afterEach(cleanup);

describe("OrderStatusBadge", () => {
  it("reads 'Expired' (and no payment pill) for an order cancelled by expiry", () => {
    render(<OrderStatusBadge status="cancelled" paymentStatus="pending" cancellationReason="expired" canPay={false} />);
    expect(screen.getByText("Expired")).toBeTruthy();
    expect(screen.queryByText("Cancelled")).toBeNull();
    expect(screen.queryByText("Payment pending")).toBeNull();
  });

  it("reads 'Cancelled' for a customer cancellation, and for one with no reason", () => {
    const { rerender } = render(<OrderStatusBadge status="cancelled" paymentStatus="pending" cancellationReason="customer" />);
    expect(screen.getByText("Cancelled")).toBeTruthy();
    rerender(<OrderStatusBadge status="cancelled" paymentStatus="pending" />);
    expect(screen.getByText("Cancelled")).toBeTruthy();
    expect(screen.queryByText("Expired")).toBeNull();
  });

  it("shows 'Payment pending' for a payable order", () => {
    render(<OrderStatusBadge status="pending" paymentStatus="pending" canPay />);
    expect(screen.getByText("Pending")).toBeTruthy();
    expect(screen.getByText("Payment pending")).toBeTruthy();
  });

  it("shows 'Payment window closed' when the server says an unpaid order can no longer be paid", () => {
    render(<OrderStatusBadge status="pending" paymentStatus="pending" canPay={false} />);
    expect(screen.getByText("Payment window closed")).toBeTruthy();
    expect(screen.queryByText("Payment pending")).toBeNull();
  });

  it("does not guess 'closed' when it was not told", () => {
    render(<OrderStatusBadge status="pending" paymentStatus="pending" />);
    expect(screen.getByText("Payment pending")).toBeTruthy();
  });

  it("shows 'Paid' only for a paid order, even if can_pay is false", () => {
    render(<OrderStatusBadge status="confirmed" paymentStatus="paid" canPay={false} cancellationReason={null} />);
    expect(screen.getByText("Paid")).toBeTruthy();
    expect(screen.queryByText("Payment window closed")).toBeNull();
  });
});
