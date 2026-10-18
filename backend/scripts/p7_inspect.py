"""
Phase 7 (M11): look at what a payment test left in the database. READ ONLY.

Run from backend/, venv active, against your DEVELOPMENT database:

    python -m scripts.p7_inspect                      # the 3 newest orders
    python -m scripts.p7_inspect --latest 10
    python -m scripts.p7_inspect --order PRM-2026-000123
    python -m scripts.p7_inspect --order PRM-2026-000123 --check

For each order it prints the order, its payment attempts, the stock of its
products, the coupon's use count and the recent webhook events. With --check
it also verifies the rules that must always hold and exits with status 1 if
any is broken. It changes nothing, and it never prints a signature or a
secret (only Razorpay ids, which are not secret).
"""

import argparse
import sys
from decimal import Decimal
from typing import List

from sqlalchemy import desc

from app.database.session import SessionLocal
from app.models import (
    Coupon,
    Inventory,
    Order,
    OrderInventoryState,
    OrderPaymentStatus,
    OrderStatus,
    PaymentTransactionStatus as S,
    PaymentWebhookEvent,
)

OPEN = (S.INITIATED, S.AUTHORIZED)


def val(x):
    return getattr(x, "value", x)


def show(db, order: Order) -> List[str]:
    print(f"\n=== {order.order_number} ===")
    print(f"  status          {val(order.status)}   payment_status {val(order.payment_status)}   stock {val(order.inventory_state)}")
    print(f"  cancelled       {val(order.cancellation_reason) or '-'}   expires_at {order.expires_at}")
    print(f"  total           {order.total_amount}   coupon {order.coupon_code or '-'}")
    for item in order.items:
        inv = db.query(Inventory).filter(Inventory.product_id == item.product_id).first() if item.product_id else None
        stock = f"quantity {inv.quantity}, reserved {inv.reserved_quantity}" if inv else "n/a"
        print(f"  item            {item.product_name_snapshot} x{item.quantity}   ({stock})")
    if order.coupon_id:
        coupon = db.get(Coupon, order.coupon_id)
        print(f"  coupon use      {coupon.code}: used_count {coupon.used_count} / limit {coupon.usage_limit}")
    payments = sorted(order.payments, key=lambda p: p.created_at)
    if not payments:
        print("  payments        none")
    for p in payments:
        flag = "   ** REFUND REQUIRED **" if p.refund_required else ""
        print(f"  payment         {val(p.status):<10} {p.amount} {p.currency}  {p.gateway_order_id}  {p.gateway_payment_id or '-'}{flag}")
        if p.failure_reason:
            print(f"                  reason: {p.failure_reason}")
    ids = [p.gateway_order_id for p in payments if p.gateway_order_id]
    if ids:
        events = (
            db.query(PaymentWebhookEvent)
            .filter(PaymentWebhookEvent.gateway_order_id.in_(ids))
            .order_by(PaymentWebhookEvent.received_at)
            .all()
        )
        for e in events:
            print(f"  webhook         {e.received_at:%H:%M:%S}  {e.event_type:<20} -> {e.outcome:<18} {e.event_id}")
        if not events:
            print("  webhook         no events received for this order")
    return check(order, payments)


def check(order: Order, payments) -> List[str]:
    problems = []
    paid = order.payment_status == OrderPaymentStatus.PAID
    if paid and order.status == OrderStatus.CANCELLED:
        problems.append("order is paid AND cancelled")
    if paid != (order.status == OrderStatus.CONFIRMED):
        problems.append("paid / confirmed out of step")
    if paid != (order.inventory_state == OrderInventoryState.CONSUMED):
        problems.append("paid / stock-consumed out of step")
    if order.status == OrderStatus.CANCELLED:
        if order.inventory_state != OrderInventoryState.RELEASED:
            problems.append("cancelled but stock not released")
        if any(p.status in OPEN for p in payments):
            problems.append("cancelled but a payment is still open")
        if order.payment_status != OrderPaymentStatus.PENDING:
            problems.append("cancelled order has a payment state")
    counted = [p for p in payments if p.status in (S.CAPTURED, S.REFUNDED) and not p.refund_required]
    if paid and len(counted) != 1:
        problems.append(f"paid order should have exactly 1 counting payment, has {len(counted)}")
    if not paid and counted:
        problems.append("money counted for an unpaid order")
    if sum(1 for p in payments if p.status in OPEN) > 1:
        problems.append("more than one open payment")
    if any(p.amount != order.total_amount for p in payments):
        problems.append("a payment's amount differs from the order total")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--order", help="an order number, e.g. PRM-2026-000123")
    parser.add_argument("--latest", type=int, default=3, help="how many of the newest orders (default 3)")
    parser.add_argument("--check", action="store_true", help="verify the payment rules; exit 1 if any is broken")
    args = parser.parse_args(argv)

    failed = False
    with SessionLocal() as db:
        query = db.query(Order)
        if args.order:
            orders = query.filter(Order.order_number == args.order).all()
            if not orders:
                print(f"No order numbered {args.order}.")
                return 2
        else:
            orders = query.order_by(desc(Order.created_at)).limit(max(1, args.latest)).all()
        for order in orders:
            problems = show(db, order)
            if args.check:
                if problems:
                    failed = True
                    for p in problems:
                        print(f"  CHECK FAILED    {p}")
                else:
                    print("  CHECK OK        all payment rules hold for this order")
        db.rollback()  # read-only: nothing to keep
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
