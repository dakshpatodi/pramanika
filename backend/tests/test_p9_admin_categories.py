"""
Phase 9 M3 - admin category management.

  CategoryRulesTests      pure format rules (no database)
  CategoryWriteTests      create / edit / (de)activate: validation, uniqueness, audit, atomicity
  CategoryListTests       list: counts, search, filters, sorting, paging
  CategoryShopTests       the public shop reacts correctly; no delete exists
  CategoryRaceTests       deactivating vs adding a product at the same moment
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.models import AdminAuditEvent, Category, Product
from app.services.catalog_rules import normalise_slug, slugify, validate_image_url
from tests.p9_support import AdminTestCase, bearer, build_admin_app
from tests.pg_support import new_session, run_concurrently


class CategoryRulesTests(unittest.TestCase):
    def test_slugify(self):
        for text, expected in [("Rolled Oats & Honey!", "rolled-oats-honey"), ("Café Müesli", "cafe-muesli"), ("  a   b  ", "a-b"), ("!!!", ""), ("100% Natural", "100-natural")]:
            with self.subTest(text=text):
                self.assertEqual(slugify(text), expected)

    def test_slug_format(self):
        self.assertEqual(normalise_slug("  Rolled-Oats "), "rolled-oats")
        for bad in ["", "a b", "a--b", "-a", "a-", "a_b", "é", "a/b", "../x"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalise_slug(bad)

    def test_image_urls(self):
        for good in ["https://cdn.example.com/a.png", "http://x.io/a?b=1", "/images/a.png"]:
            validate_image_url(good)
        for bad in ["javascript:alert(1)", "data:image/png;base64,AAA", "//evil.com/a.png", "ftp://x/a", "a.png", "https://x y/a.png", ""]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_image_url(bad)


class CategoryApiCase(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(build_admin_app(with_shop=True))
        self.admin = self.make_admin()
        self.h = bearer(self.admin)

    def post(self, body, path="/api/admin/categories"):
        return self.client.post(path, json=body, headers=self.h)

    def patch(self, cid, body):
        return self.client.patch(f"/api/admin/categories/{cid}", json=body, headers=self.h)

    def make_category(self, name="Cereals", **extra):
        r = self.post({"name": name, **extra})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["data"]

    def audit(self, action=None):
        with new_session() as s:
            q = s.query(AdminAuditEvent).order_by(AdminAuditEvent.created_at)
            if action:
                q = q.filter(AdminAuditEvent.action == action)
            return q.all()

    def category_count(self):
        with new_session() as s:
            return s.query(Category).count()


class CategoryWriteTests(CategoryApiCase):
    def test_create_makes_a_slug_from_the_name_and_audits_it(self):
        data = self.make_category("Ready Mixes", description="  Just add water  ", image_url="/img/rm.png")
        self.assertEqual((data["name"], data["slug"], data["is_active"]), ("Ready Mixes", "ready-mixes", True))
        self.assertEqual((data["description"], data["product_count"], data["active_product_count"]), ("Just add water", 0, 0))
        (event,) = self.audit("category.create")
        self.assertEqual((event.admin_user_id, event.entity_id), (self.admin.id, uuid.UUID(data["id"])))
        self.assertEqual(event.after["slug"], "ready-mixes")
        self.assertIsNone(event.before)

    def test_an_explicit_slug_is_used_and_normalised(self):
        self.assertEqual(self.make_category("Cereals", slug="  Grain-Foods ")["slug"], "grain-foods")

    def test_duplicates_are_refused_with_409_and_leave_nothing_behind(self):
        self.make_category("Cereals")
        for body in [{"name": "Cereals"}, {"name": "cereals"}, {"name": "CEREALS "}, {"name": "Other", "slug": "cereals"}]:
            with self.subTest(body=body):
                r = self.post(body)
                self.assertEqual(r.status_code, 409, r.text)
                self.assertFalse(r.json()["success"])
                self.assertRegex(r.json()["message"], r"^(name|slug): .*(already exists|already used)")  # the friendly pre-check, not the DB error
        self.assertEqual(self.category_count(), 1)
        self.assertEqual(len(self.audit("category.create")), 1)

    def test_a_name_that_makes_no_slug_needs_one_given(self):
        r = self.post({"name": "!!!"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("slug", r.json()["message"])
        self.assertEqual(self.post({"name": "!!!", "slug": "symbols"}).status_code, 201)

    def test_invalid_input_is_422(self):
        bad = [
            {}, {"name": ""}, {"name": "   "}, {"name": "x" * 101}, {"name": "A", "slug": "Bad Slug"},
            {"name": "A", "slug": "x" * 121}, {"name": "A", "image_url": "javascript:alert(1)"},
            {"name": "A", "description": "x" * 2001}, {"name": "A", "is_active": "maybe"},
            {"name": "A", "id": str(uuid.uuid4())}, {"name": "A", "created_at": "2020-01-01"}, {"name": "A", "product_count": 5},
        ]
        for body in bad:
            with self.subTest(body=str(body)[:60]):
                self.assertEqual(self.post(body).status_code, 422)
        self.assertEqual(self.category_count(), 0)

    def test_update_changes_only_what_was_sent_and_audits_before_and_after(self):
        c = self.make_category("Cereals", description="Old")
        r = self.patch(c["id"], {"name": "Breakfast Cereals", "slug": "breakfast-cereals"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()["data"]
        self.assertEqual((d["name"], d["slug"], d["description"]), ("Breakfast Cereals", "breakfast-cereals", "Old"))
        (event,) = self.audit("category.update")
        self.assertEqual(event.before, {"name": "Cereals", "slug": "cereals"})
        self.assertEqual(event.after, {"name": "Breakfast Cereals", "slug": "breakfast-cereals"})

    def test_optional_fields_can_be_cleared_but_name_and_slug_cannot(self):
        c = self.make_category("Cereals", description="x", image_url="/a.png")
        d = self.patch(c["id"], {"description": None, "image_url": None}).json()["data"]
        self.assertEqual((d["description"], d["image_url"]), (None, None))
        for body in [{"name": None}, {"slug": None}]:
            with self.subTest(body=body):
                self.assertEqual(self.patch(c["id"], body).status_code, 422)

    def test_a_no_op_update_writes_nothing(self):
        c = self.make_category("Cereals")
        r = self.patch(c["id"], {"name": "Cereals", "slug": "cereals"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"]["updated_at"], c["updated_at"])
        self.assertEqual(self.audit("category.update"), [])

    def test_update_conflicts_and_bad_bodies(self):
        a, b = self.make_category("A"), self.make_category("B")
        self.assertEqual(self.patch(b["id"], {"name": "a"}).status_code, 409)
        self.assertEqual(self.patch(b["id"], {"slug": a["slug"]}).status_code, 409)
        for body in [{}, {"is_active": False}, {"id": str(uuid.uuid4())}, {"slug": "Bad Slug"}]:
            with self.subTest(body=body):
                self.assertEqual(self.patch(b["id"], body).status_code, 422)
        self.assertEqual(self.patch(str(uuid.uuid4()), {"name": "Z"}).status_code, 404)
        self.assertEqual(self.patch("not-a-uuid", {"name": "Z"}).status_code, 422)
        self.assertEqual(self.audit("category.update"), [])

    def test_a_category_can_keep_its_own_name_while_changing_case(self):
        c = self.make_category("Cereals")
        self.assertEqual(self.patch(c["id"], {"name": "CEREALS"}).status_code, 200)

    def test_deactivate_is_refused_while_active_products_use_it(self):
        c = self.make_category("Cereals")
        p1 = self.make_product_in(c["id"])
        p2 = self.make_product_in(c["id"])
        r = self.post({}, f"/api/admin/categories/{c['id']}/deactivate")
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("2 active product", r.json()["message"])
        self.assertEqual(self.audit("category.deactivate"), [])
        self.client.post(f"/api/admin/products/{p1}/deactivate", headers=self.h)
        self.assertEqual(self.post({}, f"/api/admin/categories/{c['id']}/deactivate").status_code, 409)
        self.client.post(f"/api/admin/products/{p2}/deactivate", headers=self.h)
        r = self.post({}, f"/api/admin/categories/{c['id']}/deactivate")  # inactive products do not block
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["data"]["is_active"], r.json()["data"]["product_count"], r.json()["data"]["active_product_count"]), (False, 2, 0))

    def test_activate_and_deactivate_are_idempotent_and_audited_once(self):
        c = self.make_category("Cereals")
        for _ in range(2):
            self.assertEqual(self.post({}, f"/api/admin/categories/{c['id']}/deactivate").status_code, 200)
        self.assertEqual(len(self.audit("category.deactivate")), 1)
        for _ in range(2):
            self.assertEqual(self.post({}, f"/api/admin/categories/{c['id']}/activate").status_code, 200)
        self.assertEqual(len(self.audit("category.activate")), 1)
        self.assertEqual(self.post({}, f"/api/admin/categories/{uuid.uuid4()}/activate").status_code, 404)

    def make_product_in(self, category_id, **extra):
        n = uuid.uuid4().hex[:8]
        body = {"category_id": category_id, "name": f"P {n}", "sku": f"SKU-{n}", "price": "10.00", "initial_quantity": 5}
        body.update(extra)
        r = self.client.post("/api/admin/products", json=body, headers=self.h)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["data"]["id"]


class CategoryListTests(CategoryApiCase):
    def get(self, **params):
        return self.client.get("/api/admin/categories", params=params, headers=self.h)

    def test_counts_search_filters_sorting_and_paging(self):
        cereals = self.make_category("Cereals")
        mixes = self.make_category("Ready Mixes")
        self.make_category("100% Natural")
        self.make_category("Under_score")
        for _ in range(2):
            CategoryWriteTests.make_product_in(self, cereals["id"])
        pid = CategoryWriteTests.make_product_in(self, mixes["id"])
        self.client.post(f"/api/admin/products/{pid}/deactivate", headers=self.h)
        self.client.post(f"/api/admin/categories/{self.make_category('Hidden')['id']}/deactivate", headers=self.h)

        data = self.get(page_size=100).json()["data"]
        by_name = {c["name"]: c for c in data["categories"]}
        self.assertEqual((by_name["Cereals"]["product_count"], by_name["Cereals"]["active_product_count"]), (2, 2))
        self.assertEqual((by_name["Ready Mixes"]["product_count"], by_name["Ready Mixes"]["active_product_count"]), (1, 0))
        self.assertEqual(data["pagination"]["total"], 5)  # includes the inactive one

        self.assertEqual([c["name"] for c in self.get(search="mix").json()["data"]["categories"]], ["Ready Mixes"])
        self.assertEqual([c["name"] for c in self.get(search="%").json()["data"]["categories"]], ["100% Natural"])
        self.assertEqual([c["name"] for c in self.get(search="_").json()["data"]["categories"]], ["Under_score"])
        self.assertEqual([c["name"] for c in self.get(is_active="false").json()["data"]["categories"]], ["Hidden"])
        self.assertEqual(self.get(is_active="true").json()["data"]["pagination"]["total"], 4)

        names = [c["name"] for c in self.get(sort="name", order="asc", page_size=100).json()["data"]["categories"]]
        self.assertEqual(names, sorted(names, key=str.lower))
        top = self.get(sort="product_count", order="desc").json()["data"]["categories"][0]
        self.assertEqual(top["name"], "Cereals")

        page1 = self.get(page_size=2).json()["data"]
        page3 = self.get(page_size=2, page=3).json()["data"]
        self.assertEqual((len(page1["categories"]), page1["pagination"]["total_pages"], page1["pagination"]["has_next"]), (2, 3, True))
        self.assertEqual((len(page3["categories"]), page3["pagination"]["has_next"], page3["pagination"]["has_previous"]), (1, False, True))

    def test_bad_parameters_are_422(self):
        for params in [{"page": 0}, {"page_size": 101}, {"sort": "id; drop table"}, {"order": "sideways"}, {"is_active": "perhaps"}]:
            with self.subTest(params=params):
                self.assertEqual(self.get(**params).status_code, 422)

    def test_get_one(self):
        c = self.make_category("Cereals")
        self.assertEqual(self.client.get(f"/api/admin/categories/{c['id']}", headers=self.h).json()["data"]["name"], "Cereals")
        self.assertEqual(self.client.get(f"/api/admin/categories/{uuid.uuid4()}", headers=self.h).status_code, 404)


class CategoryShopTests(CategoryApiCase):
    def test_a_deactivated_category_leaves_the_public_shop_and_comes_back(self):
        c = self.make_category("Cereals")
        self.assertEqual([x["slug"] for x in self.client.get("/api/categories").json()["data"]], ["cereals"])
        self.post({}, f"/api/admin/categories/{c['id']}/deactivate")
        self.assertEqual(self.client.get("/api/categories").json()["data"], [])
        self.assertEqual(self.client.get("/api/categories/cereals").status_code, 404)
        self.post({}, f"/api/admin/categories/{c['id']}/activate")
        self.assertEqual(self.client.get("/api/categories/cereals").status_code, 200)

    def test_there_is_no_way_to_delete_a_category(self):
        c = self.make_category("Cereals")
        for method in ("delete", "put"):
            r = getattr(self.client, method)(f"/api/admin/categories/{c['id']}", headers=self.h)
            self.assertEqual(r.status_code, 405)
        self.assertEqual(self.client.delete("/api/admin/categories", headers=self.h).status_code, 405)
        self.assertEqual(self.category_count(), 1)

    def test_the_public_listing_is_unchanged_by_inactive_categories(self):
        a, b = self.make_category("A"), self.make_category("B")
        self.post({}, f"/api/admin/categories/{b['id']}/deactivate")
        slugs = [x["slug"] for x in self.client.get("/api/categories").json()["data"]]
        self.assertEqual(slugs, ["a"])


class CategoryLockTests(CategoryApiCase):
    def locking_statements(self, action):
        from sqlalchemy import event as sa_event

        from tests.pg_support import _get_engine

        collected = []
        engine = _get_engine()
        listener = lambda conn, cur, stmt, *a: collected.append(stmt)
        sa_event.listen(engine, "before_cursor_execute", listener)
        try:
            action()
        finally:
            sa_event.remove(engine, "before_cursor_execute", listener)
        return [st for st in collected if "FOR UPDATE" in st and "FROM categories" in st]

    def test_every_category_write_takes_the_row_for_update(self):
        c = self.make_category("Cereals")
        cid = c["id"]
        calls = {
            "update": lambda: self.patch(cid, {"name": "Cereals 2"}),
            "deactivate": lambda: self.post({}, f"/api/admin/categories/{cid}/deactivate"),
            "activate": lambda: self.post({}, f"/api/admin/categories/{cid}/activate"),
        }
        for name, call in calls.items():
            with self.subTest(action=name):
                self.assertTrue(self.locking_statements(call), f"{name} did not lock the category row")


class CategoryRaceTests(CategoryApiCase):
    def test_deactivating_never_strands_an_active_product_in_an_inactive_category(self):
        outcomes = set()
        for round_ in range(8):
            c = self.make_category(f"Race {round_}")
            client_a, client_b = TestClient(build_admin_app(with_public=False)), TestClient(build_admin_app(with_public=False))

            def deactivate():
                return client_a.post(f"/api/admin/categories/{c['id']}/deactivate", headers=self.h).status_code

            def add_product():
                return client_b.post(
                    "/api/admin/products", headers=self.h,
                    json={"category_id": c["id"], "name": f"R{round_}", "sku": f"RACE-{round_}", "price": "5.00"},
                ).status_code

            (k1, deact), (k2, create) = run_concurrently([deactivate, add_product])
            self.assertEqual((k1, k2), ("ok", "ok"))
            outcomes.add((deact, create))
            with new_session() as s:
                category = s.get(Category, uuid.UUID(c["id"]))
                active = s.query(Product).filter(Product.category_id == category.id, Product.is_active.is_(True)).count()
                self.assertFalse(not category.is_active and active, f"inactive category with {active} active product(s): {deact}/{create}")
            self.assertIn((deact, create), {(200, 422), (409, 201)}, (deact, create))


if __name__ == "__main__":
    unittest.main()
