"""
HTTP-level tests for /api/addresses and /api/orders (PostgreSQL integration).

These build a small FastAPI app from the real routers, the real auth
dependencies and real JWTs; only `get_db` is pointed at the test database.
The DomainError handler below mirrors the one in main.py (status from the
exception, body {"success": false, "message": ...}); the PowerShell smoke
test (phase6_smoke_test.ps1) covers the real main.py wiring.

See tests/pg_support.py for how to run them.
"""

import unittest
import uuid
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import addresses as addresses_api
from app.api import orders as orders_api
from app.core.exceptions import DomainError
from app.core.security import create_access_token
from app.database.session import get_db
from app.models import Order, OrderPaymentStatus, OrderStatus, User
from tests.pg_support import PostgresTestCase, new_session
from tests.test_p6_checkout import CheckoutTestCase


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

    app.include_router(addresses_api.router)
    app.include_router(orders_api.router)
    app.dependency_overrides[get_db] = override_get_db
    return app


class ApiTestCase(CheckoutTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(build_app())
        self.user = self.make_user()
        self.address = self.make_address(self.user)
        self.product = self.make_product(price="100.00", stock=10, name="Oats")

    def auth(self, user=None):
        user = user or self.user
        return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}

    def post_order(self, *, key=None, address_id=None, body=None, user=None, headers=None):
        h = dict(self.auth(user))
        if key is not False:
            h["Idempotency-Key"] = key or f"key-{uuid.uuid4()}"
        h.update(headers or {})
        payload = body if body is not None else {"shipping_address_id": str(address_id or self.address.id)}
        return self.client.post("/api/orders", json=payload, headers=h)


class AuthenticationTests(ApiTestCase):
    def test_every_endpoint_requires_a_login(self):
        some_id = uuid.uuid4()
        calls = [
            ("get", "/api/addresses", None),
            ("post", "/api/addresses", {}),
            ("post", "/api/orders", {"shipping_address_id": str(some_id)}),
            ("get", "/api/orders", None),
            ("get", f"/api/orders/{some_id}", None),
            ("post", f"/api/orders/{some_id}/cancel", None),
        ]
        for method, url, body in calls:
            with self.subTest(call=f"{method.upper()} {url}"):
                response = self.client.request(method, url, json=body, headers={"Idempotency-Key": "abcdefgh12345"})
                self.assertEqual(response.status_code, 401)

    def test_a_garbage_token_is_rejected(self):
        response = self.client.get("/api/orders", headers={"Authorization": "Bearer not-a-token"})
        self.assertEqual(response.status_code, 401)

    def test_a_deactivated_account_cannot_order(self):
        with new_session() as s:
            s.query(User).filter(User.id == self.user.id).update({User.is_active: False})
            s.commit()
        self.fill_cart(self.user, [(self.product, 1)])
        self.assertEqual(self.post_order().status_code, 403)
        self.assertEqual(self.order_count(), 0)


class AddressApiTests(ApiTestCase):
    def body(self, **overrides):
        values = dict(
            full_name="Asha Rao",
            phone_number="9876543210",
            address_line_1="12 MG Road",
            city="Pune",
            state="Maharashtra",
            postal_code="411001",
        )
        values.update(overrides)
        return values

    def test_add_then_list(self):
        response = self.client.post("/api/addresses", json=self.body(address_line_2="Flat 4"), headers=self.auth())
        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]
        self.assertEqual((data["city"], data["country"], data["address_line_2"]), ("Pune", "India", "Flat 4"))
        self.assertNotIn("user_id", data)

        listed = self.client.get("/api/addresses", headers=self.auth()).json()["data"]
        self.assertEqual(len(listed), 2)  # the one made in setUp + this one

    def test_invalid_input_is_a_422(self):
        for bad in [self.body(postal_code="12"), self.body(phone_number="abc"), self.body(city="")]:
            with self.subTest(bad=bad):
                self.assertEqual(self.client.post("/api/addresses", json=bad, headers=self.auth()).status_code, 422)

    def test_a_client_supplied_owner_is_ignored(self):
        other = self.make_user()
        response = self.client.post(
            "/api/addresses", json=dict(self.body(), user_id=str(other.id)), headers=self.auth()
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(self.client.get("/api/addresses", headers=self.auth(other)).json()["data"]), 0)

    def test_list_only_shows_the_callers_addresses(self):
        other = self.make_user()
        self.make_address(other)
        self.make_address(other)
        listed = self.client.get("/api/addresses", headers=self.auth()).json()["data"]
        self.assertEqual([a["id"] for a in listed], [str(self.address.id)])


class PlaceOrderApiTests(ApiTestCase):
    def test_place_order_end_to_end(self):
        self.fill_cart(self.user, [(self.product, 2)])  # 200 + 10 GST + 49 delivery = 259

        response = self.post_order(body={"shipping_address_id": str(self.address.id), "expected_total": 259.0})

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["success"])
        data = body["data"]
        self.assertRegex(data["order_number"], r"^PRM-\d{4}-\d{6}$")
        self.assertEqual((data["status"], data["payment_status"]), ("pending", "pending"))
        self.assertTrue(data["can_cancel"])
        self.assertEqual(data["totals"]["total"], 259.0)
        self.assertEqual(data["totals"]["gst"], 10.0)
        self.assertEqual(data["items"][0]["product_name"], "Oats")
        self.assertEqual(data["item_count"], 2)
        self.assertEqual(data["shipping_address"]["city"], "Pune")
        self.assertEqual(self.stock(self.product), (10, 2))
        self.assertEqual(self.cart_state(self.user), ({}, None))

    def test_the_response_leaks_no_internal_fields(self):
        self.fill_cart(self.user, [(self.product, 1)])
        text = self.post_order(key="my-secret-key-123").text
        for forbidden in ["my-secret-key-123", "idempotency", "fingerprint", "inventory_state", "user_id", str(self.user.id)]:
            self.assertNotIn(forbidden, text)

    def test_repeating_the_request_returns_the_same_order_with_200(self):
        self.fill_cart(self.user, [(self.product, 2)])
        key = f"key-{uuid.uuid4()}"
        first = self.post_order(key=key)
        second = self.post_order(key=key)

        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.json()["data"]["id"], second.json()["data"]["id"])
        self.assertEqual(self.order_count(), 1)
        self.assertEqual(self.stock(self.product), (10, 2))

    def test_same_key_different_address_is_a_409(self):
        self.fill_cart(self.user, [(self.product, 1)])
        key = f"key-{uuid.uuid4()}"
        self.post_order(key=key)
        response = self.post_order(key=key, address_id=self.make_address(self.user).id)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["success"])

    def test_missing_idempotency_key_header(self):
        self.fill_cart(self.user, [(self.product, 1)])
        self.assertEqual(self.post_order(key=False).status_code, 422)
        self.assertEqual(self.order_count(), 0)

    def test_malformed_idempotency_key(self):
        self.fill_cart(self.user, [(self.product, 1)])
        for bad in ["short", "has spaces in it!", "x" * 65]:
            with self.subTest(key=bad):
                self.assertEqual(self.post_order(key=bad).status_code, 400)
        self.assertEqual(self.order_count(), 0)

    def test_empty_cart_is_a_400(self):
        response = self.post_order()
        self.assertEqual(response.status_code, 400)
        self.assertIn("empty", response.json()["message"].lower())

    def test_unknown_and_foreign_addresses_are_a_404(self):
        self.fill_cart(self.user, [(self.product, 1)])
        self.assertEqual(self.post_order(address_id=uuid.uuid4()).status_code, 404)
        foreign = self.make_address(self.make_user())
        self.assertEqual(self.post_order(address_id=foreign.id).status_code, 404)
        self.assertEqual(self.order_count(), 0)

    def test_stale_total_is_a_409_and_nothing_is_ordered(self):
        self.fill_cart(self.user, [(self.product, 2)])
        response = self.post_order(body={"shipping_address_id": str(self.address.id), "expected_total": 100})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.order_count(), 0)
        self.assertEqual(self.stock(self.product), (10, 0))

    def test_insufficient_stock_is_a_409(self):
        self.fill_cart(self.user, [(self.product, 11)])
        self.assertEqual(self.post_order().status_code, 409)
        self.assertEqual(self.order_count(), 0)

    def test_bad_request_bodies_are_a_422(self):
        self.fill_cart(self.user, [(self.product, 1)])
        bad_bodies = [
            {},
            {"shipping_address_id": "not-a-uuid"},
            {"shipping_address_id": str(self.address.id), "expected_total": -1},
            {"shipping_address_id": str(self.address.id), "expected_total": "abc"},
            {"shipping_address_id": str(self.address.id), "expected_total": 10.123},
        ]
        for body in bad_bodies:
            with self.subTest(body=body):
                self.assertEqual(self.post_order(body=body).status_code, 422)
        self.assertEqual(self.order_count(), 0)

    def test_client_supplied_prices_and_owner_are_ignored(self):
        self.fill_cart(self.user, [(self.product, 1)])
        other = self.make_user()
        response = self.post_order(
            body={
                "shipping_address_id": str(self.address.id),
                "user_id": str(other.id),
                "total": 1,
                "items": [{"product_id": str(self.product.id), "price": 0.01, "quantity": 99}],
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]
        self.assertEqual((data["item_count"], data["totals"]["subtotal"]), (1, 100.0))
        with new_session() as s:
            self.assertEqual(s.query(Order).filter(Order.user_id == other.id).count(), 0)


class OrderReadAndCancelApiTests(ApiTestCase):
    def place(self, user=None, address=None, qty=1):
        user = user or self.user
        self.fill_cart(user, [(self.product, qty)])
        response = self.post_order(user=user, address_id=(address or self.address).id)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["data"]

    def test_list_and_detail(self):
        a = self.place(qty=1)
        b = self.place(qty=2)

        listed = self.client.get("/api/orders", headers=self.auth()).json()["data"]
        self.assertEqual(listed["pagination"]["total"], 2)
        self.assertEqual({o["id"] for o in listed["orders"]}, {a["id"], b["id"]})
        self.assertEqual(listed["orders"][0]["item_names"], ["Oats"])

        detail = self.client.get(f"/api/orders/{a['id']}", headers=self.auth())
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["data"]["id"], a["id"])

    def test_pagination_parameters(self):
        for _ in range(3):
            self.place()
        page = self.client.get("/api/orders?page=2&page_size=2", headers=self.auth()).json()["data"]
        self.assertEqual((len(page["orders"]), page["pagination"]["total_pages"], page["pagination"]["has_previous"]), (1, 2, True))
        for bad in ["page=0", "page_size=0", "page_size=51", "page=abc"]:
            with self.subTest(query=bad):
                self.assertEqual(self.client.get(f"/api/orders?{bad}", headers=self.auth()).status_code, 422)

    def test_other_peoples_orders_are_invisible(self):
        mine = self.place()
        stranger = self.make_user()
        self.assertEqual(self.client.get("/api/orders", headers=self.auth(stranger)).json()["data"]["pagination"]["total"], 0)
        self.assertEqual(self.client.get(f"/api/orders/{mine['id']}", headers=self.auth(stranger)).status_code, 404)
        self.assertEqual(self.client.post(f"/api/orders/{mine['id']}/cancel", headers=self.auth(stranger)).status_code, 404)
        self.assertEqual(self.client.get(f"/api/orders/{uuid.uuid4()}", headers=self.auth()).status_code, 404)
        self.assertEqual(self.client.get("/api/orders/not-a-uuid", headers=self.auth()).status_code, 422)
        # ... and the stranger's attempt changed nothing
        self.assertEqual(self.stock(self.product), (10, 1))

    def test_cancel_via_the_api_releases_stock_and_is_safe_to_repeat(self):
        coupon = self.make_coupon(usage_limit=2)
        self.fill_cart(self.user, [(self.product, 3)], coupon)
        order = self.post_order().json()["data"]
        self.assertEqual((self.stock(self.product), self.used_count(coupon)), ((10, 3), 1))

        first = self.client.post(f"/api/orders/{order['id']}/cancel", headers=self.auth())
        second = self.client.post(f"/api/orders/{order['id']}/cancel", headers=self.auth())

        self.assertEqual((first.status_code, second.status_code), (200, 200))
        data = first.json()["data"]
        self.assertEqual(data["status"], "cancelled")
        self.assertFalse(data["can_cancel"])
        self.assertIsNotNone(data["cancelled_at"])
        self.assertEqual((self.stock(self.product), self.used_count(coupon)), ((10, 0), 0))

    def test_a_paid_order_cannot_be_cancelled(self):
        order = self.place()
        with new_session() as s:
            s.query(Order).filter(Order.id == uuid.UUID(order["id"])).update({Order.payment_status: OrderPaymentStatus.PAID})
            s.commit()
        response = self.client.post(f"/api/orders/{order['id']}/cancel", headers=self.auth())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.stock(self.product), (10, 1))
        detail = self.client.get(f"/api/orders/{order['id']}", headers=self.auth()).json()["data"]
        self.assertEqual((detail["status"], detail["can_cancel"]), ("pending", False))

    def test_order_survives_later_catalogue_changes(self):
        order = self.place(qty=2)
        with new_session() as s:
            from app.models import Product

            s.query(Product).filter(Product.id == self.product.id).update({Product.price: Decimal("999.00"), Product.name: "Renamed"})
            s.commit()
        data = self.client.get(f"/api/orders/{order['id']}", headers=self.auth()).json()["data"]
        self.assertEqual((data["items"][0]["product_name"], data["items"][0]["unit_price"]), ("Oats", 100.0))


if __name__ == "__main__":
    unittest.main()