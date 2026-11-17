"""
Phase 9 M3 - admin product management.

  ProductSchemaTests     request validation (no database)
  ProductCreateTests     create: inventory row, uniqueness, category rules, audit, atomicity
  ProductUpdateTests     edit: partial changes, merged-value checks, no-ops, locks
  ProductActiveTests     activate / deactivate and what they do (and do not do) to the shop
  ProductListTests       search, filters, sorting, paging, query count
  ProductShopTests       public shop and cart keep working with admin-made products
  ProductConcurrencyTests  duplicate SKU/slug races -> clean 409; lock vs checkout
"""

import unittest
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event as sa_event
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.models import AdminAuditEvent, Category, Inventory, Order, OrderStatus, Product
from app.repositories.inventory_repository import InventoryRepository
from app.schemas.admin_catalog import ProductCreate, ProductUpdate
from app.services.order_service import OrderService
from app.services.product_service import _compute_stock_flags
from tests.p9_support import AdminTestCase, bearer, build_admin_app
from tests.pg_support import _get_engine, new_session, run_concurrently

CAT = str(uuid.uuid4())


class ProductSchemaTests(unittest.TestCase):
    base = dict(category_id=CAT, name="Oats", sku="oat-1", price="10.50")

    def test_normalisation(self):
        p = ProductCreate(**{**self.base, "name": "  Oats  ", "sku": " oat-1 ", "description": "   ", "slug": " Rolled-Oats "})
        self.assertEqual((p.name, p.sku, p.description, p.slug), ("Oats", "OAT-1", None, "rolled-oats"))
        self.assertEqual((p.price, p.initial_quantity, p.low_stock_threshold, p.is_active), (Decimal("10.50"), 0, 10, True))

    def test_bad_values(self):
        bad = [
            {"price": "0"}, {"price": "-1"}, {"price": "1.234"}, {"price": True}, {"price": "abc"}, {"price": "NaN"}, {"price": "Infinity"},
            {"price": "123456789.00"}, {"compare_at_price": "10.50"}, {"compare_at_price": "9"}, {"weight": "1"}, {"weight_unit": "kg"},
            {"weight": "1", "weight_unit": "stone"}, {"weight": "0", "weight_unit": "kg"}, {"weight": "1.2345", "weight_unit": "kg"},
            {"slug": "Bad Slug"}, {"sku": "has space"}, {"sku": "-lead"}, {"sku": ""}, {"sku": "x" * 51}, {"name": ""}, {"name": "x" * 201},
            {"image_url": "javascript:alert(1)"}, {"initial_quantity": -1}, {"initial_quantity": 1_000_001}, {"initial_quantity": 1.5},
            {"low_stock_threshold": -1}, {"short_description": "x" * 501}, {"category_id": "nope"},
            {"id": str(uuid.uuid4())}, {"reserved_quantity": 5}, {"created_at": "2020-01-01"}, {"role": "admin"},
        ]
        for extra in bad:
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                ProductCreate(**{**self.base, **extra})

    def test_update_rules(self):
        ProductUpdate(description=None)  # optional fields may be cleared
        for body in [{}, {"name": None}, {"sku": None}, {"price": None}, {"slug": None}, {"category_id": None},
                     {"is_active": True}, {"quantity": 5}, {"initial_quantity": 5}, {"reserved_quantity": 1}, {"id": str(uuid.uuid4())}]:
            with self.subTest(body=body), self.assertRaises(ValidationError):
                ProductUpdate(**body)


class ProductApiCase(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(build_admin_app(with_shop=True))
        self.admin = self.make_admin()
        self.h = bearer(self.admin)
        self.cat = self.make_category("Cereals")

    def make_category(self, name, **extra):
        r = self.client.post("/api/admin/categories", json={"name": name, **extra}, headers=self.h)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["data"]

    def body(self, **extra):
        n = uuid.uuid4().hex[:8]
        body = {"category_id": self.cat["id"], "name": f"Product {n}", "sku": f"sku-{n}", "price": "100.00", "initial_quantity": 20}
        body.update(extra)
        return body

    def create(self, **extra):
        r = self.client.post("/api/admin/products", json=self.body(**extra), headers=self.h)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["data"]

    def post(self, path, json=None):
        return self.client.post(path, json=json or {}, headers=self.h)

    def patch(self, pid, body):
        return self.client.patch(f"/api/admin/products/{pid}", json=body, headers=self.h)

    def audit(self, action=None):
        with new_session() as s:
            q = s.query(AdminAuditEvent).order_by(AdminAuditEvent.created_at)
            if action:
                q = q.filter(AdminAuditEvent.action == action)
            return q.all()

    def db_product(self, pid):
        with new_session() as s:
            p = s.get(Product, uuid.UUID(pid))
            inv = s.query(Inventory).filter(Inventory.product_id == p.id).one_or_none()
            return p, (inv.quantity, inv.reserved_quantity, inv.low_stock_threshold) if inv else None

    def counts(self):
        with new_session() as s:
            return s.query(Product).count(), s.query(Inventory).count()


class ProductCreateTests(ProductApiCase):
    def test_create_makes_the_product_and_its_inventory_row_and_audits_it(self):
        d = self.create(name="Rolled Oats", sku=" prm-oat-1 ", price="99.50", compare_at_price="120", weight="500", weight_unit="g",
                        description="  Whole grain  ", initial_quantity=40, low_stock_threshold=7, image_url="/img/oats.png")
        self.assertEqual((d["slug"], d["sku"], d["price"], d["compare_at_price"]), ("rolled-oats", "PRM-OAT-1", 99.5, 120.0))
        self.assertEqual((d["weight"], d["weight_unit"], d["description"], d["is_active"]), (500.0, "g", "Whole grain", True))
        self.assertEqual((d["quantity"], d["reserved_quantity"], d["available_quantity"], d["low_stock_threshold"], d["stock_status"]), (40, 0, 40, 7, "ok"))
        self.assertEqual(d["category"]["slug"], "cereals")
        product, stock = self.db_product(d["id"])
        self.assertEqual(stock, (40, 0, 7))
        (event,) = self.audit("product.create")
        self.assertEqual((event.admin_user_id, event.entity_id), (self.admin.id, uuid.UUID(d["id"])))
        self.assertEqual((event.after["sku"], event.after["price"], event.after["initial_quantity"]), ("PRM-OAT-1", "99.50", 40))
        self.assertNotIn("password", str(event.after).lower())

    def test_defaults_and_stock_statuses(self):
        d = self.create(initial_quantity=0)
        self.assertEqual((d["quantity"], d["low_stock_threshold"], d["stock_status"]), (0, 10, "out"))
        self.assertEqual(self.create(initial_quantity=4)["stock_status"], "low")
        self.assertEqual(self.create(initial_quantity=11)["stock_status"], "ok")

    def test_duplicates_are_409_and_atomic(self):
        first = self.create(name="Oats", sku="OAT-1")
        before = self.counts()
        cases = [dict(sku="OAT-1"), dict(sku="oat-1"), dict(sku=" Oat-1 "), dict(sku="NEW-1", slug=first["slug"]), dict(sku="NEW-2", name="Oats")]
        for extra in cases:
            with self.subTest(extra=extra):
                r = self.client.post("/api/admin/products", json=self.body(**extra), headers=self.h)
                self.assertEqual(r.status_code, 409, r.text)
                self.assertFalse(r.json()["success"])
        self.assertEqual(self.counts(), before)
        self.assertEqual(len(self.audit("product.create")), 1)

    def test_a_legacy_lower_case_sku_still_blocks_a_new_one(self):
        d = self.create(sku="ABC-1")
        with new_session() as s:
            s.execute(text("UPDATE products SET sku = 'abc-9' WHERE id = :id"), {"id": d["id"]})
            s.commit()
        self.assertEqual(self.client.post("/api/admin/products", json=self.body(sku="ABC-9"), headers=self.h).status_code, 409)

    def test_category_must_exist_and_be_active(self):
        for cid in (str(uuid.uuid4()),):
            r = self.client.post("/api/admin/products", json=self.body(category_id=cid), headers=self.h)
            self.assertEqual(r.status_code, 422)
            self.assertIn("category_id", r.json()["message"])
        inactive = self.make_category("Dormant")
        self.post(f"/api/admin/categories/{inactive['id']}/deactivate")
        r = self.client.post("/api/admin/products", json=self.body(category_id=inactive["id"]), headers=self.h)
        self.assertEqual(r.status_code, 422)
        self.assertIn("inactive", r.json()["message"])
        self.assertEqual(self.counts(), (0, 0))

    def test_an_inactive_product_can_be_created(self):
        d = self.create(is_active=False)
        self.assertFalse(d["is_active"])

    def test_invalid_bodies_create_nothing(self):
        for extra in [dict(price="0"), dict(price="1.234"), dict(compare_at_price="50"), dict(weight="1"), dict(quantity=5), dict(id=str(uuid.uuid4())), dict(sku="bad sku")]:
            with self.subTest(extra=extra):
                self.assertEqual(self.client.post("/api/admin/products", json=self.body(**extra), headers=self.h).status_code, 422)
        self.assertEqual(self.counts(), (0, 0))

    def test_a_name_with_no_slug_needs_one_given(self):
        self.assertEqual(self.client.post("/api/admin/products", json=self.body(name="***"), headers=self.h).status_code, 422)
        self.assertEqual(self.client.post("/api/admin/products", json=self.body(name="***", slug="stars"), headers=self.h).status_code, 201)


class ProductUpdateTests(ProductApiCase):
    def test_partial_update_changes_only_what_was_sent_and_never_stock(self):
        d = self.create(name="Oats", price="100", description="Keep", initial_quantity=33)
        r = self.patch(d["id"], {"price": "120.25", "name": "Rolled Oats", "short_description": "Quick"})
        self.assertEqual(r.status_code, 200, r.text)
        n = r.json()["data"]
        self.assertEqual((n["price"], n["name"], n["short_description"], n["description"]), (120.25, "Rolled Oats", "Quick", "Keep"))
        self.assertEqual((n["slug"], n["sku"], n["quantity"]), (d["slug"], d["sku"], 33))
        (event,) = self.audit("product.update")
        self.assertEqual(event.before, {"price": "100.00", "name": "Oats", "short_description": None})
        self.assertEqual(event.after, {"price": "120.25", "name": "Rolled Oats", "short_description": "Quick"})

    def test_a_no_op_update_writes_nothing(self):
        d = self.create(price="100")
        r = self.patch(d["id"], {"price": "100.00", "name": d["name"], "sku": d["sku"].lower()})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"]["updated_at"], d["updated_at"])
        self.assertEqual(self.audit("product.update"), [])

    def test_stock_active_flag_and_identity_cannot_be_set_through_an_edit(self):
        d = self.create(initial_quantity=5)
        for body in [{"quantity": 999}, {"reserved_quantity": 0}, {"is_active": False}, {"id": str(uuid.uuid4())}, {"created_at": "2020-01-01T00:00:00Z"}, {"low_stock_threshold": 1}]:
            with self.subTest(body=body):
                self.assertEqual(self.patch(d["id"], body).status_code, 422)
        _, stock = self.db_product(d["id"])
        self.assertEqual(stock, (5, 0, 10))
        self.assertEqual(self.audit("product.update"), [])

    def test_compare_at_price_is_checked_against_the_merged_values(self):
        d = self.create(price="50", compare_at_price="100")
        self.assertEqual(self.patch(d["id"], {"price": "100"}).status_code, 422)   # price would reach compare_at
        self.assertEqual(self.patch(d["id"], {"price": "150"}).status_code, 422)
        self.assertEqual(self.patch(d["id"], {"compare_at_price": "50"}).status_code, 422)
        self.assertEqual(self.patch(d["id"], {"price": "60", "compare_at_price": "70"}).status_code, 200)
        self.assertEqual(self.patch(d["id"], {"compare_at_price": None}).status_code, 200)
        self.assertEqual(self.patch(d["id"], {"price": "500"}).status_code, 200)
        p, _ = self.db_product(d["id"])
        self.assertEqual((p.price, p.compare_at_price), (Decimal("500.00"), None))

    def test_weight_and_unit_move_together(self):
        d = self.create(weight="500", weight_unit="g")
        self.assertEqual(self.patch(d["id"], {"weight": None}).status_code, 422)
        self.assertEqual(self.patch(d["id"], {"weight_unit": None}).status_code, 422)
        self.assertEqual(self.patch(d["id"], {"weight": "1.5", "weight_unit": "kg"}).status_code, 200)
        r = self.patch(d["id"], {"weight": None, "weight_unit": None})
        self.assertEqual((r.status_code, r.json()["data"]["weight"], r.json()["data"]["weight_unit"]), (200, None, None))
        self.assertEqual(self.patch(d["id"], {"weight": "2"}).status_code, 422)  # unit is now missing

    def test_sku_and_slug_changes_respect_uniqueness(self):
        a, b = self.create(sku="A-1", name="Aaa"), self.create(sku="B-1", name="Bbb")
        self.assertEqual(self.patch(b["id"], {"sku": "a-1"}).status_code, 409)
        self.assertEqual(self.patch(b["id"], {"slug": a["slug"]}).status_code, 409)
        ok = self.patch(b["id"], {"sku": "b-2", "slug": "bbb-new"})
        self.assertEqual((ok.status_code, ok.json()["data"]["sku"], ok.json()["data"]["slug"]), (200, "B-2", "bbb-new"))
        p, _ = self.db_product(a["id"])
        self.assertEqual((p.sku, p.slug), ("A-1", a["slug"]))

    def test_moving_category(self):
        other = self.make_category("Mixes")
        dormant = self.make_category("Dormant")
        self.post(f"/api/admin/categories/{dormant['id']}/deactivate")
        d = self.create()
        r = self.patch(d["id"], {"category_id": other["id"]})
        self.assertEqual((r.status_code, r.json()["data"]["category"]["slug"]), (200, "mixes"))
        self.assertEqual(self.patch(d["id"], {"category_id": dormant["id"]}).status_code, 422)   # active product -> inactive category
        self.assertEqual(self.patch(d["id"], {"category_id": str(uuid.uuid4())}).status_code, 422)
        self.post(f"/api/admin/products/{d['id']}/deactivate")
        self.assertEqual(self.patch(d["id"], {"category_id": dormant["id"]}).status_code, 200)  # inactive product may rest there
        self.assertEqual(self.post(f"/api/admin/products/{d['id']}/activate").status_code, 409)  # ...but cannot be activated there

    def test_clearing_optional_text(self):
        d = self.create(description="x", ingredients="y", image_url="/a.png")
        n = self.patch(d["id"], {"description": None, "ingredients": "   ", "image_url": None}).json()["data"]
        self.assertEqual((n["description"], n["ingredients"], n["image_url"]), (None, None, None))

    def test_missing_and_malformed_ids(self):
        self.assertEqual(self.patch(str(uuid.uuid4()), {"name": "x"}).status_code, 404)
        self.assertEqual(self.patch("nope", {"name": "x"}).status_code, 422)

    def test_a_failed_update_changes_nothing(self):
        a, b = self.create(sku="A-1", name="Aaa"), self.create(sku="B-1", name="Bbb")
        r = self.patch(b["id"], {"name": "Changed", "price": "77", "sku": "A-1"})
        self.assertEqual(r.status_code, 409)
        p, _ = self.db_product(b["id"])
        self.assertEqual((p.name, p.price, p.sku), ("Bbb", Decimal("100.00"), "B-1"))
        self.assertEqual(self.audit("product.update"), [])


class ProductActiveTests(ProductApiCase):
    def test_deactivate_hides_the_product_but_leaves_stock_and_orders_alone(self):
        user = self.make_user()
        d = self.create(initial_quantity=10)
        product = self.db_product(d["id"])[0]
        order = self.make_order(user, [(product, 3)])  # reserves 3
        self.assertEqual(self.db_product(d["id"])[1], (10, 3, 10))
        r = self.post(f"/api/admin/products/{d['id']}/deactivate")
        self.assertEqual((r.status_code, r.json()["data"]["is_active"]), (200, False))
        self.assertEqual(self.db_product(d["id"])[1], (10, 3, 10))                     # stock and reservation untouched
        with new_session() as s:
            self.assertEqual(s.get(Order, order.id).status, OrderStatus.PENDING)       # the order is untouched
        # the customer can still cancel it and the reservation is released exactly once
        with new_session() as s:
            OrderService(s).cancel_order(user.id, order.id)
        self.assertEqual(self.db_product(d["id"])[1], (10, 0, 10))
        (event,) = self.audit("product.deactivate")
        self.assertEqual((event.before, event.after), ({"is_active": True}, {"is_active": False}))

    def test_activate_and_deactivate_are_idempotent_and_audited_once(self):
        d = self.create()
        for _ in range(2):
            self.assertEqual(self.post(f"/api/admin/products/{d['id']}/deactivate").status_code, 200)
        for _ in range(2):
            self.assertEqual(self.post(f"/api/admin/products/{d['id']}/activate").status_code, 200)
        self.assertEqual((len(self.audit("product.deactivate")), len(self.audit("product.activate"))), (1, 1))
        self.assertEqual(self.post(f"/api/admin/products/{uuid.uuid4()}/activate").status_code, 404)

    def test_activation_needs_an_active_category(self):
        d = self.create()
        self.post(f"/api/admin/products/{d['id']}/deactivate")
        self.post(f"/api/admin/categories/{self.cat['id']}/deactivate")
        r = self.post(f"/api/admin/products/{d['id']}/activate")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.audit("product.activate"), [])
        self.post(f"/api/admin/categories/{self.cat['id']}/activate")
        self.assertEqual(self.post(f"/api/admin/products/{d['id']}/activate").status_code, 200)

    def test_there_is_no_product_delete(self):
        d = self.create()
        for method in ("delete", "put"):
            self.assertEqual(getattr(self.client, method)(f"/api/admin/products/{d['id']}", headers=self.h).status_code, 405)
        self.assertEqual(self.counts(), (1, 1))


class ProductListTests(ProductApiCase):
    def get(self, **params):
        return self.client.get("/api/admin/products", params=params, headers=self.h)

    def seed(self):
        mixes = self.make_category("Mixes")
        self.ids = {
            "oats": self.create(name="Rolled Oats", sku="OAT-1", price="30", initial_quantity=50)["id"],
            "muesli": self.create(name="Fruit Muesli", sku="MUS-1", price="10", initial_quantity=5)["id"],
            "poha": self.create(name="Instant Poha", sku="POH-1", price="20", initial_quantity=0, category_id=mixes["id"])["id"],
            "idli": self.create(name="Idli Mix", sku="IDL-1", price="20", initial_quantity=100, category_id=mixes["id"])["id"],
            "pct": self.create(name="50% Off Bundle", sku="PCT_1", price="5", initial_quantity=11)["id"],
            "edge": self.create(name="Edge Case", sku="EDG-1", price="7", initial_quantity=10)["id"],  # exactly at the threshold
        }
        self.post(f"/api/admin/products/{self.ids['idli']}/deactivate")
        self.mixes = mixes

    def names(self, **params):
        return [p["name"] for p in self.get(**params).json()["data"]["products"]]

    def test_the_list_includes_inactive_products_with_category_and_stock(self):
        self.seed()
        data = self.get(page_size=100).json()["data"]
        self.assertEqual(data["pagination"]["total"], 6)
        idli = next(p for p in data["products"] if p["sku"] == "IDL-1")
        self.assertFalse(idli["is_active"])
        self.assertEqual((idli["category"]["name"], idli["available_quantity"], idli["stock_status"]), ("Mixes", 100, "ok"))
        self.assertEqual(set(idli), {"id", "name", "slug", "sku", "price", "compare_at_price", "image_url", "is_active", "category", "quantity",
                                     "reserved_quantity", "available_quantity", "low_stock_threshold", "stock_status", "created_at", "updated_at"})
        # the list is light: long text and weight appear only on the single-product view

    def test_search_by_name_sku_slug_with_wildcards_escaped(self):
        self.seed()
        self.assertEqual(self.names(search="oats"), ["Rolled Oats"])
        self.assertEqual(self.names(search="mus-1"), ["Fruit Muesli"])
        self.assertEqual(self.names(search="instant-poha"), ["Instant Poha"])
        self.assertEqual(self.names(search="%"), ["50% Off Bundle"])
        self.assertEqual(self.names(search="_"), ["50% Off Bundle"])
        self.assertEqual(self.names(search="zzz"), [])
        self.assertEqual(self.names(search="' OR 1=1 --"), [])

    def test_filters(self):
        self.seed()
        self.assertEqual(sorted(self.names(category_id=self.mixes["id"])), ["Idli Mix", "Instant Poha"])
        self.assertEqual(self.names(is_active="false"), ["Idli Mix"])
        self.assertEqual(self.get(is_active="true").json()["data"]["pagination"]["total"], 5)
        self.assertEqual(self.names(stock="out"), ["Instant Poha"])
        self.assertEqual(sorted(self.names(stock="low")), ["Edge Case", "Fruit Muesli"])  # at the threshold counts as low
        self.assertEqual(sorted(self.names(stock="ok")), ["50% Off Bundle", "Idli Mix", "Rolled Oats"])
        self.assertEqual(self.names(search="mix", category_id=self.mixes["id"], is_active="false"), ["Idli Mix"])

    def test_stock_filters_agree_with_the_shops_own_rule(self):
        self.seed()
        with new_session() as s:
            for product in s.query(Product).all():
                in_stock, low = _compute_stock_flags(product)
                expected = "low" if low else ("ok" if in_stock else "out")
                row = next(p for p in self.get(page_size=100).json()["data"]["products"] if p["id"] == str(product.id))
                self.assertEqual(row["stock_status"], expected, product.name)

    def test_sorting_and_stable_paging(self):
        self.seed()
        self.assertEqual(self.names(sort="price", order="asc")[0], "50% Off Bundle")
        self.assertEqual(self.names(sort="price", order="desc")[0], "Rolled Oats")
        self.assertEqual(self.names(sort="name", order="asc"), ["50% Off Bundle", "Edge Case", "Fruit Muesli", "Idli Mix", "Instant Poha", "Rolled Oats"])
        self.assertEqual(self.names(sort="available", order="desc")[:2], ["Idli Mix", "Rolled Oats"])
        self.assertEqual(self.names(sort="sku", order="asc")[0], "Edge Case")
        default = self.get().json()["data"]["products"]
        self.assertEqual(default[0]["name"], "Edge Case")  # newest first
        seen = []
        for page in (1, 2, 3):
            seen += self.names(sort="price", order="asc", page=page, page_size=2)
        self.assertEqual(len(seen), 6)
        self.assertEqual(len(set(seen)), 6)  # equal prices tie-break by id: no duplicates, none missing
        p = self.get(page_size=2).json()["data"]["pagination"]
        self.assertEqual((p["total"], p["total_pages"], p["has_next"], p["has_previous"]), (6, 3, True, False))

    def test_bad_parameters_are_422(self):
        for params in [{"page": 0}, {"page_size": 0}, {"page_size": 101}, {"sort": "price; drop table products"}, {"order": "up"},
                       {"stock": "plenty"}, {"category_id": "x"}, {"is_active": "perhaps"}, {"search": ""}]:
            with self.subTest(params=params):
                self.assertEqual(self.get(**params).status_code, 422)

    def test_two_queries_per_page_whatever_the_size(self):
        self.seed()
        statements = []
        engine = _get_engine()
        listener = lambda conn, cur, stmt, *a: statements.append(stmt)
        sa_event.listen(engine, "before_cursor_execute", listener)
        try:
            self.assertEqual(self.get(page_size=100).status_code, 200)
        finally:
            sa_event.remove(engine, "before_cursor_execute", listener)
        shop = [s for s in statements if "FROM products" in s or "FROM categories" in s]
        self.assertEqual(len(shop), 2, shop)

    def test_get_one(self):
        d = self.create(description="Full text")
        r = self.client.get(f"/api/admin/products/{d['id']}", headers=self.h)
        self.assertEqual((r.status_code, r.json()["data"]["description"]), (200, "Full text"))
        self.assertEqual(self.client.get(f"/api/admin/products/{uuid.uuid4()}", headers=self.h).status_code, 404)


class ProductShopTests(ProductApiCase):
    def test_an_admin_made_product_is_sold_through_the_normal_shop_and_cart(self):
        d = self.create(name="Muesli", price="99.50", initial_quantity=8, low_stock_threshold=10)
        listing = self.client.get("/api/products").json()["data"]["products"]
        self.assertEqual([(p["sku"], p["price"], p["in_stock"], p["low_stock"]) for p in listing], [(d["sku"], 99.5, True, True)])
        detail = self.client.get(f"/api/products/{d['slug']}")
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("quantity", str(detail.json()["data"]).replace("quantity_", ""))  # public pages show no stock numbers
        user = self.make_user()
        h = bearer(user)
        r = self.client.post("/api/cart/items", json={"product_id": d["id"], "quantity": 2}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["items"][0]["unit_price"], 99.5)

    def test_deactivating_removes_it_from_the_shop_and_flags_cart_lines(self):
        d = self.create(initial_quantity=8)
        user = self.make_user()
        h = bearer(user)
        self.assertEqual(self.client.post("/api/cart/items", json={"product_id": d["id"]}, headers=h).status_code, 200)
        self.post(f"/api/admin/products/{d['id']}/deactivate")
        self.assertEqual(self.client.get("/api/products").json()["data"]["products"], [])
        self.assertEqual(self.client.get(f"/api/products/{d['slug']}").status_code, 404)
        cart = self.client.get("/api/cart", headers=h).json()["data"]
        self.assertTrue(cart["has_issues"])
        self.assertIsNotNone(cart["items"][0]["issue"])
        self.assertIn(self.client.post("/api/cart/items", json={"product_id": d["id"]}, headers=h).status_code, (404, 409, 422))
        self.post(f"/api/admin/products/{d['id']}/activate")
        self.assertFalse(self.client.get("/api/cart", headers=h).json()["data"]["has_issues"])

    def test_a_price_change_reaches_the_shop_and_the_cart_but_not_existing_orders(self):
        d = self.create(price="100", initial_quantity=10)
        user = self.make_user()
        product = self.db_product(d["id"])[0]
        order = self.make_order(user, [(product, 1)])
        self.patch(d["id"], {"price": "250"})
        self.assertEqual(self.client.get(f"/api/products/{d['slug']}").json()["data"]["price"], 250.0)
        with new_session() as s:
            self.assertEqual(s.get(Order, order.id).items[0].unit_price, Decimal("100.00"))  # snapshot

    def test_the_admin_api_does_not_change_public_responses(self):
        d = self.create()
        before = self.client.get("/api/products").json()
        self.patch(d["id"], {"name": d["name"]})  # no-op
        self.assertEqual(self.client.get("/api/products").json(), before)


class ProductLockTests(ProductApiCase):
    def product_lock_statements(self, action):
        collected = []
        engine = _get_engine()
        listener = lambda conn, cur, stmt, *a: collected.append(stmt)
        sa_event.listen(engine, "before_cursor_execute", listener)
        try:
            action()
        finally:
            sa_event.remove(engine, "before_cursor_execute", listener)
        return [st for st in collected if "FOR UPDATE" in st and "FROM products" in st and "FROM categories" not in st]

    def test_every_product_write_takes_the_product_row_for_update(self):
        d = self.create()
        pid = d["id"]
        calls = {
            "update": lambda: self.patch(pid, {"name": "Renamed"}),
            "deactivate": lambda: self.post(f"/api/admin/products/{pid}/deactivate"),
            "activate": lambda: self.post(f"/api/admin/products/{pid}/activate"),
        }
        for name, call in calls.items():
            with self.subTest(action=name):
                self.assertTrue(self.product_lock_statements(call), f"{name} did not lock the product row")

    def test_a_read_does_not_lock(self):
        d = self.create()
        self.assertEqual(self.product_lock_statements(lambda: self.client.get(f"/api/admin/products/{d['id']}", headers=self.h)), [])
        self.assertEqual(self.product_lock_statements(lambda: self.client.get("/api/admin/products", headers=self.h)), [])

    def test_two_edits_that_are_each_valid_alone_cannot_both_land(self):
        # price 50 / compare 100. A raises price to 90 (valid vs 100); B lowers compare to 80 (valid vs 50).
        # Together they would leave price 90 above compare 80, so the second to commit must be refused.
        d = self.create(price="50", compare_at_price="100")
        a, b = (TestClient(build_admin_app(with_public=False)) for _ in range(2))
        for _ in range(1):
            results = run_concurrently([
                lambda: a.patch(f"/api/admin/products/{d['id']}", json={"price": "90"}, headers=self.h).status_code,
                lambda: b.patch(f"/api/admin/products/{d['id']}", json={"compare_at_price": "80"}, headers=self.h).status_code,
            ])
            self.assertEqual([k for k, _ in results], ["ok", "ok"], results)
        p, _ = self.db_product(d["id"])
        self.assertTrue(p.compare_at_price is None or p.compare_at_price > p.price, (p.price, p.compare_at_price))
        self.assertEqual(sorted(v for _, v in results), [200, 422], results)


class ProductConcurrencyTests(ProductApiCase):
    def clients(self, n):
        return [TestClient(build_admin_app(with_public=False)) for _ in range(n)]

    def test_two_admins_creating_the_same_sku_get_one_201_and_one_409(self):
        for round_ in range(6):
            a, b = self.clients(2)
            payload = lambda: self.body(sku=f"RACE-{round_}", slug=f"race-{round_}-{uuid.uuid4().hex[:4]}")
            pa, pb = payload(), payload()
            pb["name"] = pa["name"] + " b"
            results = run_concurrently([
                lambda: a.post("/api/admin/products", json=pa, headers=self.h).status_code,
                lambda: b.post("/api/admin/products", json=pb, headers=self.h).status_code,
            ])
            self.assertEqual([k for k, _ in results], ["ok", "ok"], results)
            self.assertEqual(sorted(v for _, v in results), [201, 409], results)
        self.assertEqual(self.counts(), (6, 6))  # every product has exactly one inventory row

    def test_two_admins_taking_the_same_slug_get_one_200_and_one_409(self):
        x, y = self.create(name="Xx"), self.create(name="Yy")
        a, b = self.clients(2)
        results = run_concurrently([
            lambda: a.patch(f"/api/admin/products/{x['id']}", json={"slug": "same-slug"}, headers=self.h).status_code,
            lambda: b.patch(f"/api/admin/products/{y['id']}", json={"slug": "same-slug"}, headers=self.h).status_code,
        ])
        self.assertEqual(sorted(v for _, v in results), [200, 409], results)

    def test_an_admin_edit_waits_for_a_checkout_that_holds_the_product(self):
        d = self.create(initial_quantity=10)
        pid = uuid.UUID(d["id"])
        checkout = new_session()
        try:
            InventoryRepository(checkout).lock_products([pid])           # what checkout does (share lock)
            admin_session = new_session()
            try:
                admin_session.execute(text("SET LOCAL lock_timeout = '300ms'"))
                from app.schemas.admin_catalog import ProductUpdate as PU
                from app.services.admin_product_service import AdminProductService
                with self.assertRaises(OperationalError):
                    AdminProductService(admin_session).update(self.admin, pid, PU(price=Decimal("5.00")))
            finally:
                admin_session.close()
        finally:
            checkout.rollback()
            checkout.close()
        self.assertEqual(self.db_product(d["id"])[0].price, Decimal("100.00"))
        self.assertEqual(self.audit("product.update"), [])


if __name__ == "__main__":
    unittest.main()
