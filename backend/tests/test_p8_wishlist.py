"""
Phase 8 M2 - wishlist (list, add, remove).

  WishlistSchemaTests      request validation (no database)
  WishlistServiceTests     the rules, against PostgreSQL
  WishlistLimitTests       the bounded list
  WishlistConcurrencyTests real threads: no duplicates, no lost wishlist, cap holds
  WishlistQueryTests       one query per page, not one per row
  WishlistApiTests         HTTP: login, ownership, idempotency, shapes, no leaks

See tests/pg_support.py for how to run the PostgreSQL ones.
"""

import unittest
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, text

from app.api import wishlist as wishlist_api
from app.core.exceptions import DomainError, ProductUnavailableError, WishlistFullError
from app.core.security import create_access_token
from app.database.session import get_db
from app.models import Product, Wishlist, WishlistItem
from app.schemas.wishlist import WishlistAddRequest
from app.services.wishlist_service import MAX_WISHLIST_ITEMS, WishlistService
from tests.pg_support import PostgresTestCase, new_session, run_concurrently


class WishlistSchemaTests(unittest.TestCase):
    def test_a_product_id_is_required_and_must_be_a_uuid(self):
        WishlistAddRequest(product_id=str(uuid.uuid4()))
        for bad in [{}, {"product_id": "abc"}, {"product_id": None}, {"product_id": ""}]:
            with self.subTest(body=bad), self.assertRaises(ValidationError):
                WishlistAddRequest.model_validate(bad)

    def test_nothing_else_is_accepted(self):
        for key in ["user_id", "wishlist_id", "quantity", "id"]:
            with self.subTest(field=key), self.assertRaises(ValidationError):
                WishlistAddRequest.model_validate({"product_id": str(uuid.uuid4()), key: "x"})


class WishlistTestCase(PostgresTestCase):
    def rows(self, user_id):
        with new_session() as s:
            q = (
                s.query(WishlistItem.product_id)
                .join(Wishlist, Wishlist.id == WishlistItem.wishlist_id)
                .filter(Wishlist.user_id == user_id)
            )
            return {r[0] for r in q.all()}

    def wishlist_rows(self, user_id):
        with new_session() as s:
            return s.query(Wishlist).filter(Wishlist.user_id == user_id).count()

    def deactivate(self, product):
        with new_session() as s:
            s.get(Product, product.id).is_active = False
            s.commit()


class WishlistServiceTests(WishlistTestCase):
    def test_the_first_add_creates_the_wishlist_and_returns_the_product(self):
        user = self.make_user()
        product = self.make_product(price="120.00", stock=10, name="Rolled Oats")
        self.assertEqual(self.wishlist_rows(user.id), 0)

        result = WishlistService(self.db).add(user.id, product.id)

        self.assertTrue(result.created)
        self.assertEqual(self.wishlist_rows(user.id), 1)
        item = result.item
        self.assertEqual((item.product_id, item.name, item.slug, item.price), (product.id, "Rolled Oats", product.slug, 120.0))
        self.assertTrue(item.is_available)
        self.assertTrue(item.in_stock)
        self.assertEqual(self.rows(user.id), {product.id})

    def test_adding_again_is_a_quiet_no_op(self):
        user = self.make_user()
        product = self.make_product()
        svc = WishlistService(self.db)
        first = svc.add(user.id, product.id)
        second = svc.add(user.id, product.id)
        self.assertEqual((first.created, second.created), (True, False))
        self.assertEqual(second.item.added_at, first.item.added_at)
        self.assertEqual(self.rows(user.id), {product.id})
        with new_session() as s:
            self.assertEqual(s.query(WishlistItem).count(), 1)

    def test_an_unknown_product_is_refused_and_no_wishlist_is_left_behind(self):
        user = self.make_user()
        with self.assertRaises(ProductUnavailableError):
            WishlistService(self.db).add(user.id, uuid.uuid4())
        self.assertEqual(self.wishlist_rows(user.id), 0)

    def test_a_deactivated_product_cannot_be_added(self):
        user = self.make_user()
        product = self.make_product(active=False)
        with self.assertRaises(ProductUnavailableError):
            WishlistService(self.db).add(user.id, product.id)
        self.assertEqual(self.rows(user.id), set())

    def test_an_out_of_stock_product_can_be_saved_and_is_flagged(self):
        user = self.make_user()
        sold_out = self.make_product(stock=3, reserved=3)
        result = WishlistService(self.db).add(user.id, sold_out.id)
        self.assertTrue(result.item.is_available)
        self.assertFalse(result.item.in_stock)  # available = quantity - reserved, the catalogue's own rule
        self.assertFalse(result.item.low_stock)

    def test_low_stock_follows_the_catalogue_rule(self):
        user = self.make_user()
        scarce = self.make_product(stock=5)  # threshold defaults to 10
        item = WishlistService(self.db).add(user.id, scarce.id).item
        self.assertEqual((item.in_stock, item.low_stock), (True, True))

    def test_list_is_newest_first_and_only_shows_the_owners_items(self):
        mine, theirs = self.make_user(), self.make_user()
        a, b, c = (self.make_product(name=n) for n in "ABC")
        other = self.make_product(name="Not mine")
        svc = WishlistService(self.db)
        for p in (a, b, c):
            svc.add(mine.id, p.id)
        svc.add(theirs.id, other.id)

        listed = svc.list_items(mine.id, page=1, page_size=12)
        self.assertEqual([i.name for i in listed.items], ["C", "B", "A"])
        self.assertEqual(listed.pagination.total, 3)

    def test_pagination(self):
        user = self.make_user()
        svc = WishlistService(self.db)
        for n in range(5):
            svc.add(user.id, self.make_product(name=f"P{n}").id)
        p1 = svc.list_items(user.id, page=1, page_size=2)
        p3 = svc.list_items(user.id, page=3, page_size=2)
        p9 = svc.list_items(user.id, page=9, page_size=2)
        self.assertEqual([i.name for i in p1.items], ["P4", "P3"])
        self.assertEqual((p1.pagination.total, p1.pagination.total_pages, p1.pagination.has_next, p1.pagination.has_previous), (5, 3, True, False))
        self.assertEqual([i.name for i in p3.items], ["P0"])
        self.assertEqual((p3.pagination.has_next, p3.pagination.has_previous), (False, True))
        self.assertEqual(p9.items, [])

    def test_an_empty_wishlist_lists_as_empty_not_an_error(self):
        user = self.make_user()
        listed = WishlistService(self.db).list_items(user.id, page=1, page_size=12)
        self.assertEqual((listed.items, listed.pagination.total, listed.pagination.total_pages), ([], 0, 0))

    def test_a_product_deactivated_later_stays_listed_flagged_and_removable(self):
        user = self.make_user()
        product = self.make_product(stock=50)
        svc = WishlistService(self.db)
        svc.add(user.id, product.id)
        self.deactivate(product)

        item = svc.list_items(user.id, page=1, page_size=12).items[0]
        self.assertEqual(item.product_id, product.id)
        self.assertFalse(item.is_available)
        self.assertFalse(item.in_stock)  # plenty on the shelf, but it cannot be bought
        self.assertTrue(svc.remove(user.id, product.id))
        self.assertEqual(self.rows(user.id), set())

    def test_a_product_deleted_outright_simply_disappears_from_the_list(self):
        user = self.make_user()
        product = self.make_product()
        svc = WishlistService(self.db)
        svc.add(user.id, product.id)
        with new_session() as s:
            s.execute(text("delete from products where id = :id"), {"id": product.id})
            s.commit()
        self.assertEqual(svc.list_items(user.id, page=1, page_size=12).items, [])
        self.assertEqual(svc.product_ids(user.id).product_ids, [])

    def test_remove_is_idempotent(self):
        user = self.make_user()
        product = self.make_product()
        svc = WishlistService(self.db)
        svc.add(user.id, product.id)
        self.assertTrue(svc.remove(user.id, product.id))
        self.assertFalse(svc.remove(user.id, product.id))
        self.assertFalse(svc.remove(user.id, uuid.uuid4()))

    def test_removing_never_touches_another_users_wishlist(self):
        mine, theirs = self.make_user(), self.make_user()
        product = self.make_product()
        svc = WishlistService(self.db)
        svc.add(theirs.id, product.id)
        self.assertFalse(svc.remove(mine.id, product.id))  # I have no wishlist at all
        svc.add(mine.id, product.id)
        self.assertTrue(svc.remove(mine.id, product.id))
        self.assertEqual(self.rows(theirs.id), {product.id})

    def test_product_ids_are_the_owners_only(self):
        mine, theirs = self.make_user(), self.make_user()
        p1, p2 = self.make_product(), self.make_product()
        svc = WishlistService(self.db)
        svc.add(mine.id, p1.id)
        svc.add(theirs.id, p2.id)
        self.assertEqual(svc.product_ids(mine.id).product_ids, [p1.id])
        self.assertEqual(svc.product_ids(self.make_user().id).product_ids, [])

    def test_each_user_has_their_own_wishlist_row(self):
        a, b = self.make_user(), self.make_user()
        product = self.make_product()
        svc = WishlistService(self.db)
        svc.add(a.id, product.id)
        svc.add(b.id, product.id)
        self.assertEqual((self.wishlist_rows(a.id), self.wishlist_rows(b.id)), (1, 1))


class WishlistLimitTests(WishlistTestCase):
    def fill(self, user, count):
        svc = WishlistService(self.db)
        products = [self.make_product() for _ in range(count)]
        for p in products:
            svc.add(user.id, p.id)
        return products

    def test_the_limit_is_enforced_and_nothing_is_added_past_it(self):
        user = self.make_user()
        self.fill(user, MAX_WISHLIST_ITEMS)
        extra = self.make_product()
        with self.assertRaises(WishlistFullError):
            WishlistService(self.db).add(user.id, extra.id)
        self.assertEqual(len(self.rows(user.id)), MAX_WISHLIST_ITEMS)
        self.assertNotIn(extra.id, self.rows(user.id))

    def test_a_full_wishlist_can_still_re_add_what_it_has_and_remove(self):
        user = self.make_user()
        products = self.fill(user, MAX_WISHLIST_ITEMS)
        svc = WishlistService(self.db)
        self.assertFalse(svc.add(user.id, products[0].id).created)  # already there: not a new row, not refused
        svc.remove(user.id, products[1].id)
        self.assertTrue(svc.add(user.id, self.make_product().id).created)
        self.assertEqual(len(self.rows(user.id)), MAX_WISHLIST_ITEMS)

    def test_the_limit_is_per_user(self):
        a, b = self.make_user(), self.make_user()
        self.fill(a, MAX_WISHLIST_ITEMS)
        self.assertTrue(WishlistService(self.db).add(b.id, self.make_product().id).created)


class WishlistConcurrencyTests(WishlistTestCase):
    def test_the_same_product_added_by_many_tabs_makes_one_row(self):
        user = self.make_user()
        product = self.make_product()
        user_id, product_id = user.id, product.id

        def run():
            with new_session() as s:
                return WishlistService(s).add(user_id, product_id).created

        results = run_concurrently([run] * 8)
        self.assertEqual([r for r in results if r[0] == "err"], [])
        self.assertEqual(sum(1 for r in results if r[1] is True), 1)
        self.assertEqual(self.rows(user_id), {product_id})
        self.assertEqual(self.wishlist_rows(user_id), 1)

    def test_the_first_ever_adds_racing_create_exactly_one_wishlist(self):
        user = self.make_user()
        ids = [self.make_product().id for _ in range(6)]
        user_id = user.id

        def job(product_id):
            def run():
                with new_session() as s:
                    return WishlistService(s).add(user_id, product_id).created

            return run

        results = run_concurrently([job(i) for i in ids])
        self.assertEqual([r for r in results if r[0] == "err"], [])
        self.assertEqual(self.wishlist_rows(user_id), 1)
        self.assertEqual(self.rows(user_id), set(ids))

    def test_racing_adds_cannot_push_the_list_past_the_cap(self):
        user = self.make_user()
        svc = WishlistService(self.db)
        for _ in range(MAX_WISHLIST_ITEMS - 1):
            svc.add(user.id, self.make_product().id)
        racers = [self.make_product().id for _ in range(5)]
        user_id = user.id

        def job(product_id):
            def run():
                with new_session() as s:
                    return WishlistService(s).add(user_id, product_id).created

            return run

        results = run_concurrently([job(i) for i in racers])
        self.assertEqual(sum(1 for r in results if r[0] == "ok"), 1)
        full = [r for r in results if r[0] == "err"]
        self.assertEqual(len(full), 4)
        self.assertTrue(all(isinstance(r[1], WishlistFullError) for r in full))
        self.assertEqual(len(self.rows(user_id)), MAX_WISHLIST_ITEMS)

    def test_add_and_remove_racing_leave_a_consistent_list(self):
        user = self.make_user()
        product = self.make_product()
        WishlistService(self.db).add(user.id, product.id)
        user_id, product_id = user.id, product.id

        def add():
            with new_session() as s:
                return WishlistService(s).add(user_id, product_id).created

        def remove():
            with new_session() as s:
                return WishlistService(s).remove(user_id, product_id)

        results = run_concurrently([add, remove, add, remove])
        self.assertEqual([r for r in results if r[0] == "err"], [])
        self.assertIn(len(self.rows(user_id)), (0, 1))
        with new_session() as s:
            self.assertEqual(s.query(WishlistItem).count(), len(self.rows(user_id)))


class WishlistQueryTests(WishlistTestCase):
    def test_a_page_costs_a_fixed_number_of_queries(self):
        user = self.make_user()
        svc = WishlistService(self.db)
        for n in range(10):
            svc.add(user.id, self.make_product(name=f"P{n}").id)

        user_id = user.id
        session = new_session()
        statements = []

        def count(conn, cursor, statement, *args):
            statements.append(statement)

        engine = session.get_bind()
        event.listen(engine, "before_cursor_execute", count)
        try:
            listed = WishlistService(session).list_items(user_id, page=1, page_size=10)
            self.assertEqual(len(listed.items), 10)
            self.assertTrue(all(i.in_stock for i in listed.items))
        finally:
            event.remove(engine, "before_cursor_execute", count)
            session.close()
        selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
        self.assertLessEqual(len(selects), 2, selects)  # the count and the page (product + inventory joined in)


def build_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError):
        return JSONResponse(status_code=exc.http_status, content={"success": False, "message": exc.message})

    def override_get_db():
        session = new_session()
        try:
            yield session
        finally:
            session.close()

    app.include_router(wishlist_api.router)
    app.dependency_overrides[get_db] = override_get_db
    return app


class WishlistApiTests(WishlistTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(build_app())
        self.user = self.make_user()
        self.product = self.make_product(price="99.50", stock=20, name="Muesli")

    def auth(self, user=None):
        user = user or self.user
        return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}

    def add(self, product=None, user=None):
        return self.client.post(
            "/api/wishlist/items", json={"product_id": str((product or self.product).id)}, headers=self.auth(user)
        )

    def test_every_endpoint_requires_a_login(self):
        pid = uuid.uuid4()
        calls = [
            ("get", "/api/wishlist", None),
            ("get", "/api/wishlist/product-ids", None),
            ("post", "/api/wishlist/items", {"product_id": str(pid)}),
            ("delete", f"/api/wishlist/items/{pid}", None),
        ]
        for method, url, body in calls:
            with self.subTest(call=f"{method} {url}"):
                r = getattr(self.client, method)(url, **({"json": body} if body is not None else {}))
                self.assertEqual(r.status_code, 401)

    def test_add_is_201_then_200_and_returns_the_item(self):
        first = self.add()
        self.assertEqual(first.status_code, 201, first.text)
        data = first.json()["data"]
        self.assertEqual((data["product_id"], data["name"], data["price"]), (str(self.product.id), "Muesli", 99.5))
        again = self.add()
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["data"]["product_id"], str(self.product.id))
        self.assertEqual(len(self.client.get("/api/wishlist", headers=self.auth()).json()["data"]["items"]), 1)

    def test_the_response_shows_no_stock_numbers_or_internal_fields(self):
        data = self.add().json()["data"]
        self.assertEqual(
            set(data),
            {"product_id", "name", "slug", "price", "compare_at_price", "image_url", "is_available", "in_stock", "low_stock", "added_at"},
        )

    def test_unknown_inactive_and_malformed_products(self):
        inactive = self.make_product(active=False)
        self.assertEqual(self.add(inactive).status_code, 404)
        r = self.client.post("/api/wishlist/items", json={"product_id": str(uuid.uuid4())}, headers=self.auth())
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.json()["success"])
        for body in [{}, {"product_id": "abc"}, {"product_id": str(self.product.id), "user_id": str(uuid.uuid4())}]:
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/api/wishlist/items", json=body, headers=self.auth()).status_code, 422)

    def test_list_pagination_and_validation(self):
        for n in range(3):
            self.add(self.make_product(name=f"P{n}"))
        r = self.client.get("/api/wishlist?page=1&page_size=2", headers=self.auth())
        self.assertEqual(r.status_code, 200)
        body = r.json()["data"]
        self.assertEqual([i["name"] for i in body["items"]], ["P2", "P1"])
        self.assertEqual((body["pagination"]["total"], body["pagination"]["total_pages"], body["pagination"]["has_next"]), (3, 2, True))
        for bad in ["page=0", "page_size=0", "page_size=51", "page=x"]:
            with self.subTest(query=bad):
                self.assertEqual(self.client.get(f"/api/wishlist?{bad}", headers=self.auth()).status_code, 422)

    def test_remove_is_200_whether_or_not_it_was_there(self):
        self.add()
        first = self.client.delete(f"/api/wishlist/items/{self.product.id}", headers=self.auth())
        again = self.client.delete(f"/api/wishlist/items/{self.product.id}", headers=self.auth())
        self.assertEqual((first.status_code, again.status_code), (200, 200))
        self.assertNotEqual(first.json()["message"], again.json()["message"])
        self.assertEqual(self.client.delete("/api/wishlist/items/not-a-uuid", headers=self.auth()).status_code, 422)

    def test_product_ids_endpoint(self):
        other = self.make_product()
        self.add()
        self.add(other)
        ids = self.client.get("/api/wishlist/product-ids", headers=self.auth()).json()["data"]["product_ids"]
        self.assertEqual(ids, [str(other.id), str(self.product.id)])

    def test_users_never_see_or_change_each_others_wishlists(self):
        other_user = self.make_user()
        self.add()
        self.assertEqual(self.client.get("/api/wishlist", headers=self.auth(other_user)).json()["data"]["items"], [])
        self.assertEqual(self.client.get("/api/wishlist/product-ids", headers=self.auth(other_user)).json()["data"]["product_ids"], [])
        self.client.delete(f"/api/wishlist/items/{self.product.id}", headers=self.auth(other_user))
        self.assertEqual(len(self.client.get("/api/wishlist", headers=self.auth()).json()["data"]["items"]), 1)

    def test_a_full_wishlist_is_409_on_a_new_product_but_re_adding_is_fine(self):
        first = self.product
        self.add(first)
        for _ in range(MAX_WISHLIST_ITEMS - 1):
            self.add(self.make_product())
        r = self.add(self.make_product())
        self.assertEqual(r.status_code, 409)
        self.assertFalse(r.json()["success"])
        self.assertEqual(self.add(first).status_code, 200)

    def test_an_inactive_product_stays_listed_and_can_be_removed(self):
        self.add()
        self.deactivate(self.product)
        item = self.client.get("/api/wishlist", headers=self.auth()).json()["data"]["items"][0]
        self.assertEqual((item["is_available"], item["in_stock"]), (False, False))
        self.assertEqual(self.client.delete(f"/api/wishlist/items/{self.product.id}", headers=self.auth()).status_code, 200)
        self.assertEqual(self.client.get("/api/wishlist", headers=self.auth()).json()["data"]["items"], [])


if __name__ == "__main__":
    unittest.main()
