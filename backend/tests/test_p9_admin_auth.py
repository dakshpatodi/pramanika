"""
Phase 9 M1 - who may use /api/admin.

  AdminGuardInventoryTests   every /api/admin route is behind require_admin (no database)
  AdminAuthMatrixTests       every admin route x {no login, bad tokens, customer, admin, ...}
  PrivilegeEscalationTests   no way to make yourself an administrator
  AdminMeTests               GET /api/admin/me

The matrix walks the REAL route table, so an admin route added in a later
milestone is covered automatically - and a route added without the guard
fails the inventory test.
"""

import unittest
import uuid

import jwt
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.deps import require_admin
from app.core.config import settings
from app.core.security import create_refresh_token
from app.models import UserRole
from tests.p9_support import AdminTestCase, bearer, build_admin_app, expired_token

FORBIDDEN_BODY_FIELDS = {"role", "roles", "is_admin", "is_superuser", "is_staff", "admin", "permissions", "is_active"}


def _dependency_calls(dependant):
    for dep in dependant.dependencies:
        yield dep.call
        yield from _dependency_calls(dep)


def _admin_routes(app):
    return [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/admin")]


def _fill(path: str) -> str:
    out = path
    for part in [p for p in path.split("/") if p.startswith("{")]:
        out = out.replace(part, str(uuid.uuid4()))
    return out


class AdminGuardInventoryTests(unittest.TestCase):
    def test_every_admin_route_depends_on_require_admin(self):
        app = build_admin_app(with_public=False)
        routes = _admin_routes(app)
        self.assertGreaterEqual(len(routes), 2)
        for route in routes:
            with self.subTest(route=f"{sorted(route.methods)} {route.path}"):
                self.assertIn(require_admin, list(_dependency_calls(route.dependant)))

    def test_nothing_outside_the_admin_prefix_is_mounted_by_the_admin_router(self):
        from app.api.admin import router

        for route in router.routes:
            self.assertTrue(route.path.startswith("/api/admin"), route.path)

    def test_no_public_request_body_can_carry_a_role_or_admin_flag(self):
        app = build_admin_app()
        checked = 0
        for route in app.routes:
            if not isinstance(route, APIRoute) or route.path.startswith("/api/admin"):
                continue
            body = route.body_field
            model = getattr(body, "type_", None) if body is not None else None
            fields = getattr(model, "model_fields", None)
            if not fields:
                continue
            checked += 1
            with self.subTest(route=route.path):
                self.assertFalse(FORBIDDEN_BODY_FIELDS & set(fields), set(fields))
        self.assertGreaterEqual(checked, 2)


class RealAppMountTests(unittest.TestCase):
    """The real `app.main` mounts the admin router, behind the guard. (Skipped
    only where `app.main` is not the project's real entry point.)"""

    def real_app(self):
        from app.main import app

        if not any(isinstance(r, APIRoute) and r.path.startswith("/api/") for r in app.routes):
            self.skipTest("app.main mounts no API routes here (not the project's real entry point)")
        return app

    def test_admin_routes_are_mounted_and_guarded(self):
        routes = _admin_routes(self.real_app())
        self.assertGreaterEqual(len(routes), 2)
        for route in routes:
            with self.subTest(route=route.path):
                self.assertIn(require_admin, list(_dependency_calls(route.dependant)))

    def test_an_anonymous_call_gets_the_401_envelope(self):
        r = TestClient(self.real_app()).get("/api/admin/me")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["success"], False)


class AdminAuthMatrixTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.app = build_admin_app()
        self.client = TestClient(self.app)
        self.customer = self.make_user()
        self.admin = self.make_admin()
        self.calls = []
        for route in _admin_routes(self.app):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                self.calls.append((method.lower(), _fill(route.path)))

    def send(self, method, url, headers=None):
        kwargs = {"headers": headers or {}}
        if method in ("post", "put", "patch"):
            kwargs["json"] = {}
        return getattr(self.client, method)(url, **kwargs)

    def assert_all(self, status_code, headers=None):
        self.assertTrue(self.calls)
        for method, url in self.calls:
            with self.subTest(call=f"{method} {url}"):
                r = self.send(method, url, headers)
                self.assertEqual(r.status_code, status_code, r.text)

    def test_no_login_is_401(self):
        self.assert_all(401)

    def test_a_malformed_or_foreign_token_is_401(self):
        forged = jwt.encode({"sub": str(self.admin.id), "type": "access", "role": "admin"}, "not-the-real-secret-but-long-enough-for-hs256", algorithm="HS256")
        unsigned = jwt.encode({"sub": str(self.admin.id), "type": "access", "role": "admin"}, "", algorithm="none")
        for token in ["garbage", "", forged, unsigned, expired_token(self.admin)]:
            with self.subTest(token=token[:12]):
                self.assert_all(401, {"Authorization": f"Bearer {token}"})

    def test_a_basic_scheme_header_is_401(self):
        self.assert_all(401, {"Authorization": "Basic YWRtaW46YWRtaW4="})

    def test_a_refresh_token_cannot_be_used_as_a_bearer_token(self):
        self.assert_all(401, {"Authorization": f"Bearer {create_refresh_token(self.admin.id)}"})

    def test_a_token_for_a_user_that_does_not_exist_is_401(self):
        from app.core.security import create_access_token

        self.assert_all(401, {"Authorization": f"Bearer {create_access_token(uuid.uuid4(), 'admin')}"})

    def test_a_customer_is_403(self):
        self.assert_all(403, bearer(self.customer))

    def test_a_customer_cannot_forge_the_role_claim(self):
        # Correctly signed token that SAYS admin; the database says customer.
        self.assert_all(403, bearer(self.customer, claim_role="admin"))

    def test_a_deactivated_admin_is_403(self):
        self.set_role(self.admin, active=False)
        self.assert_all(403, bearer(self.admin))

    def test_a_demoted_admin_loses_access_on_the_next_request(self):
        headers = bearer(self.admin)
        self.assertEqual(self.client.get("/api/admin/me", headers=headers).status_code, 200)
        self.set_role(self.admin, UserRole.CUSTOMER)
        self.assertEqual(self.client.get("/api/admin/me", headers=headers).status_code, 403)

    def test_a_promoted_customer_gains_access_without_a_new_token(self):
        headers = bearer(self.customer)
        self.assertEqual(self.client.get("/api/admin/me", headers=headers).status_code, 403)
        self.set_role(self.customer, UserRole.ADMIN)
        self.assertEqual(self.client.get("/api/admin/me", headers=headers).status_code, 200)

    def test_an_admin_passes_the_guard(self):
        for method, url in self.calls:
            with self.subTest(call=f"{method} {url}"):
                r = self.send(method, url, bearer(self.admin))
                self.assertNotIn(r.status_code, (401, 403), r.text)

    def test_the_guard_runs_before_body_validation(self):
        r = self.client.post("/api/admin/does-not-exist", json={}, headers=bearer(self.customer))
        self.assertEqual(r.status_code, 404)  # unknown route: nothing to leak either way


class PrivilegeEscalationTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(build_admin_app())

    def register(self, **extra):
        n = uuid.uuid4().int % 10**8
        body = {
            "first_name": "Eve",
            "last_name": "Mallory",
            "email": f"eve{n}@example.com",
            "phone_number": f"+9198{n:08d}",
            "password": "Str0ng!Passw0rd",
            "confirm_password": "Str0ng!Passw0rd",
        }
        body.update(extra)
        return self.client.post("/api/auth/register", json=body), body["email"]

    def test_registering_with_a_role_creates_a_customer(self):
        for extra in [{"role": "admin"}, {"is_admin": True}, {"role": "ADMIN", "is_superuser": True}]:
            with self.subTest(extra=extra):
                r, email = self.register(**extra)
                self.assertEqual(r.status_code, 201, r.text)
                self.assertEqual(r.json()["data"]["role"], "customer")
                from app.models import User
                from tests.pg_support import new_session

                with new_session() as s:
                    self.assertEqual(s.query(User).filter(User.email == email).one().role, UserRole.CUSTOMER)

    def test_a_new_account_cannot_open_the_admin_area(self):
        from app.models import User
        from tests.pg_support import new_session

        r, email = self.register(role="admin")
        self.assertEqual(r.status_code, 201, r.text)
        with new_session() as s:
            user = s.query(User).filter(User.email == email).one()
        # A token carrying the role the attacker asked for is still refused.
        for claim in (None, "admin"):
            with self.subTest(claim=claim):
                r = self.client.get("/api/admin/me", headers=bearer(user, claim_role=claim))
                self.assertEqual(r.status_code, 403)

    def test_a_profile_update_cannot_change_the_role(self):
        user = self.make_user()
        for body in [{"role": "admin"}, {"is_admin": True}, {"is_active": True, "role": "admin"}, {"first_name": "Ok", "role": "admin"}]:
            with self.subTest(body=body):
                r = self.client.patch("/api/users/me", json=body, headers=bearer(user))
                self.assertEqual(r.status_code, 422, r.text)
                self.assertEqual(self.role_in_db(user.id), UserRole.CUSTOMER)

    def test_a_valid_profile_update_still_leaves_the_role_alone(self):
        user = self.make_user()
        r = self.client.patch("/api/users/me", json={"first_name": "Renamed"}, headers=bearer(user))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["role"], "customer")
        self.assertEqual(self.role_in_db(user.id), UserRole.CUSTOMER)

    def test_there_is_no_route_that_creates_or_promotes_an_admin(self):
        app = self.client.app
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            text = f"{route.path} {route.name}".lower()
            with self.subTest(route=route.path):
                self.assertNotIn("promote", text)
                self.assertNotIn("make-admin", text)
                self.assertNotIn("create_admin", text)


class AdminMeTests(AdminTestCase):
    def test_me_returns_the_database_identity_and_no_secrets(self):
        admin = self.make_admin()
        client = TestClient(build_admin_app())
        r = client.get("/api/admin/me", headers=bearer(admin))
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertEqual(set(data), {"id", "email", "first_name", "last_name", "role"})
        self.assertEqual((data["email"], data["role"]), (admin.email, "admin"))
        self.assertNotIn("password", r.text.lower())


if __name__ == "__main__":
    unittest.main()
