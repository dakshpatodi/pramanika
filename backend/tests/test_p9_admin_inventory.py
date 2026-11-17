"""
Phase 9 M4 - admin inventory.

  InventorySchemaTests     request validation (no database)
  InventoryViewTests       lists/filters/sorting/paging; reads change nothing; reservation detail
  InventorySetTests        set quantity with expected_quantity
  InventoryAdjustTests     adjust by +/-n
  InventoryThresholdTests  low-stock threshold; combined requests are atomic
  InventoryAuditTests      what is written to the audit trail
  InventoryInvariantTests  reservations, checkout, cancel and payment keep working
  InventoryRaceTests       real threads: no lost updates, never below reserved
"""

import unittest
import uuid

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event as sa_event
from sqlalchemy import text

from app.models import AdminAuditEvent, Inventory
from app.repositories.inventory_repository import InventoryRepository
from app.schemas.admin_inventory import InventoryUpdate
from app.services.admin_inventory_service import AdminInventoryService
from app.services.order_service import OrderService
from tests.p9_support import AdminTestCase, bearer, build_admin_app
from tests.pg_support import _get_engine, new_session, run_concurrently


class InventorySchemaTests(unittest.TestCase):
    def test_valid_shapes(self):
        InventoryUpdate(quantity=5, expected_quantity=3)
        InventoryUpdate(adjust_by=-2, reason="  recount  ")
        InventoryUpdate(adjust_by=5)
        InventoryUpdate(low_stock_threshold=0)
        self.assertEqual(InventoryUpdate(adjust_by=1, reason="   ").reason, None)

    def test_invalid_shapes(self):
        bad = [
            {}, {"quantity": 5}, {"expected_quantity": 1}, {"quantity": 5, "expected_quantity": 1, "adjust_by": 1},
            {"adjust_by": 0}, {"adjust_by": None}, {"quantity": None, "expected_quantity": 1},
            {"adjust_by": True}, {"adjust_by": "5"}, {"adjust_by": 1.0}, {"adjust_by": 1_000_001}, {"adjust_by": -1_000_001},
            {"quantity": -1, "expected_quantity": 1}, {"quantity": 1_000_001, "expected_quantity": 1}, {"quantity": "5", "expected_quantity": 1},
            {"quantity": 5.5, "expected_quantity": 1}, {"quantity": 5, "expected_quantity": -1},
            {"low_stock_threshold": -1}, {"low_stock_threshold": 1.5}, {"low_stock_threshold": 1, "reason": "x"},
            {"adjust_by": 1, "reason": "x" * 201},
            {"reserved_quantity": 0, "adjust_by": 1}, {"product_id": str(uuid.uuid4()), "adjust_by": 1}, {"id": 1, "adjust_by": 1},
            {"is_active": False, "adjust_by": 1}, {"price": 1, "adjust_by": 1},
        ]
        for body in bad:
            with self.subTest(body=body), self.assertRaises(ValidationError):
                InventoryUpdate(**body)


class InventoryCase(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(build_admin_app(with_shop=True))
        self.admin = self.make_admin()
        self.h = bearer(self.admin)

    def url(self, product):
        return f"/api/admin/inventory/{product.id}"

    def patch(self, product, body):
        return self.client.patch(self.url(product), json=body, headers=self.h)

    def detail(self, product):
        return self.client.get(self.url(product), headers=self.h).json()["data"]

    def audit(self):
        with new_session() as s:
            return s.query(AdminAuditEvent).order_by(AdminAuditEvent.created_at).all()

    def db_inventory(self, product):
        with new_session() as s:
            row = s.query(Inventory).filter(Inventory.product_id == product.id).one()
            return row.quantity, row.reserved_quantity, row.low_stock_threshold, row.updated_at


class InventoryViewTests(InventoryCase):
    def get(self, **params):
        return self.client.get("/api/admin/inventory", params=params, headers=self.h)

    def names(self, **params):
        return [i["name"] for i in self.get(**params).json()["data"]["items"]]

    def seed(self):
        self.healthy = self.make_product(stock=50, name="Healthy")
        self.lowp = self.make_product(stock=5, name="Lowish")
        self.edge = self.make_product(stock=10, name="Edge")
        self.out = self.make_product(stock=0, name="Empty")
        self.allres = self.make_product(stock=4, name="AllReserved")
        self.inactive = self.make_product(stock=0, active=False, name="Dormant")
        user = self.make_user()
        self.make_order(user, [(self.allres, 4)])  # reserves all 4

    def test_list_shape_and_the_low_and_out_lists(self):
        self.seed()
        data = self.get(page_size=100).json()["data"]
        self.assertEqual(data["pagination"]["total"], 6)
        row = next(i for i in data["items"] if i["name"] == "AllReserved")
        self.assertEqual(
            (row["quantity"], row["reserved_quantity"], row["available_quantity"], row["stock_status"]), (4, 4, 0, "out")
        )
        self.assertEqual(
            set(row),
            {"product_id", "name", "sku", "is_active", "category", "quantity", "reserved_quantity", "available_quantity",
             "low_stock_threshold", "stock_status", "updated_at"},
        )
        self.assertEqual(sorted(self.names(stock="low")), ["Edge", "Lowish"])  # at the threshold counts as low
        self.assertEqual(sorted(self.names(stock="out")), ["AllReserved", "Dormant", "Empty"])
        self.assertEqual(sorted(self.names(stock="ok")), ["Healthy"])

    def test_the_lists_agree_with_the_dashboard_counts(self):
        self.seed()
        d = self.client.get("/api/admin/dashboard", headers=self.h).json()["data"]["products"]
        low = self.get(stock="low", is_active="true").json()["data"]["pagination"]["total"]
        out = self.get(stock="out", is_active="true").json()["data"]["pagination"]["total"]
        self.assertEqual((low, out), (d["low_stock"], d["out_of_stock"]))

    def test_search_filters_sorting_and_paging(self):
        self.seed()
        self.assertEqual(self.names(search="lowi"), ["Lowish"])
        self.assertEqual(self.names(is_active="false"), ["Dormant"])
        self.assertEqual(self.names(sort="available", order="desc")[0], "Healthy")
        self.assertEqual(self.names(sort="quantity", order="asc")[-1], "Healthy")
        self.assertEqual(self.names(sort="name", order="asc"), sorted(self.names(page_size=100), key=str.lower))
        self.assertEqual(self.names(sort="sku", order="asc"), sorted(self.names(page_size=100), key=lambda n: next(
            p.sku for p in [self.healthy, self.lowp, self.edge, self.out, self.allres, self.inactive] if p.name == n)))
        seen = []
        for page in (1, 2, 3):
            seen += self.names(page=page, page_size=2, sort="available")
        self.assertEqual((len(seen), len(set(seen))), (6, 6))
        p = self.get(page_size=4).json()["data"]["pagination"]
        self.assertEqual((p["total_pages"], p["has_next"], p["has_previous"]), (2, True, False))

    def test_bad_parameters_are_422(self):
        for params in [{"page": 0}, {"page_size": 101}, {"stock": "plenty"}, {"sort": "price"}, {"order": "up"}, {"category_id": "x"}]:
            with self.subTest(params=params):
                self.assertEqual(self.get(**params).status_code, 422)

    def test_viewing_changes_nothing(self):
        self.seed()
        before = [self.db_inventory(p) for p in (self.healthy, self.lowp, self.allres)]
        self.get(page_size=100)
        self.get(stock="low")
        for p in (self.healthy, self.allres):
            self.detail(p)
        self.assertEqual(before, [self.db_inventory(p) for p in (self.healthy, self.lowp, self.allres)])
        self.assertEqual(self.audit(), [])

    def test_reads_take_no_locks_and_use_two_queries(self):
        self.seed()
        statements = []
        engine = _get_engine()
        listener = lambda conn, cur, stmt, *a: statements.append(stmt)
        sa_event.listen(engine, "before_cursor_execute", listener)
        try:
            self.get(page_size=100)
        finally:
            sa_event.remove(engine, "before_cursor_execute", listener)
        shop = [s for s in statements if "FROM products" in s]
        self.assertEqual(len(shop), 2, shop)
        self.assertFalse([s for s in statements if "FOR UPDATE" in s or "FOR SHARE" in s])

    def test_detail_shows_what_holds_the_reservation(self):
        self.seed()
        user = self.make_user()
        self.make_order(user, [(self.healthy, 3)])
        self.make_order(user, [(self.healthy, 2)])
        d = self.detail(self.healthy)
        self.assertEqual((d["reserved_quantity"], d["open_order_count"], d["open_order_units"], d["reservations_match"]), (5, 2, 5, True))
        clean = self.detail(self.lowp)
        self.assertEqual((clean["open_order_count"], clean["open_order_units"], clean["reservations_match"]), (0, 0, True))

    def test_detail_flags_books_that_have_drifted(self):
        self.seed()
        with new_session() as s:
            s.execute(text("UPDATE inventory SET reserved_quantity = 2 WHERE product_id = :p"), {"p": self.healthy.id})
            s.commit()
        d = self.detail(self.healthy)
        self.assertEqual((d["reserved_quantity"], d["open_order_units"], d["reservations_match"]), (2, 0, False))

    def test_a_cancelled_or_expired_order_no_longer_counts(self):
        self.seed()
        user = self.make_user()
        order = self.make_order(user, [(self.healthy, 3)])
        with new_session() as s:
            OrderService(s).cancel_order(user.id, order.id)
        d = self.detail(self.healthy)
        self.assertEqual((d["reserved_quantity"], d["open_order_units"], d["reservations_match"]), (0, 0, True))

    def test_unknown_product(self):
        self.assertEqual(self.client.get(f"/api/admin/inventory/{uuid.uuid4()}", headers=self.h).status_code, 404)
        self.assertEqual(self.client.get("/api/admin/inventory/nope", headers=self.h).status_code, 422)


class InventorySetTests(InventoryCase):
    def test_set_with_the_value_you_saw(self):
        p = self.make_product(stock=10)
        r = self.patch(p, {"quantity": 25, "expected_quantity": 10})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()["data"]
        self.assertEqual((d["quantity"], d["available_quantity"], d["stock_status"]), (25, 25, "ok"))
        self.assertEqual(self.db_inventory(p)[:2], (25, 0))

    def test_a_stale_expected_quantity_is_refused_and_changes_nothing(self):
        p = self.make_product(stock=10)
        before = self.db_inventory(p)
        r = self.patch(p, {"quantity": 25, "expected_quantity": 7})
        self.assertEqual(r.status_code, 409)
        self.assertIn("now 10", r.json()["message"])
        self.assertEqual(self.db_inventory(p), before)
        self.assertEqual(self.audit(), [])

    def test_a_sale_between_view_and_save_is_not_overwritten(self):
        p = self.make_product(stock=10)
        user = self.make_user()
        order = self.make_order(user, [(p, 3)])
        seen = self.detail(p)["quantity"]  # admin loads: 10
        with new_session() as s:  # payment captured: 3 units consumed (quantity 7, reserved 0)
            InventoryRepository(s).consume(p.id, 3)
            s.commit()
        r = self.patch(p, {"quantity": 15, "expected_quantity": seen})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.db_inventory(p)[:2], (7, 0))

    def test_cannot_set_below_reserved_but_can_set_to_it(self):
        p = self.make_product(stock=10)
        self.make_order(self.make_user(), [(p, 4)])
        r = self.patch(p, {"quantity": 3, "expected_quantity": 10})
        self.assertEqual(r.status_code, 409)
        self.assertIn("4 unit(s) are reserved", r.json()["message"])
        self.assertEqual(self.db_inventory(p)[:2], (10, 4))
        r = self.patch(p, {"quantity": 4, "expected_quantity": 10})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()["data"]
        self.assertEqual((d["quantity"], d["reserved_quantity"], d["available_quantity"], d["stock_status"]), (4, 4, 0, "out"))

    def test_set_to_zero_when_nothing_is_reserved(self):
        p = self.make_product(stock=10)
        r = self.patch(p, {"quantity": 0, "expected_quantity": 10})
        self.assertEqual((r.status_code, r.json()["data"]["stock_status"]), (200, "out"))

    def test_setting_the_same_value_is_a_quiet_no_op(self):
        p = self.make_product(stock=10)
        before = self.db_inventory(p)
        r = self.patch(p, {"quantity": 10, "expected_quantity": 10})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.db_inventory(p), before)
        self.assertEqual(self.audit(), [])

    def test_bad_bodies_are_422_and_change_nothing(self):
        p = self.make_product(stock=10)
        before = self.db_inventory(p)
        for body in [{}, {"quantity": 5}, {"quantity": -1, "expected_quantity": 10}, {"quantity": 2_000_000, "expected_quantity": 10},
                     {"quantity": "5", "expected_quantity": 10}, {"quantity": 5, "expected_quantity": 10, "reserved_quantity": 0},
                     {"quantity": 5, "expected_quantity": 10, "adjust_by": 1}]:
            with self.subTest(body=body):
                self.assertEqual(self.patch(p, body).status_code, 422)
        self.assertEqual(self.db_inventory(p), before)

    def test_unknown_product_is_404(self):
        r = self.client.patch(f"/api/admin/inventory/{uuid.uuid4()}", json={"adjust_by": 1}, headers=self.h)
        self.assertEqual(r.status_code, 404)


class InventoryAdjustTests(InventoryCase):
    def test_receive_and_write_off(self):
        p = self.make_product(stock=10)
        self.assertEqual(self.patch(p, {"adjust_by": 15}).json()["data"]["quantity"], 25)
        self.assertEqual(self.patch(p, {"adjust_by": -5}).json()["data"]["quantity"], 20)
        self.assertEqual(self.db_inventory(p)[:2], (20, 0))

    def test_cannot_remove_below_zero(self):
        p = self.make_product(stock=3)
        r = self.patch(p, {"adjust_by": -4})
        self.assertEqual(r.status_code, 409)
        self.assertIn("only 3 in stock", r.json()["message"])
        self.assertEqual(self.db_inventory(p)[:2], (3, 0))

    def test_cannot_remove_into_the_reserved_units(self):
        p = self.make_product(stock=10)
        self.make_order(self.make_user(), [(p, 4)])
        r = self.patch(p, {"adjust_by": -7})
        self.assertEqual(r.status_code, 409)
        self.assertIn("at most 6 can be removed", r.json()["message"])
        self.assertEqual(self.patch(p, {"adjust_by": -6}).status_code, 200)
        d = self.detail(p)
        self.assertEqual((d["quantity"], d["reserved_quantity"], d["available_quantity"]), (4, 4, 0))
        self.assertEqual(self.patch(p, {"adjust_by": -1}).status_code, 409)

    def test_the_total_cannot_exceed_the_cap(self):
        p = self.make_product(stock=999_990)
        r = self.patch(p, {"adjust_by": 20})
        self.assertEqual(r.status_code, 409)
        self.assertIn("1,000,000", r.json()["message"])
        self.assertEqual(self.patch(p, {"adjust_by": 10}).status_code, 200)

    def test_reason_is_kept_in_the_audit_trail(self):
        p = self.make_product(stock=10)
        self.patch(p, {"adjust_by": -2, "reason": "  damaged in transit  "})
        (event,) = self.audit()
        self.assertEqual(event.after["reason"], "damaged in transit")


class InventoryThresholdTests(InventoryCase):
    def test_threshold_changes_the_status_without_touching_stock(self):
        p = self.make_product(stock=20)
        self.assertEqual(self.detail(p)["stock_status"], "ok")
        r = self.patch(p, {"low_stock_threshold": 25})
        self.assertEqual((r.status_code, r.json()["data"]["stock_status"], r.json()["data"]["quantity"]), (200, "low", 20))
        r = self.patch(p, {"low_stock_threshold": 0})
        self.assertEqual(r.json()["data"]["stock_status"], "ok")
        self.assertEqual(self.db_inventory(p)[:2], (20, 0))

    def test_threshold_can_be_set_with_an_adjustment_in_one_request(self):
        p = self.make_product(stock=20)
        r = self.patch(p, {"adjust_by": -15, "low_stock_threshold": 8})
        d = r.json()["data"]
        self.assertEqual((r.status_code, d["quantity"], d["low_stock_threshold"], d["stock_status"]), (200, 5, 8, "low"))
        self.assertEqual(len(self.audit()), 1)  # one request, one audit row

    def test_a_refused_adjustment_does_not_apply_the_threshold(self):
        p = self.make_product(stock=3)
        before = self.db_inventory(p)
        r = self.patch(p, {"adjust_by": -9, "low_stock_threshold": 99})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.db_inventory(p)[:3], before[:3])
        self.assertEqual(self.audit(), [])

    def test_an_unchanged_threshold_writes_nothing(self):
        p = self.make_product(stock=3)
        self.assertEqual(self.patch(p, {"low_stock_threshold": 10}).status_code, 200)
        self.assertEqual(self.audit(), [])


class InventoryAuditTests(InventoryCase):
    def test_set_is_audited_with_only_the_changed_fields(self):
        p = self.make_product(stock=10)
        self.patch(p, {"quantity": 30, "expected_quantity": 10, "low_stock_threshold": 10, "reason": "stock-take"})
        (event,) = self.audit()
        self.assertEqual((event.action, event.entity_type, event.entity_id, event.admin_user_id), ("inventory.update", "inventory", p.id, self.admin.id))
        self.assertEqual(event.before, {"quantity": 10})
        self.assertEqual(event.after, {"quantity": 30, "method": "set", "reason": "stock-take"})

    def test_adjust_is_audited_with_the_delta(self):
        p = self.make_product(stock=10)
        self.patch(p, {"adjust_by": 5})
        (event,) = self.audit()
        self.assertEqual(event.before, {"quantity": 10})
        self.assertEqual(event.after, {"quantity": 15, "method": "adjust", "adjust_by": 5})

    def test_a_refusal_leaves_no_audit_row(self):
        p = self.make_product(stock=2)
        self.patch(p, {"adjust_by": -5})
        self.patch(p, {"quantity": 0, "expected_quantity": 99})
        self.assertEqual(self.audit(), [])


class InventoryInvariantTests(InventoryCase):
    def test_a_missing_inventory_row_is_created_on_demand(self):
        p = self.make_product(stock=5)
        with new_session() as s:
            s.query(Inventory).filter(Inventory.product_id == p.id).delete()
            s.commit()
        self.assertEqual(self.detail(p)["stock_status"], "out")
        r = self.patch(p, {"adjust_by": 12})
        self.assertEqual((r.status_code, r.json()["data"]["quantity"], r.json()["data"]["low_stock_threshold"]), (200, 12, 10))
        with new_session() as s:
            self.assertEqual(s.query(Inventory).filter(Inventory.product_id == p.id).count(), 1)

    def test_raising_stock_makes_it_buyable_and_the_shop_agrees(self):
        p = self.make_product(stock=0)
        self.assertFalse(self.client.get(f"/api/products/{p.slug}").json()["data"]["in_stock"])
        self.patch(p, {"adjust_by": 30})
        pub = self.client.get(f"/api/products/{p.slug}").json()["data"]
        self.assertEqual((pub["in_stock"], pub["low_stock"]), (True, False))
        r = self.client.post("/api/cart/items", json={"product_id": str(p.id), "quantity": 2}, headers=bearer(self.make_user()))
        self.assertEqual(r.status_code, 200, r.text)

    def test_the_full_reservation_lifecycle_stays_consistent_with_admin_changes(self):
        p = self.make_product(stock=10)
        user = self.make_user()
        order = self.make_order(user, [(p, 6)])                          # reserved 6
        self.assertEqual(self.patch(p, {"adjust_by": -5}).status_code, 409)   # would drop to 5 < 6
        self.assertEqual(self.patch(p, {"adjust_by": -4}).status_code, 200)   # quantity 6 == reserved 6
        with new_session() as s:                                          # nothing left to reserve
            self.assertFalse(InventoryRepository(s).try_reserve(p.id, 1))
        with new_session() as s:                                          # customer cancels: units come back
            OrderService(s).cancel_order(user.id, order.id)
        self.assertEqual(self.db_inventory(p)[:2], (6, 0))
        self.assertEqual(self.patch(p, {"quantity": 2, "expected_quantity": 6}).status_code, 200)  # now allowed
        d = self.detail(p)
        self.assertEqual((d["quantity"], d["reserved_quantity"], d["reservations_match"]), (2, 0, True))

    def test_a_payment_consuming_stock_still_works_after_an_admin_change(self):
        p = self.make_product(stock=10)
        self.make_order(self.make_user(), [(p, 3)])
        self.patch(p, {"adjust_by": 5})                                   # 15 / reserved 3
        with new_session() as s:
            self.assertTrue(InventoryRepository(s).consume(p.id, 3))
            s.commit()
        self.assertEqual(self.db_inventory(p)[:2], (12, 0))

    def test_the_database_checks_are_the_last_line_of_defence(self):
        # Even if the application check were bypassed, the CHECK still refuses.
        from sqlalchemy.exc import IntegrityError

        p = self.make_product(stock=10, reserved=4)
        with new_session() as s:
            with self.assertRaises(IntegrityError):
                s.execute(text("UPDATE inventory SET quantity = 3 WHERE product_id = :p"), {"p": p.id})
            s.rollback()

    def test_nothing_in_the_admin_api_can_write_reserved_quantity(self):
        p = self.make_product(stock=10, reserved=2)
        for body in [{"reserved_quantity": 0}, {"reserved_quantity": 0, "adjust_by": 1}, {"quantity": 5, "expected_quantity": 10, "reserved_quantity": 0}]:
            self.assertEqual(self.patch(p, body).status_code, 422)
        self.assertEqual(self.db_inventory(p)[:2], (10, 2))


class InventoryRepositoryRuleTests(InventoryCase):
    """The conditional UPDATEs carry the rules themselves (the service also checks,
    but the statement must be safe on its own - it is what the database enforces)."""

    def run_write(self, fn):
        with new_session() as s:
            result = fn(AdminInventoryRepositoryFor(s))
            s.commit()
            return result

    def test_set_quantity_only_applies_to_the_value_that_was_expected(self):
        p = self.make_product(stock=10)
        self.assertFalse(self.run_write(lambda r: r.set_quantity(p.id, 9, 20)))
        self.assertEqual(self.db_inventory(p)[0], 10)
        self.assertTrue(self.run_write(lambda r: r.set_quantity(p.id, 10, 20)))
        self.assertEqual(self.db_inventory(p)[0], 20)

    def test_set_quantity_refuses_to_go_below_reserved(self):
        p = self.make_product(stock=10, reserved=4)
        self.assertFalse(self.run_write(lambda r: r.set_quantity(p.id, 10, 3)))
        self.assertTrue(self.run_write(lambda r: r.set_quantity(p.id, 10, 4)))
        self.assertEqual(self.db_inventory(p)[:2], (4, 4))

    def test_add_quantity_respects_reserved_zero_and_cap(self):
        p = self.make_product(stock=10, reserved=4)
        self.assertFalse(self.run_write(lambda r: r.add_quantity(p.id, -7)))
        self.assertTrue(self.run_write(lambda r: r.add_quantity(p.id, -6)))
        self.assertFalse(self.run_write(lambda r: r.add_quantity(p.id, -1)))
        self.assertFalse(self.run_write(lambda r: r.add_quantity(p.id, 1_000_000)))
        self.assertTrue(self.run_write(lambda r: r.add_quantity(p.id, 999_996)))
        self.assertEqual(self.db_inventory(p)[:2], (1_000_000, 4))


def AdminInventoryRepositoryFor(session):
    from app.repositories.admin_inventory_repository import AdminInventoryRepository

    return AdminInventoryRepository(session)


class InventoryLockTests(InventoryCase):
    def statements(self, action):
        collected = []
        engine = _get_engine()
        listener = lambda conn, cur, stmt, *a: collected.append(stmt)
        sa_event.listen(engine, "before_cursor_execute", listener)
        try:
            action()
        finally:
            sa_event.remove(engine, "before_cursor_execute", listener)
        return collected

    def test_every_stock_write_locks_the_inventory_row_and_uses_conditional_updates(self):
        p = self.make_product(stock=10)
        calls = {
            "set": {"quantity": 12, "expected_quantity": 10},
            "adjust": {"adjust_by": 1},
            "threshold": {"low_stock_threshold": 3},
        }
        for name, body in calls.items():
            with self.subTest(action=name):
                stmts = self.statements(lambda: self.patch(p, body))
                self.assertTrue([s for s in stmts if "FOR UPDATE" in s and "FROM inventory" in s], f"{name}: inventory row not locked")
                updates = [s for s in stmts if s.startswith("UPDATE inventory")]
                self.assertEqual(len(updates), 1, updates)
                if name != "threshold":
                    self.assertIn("WHERE", updates[0])
                    self.assertIn("reserved_quantity", updates[0])  # the reservation rule is in the WHERE clause


class InventoryRaceTests(InventoryCase):
    def clients(self, n):
        return [TestClient(build_admin_app(with_public=False)) for _ in range(n)]

    def test_concurrent_adjustments_are_never_lost(self):
        p = self.make_product(stock=0)
        url, pid = self.url(p), p.id        # read ORM attributes here, not inside the threads
        cs = self.clients(10)
        results = run_concurrently([
            (lambda c=c: c.patch(url, json={"adjust_by": 1}, headers=self.h).status_code) for c in cs
        ])
        self.assertEqual([v for _, v in results], [200] * 10, results)
        self.assertEqual(self.db_inventory(p)[0], 10)
        self.assertEqual(len(self.audit()), 10)

    def test_concurrent_removals_stop_at_the_reserved_floor(self):
        p = self.make_product(stock=10)
        self.make_order(self.make_user(), [(p, 4)])             # floor: 4
        url = self.url(p)
        cs = self.clients(4)
        results = run_concurrently([
            (lambda c=c: c.patch(url, json={"adjust_by": -3}, headers=self.h).status_code) for c in cs
        ])
        codes = sorted(v for _, v in results)
        self.assertEqual(codes, [200, 200, 409, 409], results)   # 10 -> 7 -> 4, then refused
        self.assertEqual(self.db_inventory(p)[:2], (4, 4))

    def test_two_admins_setting_from_the_same_view_get_one_winner(self):
        p = self.make_product(stock=10)
        url = self.url(p)
        a, b = self.clients(2)
        results = run_concurrently([
            lambda: a.patch(url, json={"quantity": 20, "expected_quantity": 10}, headers=self.h).status_code,
            lambda: b.patch(url, json={"quantity": 30, "expected_quantity": 10}, headers=self.h).status_code,
        ])
        self.assertEqual(sorted(v for _, v in results), [200, 409], results)
        self.assertIn(self.db_inventory(p)[0], (20, 30))

    def test_admin_lowering_stock_while_customers_reserve(self):
        for round_ in range(6):
            p = self.make_product(stock=10)
            url, pid = self.url(p), p.id
            (admin_client,) = self.clients(1)

            def admin_removes():
                return admin_client.patch(url, json={"adjust_by": -8}, headers=self.h).status_code

            def checkout_reserves():
                s = new_session()
                try:
                    ok = InventoryRepository(s).try_reserve(pid, 5)
                    s.commit()
                    return ok
                finally:
                    s.close()

            results = run_concurrently([admin_removes, checkout_reserves])
            self.assertEqual([k for k, _ in results], ["ok", "ok"], results)
            quantity, reserved, *_ = self.db_inventory(p)
            self.assertGreaterEqual(quantity, reserved)   # the invariant, whichever won
            admin_code, reserved_ok = results[0][1], results[1][1]
            # removing 8 of 10 leaves 2: valid only if the 5 were not reserved first
            self.assertIn((admin_code, reserved_ok, quantity, reserved), {(200, False, 2, 0), (409, True, 10, 5)})


if __name__ == "__main__":
    unittest.main()
