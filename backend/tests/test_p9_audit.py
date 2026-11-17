"""
Phase 9 M1 - the admin audit trail.

  AuditServiceUnitTests   guards: action format, secret-looking keys, JSON-safe values (no database)
  AuditServiceDbTests     the row, rollback atomicity, append-only usage
  AuditEndpointTests      GET /api/admin/audit-events: paging, filters, validation, ordering
"""

import unittest
import uuid
from decimal import Decimal
from unittest import mock

from fastapi.testclient import TestClient

from app.models import AdminAuditEvent, User
from app.services.audit_service import CLI_ACTOR, AuditService, _jsonable
from tests.p9_support import AdminTestCase, bearer, build_admin_app
from tests.pg_support import new_session


class AuditServiceUnitTests(unittest.TestCase):
    def service(self):
        return AuditService(mock.MagicMock())

    def admin(self):
        return mock.MagicMock(id=uuid.uuid4(), email="a@example.com")

    def test_bad_actions_are_refused(self):
        for action in ["", "product", "Product.update", "product.Update", "product.update.x", "product update", "1.x", "product.", ".update"]:
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.service().record(admin=self.admin(), action=action, entity_type="product")

    def test_bad_entity_types_are_refused(self):
        for entity in ["", "Product", "a b", "x.y", "1"]:
            with self.subTest(entity=entity), self.assertRaises(ValueError):
                self.service().record(admin=self.admin(), action="product.update", entity_type=entity)

    def test_secret_looking_keys_are_refused_at_any_depth(self):
        for payload in [
            {"password": "x"},
            {"password_hash": "x"},
            {"access_token": "x"},
            {"razorpay_signature": "x"},
            {"RAZORPAY_KEY_SECRET": "x"},
            {"nested": {"api_key": "x"}},
            {"items": [{"authorization": "x"}]},
        ]:
            for side in ("before", "after"):
                with self.subTest(payload=payload, side=side), self.assertRaises(ValueError):
                    self.service().record(admin=self.admin(), action="user.update", entity_type="user", **{side: payload})

    def test_ordinary_fields_are_accepted(self):
        svc = self.service()
        svc.record(
            admin=self.admin(),
            action="product.update",
            entity_type="product",
            before={"price": Decimal("10.50"), "sku": "A-1", "is_active": True},
            after={"price": Decimal("12.00"), "low_stock_threshold": 5},
        )
        svc.db.add.assert_called_once()
        event = svc.db.add.call_args[0][0]
        self.assertEqual(event.before["price"], "10.50")

    def test_an_event_needs_an_actor(self):
        with self.assertRaises(ValueError):
            self.service().record(admin=None, action="user.promote_admin", entity_type="user")

    def test_values_are_made_json_safe(self):
        import datetime
        import enum

        class Color(enum.Enum):
            RED = "red"

        u = uuid.uuid4()
        out = _jsonable({"d": Decimal("1.5"), "u": u, "e": Color.RED, "t": datetime.datetime(2026, 1, 2, 3, 4, 5), "l": [Decimal("2")]})
        self.assertEqual(out, {"d": "1.5", "u": str(u), "e": "red", "t": "2026-01-02T03:04:05", "l": ["2"]})
        with self.assertRaises(ValueError):
            _jsonable({"x": object()})


class AuditServiceDbTests(AdminTestCase):
    def test_the_event_is_written_with_the_admin_and_commits_with_the_caller(self):
        admin = self.make_admin()
        entity = uuid.uuid4()
        AuditService(self.db).record(
            admin=admin, action="product.update", entity_type="product", entity_id=entity,
            before={"price": Decimal("1.00")}, after={"price": Decimal("2.00")},
        )
        with new_session() as other:
            self.assertEqual(other.query(AdminAuditEvent).count(), 0)  # flushed, not committed
        self.db.commit()
        with new_session() as other:
            row = other.query(AdminAuditEvent).one()
            self.assertEqual((row.admin_user_id, row.admin_email, row.action, row.entity_id), (admin.id, admin.email, "product.update", entity))
            self.assertEqual((row.before, row.after), ({"price": "1.00"}, {"price": "2.00"}))
            self.assertIsNotNone(row.created_at)

    def test_the_event_is_flushed_so_the_caller_can_see_it_before_committing(self):
        admin = self.make_admin()
        event = AuditService(self.db).record(admin=admin, action="product.update", entity_type="product")
        self.assertIsNotNone(event.id)
        self.assertEqual(self.db.query(AdminAuditEvent).count(), 1)  # visible inside the open transaction
        self.db.rollback()

    def test_a_rollback_removes_the_event_with_the_change(self):
        admin = self.make_admin()
        AuditService(self.db).record(admin=admin, action="product.update", entity_type="product")
        self.db.rollback()
        with new_session() as other:
            self.assertEqual(other.query(AdminAuditEvent).count(), 0)

    def test_deleting_the_admin_keeps_the_trail_and_its_email(self):
        admin = self.make_admin()
        email = admin.email
        AuditService(self.db).record(admin=admin, action="product.update", entity_type="product")
        self.db.commit()
        with new_session() as s:
            s.delete(s.get(User, admin.id))
            s.commit()
        with new_session() as s:
            row = s.query(AdminAuditEvent).one()
            self.assertIsNone(row.admin_user_id)
            self.assertEqual(row.admin_email, email)

    def test_cli_events_have_no_user(self):
        AuditService(self.db).record(admin=None, actor_label=CLI_ACTOR, action="user.promote_admin", entity_type="user")
        self.db.commit()
        with new_session() as s:
            row = s.query(AdminAuditEvent).one()
            self.assertEqual((row.admin_user_id, row.admin_email), (None, CLI_ACTOR))


class AuditEndpointTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(build_admin_app())
        self.admin = self.make_admin()
        self.entity_a, self.entity_b = uuid.uuid4(), uuid.uuid4()
        svc = AuditService(self.db)
        for i in range(5):
            svc.record(admin=self.admin, action="product.update", entity_type="product", entity_id=self.entity_a, after={"n": i})
            self.db.commit()  # one transaction per event, as in production (now() is per transaction)
        svc.record(admin=self.admin, action="order.status_change", entity_type="order", entity_id=self.entity_b, after={"status": "shipped"})
        self.db.commit()

    def get(self, **params):
        return self.client.get("/api/admin/audit-events", params=params, headers=bearer(self.admin))

    def test_lists_newest_first_with_pagination(self):
        r = self.get(page_size=4)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertEqual(len(data["events"]), 4)
        self.assertEqual(data["events"][0]["action"], "order.status_change")
        self.assertEqual(data["pagination"], {"total": 6, "page": 1, "page_size": 4, "total_pages": 2, "has_next": True, "has_previous": False})
        second = self.get(page_size=4, page=2).json()["data"]
        self.assertEqual(len(second["events"]), 2)
        self.assertFalse(second["pagination"]["has_next"])
        ids = [e["id"] for e in data["events"]] + [e["id"] for e in second["events"]]
        self.assertEqual(len(set(ids)), 6)

    def test_filters(self):
        self.assertEqual(self.get(entity_type="order").json()["data"]["pagination"]["total"], 1)
        self.assertEqual(self.get(entity_id=str(self.entity_a)).json()["data"]["pagination"]["total"], 5)
        self.assertEqual(self.get(action="product.update").json()["data"]["pagination"]["total"], 5)
        self.assertEqual(self.get(entity_type="product", action="order.status_change").json()["data"]["pagination"]["total"], 0)

    def test_an_empty_result_has_zero_pages(self):
        p = self.get(entity_type="nothing").json()["data"]["pagination"]
        self.assertEqual((p["total"], p["total_pages"], p["has_next"]), (0, 0, False))

    def test_bad_parameters_are_422(self):
        for params in [{"page": 0}, {"page_size": 0}, {"page_size": 51}, {"entity_id": "x"}, {"entity_type": "A;DROP"}, {"action": "nodot"}]:
            with self.subTest(params=params):
                self.assertEqual(self.get(**params).status_code, 422)

    def test_the_response_has_exactly_the_documented_fields(self):
        event = self.get(page_size=1).json()["data"]["events"][0]
        self.assertEqual(set(event), {"id", "admin_user_id", "admin_email", "action", "entity_type", "entity_id", "before", "after", "created_at"})

    def test_one_page_is_two_queries_not_one_per_row(self):
        from sqlalchemy import event as sa_event

        from tests.pg_support import _get_engine

        statements = []
        engine = _get_engine()
        listener = lambda conn, cur, stmt, *a: statements.append(stmt)
        sa_event.listen(engine, "before_cursor_execute", listener)
        try:
            self.assertEqual(self.get(page_size=50).status_code, 200)
        finally:
            sa_event.remove(engine, "before_cursor_execute", listener)
        audit = [s for s in statements if "admin_audit_events" in s]
        self.assertEqual(len(audit), 2, audit)


if __name__ == "__main__":
    unittest.main()
