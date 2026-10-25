"""
Phase 8 M1 - profile update (PATCH /api/users/me).

  ProfileSchemaTests   what the request accepts and refuses (no database)
  ProfileServiceTests  the rules, against PostgreSQL
  ProfileApiTests      HTTP: authentication, protected fields, duplicates

See tests/pg_support.py for how to run the PostgreSQL ones.
"""

import unittest
from unittest import mock

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api import users as users_api
from app.core.exceptions import DomainError, DuplicatePhoneError
from app.core.security import create_access_token
from app.database.session import get_db
from app.models import User, UserRole
from app.schemas.user import UserUpdateRequest
from app.services.user_service import UserService
from tests.pg_support import PostgresTestCase, new_session


class ProfileSchemaTests(unittest.TestCase):
    def test_a_single_field_is_enough(self):
        p = UserUpdateRequest(first_name="Asha")
        self.assertEqual(p.model_fields_set, {"first_name"})

    def test_values_are_trimmed(self):
        p = UserUpdateRequest(first_name="  Asha ", last_name=" Rao  ", phone_number="+919876543210")
        self.assertEqual((p.first_name, p.last_name), ("Asha", "Rao"))

    def test_an_empty_request_is_refused(self):
        with self.assertRaises(ValidationError):
            UserUpdateRequest()

    def test_protected_and_unknown_fields_are_refused_not_ignored(self):
        for key, value in [
            ("id", "00000000-0000-0000-0000-000000000000"),
            ("email", "new@example.com"),
            ("role", "admin"),
            ("is_active", False),
            ("is_verified", True),
            ("password_hash", "x"),
            ("password", "Abcdef1!"),
            ("created_at", "2020-01-01T00:00:00Z"),
            ("nickname", "x"),
        ]:
            with self.subTest(field=key), self.assertRaises(ValidationError):
                UserUpdateRequest.model_validate({"first_name": "Asha", key: value})

    def test_a_present_field_cannot_be_null_or_blank(self):
        for field in ["first_name", "last_name", "phone_number"]:
            for bad in [None, "", "   "]:
                with self.subTest(field=field, value=bad), self.assertRaises(ValidationError):
                    UserUpdateRequest.model_validate({field: bad})

    def test_phone_follows_the_registration_rule(self):
        UserUpdateRequest(phone_number="9876543210")
        for bad in ["abc", "0123456789", "12345", "98765 43210", "+0123456789"]:
            with self.subTest(phone=bad), self.assertRaises(ValidationError):
                UserUpdateRequest(phone_number=bad)

    def test_over_long_names_are_refused(self):
        with self.assertRaises(ValidationError):
            UserUpdateRequest(first_name="x" * 101)
        with self.assertRaises(ValidationError):
            UserUpdateRequest(last_name="x" * 101)


class ProfileServiceTests(PostgresTestCase):
    def fresh(self, user_id):
        with new_session() as s:
            u = s.get(User, user_id)
            return (u.first_name, u.last_name, u.email, u.phone_number, u.role, u.is_active, u.is_verified, u.password_hash)

    def test_changes_only_the_fields_that_were_sent(self):
        user = self.make_user()
        before = self.fresh(user.id)
        UserService(self.db).update_profile(user, UserUpdateRequest(first_name="Asha"))
        after = self.fresh(user.id)
        self.assertEqual(after[0], "Asha")
        self.assertEqual(after[1:], before[1:])

    def test_updates_all_three_fields(self):
        user = self.make_user()
        UserService(self.db).update_profile(
            user, UserUpdateRequest(first_name="Asha", last_name="Rao", phone_number="+919811122233")
        )
        first, last, email, phone, *_ = self.fresh(user.id)
        self.assertEqual((first, last, phone), ("Asha", "Rao", "+919811122233"))

    def test_sending_the_current_values_writes_nothing(self):
        user = self.make_user()
        with new_session() as s:
            stamp = s.get(User, user.id).updated_at
        UserService(self.db).update_profile(
            user, UserUpdateRequest(first_name=user.first_name, phone_number=user.phone_number)
        )
        with new_session() as s:
            self.assertEqual(s.get(User, user.id).updated_at, stamp)

    def test_role_and_account_flags_cannot_change_through_the_service(self):
        user = self.make_user()
        self.assertEqual(user.role, UserRole.CUSTOMER)
        UserService(self.db).update_profile(user, UserUpdateRequest(last_name="Changed"))
        _, _, _, _, role, active, verified, _ = self.fresh(user.id)
        self.assertEqual((role, active, verified), (UserRole.CUSTOMER, True, False))

    def test_a_phone_number_used_by_another_account_is_refused_and_nothing_changes(self):
        mine, theirs = self.make_user(), self.make_user()
        before = self.fresh(mine.id)
        with self.assertRaises(DuplicatePhoneError):
            UserService(self.db).update_profile(
                mine, UserUpdateRequest(first_name="Changed", phone_number=theirs.phone_number)
            )
        self.assertEqual(self.fresh(mine.id), before)  # the first name was not applied either

    def test_keeping_your_own_phone_number_is_not_a_duplicate(self):
        user = self.make_user()
        UserService(self.db).update_profile(
            user, UserUpdateRequest(first_name="Asha", phone_number=user.phone_number)
        )
        self.assertEqual(self.fresh(user.id)[0], "Asha")

    def test_losing_the_race_for_a_phone_number_is_reported_as_a_duplicate(self):
        mine, theirs = self.make_user(), self.make_user()
        service = UserService(self.db)
        real = service.repository.get_by_phone
        calls = {"n": 0}

        def blind_first_time(phone):
            calls["n"] += 1
            return None if calls["n"] == 1 else real(phone)  # the pre-check misses; the constraint catches it

        with mock.patch.object(service.repository, "get_by_phone", side_effect=blind_first_time):
            with self.assertRaises(DuplicatePhoneError):
                service.update_profile(mine, UserUpdateRequest(phone_number=theirs.phone_number))
        self.assertNotEqual(self.fresh(mine.id)[3], theirs.phone_number)

    def test_an_unrelated_database_error_is_not_disguised_and_rolls_back(self):
        user = self.make_user()
        before = self.fresh(user.id)
        service = UserService(self.db)
        with mock.patch.object(self.db, "commit", side_effect=IntegrityError("x", {}, Exception("other"))):
            with self.assertRaises(IntegrityError):
                service.update_profile(user, UserUpdateRequest(first_name="Changed"))
        self.assertEqual(self.fresh(user.id), before)


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

    app.include_router(users_api.router)
    app.dependency_overrides[get_db] = override_get_db
    return app


class ProfileApiTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(build_app())
        self.user = self.make_user()

    def auth(self, user=None):
        user = user or self.user
        return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}

    def fresh(self, user_id):
        with new_session() as s:
            u = s.get(User, user_id)
            return {c: getattr(u, c) for c in ("first_name", "last_name", "email", "phone_number", "role", "is_active")}

    def test_both_methods_require_a_login(self):
        self.assertEqual(self.client.get("/api/users/me").status_code, 401)
        self.assertEqual(self.client.patch("/api/users/me", json={"first_name": "A"}).status_code, 401)
        bad = {"Authorization": "Bearer not-a-token"}
        self.assertEqual(self.client.patch("/api/users/me", json={"first_name": "A"}, headers=bad).status_code, 401)

    def test_a_deactivated_account_cannot_edit(self):
        with new_session() as s:
            s.get(User, self.user.id).is_active = False
            s.commit()
        r = self.client.patch("/api/users/me", json={"first_name": "A"}, headers=self.auth())
        self.assertEqual(r.status_code, 403)

    def test_updates_and_returns_the_new_profile(self):
        r = self.client.patch(
            "/api/users/me", json={"first_name": "Asha", "phone_number": "+919811122233"}, headers=self.auth()
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["first_name"], "Asha")
        self.assertEqual(body["data"]["phone_number"], "+919811122233")
        self.assertNotIn("password_hash", body["data"])
        self.assertEqual(self.client.get("/api/users/me", headers=self.auth()).json()["data"]["first_name"], "Asha")
        self.assertEqual(self.fresh(self.user.id)["first_name"], "Asha")

    def test_protected_fields_are_refused_and_nothing_is_written(self):
        before = self.fresh(self.user.id)
        for key, value in [("role", "admin"), ("email", "x@example.com"), ("is_active", False), ("id", str(self.user.id))]:
            with self.subTest(field=key):
                r = self.client.patch("/api/users/me", json={"first_name": "Hacker", key: value}, headers=self.auth())
                self.assertEqual(r.status_code, 422, r.text)
                self.assertEqual(self.fresh(self.user.id), before)

    def test_an_empty_body_and_bad_values_are_422(self):
        for body in [{}, {"first_name": ""}, {"first_name": None}, {"phone_number": "12"}]:
            with self.subTest(body=body):
                self.assertEqual(self.client.patch("/api/users/me", json=body, headers=self.auth()).status_code, 422)

    def test_a_phone_number_owned_by_someone_else_is_409(self):
        other = self.make_user()
        r = self.client.patch("/api/users/me", json={"phone_number": other.phone_number}, headers=self.auth())
        self.assertEqual(r.status_code, 409)
        self.assertFalse(r.json()["success"])
        self.assertNotEqual(self.fresh(self.user.id)["phone_number"], other.phone_number)

    def test_a_user_can_only_change_themselves(self):
        other = self.make_user()
        before_other = self.fresh(other.id)
        self.client.patch("/api/users/me", json={"first_name": "Mine"}, headers=self.auth())
        self.assertEqual(self.fresh(other.id), before_other)
        self.assertEqual(self.fresh(self.user.id)["first_name"], "Mine")


if __name__ == "__main__":
    unittest.main()
