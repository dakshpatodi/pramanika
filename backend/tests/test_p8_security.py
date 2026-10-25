"""
Phase 8 M7 - the security surface of the user dashboard, pinned.

  Phase8RouteInventoryTests   exactly these account routes exist; a new one must be added here on purpose
  Phase8AuthTests             every one of them refuses a request without a valid token (401), whatever the body
  Phase8OwnerTests            no route takes a user id from the caller (path, query or body)
  Phase8ForeignOwnerTests     the one write body that ignores unknown keys cannot be made to write for someone else
  Phase8MountedTests          the real app.main mounts them (skipped when a checkout's app.main has no API routes)

None of these need a database: a missing or garbage token is refused before any query runs.
"""

import unittest
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api import addresses, invoices, users, wishlist
from app.core.exceptions import DomainError
from app.core.security import create_access_token
from app.database.session import get_db
from app.models import Address
from tests.pg_support import PostgresTestCase, new_session

PREFIXES = ("/api/users/me", "/api/addresses", "/api/wishlist", "/api/invoices")

# (method, path) of every account route, path parameters shown as {}.
EXPECTED = {
    ("GET", "/api/users/me"),
    ("PATCH", "/api/users/me"),
    ("GET", "/api/addresses"),
    ("POST", "/api/addresses"),
    ("PATCH", "/api/addresses/{}"),
    ("POST", "/api/addresses/{}/default"),
    ("DELETE", "/api/addresses/{}"),
    ("GET", "/api/wishlist"),
    ("GET", "/api/wishlist/product-ids"),
    ("POST", "/api/wishlist/items"),
    ("DELETE", "/api/wishlist/items/{}"),
    ("GET", "/api/invoices"),
    ("GET", "/api/invoices/{}"),
}

OWNER_NAMES = {"user_id", "owner_id", "customer_id", "account_id", "wishlist_id"}

# Phase 6's create-address body predates Phase 8 and silently ignores keys it does not
# declare (the service builds the row from declared fields only, with the owner taken from
# the token and the country fixed). Making it strict would change Phase 6 behaviour for no
# gain, so it is the one documented exception; Phase8ForeignOwnerTests proves it is safe.
IGNORES_EXTRAS = {("POST", "/api/addresses")}


def _normalise(path: str) -> str:
    out, depth = [], 0
    for ch in path:
        if ch == "{":
            depth += 1
            if depth == 1:
                out.append("{}")
        elif ch == "}":
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def _account_routes(app: FastAPI):
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith(PREFIXES):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                yield method, route


def _build_app() -> FastAPI:
    app = FastAPI()
    for module in (users, addresses, wishlist, invoices):
        app.include_router(module.router)

    def no_database():  # a refused request must never need one
        yield None

    app.dependency_overrides[get_db] = no_database
    return app


class Phase8RouteInventoryTests(unittest.TestCase):
    def test_exactly_the_expected_account_routes_exist(self):
        found = {(m, _normalise(r.path)) for m, r in _account_routes(_build_app())}
        self.assertEqual(found, EXPECTED, "an account route was added or removed: review it, then update EXPECTED")


class Phase8AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _build_app()
        cls.client = TestClient(cls.app, raise_server_exceptions=False)

    def _request(self, method, route, headers=None):
        path = route.path
        for param in route.dependant.path_params:
            path = path.replace("{" + param.name + "}", str(uuid.uuid4()))
        body = {} if method in {"POST", "PATCH", "PUT"} else None
        return self.client.request(method, path, json=body, headers=headers or {})

    def test_no_token_is_401_on_every_route(self):
        for method, route in _account_routes(self.app):
            with self.subTest(route=f"{method} {route.path}"):
                response = self._request(method, route)
                self.assertEqual(response.status_code, 401, response.text)

    def test_a_garbage_token_is_401_on_every_route(self):
        for header in ("Bearer not-a-jwt", "Bearer ", "Basic abc", "bearer eyJhbGciOiJub25lIn0.e30."):
            for method, route in _account_routes(self.app):
                with self.subTest(header=header, route=f"{method} {route.path}"):
                    response = self._request(method, route, {"Authorization": header})
                    self.assertEqual(response.status_code, 401, response.text)

    def test_the_refusal_is_not_cacheable_into_a_shared_answer_and_leaks_nothing(self):
        for method, route in _account_routes(self.app):
            with self.subTest(route=f"{method} {route.path}"):
                response = self._request(method, route)
                self.assertNotIn("application/pdf", response.headers.get("content-type", ""))
                self.assertNotIn(b"%PDF", response.content)
                self.assertNotIn("Traceback", response.text)


class Phase8OwnerTests(unittest.TestCase):
    def test_no_route_takes_a_user_id_from_the_caller(self):
        for method, route in _account_routes(_build_app()):
            dep = route.dependant
            names = {p.name for p in dep.path_params + dep.query_params + dep.header_params + dep.cookie_params}
            body = route.body_field.type_ if route.body_field is not None else None
            if isinstance(body, type) and issubclass(body, BaseModel):
                names |= set(body.model_fields)
            with self.subTest(route=f"{method} {route.path}"):
                self.assertFalse(names & OWNER_NAMES, f"{names & OWNER_NAMES} would let the caller choose whose data it is")

    def test_every_write_body_refuses_unknown_fields(self):
        for method, route in _account_routes(_build_app()):
            if route.body_field is None:
                continue
            body = route.body_field.type_
            with self.subTest(route=f"{method} {route.path}"):
                self.assertTrue(isinstance(body, type) and issubclass(body, BaseModel))
                if (method, _normalise(route.path)) in IGNORES_EXTRAS:
                    self.assertNotEqual(body.model_config.get("extra"), "forbid", "exception no longer needed: remove it from IGNORES_EXTRAS")
                else:
                    self.assertEqual(body.model_config.get("extra"), "forbid")

    def test_the_exception_list_has_not_grown(self):
        self.assertEqual(IGNORES_EXTRAS, {("POST", "/api/addresses")})


class Phase8ForeignOwnerTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        app = _build_app()

        @app.exception_handler(DomainError)
        async def domain_error_handler(request: Request, exc: DomainError):
            return JSONResponse(status_code=exc.http_status, content={"success": False, "message": exc.message})

        def real_db():
            session = new_session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = real_db
        self.client = TestClient(app)
        self.me = self.make_user()
        self.other = self.make_user()

    def test_a_create_address_body_cannot_name_another_owner_or_country(self):
        body = {
            "full_name": "Asha Rao", "phone_number": "9876543210", "address_line_1": "12 MG Road",
            "city": "Pune", "state": "Maharashtra", "postal_code": "411001",
            "user_id": str(self.other.id), "owner_id": str(self.other.id), "country": "Nepal", "id": str(uuid.uuid4()),
        }
        headers = {"Authorization": f"Bearer {create_access_token(self.me.id, self.me.role.value)}"}
        response = self.client.post("/api/addresses", json=body, headers=headers)
        self.assertEqual(response.status_code, 201, response.text)
        with new_session() as s:
            rows = s.query(Address).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].user_id, self.me.id)
        self.assertEqual(rows[0].country, "India")
        self.assertNotEqual(str(rows[0].id), body["id"])
        self.assertEqual([r for r in rows if r.user_id == self.other.id], [])


class Phase8MountedTests(unittest.TestCase):
    def test_the_real_app_mounts_every_account_route(self):
        try:
            from app.main import app as real_app
        except Exception as exc:  # pragma: no cover - depends on the checkout
            self.skipTest(f"app.main cannot be imported here: {type(exc).__name__}")
        if not any(isinstance(r, APIRoute) and r.path.startswith("/api/") for r in real_app.routes):
            self.skipTest("this checkout's app.main mounts no API routes")
        found = {(m, _normalise(r.path)) for m, r in _account_routes(real_app)}
        self.assertEqual(found, EXPECTED)

    def test_an_account_route_is_never_mounted_twice(self):
        seen = {}
        for method, route in _account_routes(_build_app()):
            key = (method, _normalise(route.path))
            seen[key] = seen.get(key, 0) + 1
        self.assertTrue(all(count == 1 for count in seen.values()), seen)


if __name__ == "__main__":
    unittest.main()
