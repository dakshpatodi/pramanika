"""
Phase 9 M2 - admin dashboard metrics.

Every definition is pinned by a test against hand-computed numbers:

  DashboardCountTests    orders by status, customers, products, the stock rule
  DashboardRevenueTests  paid-only revenue, 30-day window, no double counting
  DashboardRecentTests   recent orders: newest first, capped, joined in one query
  DashboardEfficiencyTests  a fixed number of queries; read-only
  DashboardApiTests      HTTP: shape, auth, no secrets
"""

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import event as sa_event
from sqlalchemy import text

from app.models import (
    AdminAuditEvent,
    Inventory,
    Order,
    OrderInventoryState,
    OrderPaymentStatus,
    OrderStatus,
    PaymentTransactionStatus,
    Product,
    User,
    UserRole,
)
from app.services.admin_dashboard_service import RECENT_ORDERS_LIMIT, AdminDashboardService
from app.services.product_service import _compute_stock_flags
from tests.p9_support import AdminTestCase, bearer, build_admin_app
from tests.pg_support import _get_engine, new_session

NOW = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)


class DashboardTestCase(AdminTestCase):
    def build(self, now=NOW):
        with new_session() as s:
            return AdminDashboardService(s).build(now=now)

    def paid_order(self, user, product, qty=1, *, paid_days_ago=1, status=OrderStatus.CONFIRMED, with_payment=True):
        order = self.make_order(
            user,
            [(product, qty)],
            status=status,
            payment_status=OrderPaymentStatus.PAID,
            inventory_state=OrderInventoryState.CONSUMED,
        )
        if with_payment:
            self.make_payment(
                order, status=PaymentTransactionStatus.CAPTURED, paid_at=NOW - timedelta(days=paid_days_ago)
            )
        return order

    def set_order_columns(self, order, **columns):
        sets = ", ".join(f"{k} = :{k}" for k in columns)
        with new_session() as s:
            s.execute(text(f"UPDATE orders SET {sets} WHERE id = :id"), {**columns, "id": order.id})
            s.commit()


class DashboardCountTests(DashboardTestCase):
    def test_an_empty_shop_is_all_zeros(self):
        d = self.build()
        self.assertEqual(d.orders.total, 0)
        self.assertEqual(set(d.orders.by_status), {s.value for s in OrderStatus})
        self.assertEqual(set(d.orders.by_status.values()), {0})
        self.assertEqual((d.customers.total, d.customers.new_last_30_days), (0, 0))
        self.assertEqual(d.products.model_dump(), dict(total=0, active=0, inactive=0, low_stock=0, out_of_stock=0))
        self.assertEqual((d.revenue.all_time, d.revenue.last_30_days, d.revenue.all_time_orders), (0.0, 0.0, 0))
        self.assertEqual(d.recent_orders, [])

    def test_orders_are_counted_once_by_status(self):
        user = self.make_user()
        product = self.make_product(stock=100)
        plan = {
            OrderStatus.PENDING: 3,
            OrderStatus.CONFIRMED: 2,
            OrderStatus.PROCESSING: 1,
            OrderStatus.SHIPPED: 4,
            OrderStatus.DELIVERED: 5,
            OrderStatus.CANCELLED: 2,
            OrderStatus.REFUNDED: 1,
        }
        for status, n in plan.items():
            for _ in range(n):
                self.make_order(user, [(product, 1)], status=status, reserve_stock=False)
        d = self.build()
        self.assertEqual(d.orders.total, 18)
        self.assertEqual(d.orders.by_status, {s.value: n for s, n in plan.items()})
        self.assertEqual(sum(d.orders.by_status.values()), d.orders.total)

    def test_customers_exclude_admins_and_count_new_ones_in_the_window(self):
        old, recent, _admin = self.make_user(), self.make_user(), self.make_admin()
        self.make_user()
        with new_session() as s:
            s.execute(text("UPDATE users SET created_at = :t WHERE id = :id"), {"t": NOW - timedelta(days=45), "id": old.id})
            s.execute(text("UPDATE users SET created_at = :t WHERE id = :id"), {"t": NOW - timedelta(days=29), "id": recent.id})
            s.execute(text("UPDATE users SET created_at = :t WHERE role = 'admin'"), {"t": NOW - timedelta(days=1)})
            s.commit()
        d = self.build()
        self.assertEqual(d.customers.total, 3)
        # `recent` (29 days old) and the account made just now (real clock, later than NOW - 30d) are new.
        self.assertEqual(d.customers.new_last_30_days, 2)

    def test_product_stock_counts_follow_the_shops_own_rule(self):
        cases = [  # (quantity, reserved, threshold, active)
            (100, 0, 10, True),   # healthy
            (11, 0, 10, True),    # one above the threshold: healthy
            (10, 0, 10, True),    # at the threshold: low
            (20, 12, 10, True),   # available 8: low (reserved counts)
            (5, 0, 10, True),     # low
            (1, 0, 10, True),     # low
            (10, 10, 10, True),   # all reserved: out
            (0, 0, 10, True),     # empty: out
            (3, 0, None, True),   # NULL threshold = 0: never low, healthy
            (0, 0, None, True),   # out
            (0, 0, 10, False),    # inactive: never counted as out of stock
            (5, 0, 10, False),    # inactive: never counted as low
        ]
        products = []
        for qty, reserved, threshold, active in cases:
            p = self.make_product(stock=qty, reserved=reserved, active=active)
            with new_session() as s:
                s.query(Inventory).filter(Inventory.product_id == p.id).update({Inventory.low_stock_threshold: threshold})
                s.commit()
            products.append(p.id)
        # a product with no inventory row at all is unavailable
        orphan = self.make_product(stock=7)
        with new_session() as s:
            s.query(Inventory).filter(Inventory.product_id == orphan.id).delete()
            s.commit()

        d = self.build()
        self.assertEqual((d.products.total, d.products.active, d.products.inactive), (13, 11, 2))

        # Cross-check against the function the public shop uses for the same flags.
        low = out = 0
        with new_session() as s:
            for product in s.query(Product).filter(Product.is_active.is_(True)).all():
                if product.inventory is None:
                    out += 1
                    continue
                in_stock, low_stock = _compute_stock_flags(product)
                out += 0 if in_stock else 1
                low += 1 if low_stock else 0
        self.assertEqual((d.products.low_stock, d.products.out_of_stock), (low, out))
        self.assertEqual((d.products.low_stock, d.products.out_of_stock), (4, 4))


class DashboardRevenueTests(DashboardTestCase):
    def test_only_paid_orders_count(self):
        user = self.make_user()
        a = self.make_product(price="100.50", stock=50)
        b = self.make_product(price="200.00", stock=50)
        self.paid_order(user, a, 2)                                           # 201.00 counted
        self.paid_order(user, b, 1, status=OrderStatus.DELIVERED)            # 200.00 counted
        # ignored:
        self.make_order(user, [(a, 5)])                                       # unpaid, pending
        self.make_order(user, [(a, 5)], payment_status=OrderPaymentStatus.FAILED)
        self.make_order(user, [(a, 5)], status=OrderStatus.CANCELLED, reserve_stock=False)
        self.make_order(user, [(a, 5)], status=OrderStatus.REFUNDED, payment_status=OrderPaymentStatus.REFUNDED,
                        inventory_state=OrderInventoryState.CONSUMED)
        # defensive: an order somehow paid AND cancelled/refunded never counts
        self.paid_order(user, a, 3, status=OrderStatus.CANCELLED)
        self.paid_order(user, a, 3, status=OrderStatus.REFUNDED)
        d = self.build()
        self.assertEqual((d.revenue.all_time, d.revenue.all_time_orders), (401.0, 2))
        self.assertEqual((d.revenue.last_30_days, d.revenue.last_30_days_orders), (401.0, 2))
        self.assertEqual(d.revenue.currency, "INR")

    def test_the_thirty_day_window_is_dated_by_the_payment(self):
        user = self.make_user()
        p = self.make_product(price="100.00", stock=50)
        self.paid_order(user, p, 1, paid_days_ago=40)   # all-time only
        self.paid_order(user, p, 2, paid_days_ago=10)   # both
        self.paid_order(user, p, 3, paid_days_ago=0)    # both
        d = self.build()
        self.assertEqual((d.revenue.all_time, d.revenue.all_time_orders), (600.0, 3))
        self.assertEqual((d.revenue.last_30_days, d.revenue.last_30_days_orders), (500.0, 2))

    def test_the_window_edge_is_inclusive(self):
        user = self.make_user()
        p = self.make_product(price="100.00", stock=50)
        order = self.paid_order(user, p, 1, paid_days_ago=30)  # exactly NOW - 30d
        self.assertEqual(self.build().revenue.last_30_days_orders, 1)
        with new_session() as s:
            s.execute(text("UPDATE payments SET paid_at = paid_at - interval '1 second' WHERE order_id = :id"), {"id": order.id})
            s.commit()
        self.assertEqual(self.build().revenue.last_30_days_orders, 0)

    def test_an_order_with_two_captured_payments_is_counted_once(self):
        user = self.make_user()
        p = self.make_product(price="100.00", stock=50)
        order = self.paid_order(user, p, 1)
        self.make_payment(order, status=PaymentTransactionStatus.CAPTURED, paid_at=NOW - timedelta(days=2), refund_required=True)
        d = self.build()
        self.assertEqual((d.revenue.all_time, d.revenue.all_time_orders), (100.0, 1))

    def test_a_captured_payment_on_an_unpaid_order_adds_nothing(self):
        # e.g. the customer paid after the order expired: money to refund, not revenue
        user = self.make_user()
        p = self.make_product(price="100.00", stock=50)
        order = self.make_order(user, [(p, 1)], status=OrderStatus.CANCELLED, reserve_stock=False)
        self.make_payment(order, status=PaymentTransactionStatus.CAPTURED, refund_required=True)
        self.assertEqual(self.build().revenue.all_time, 0.0)

    def test_a_paid_order_without_a_payment_row_falls_back_to_its_own_date(self):
        user = self.make_user()
        p = self.make_product(price="100.00", stock=50)
        order = self.paid_order(user, p, 1, with_payment=False)
        self.assertEqual(self.build().revenue.last_30_days_orders, 1)
        self.set_order_columns(order, updated_at=NOW - timedelta(days=60))
        d = self.build()
        self.assertEqual((d.revenue.all_time_orders, d.revenue.last_30_days_orders), (1, 0))

    def test_revenue_is_what_the_customer_paid_not_the_goods_subtotal(self):
        user = self.make_user()
        p = self.make_product(price="100.00", stock=50)
        order = self.paid_order(user, p, 2)  # subtotal 200.00
        # discount 20, GST 9, delivery 40 -> customer paid 229.00
        self.set_order_columns(order, discount_amount=20, tax_amount=9, delivery_charge=40, total_amount=229)
        d = self.build()
        self.assertEqual((d.revenue.all_time, d.revenue.last_30_days), (229.0, 229.0))

    def test_money_is_exact_to_the_paisa(self):
        user = self.make_user()
        p = self.make_product(price="33.33", stock=50)
        for _ in range(3):
            self.paid_order(user, p, 1)
        self.assertEqual(self.build().revenue.all_time, 99.99)


class DashboardRecentTests(DashboardTestCase):
    def test_newest_first_capped_and_with_the_customer(self):
        user = self.make_user()
        with new_session() as s:
            s.execute(text("UPDATE users SET first_name = 'Asha', last_name = 'Rao' WHERE id = :id"), {"id": user.id})
            s.commit()
        p = self.make_product(stock=100)
        orders = [self.make_order(user, [(p, 1)]) for _ in range(12)]
        for i, o in enumerate(orders):
            self.set_order_columns(o, created_at=NOW - timedelta(hours=len(orders) - i))
        d = self.build()
        self.assertEqual(RECENT_ORDERS_LIMIT, 10)  # the documented size of the list
        self.assertEqual(len(d.recent_orders), 10)
        self.assertEqual([r.id for r in d.recent_orders], [o.id for o in reversed(orders)][:10])
        first = d.recent_orders[0]
        self.assertEqual((first.customer_name, first.customer_email), ("Asha Rao", user.email))
        self.assertEqual((first.status, first.payment_status), ("pending", "pending"))
        self.assertEqual(d.orders.total, 12)


class DashboardEfficiencyTests(DashboardTestCase):
    def statements(self):
        collected = []
        engine = _get_engine()
        listener = lambda conn, cur, stmt, *a: collected.append(stmt)
        sa_event.listen(engine, "before_cursor_execute", listener)
        try:
            self.build()
        finally:
            sa_event.remove(engine, "before_cursor_execute", listener)
        return collected

    def test_a_fixed_five_queries_whatever_the_size(self):
        small = self.statements()
        user = self.make_user()
        p = self.make_product(stock=500)
        for _ in range(25):
            self.paid_order(user, p, 1)
            self.make_order(user, [(p, 1)])
        large = self.statements()
        self.assertEqual((len(small), len(large)), (5, 5), large)

    def test_building_the_dashboard_changes_nothing(self):
        user = self.make_user()
        p = self.make_product(stock=10, reserved=3)
        self.paid_order(user, p, 1)
        before = (self.stock(p), self.count("orders"), self.count("payments"), self.count("inventory"))
        self.build()
        self.build()
        self.assertEqual(before, (self.stock(p), self.count("orders"), self.count("payments"), self.count("inventory")))
        with new_session() as s:
            self.assertEqual(s.query(AdminAuditEvent).count(), 0)

    def count(self, table):
        with new_session() as s:
            return s.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


class DashboardApiTests(DashboardTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(build_admin_app())
        self.admin = self.make_admin()

    def test_requires_an_admin(self):
        customer = self.make_user()
        self.assertEqual(self.client.get("/api/admin/dashboard").status_code, 401)
        self.assertEqual(self.client.get("/api/admin/dashboard", headers=bearer(customer)).status_code, 403)

    def test_shape_and_values(self):
        customer = self.make_user()
        p = self.make_product(price="250.00", stock=3)
        self.paid_order(customer, p, 2)
        r = self.client.get("/api/admin/dashboard", headers=bearer(self.admin))
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertEqual(set(data), {"generated_at", "orders", "customers", "products", "revenue", "recent_orders"})
        self.assertEqual(data["orders"]["total"], 1)
        self.assertEqual(data["orders"]["by_status"]["confirmed"], 1)
        self.assertEqual(data["revenue"]["all_time"], 500.0)
        self.assertEqual(data["customers"]["total"], 1)
        self.assertEqual(set(data["recent_orders"][0]), {"id", "order_number", "customer_name", "customer_email", "total_amount", "status", "payment_status", "created_at"})

    def test_no_secrets_or_payment_identifiers_leak(self):
        customer = self.make_user()
        p = self.make_product(stock=5)
        self.paid_order(customer, p, 1)
        text_ = self.client.get("/api/admin/dashboard", headers=bearer(self.admin)).text.lower()
        for needle in ["password", "hash", "razorpay", "gateway", "signature", "pay_t", "order_t", "token"]:
            self.assertNotIn(needle, text_)


if __name__ == "__main__":
    unittest.main()
