"""
Phase 9 M5 - admin order management.

  FulfilmentRulesTests    the rule table (no database)
  OrderSchemaTests        what a status request may contain (no database)
  OrderListTests          filters, search, dates, sorting, paging, cost, read-only
  OrderDetailTests        what the admin sees (and never sees)
  OrderAdvanceTests       the one action: forward, one step, paid orders only, audited
  OrderInvariantTests     checkout / payment / cancel / expiry behave exactly as before
  OrderRaceTests          real threads: one winner, consistent audit
"""

import itertools
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event as sa_event
from sqlalchemy import text

from app.models import (
    AdminAuditEvent,
    Coupon,
    Inventory,
    Order,
    OrderCancellationReason,
    OrderInventoryState,
    OrderPaymentStatus,
    OrderStatus,
    Payment,
    PaymentTransactionStatus,
)
from app.schemas.admin_orders import OrderStatusUpdate
from app.services.fulfilment_rules import NEXT_STEP, is_fulfillable, next_status, refusal_reason
from tests.p9_support import AdminTestCase, bearer, build_admin_app
from tests.pg_support import _get_engine, new_session, run_concurrently

S, PS, INV = OrderStatus, OrderPaymentStatus, OrderInventoryState
NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


class FulfilmentRulesTests(unittest.TestCase):
    def test_only_paid_consumed_orders_have_a_next_step(self):
        expected = {S.CONFIRMED: S.PROCESSING, S.PROCESSING: S.SHIPPED, S.SHIPPED: S.DELIVERED}
        for status, payment, inv in itertools.product(S, PS, INV):
            with self.subTest(status=status.value, payment=payment.value, inventory=inv.value):
                got = next_status(status, payment, inv)
                if payment == PS.PAID and inv == INV.CONSUMED and status in expected:
                    self.assertEqual(got, expected[status])
                else:
                    self.assertIsNone(got)
                self.assertEqual(is_fulfillable(status, payment, inv), got is not None)

    def test_the_path_is_exactly_three_steps_forward(self):
        self.assertEqual(NEXT_STEP, {S.CONFIRMED: S.PROCESSING, S.PROCESSING: S.SHIPPED, S.SHIPPED: S.DELIVERED})

    def test_refusal_messages(self):
        paid = (PS.PAID, INV.CONSUMED)
        self.assertIn("cancelled", refusal_reason(S.CANCELLED, PS.PENDING, INV.RELEASED, S.PROCESSING))
        self.assertIn("refunded", refusal_reason(S.REFUNDED, PS.REFUNDED, INV.CONSUMED, S.PROCESSING))
        self.assertIn("has not been paid", refusal_reason(S.PENDING, PS.PENDING, INV.RESERVED, S.PROCESSING))
        self.assertIn("has not been paid", refusal_reason(S.CONFIRMED, PS.PAID, INV.RESERVED, S.PROCESSING))
        self.assertIn("already delivered", refusal_reason(S.DELIVERED, *paid, S.SHIPPED))
        self.assertIn("backward", refusal_reason(S.SHIPPED, *paid, S.PROCESSING))
        self.assertIn("next step after confirmed is processing", refusal_reason(S.CONFIRMED, *paid, S.DELIVERED))
        self.assertIn("next step after processing is shipped", refusal_reason(S.PROCESSING, *paid, S.DELIVERED))


class OrderSchemaTests(unittest.TestCase):
    def test_only_fulfilment_statuses_can_be_requested(self):
        for status in ["processing", "shipped", "delivered"]:
            self.assertEqual(OrderStatusUpdate(status=status).status.value, status)
        for status in ["confirmed", "pending", "cancelled", "refunded", "paid", "expired", "PROCESSING", "", None, 1]:
            with self.subTest(status=status), self.assertRaises(ValidationError):
                OrderStatusUpdate(status=status)

    def test_nothing_else_can_ride_along(self):
        for extra in ["payment_status", "inventory_state", "total_amount", "id", "user_id", "cancellation_reason", "is_paid", "paid"]:
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                OrderStatusUpdate.model_validate({"status": "shipped", extra: "x"})

    def test_note(self):
        self.assertEqual(OrderStatusUpdate(status="shipped", note="  courier X  ").note, "courier X")
        self.assertIsNone(OrderStatusUpdate(status="shipped", note="   ").note)
        with self.assertRaises(ValidationError):
            OrderStatusUpdate(status="shipped", note="x" * 201)


class OrderCase(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(build_admin_app(with_shop=True))
        self.admin = self.make_admin()
        self.h = bearer(self.admin)
        self.product = self.make_product(price="100.00", stock=100, name="Muesli")

    def customer(self, first="Asha", last="Rao", email=None, phone=None):
        user = self.make_user()
        with new_session() as s:
            s.execute(
                text("UPDATE users SET first_name=:f, last_name=:l, email=COALESCE(:e, email), phone_number=COALESCE(:p, phone_number) WHERE id=:id"),
                {"f": first, "l": last, "e": email, "p": phone, "id": user.id},
            )
            s.commit()
        return user

    def paid_order(self, user=None, qty=1, status=S.CONFIRMED, **kw):
        user = user or self.customer()
        order = self.make_order(user, [(self.product, qty)], status=status, payment_status=PS.PAID, inventory_state=INV.CONSUMED, **kw)
        self.make_payment(order, status=PaymentTransactionStatus.CAPTURED)
        return order

    def open_order(self, user=None, qty=1):
        return self.make_order(user or self.customer(), [(self.product, qty)])

    def post_status(self, order_id, status, **extra):
        return self.client.post(f"/api/admin/orders/{order_id}/status", json={"status": status, **extra}, headers=self.h)

    def audit(self, action=None):
        with new_session() as s:
            q = s.query(AdminAuditEvent).order_by(AdminAuditEvent.created_at)
            if action:
                q = q.filter(AdminAuditEvent.action == action)
            return q.all()

    def row(self, order_id):
        with new_session() as s:
            o = s.get(Order, order_id)
            inv = s.query(Inventory).filter(Inventory.product_id == self.product.id).one()
            pays = [(p.id, p.status, p.refund_required) for p in s.query(Payment).filter(Payment.order_id == order_id).order_by(Payment.id)]
            return dict(status=o.status, payment=o.payment_status, inventory=o.inventory_state, total=o.total_amount,
                        coupon=o.coupon_id, stock=(inv.quantity, inv.reserved_quantity), payments=pays, reason=o.cancellation_reason)


class OrderListTests(OrderCase):
    def get(self, **params):
        return self.client.get("/api/admin/orders", params=params, headers=self.h)

    def numbers(self, **params):
        return [o["order_number"] for o in self.get(**params).json()["data"]["orders"]]

    def seed(self):
        self.asha = self.customer("Asha", "Rao", "asha@example.com", "+919800000001")
        self.ravi = self.customer("Ravi", "Iyer", "ravi@example.com", "+919800000002")
        self.o_paid = self.paid_order(self.asha, qty=2)
        self.o_open = self.open_order(self.ravi, qty=3)
        self.o_cancel = self.make_order(self.ravi, [(self.product, 1)], status=S.CANCELLED, inventory_state=INV.RELEASED, reserve_stock=False)
        self.o_ship = self.paid_order(self.ravi, status=S.SHIPPED)
        for i, o in enumerate([self.o_paid, self.o_open, self.o_cancel, self.o_ship]):
            with new_session() as s:
                s.execute(text("UPDATE orders SET created_at=:t WHERE id=:id"), {"t": NOW - timedelta(days=10 - i), "id": o.id})
                s.commit()

    def test_list_shape_and_fields(self):
        self.seed()
        data = self.get().json()["data"]
        self.assertEqual(data["pagination"]["total"], 4)
        paid = next(o for o in data["orders"] if o["order_number"] == self.o_paid.order_number)
        self.assertEqual((paid["status"], paid["payment_status"], paid["inventory_state"]), ("confirmed", "paid", "consumed"))
        self.assertEqual((paid["customer_name"], paid["customer_email"], paid["customer_phone"], paid["item_count"]), ("Asha Rao", "asha@example.com", "+919800000001", 2))
        self.assertEqual((paid["total_amount"], paid["next_status"]), (200.0, "processing"))
        self.assertEqual(set(paid), {"id", "order_number", "status", "payment_status", "inventory_state", "cancellation_reason", "customer_name",
                                     "customer_email", "customer_phone", "item_count", "total_amount", "next_status", "created_at"})
        by_num = {o["order_number"]: o for o in data["orders"]}
        self.assertIsNone(by_num[self.o_open.order_number]["next_status"])       # unpaid: nothing to do
        self.assertEqual(by_num[self.o_cancel.order_number]["cancellation_reason"], "customer")
        self.assertEqual(by_num[self.o_ship.order_number]["next_status"], "delivered")

    def test_filters(self):
        self.seed()
        self.assertEqual(self.numbers(status="confirmed"), [self.o_paid.order_number])
        self.assertEqual(sorted(self.numbers(payment_status="paid")), sorted([self.o_paid.order_number, self.o_ship.order_number]))
        self.assertEqual(self.numbers(inventory_state="reserved"), [self.o_open.order_number])
        self.assertEqual(self.numbers(inventory_state="released"), [self.o_cancel.order_number])
        self.assertEqual(self.numbers(status="shipped", payment_status="paid"), [self.o_ship.order_number])
        self.assertEqual(self.numbers(status="delivered"), [])

    def test_search_across_order_number_customer_and_shipping(self):
        self.seed()
        self.assertEqual(self.numbers(search=self.o_open.order_number), [self.o_open.order_number])
        self.assertEqual(self.numbers(search=self.o_open.order_number.lower()), [self.o_open.order_number])  # case-insensitive
        self.assertEqual(self.numbers(search="asha@example"), [self.o_paid.order_number])
        self.assertEqual(self.numbers(search="9800000002").__len__(), 3)                                    # all of Ravi's
        self.assertEqual(self.numbers(search="ravi iyer").__len__(), 3)
        self.assertEqual(self.numbers(search="IYER").__len__(), 3)
        with new_session() as s:
            s.execute(text("UPDATE orders SET shipping_full_name='Priya Nair', shipping_phone_number='+919811111111' WHERE id=:id"), {"id": self.o_paid.id})
            s.commit()
        self.assertEqual(self.numbers(search="priya"), [self.o_paid.order_number])
        self.assertEqual(self.numbers(search="9811111111"), [self.o_paid.order_number])
        self.assertEqual(self.numbers(search="nobody-here"), [])
        self.assertEqual(self.numbers(search="' OR 1=1 --"), [])

    def test_search_wildcards_are_literal(self):
        self.seed()
        with new_session() as s:
            s.execute(text("UPDATE orders SET shipping_full_name='100% Cotton_Man' WHERE id=:id"), {"id": self.o_paid.id})
            s.commit()
        self.assertEqual(self.numbers(search="%"), [self.o_paid.order_number])
        self.assertEqual(self.numbers(search="_"), [self.o_paid.order_number])
        self.assertEqual(self.numbers(search="t%n"), [])      # would match "tton" if % were a wildcard
        self.assertEqual(self.numbers(search="t_o"), [])      # would match "tto" if _ were a wildcard
        self.assertEqual(self.numbers(search="n_m"), [self.o_paid.order_number])   # literal text, case-insensitive

    def test_date_range_is_inclusive_and_checked(self):
        self.seed()
        lo, hi = (NOW - timedelta(days=9)).isoformat(), (NOW - timedelta(days=8)).isoformat()
        self.assertEqual(sorted(self.numbers(created_from=lo, created_to=hi)), sorted([self.o_open.order_number, self.o_cancel.order_number]))
        self.assertEqual(self.numbers(created_from=(NOW - timedelta(days=7)).isoformat()), [self.o_ship.order_number])
        self.assertEqual(self.numbers(created_to=(NOW - timedelta(days=10)).isoformat()), [self.o_paid.order_number])
        r = self.get(created_from=hi, created_to=lo)
        self.assertEqual(r.status_code, 422)
        self.assertIn("created_to", r.json()["message"])
        self.assertEqual(self.get(created_from="yesterday").status_code, 422)

    def test_sorting_and_paging(self):
        self.seed()
        self.assertEqual(self.numbers()[0], self.o_ship.order_number)                      # newest first
        self.assertEqual(self.numbers(sort="created_at", order="asc")[0], self.o_paid.order_number)
        self.assertEqual(self.numbers(sort="total", order="desc")[0], self.o_open.order_number)   # 300
        self.assertEqual(self.numbers(sort="order_number", order="asc"), sorted(self.numbers()))
        seen = []
        for page in (1, 2):
            seen += self.numbers(page=page, page_size=2)
        self.assertEqual((len(seen), len(set(seen))), (4, 4))
        p = self.get(page_size=3).json()["data"]["pagination"]
        self.assertEqual((p["total"], p["total_pages"], p["has_next"], p["has_previous"]), (4, 2, True, False))

    def test_paging_is_stable_when_sort_values_tie(self):
        user = self.customer()
        for _ in range(5):
            self.open_order(user)                                 # five orders with the same status
        statements = []
        engine = _get_engine()
        listener = lambda conn, cur, stmt, *a: statements.append(stmt)
        sa_event.listen(engine, "before_cursor_execute", listener)
        try:
            seen = []
            for page in range(1, 6):
                seen += self.numbers(sort="status", page=page, page_size=1)
        finally:
            sa_event.remove(engine, "before_cursor_execute", listener)
        self.assertEqual(len(set(seen)), 5)
        pages = [s for s in statements if s.startswith("SELECT") and "LIMIT" in s and "FROM orders" in s]
        self.assertEqual(len(pages), 5)
        self.assertTrue(all("ORDER BY orders.status ASC, orders.id" in s or "ORDER BY orders.status DESC, orders.id" in s for s in pages), pages[0][-200:])

    def test_bad_parameters_are_422(self):
        for params in [{"page": 0}, {"page_size": 101}, {"status": "shipping"}, {"payment_status": "free"}, {"inventory_state": "x"},
                       {"sort": "customer"}, {"order": "up"}, {"search": ""}]:
            with self.subTest(params=params):
                self.assertEqual(self.get(**params).status_code, 422)

    def test_two_queries_per_page_no_locks_and_no_writes(self):
        self.seed()
        before = [self.row(o.id) for o in (self.o_paid, self.o_open)]
        statements = []
        engine = _get_engine()
        listener = lambda conn, cur, stmt, *a: statements.append(stmt)
        sa_event.listen(engine, "before_cursor_execute", listener)
        try:
            self.assertEqual(self.get(page_size=100).status_code, 200)
        finally:
            sa_event.remove(engine, "before_cursor_execute", listener)
        self.assertEqual(len([s for s in statements if "FROM orders" in s]), 2, statements)
        self.assertFalse([s for s in statements if s.startswith(("UPDATE", "INSERT", "DELETE")) or "FOR UPDATE" in s])
        self.assertEqual(before, [self.row(o.id) for o in (self.o_paid, self.o_open)])
        self.assertEqual(self.audit(), [])


class OrderDetailTests(OrderCase):
    def test_a_paid_order_in_full(self):
        user = self.customer("Asha", "Rao", "asha@example.com", "+919800000001")
        coupon = self.make_coupon(code="WELCOME10")
        order = self.paid_order(user, qty=2, coupon=coupon)
        with new_session() as s:
            s.execute(text("UPDATE orders SET discount_amount=20, taxable_amount=180, tax_amount=9, gst_rate=0.05, delivery_charge=40, total_amount=229, "
                           "shipping_full_name='Asha R', shipping_address_line_1='1 Test St', shipping_city='Pune', shipping_state='MH', "
                           "shipping_postal_code='411001', shipping_country='India' WHERE id=:id"), {"id": order.id})
            s.commit()
        d = self.client.get(f"/api/admin/orders/{order.id}", headers=self.h).json()["data"]
        self.assertEqual((d["status"], d["payment_status"], d["inventory_state"], d["can_advance"], d["next_status"]), ("confirmed", "paid", "consumed", True, "processing"))
        self.assertEqual(d["customer"], {"id": str(user.id), "name": "Asha Rao", "email": "asha@example.com", "phone_number": "+919800000001"})
        self.assertEqual(d["coupon_code"], "WELCOME10")
        self.assertEqual(d["items"], [{"product_id": str(self.product.id), "name": "Muesli", "sku": self.product.sku, "unit_price": 100.0, "quantity": 2, "subtotal": 200.0}])
        self.assertEqual(d["totals"], {"subtotal": 200.0, "discount": 20.0, "taxable_amount": 180.0, "gst_rate": 0.05, "gst": 9.0, "delivery_charge": 40.0, "total": 229.0})
        self.assertEqual((d["shipping_address"]["full_name"], d["shipping_address"]["city"], d["shipping_address"]["postal_code"]), ("Asha R", "Pune", "411001"))
        self.assertEqual(d["reserved_units"], 0)                      # consumed, not reserved
        (pay,) = d["payments"]
        self.assertEqual((pay["status"], pay["gateway"], pay["amount"], pay["currency"], pay["refund_required"]), ("captured", "razorpay", 200.0, "INR", False))
        self.assertTrue(pay["gateway_order_id"].startswith("order_T") and pay["gateway_payment_id"].startswith("pay_T"))
        self.assertIsNotNone(pay["paid_at"])

    def test_an_open_order_shows_its_reservation_and_attempts(self):
        order = self.open_order(qty=3)
        self.make_payment(order)                                                 # an initiated attempt
        self.make_payment(order, status=PaymentTransactionStatus.FAILED, failure_reason="card declined")
        d = self.client.get(f"/api/admin/orders/{order.id}", headers=self.h).json()["data"]
        self.assertEqual((d["status"], d["payment_status"], d["inventory_state"], d["reserved_units"], d["can_advance"]), ("pending", "pending", "reserved", 3, False))
        self.assertEqual(sorted(p["status"] for p in d["payments"]), ["failed", "initiated"])
        self.assertIn("card declined", [p["failure_reason"] for p in d["payments"]])

    def test_a_cancelled_order(self):
        order = self.make_order(self.customer(), [(self.product, 2)], status=S.CANCELLED, inventory_state=INV.RELEASED, reserve_stock=False,
                                cancellation_reason=OrderCancellationReason.EXPIRED)
        d = self.client.get(f"/api/admin/orders/{order.id}", headers=self.h).json()["data"]
        self.assertEqual((d["status"], d["cancellation_reason"], d["reserved_units"], d["can_advance"]), ("cancelled", "expired", 0, False))

    def test_secrets_and_signatures_never_appear(self):
        order = self.paid_order()
        with new_session() as s:
            s.execute(text("UPDATE payments SET gateway_signature='SIGNATURE-SECRET-123' WHERE order_id=:id"), {"id": order.id})
            s.commit()
        body = self.client.get(f"/api/admin/orders/{order.id}", headers=self.h).text
        for needle in ["SIGNATURE-SECRET", "signature", "password", "hash", "token", "secret"]:
            self.assertNotIn(needle.lower(), body.lower())

    def test_the_detail_is_a_fixed_number_of_queries(self):
        order = self.paid_order(qty=3)
        for _ in range(3):
            self.make_payment(order, status=PaymentTransactionStatus.FAILED)
        url = f"/api/admin/orders/{order.id}"          # read before listening: touching `order` later would query
        statements = []
        engine = _get_engine()
        listener = lambda conn, cur, stmt, *a: statements.append(stmt)
        sa_event.listen(engine, "before_cursor_execute", listener)
        try:
            self.client.get(url, headers=self.h)
        finally:
            sa_event.remove(engine, "before_cursor_execute", listener)
        selects = [s for s in statements if s.startswith("SELECT")]
        self.assertEqual(len(selects), 4, [s[:60] for s in selects])    # the admin, then the order + customer, lines, payments
        self.assertFalse([s for s in statements if "FOR UPDATE" in s or s.startswith(("UPDATE", "INSERT", "DELETE"))])

    def test_unknown_and_malformed_ids(self):
        self.assertEqual(self.client.get(f"/api/admin/orders/{uuid.uuid4()}", headers=self.h).status_code, 404)
        self.assertEqual(self.client.get("/api/admin/orders/nope", headers=self.h).status_code, 422)


class OrderAdvanceTests(OrderCase):
    def test_the_whole_path_with_an_audit_row_per_step(self):
        order = self.paid_order()
        for target, expect_next in [("processing", "shipped"), ("shipped", "delivered"), ("delivered", None)]:
            r = self.post_status(order.id, target, note=f"to {target}")
            self.assertEqual(r.status_code, 200, r.text)
            d = r.json()["data"]
            self.assertEqual((d["status"], d["next_status"], d["can_advance"]), (target, expect_next, expect_next is not None))
        events = self.audit("order.status_change")
        self.assertEqual([(e.before["status"], e.after["status"]) for e in events], [("confirmed", "processing"), ("processing", "shipped"), ("shipped", "delivered")])
        self.assertEqual({(e.entity_type, e.entity_id, e.admin_user_id) for e in events}, {("order", order.id, self.admin.id)})
        self.assertEqual(events[0].after["note"], "to processing")

    def test_steps_cannot_be_skipped_or_reversed(self):
        order = self.paid_order()
        for target in ("shipped", "delivered"):
            r = self.post_status(order.id, target)
            self.assertEqual(r.status_code, 409, r.text)
            self.assertIn("next step after confirmed is processing", r.json()["message"])
        self.assertEqual(self.post_status(order.id, "processing").status_code, 200)
        self.assertEqual(self.post_status(order.id, "delivered").status_code, 409)
        self.assertEqual(self.post_status(order.id, "shipped").status_code, 200)
        r = self.post_status(order.id, "processing")
        self.assertEqual(r.status_code, 409)
        self.assertIn("backward", r.json()["message"])
        self.assertEqual(self.post_status(order.id, "delivered").status_code, 200)
        r = self.post_status(order.id, "shipped")
        self.assertEqual(r.status_code, 409)
        self.assertIn("already delivered", r.json()["message"])
        self.assertEqual(len(self.audit("order.status_change")), 3)

    def test_repeating_the_current_step_is_a_quiet_success(self):
        order = self.paid_order()
        self.post_status(order.id, "processing")
        for _ in range(3):
            r = self.post_status(order.id, "processing")
            self.assertEqual((r.status_code, r.json()["data"]["status"]), (200, "processing"))
        self.assertEqual(len(self.audit("order.status_change")), 1)
        self.post_status(order.id, "shipped")
        self.post_status(order.id, "delivered")
        self.assertEqual(self.post_status(order.id, "delivered").status_code, 200)
        self.assertEqual(len(self.audit("order.status_change")), 3)

    def test_an_unpaid_order_cannot_be_fulfilled(self):
        order = self.open_order()
        before = self.row(order.id)
        for target in ("processing", "shipped", "delivered"):
            r = self.post_status(order.id, target)
            self.assertEqual(r.status_code, 409, r.text)
            self.assertIn("has not been paid", r.json()["message"])
        self.assertEqual(self.row(order.id), before)
        self.assertEqual(self.audit(), [])

    def test_cancelled_expired_and_refunded_orders_cannot_be_fulfilled(self):
        user = self.customer()
        cancelled = self.make_order(user, [(self.product, 1)], status=S.CANCELLED, inventory_state=INV.RELEASED, reserve_stock=False)
        expired = self.make_order(user, [(self.product, 1)], status=S.CANCELLED, inventory_state=INV.RELEASED, reserve_stock=False,
                                  cancellation_reason=OrderCancellationReason.EXPIRED)
        refunded = self.make_order(user, [(self.product, 1)], status=S.REFUNDED, payment_status=PS.REFUNDED, inventory_state=INV.CONSUMED)
        for order in (cancelled, expired, refunded):
            before = self.row(order.id)
            for target in ("processing", "shipped", "delivered"):
                with self.subTest(order=order.order_number, target=target):
                    self.assertEqual(self.post_status(order.id, target).status_code, 409)
            self.assertEqual(self.row(order.id), before)
        self.assertEqual(self.audit(), [])

    def test_repeating_a_step_is_only_quiet_for_a_properly_paid_order(self):
        """A row that says 'shipped' but was never paid is bad data, not a success to repeat."""
        order = self.make_order(self.customer(), [(self.product, 1)], status=S.SHIPPED, payment_status=PS.PENDING, inventory_state=INV.RESERVED)
        r = self.post_status(order.id, "shipped")
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("has not been paid", r.json()["message"])

    def test_a_paid_flag_without_consumed_stock_is_not_fulfillable(self):
        order = self.make_order(self.customer(), [(self.product, 1)], status=S.CONFIRMED, payment_status=PS.PAID, inventory_state=INV.RESERVED)
        r = self.post_status(order.id, "processing")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.row(order.id)["status"], S.CONFIRMED)

    def test_invalid_targets_and_bodies_are_422_and_change_nothing(self):
        order = self.paid_order()
        for body in [{"status": "confirmed"}, {"status": "cancelled"}, {"status": "refunded"}, {"status": "pending"}, {"status": "paid"}, {"status": "bogus"},
                     {}, {"status": None}, {"status": "shipped", "payment_status": "paid"}, {"status": "processing", "inventory_state": "released"},
                     {"status": "processing", "total_amount": 1}, {"payment_status": "paid"}, {"status": "processing", "note": "x" * 201}]:
            with self.subTest(body=body):
                r = self.client.post(f"/api/admin/orders/{order.id}/status", json=body, headers=self.h)
                self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(self.row(order.id)["status"], S.CONFIRMED)
        self.assertEqual(self.audit(), [])

    def test_there_is_no_way_to_mark_paid_cancel_refund_or_edit(self):
        order = self.open_order()
        for method, path in [("delete", f"/api/admin/orders/{order.id}"), ("put", f"/api/admin/orders/{order.id}"), ("patch", f"/api/admin/orders/{order.id}"),
                             ("post", f"/api/admin/orders/{order.id}/cancel"), ("post", f"/api/admin/orders/{order.id}/pay"),
                             ("post", f"/api/admin/orders/{order.id}/refund"), ("post", f"/api/admin/orders/{order.id}/mark-paid")]:
            with self.subTest(call=f"{method} {path}"):
                self.assertIn(self.client.request(method.upper(), path, json={"status": "paid"}, headers=self.h).status_code, (404, 405))
        self.assertEqual(self.row(order.id)["payment"], PS.PENDING)

    def test_unknown_order_is_404(self):
        self.assertEqual(self.post_status(uuid.uuid4(), "processing").status_code, 404)
        self.assertEqual(self.client.post("/api/admin/orders/nope/status", json={"status": "processing"}, headers=self.h).status_code, 422)

    def test_advancing_touches_nothing_but_the_status(self):
        coupon = self.make_coupon(code="KEEP10")
        order = self.paid_order(qty=2, coupon=coupon)
        before = self.row(order.id)
        with new_session() as s:
            used_before = s.get(Coupon, coupon.id).used_count
        for target in ("processing", "shipped", "delivered"):
            self.assertEqual(self.post_status(order.id, target).status_code, 200)
        after = self.row(order.id)
        self.assertEqual({k: v for k, v in after.items() if k != "status"}, {k: v for k, v in before.items() if k != "status"})
        self.assertEqual(after["status"], S.DELIVERED)
        with new_session() as s:
            self.assertEqual(s.get(Coupon, coupon.id).used_count, used_before)


class OrderStatementTests(OrderCase):
    def test_an_advance_locks_the_order_row_and_uses_a_conditional_update(self):
        order = self.paid_order()
        url = f"/api/admin/orders/{order.id}/status"
        statements = []
        engine = _get_engine()
        listener = lambda conn, cur, stmt, *a: statements.append(stmt)
        sa_event.listen(engine, "before_cursor_execute", listener)
        try:
            self.assertEqual(self.client.post(url, json={"status": "processing"}, headers=self.h).status_code, 200)
        finally:
            sa_event.remove(engine, "before_cursor_execute", listener)
        locks = [s for s in statements if s.startswith("SELECT") and "FROM orders" in s and "FOR UPDATE" in s]
        self.assertEqual(len(locks), 1, statements)
        updates = [s for s in statements if s.startswith("UPDATE orders")]
        self.assertEqual(len(updates), 1, statements)
        for clause in ("orders.status = ", "orders.payment_status = ", "orders.inventory_state = "):
            self.assertIn(clause, updates[0])
        self.assertLess(statements.index(locks[0]), statements.index(updates[0]))

    def test_a_refusal_changes_and_audits_nothing_and_holds_no_lock(self):
        order = self.open_order()
        self.assertEqual(self.post_status(order.id, "processing").status_code, 409)
        with new_session() as s:                                     # would block forever if a lock leaked
            s.execute(text("SET LOCAL lock_timeout = '2s'"))
            s.execute(text("UPDATE orders SET updated_at = now() WHERE id = :id"), {"id": order.id})
            s.commit()
        self.assertEqual(self.audit(), [])


class AuditOrderingTests(OrderCase):
    def test_an_event_written_after_waiting_sorts_after_the_event_it_waited_for(self):
        """The audit time is when the row is written, not when the transaction began."""
        first = self.paid_order()
        waiter = new_session()
        try:
            waiter.execute(text("SELECT 1"))                         # the waiter's transaction starts now (now() freezes here)
            self.assertEqual(self.post_status(first.id, "processing").status_code, 200)   # committed afterwards
            from app.services.audit_service import AuditService

            AuditService(waiter).record(admin=self.admin, action="order.status_change", entity_type="order", entity_id=first.id,
                                        before={"status": "processing"}, after={"status": "shipped"})
            waiter.commit()
        finally:
            waiter.close()
        events = self.audit("order.status_change")
        self.assertEqual([e.after["status"] for e in events], ["processing", "shipped"])


class OrderInvariantTests(OrderCase):
    def test_the_customer_sees_the_new_status_and_still_cannot_cancel(self):
        user = self.customer()
        order = self.paid_order(user)
        self.post_status(order.id, "processing")
        self.post_status(order.id, "shipped")
        mine = self.client.get(f"/api/orders/{order.id}", headers=bearer(user))
        self.assertEqual(mine.status_code, 200, mine.text)
        data = mine.json()["data"]
        self.assertEqual((data["status"], data["payment_status"], data["can_cancel"], data["can_pay"]), ("shipped", "paid", False, False))
        cancel = self.client.post(f"/api/orders/{order.id}/cancel", headers=bearer(user))
        self.assertIn(cancel.status_code, (400, 409), cancel.text)
        self.assertEqual(self.row(order.id)["status"], S.SHIPPED)

    def test_a_late_gateway_capture_after_fulfilment_started_is_flagged_not_applied(self):
        from app.services.payment_capture import apply_capture

        order = self.paid_order()
        self.post_status(order.id, "processing")
        self.post_status(order.id, "shipped")
        duplicate = self.make_payment(order)                                     # a second attempt that the gateway then captures
        with new_session() as s:
            fresh_order = s.get(Order, order.id)
            fresh_payment = s.get(Payment, duplicate.id)
            apply_capture(s, fresh_order, fresh_payment, payment_id="pay_dup_1", signature="sig", now=NOW)
            s.commit()
        row = self.row(order.id)
        self.assertEqual((row["status"], row["payment"], row["inventory"]), (S.SHIPPED, PS.PAID, INV.CONSUMED))   # untouched
        self.assertIn(True, [refund for _, _, refund in row["payments"]])                                       # flagged for refund
        self.assertEqual(row["stock"], (100, 0))                                                                # stock not double-consumed

    def test_the_expiry_job_never_touches_a_fulfilled_order(self):
        from app.services.order_expiry_service import run_expiry_pass

        order = self.paid_order()
        self.post_status(order.id, "processing")
        with new_session() as s:
            s.execute(text("UPDATE orders SET expires_at = :t WHERE id = :id"), {"t": NOW - timedelta(days=5), "id": order.id})
            s.commit()
        run_expiry_pass(new_session, clock=lambda: NOW + timedelta(days=30))
        row = self.row(order.id)
        self.assertEqual((row["status"], row["payment"], row["inventory"]), (S.PROCESSING, PS.PAID, INV.CONSUMED))

    def test_an_open_order_still_expires_and_cancels_normally_with_admin_views_around(self):
        from app.services.order_service import OrderService

        user = self.customer()
        order = self.open_order(user, qty=4)
        self.assertEqual(self.client.get(f"/api/admin/orders/{order.id}", headers=self.h).json()["data"]["reserved_units"], 4)
        self.assertEqual(self.row(order.id)["stock"], (100, 4))
        with new_session() as s:
            OrderService(s).cancel_order(user.id, order.id)
        row = self.row(order.id)
        self.assertEqual((row["status"], row["inventory"], row["stock"]), (S.CANCELLED, INV.RELEASED, (100, 0)))
        d = self.client.get(f"/api/admin/orders/{order.id}", headers=self.h).json()["data"]
        self.assertEqual((d["reserved_units"], d["cancellation_reason"]), (0, "customer"))

    def test_invoices_still_work_for_a_delivered_order(self):
        from app.models import OrderPaymentStatus

        order = self.paid_order()
        for target in ("processing", "shipped", "delivered"):
            self.post_status(order.id, target)
        with new_session() as s:
            self.assertEqual(s.get(Order, order.id).payment_status, OrderPaymentStatus.PAID)   # the invoice rule (paid) still holds


class OrderRaceTests(OrderCase):
    def clients(self, n):
        return [TestClient(build_admin_app(with_public=False)) for _ in range(n)]

    def test_two_admins_pressing_the_same_button_make_one_change(self):
        for _ in range(5):
            order = self.paid_order()
            oid = str(order.id)
            a, b = self.clients(2)
            results = run_concurrently([
                lambda: a.post(f"/api/admin/orders/{oid}/status", json={"status": "processing"}, headers=self.h).status_code,
                lambda: b.post(f"/api/admin/orders/{oid}/status", json={"status": "processing"}, headers=self.h).status_code,
            ])
            self.assertEqual([v for _, v in results], [200, 200], results)
            self.assertEqual(self.row(order.id)["status"], S.PROCESSING)
            with new_session() as s:
                self.assertEqual(s.query(AdminAuditEvent).filter(AdminAuditEvent.entity_id == order.id).count(), 1)

    def test_a_skip_racing_the_valid_step_never_lands_out_of_order(self):
        for _ in range(5):
            order = self.paid_order()
            oid = str(order.id)
            a, b = self.clients(2)
            results = run_concurrently([
                lambda: a.post(f"/api/admin/orders/{oid}/status", json={"status": "processing"}, headers=self.h).status_code,
                lambda: b.post(f"/api/admin/orders/{oid}/status", json={"status": "shipped"}, headers=self.h).status_code,
            ])
            codes = tuple(v for _, v in results)
            self.assertIn(codes, {(200, 200), (200, 409)}, results)       # shipped only ever follows processing
            with new_session() as s:
                events = s.query(AdminAuditEvent).filter(AdminAuditEvent.entity_id == order.id).order_by(AdminAuditEvent.created_at).all()
            self.assertEqual([(e.before["status"], e.after["status"]) for e in events],
                             [("confirmed", "processing")] + ([("processing", "shipped")] if codes == (200, 200) else []))
            self.assertEqual(self.row(order.id)["status"], S.SHIPPED if codes == (200, 200) else S.PROCESSING)

    def test_admin_advance_racing_the_payment_that_pays_the_order(self):
        from app.services.payment_capture import apply_capture

        for _ in range(4):
            order = self.open_order()
            payment = self.make_payment(order)
            oid, pid = order.id, payment.id
            (a,) = self.clients(1)

            def pay():
                s = new_session()
                try:
                    from app.repositories.order_repository import OrderRepository

                    locked = OrderRepository(s).get_for_update(oid)
                    p = s.get(Payment, pid)
                    apply_capture(s, locked, p, payment_id=f"pay_{uuid.uuid4().hex[:8]}", signature="sig", now=NOW)
                    s.commit()
                    return "paid"
                finally:
                    s.close()

            def advance():
                return a.post(f"/api/admin/orders/{oid}/status", json={"status": "processing"}, headers=self.h).status_code

            results = run_concurrently([pay, advance])
            self.assertEqual(results[0], ("ok", "paid"), results)
            code = results[1][1]
            row = self.row(oid)
            # Either the admin ran first (refused: not paid yet) and the order is simply confirmed,
            # or payment landed first and the admin moved it on. Never "processing" without payment.
            self.assertIn((code, row["status"]), {(409, S.CONFIRMED), (200, S.PROCESSING)}, (code, row))
            self.assertEqual((row["payment"], row["inventory"]), (PS.PAID, INV.CONSUMED))


if __name__ == "__main__":
    unittest.main()
