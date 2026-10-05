"""
Address list + add: request validation (no database needed) and the
service's default-address rules (PostgreSQL integration tests).

See tests/pg_support.py for how to run the PostgreSQL ones.
"""

import unittest

from pydantic import ValidationError

from app.models import Address
from app.schemas.address import AddressCreateRequest
from app.services.address_service import AddressService
from tests.pg_support import PostgresTestCase, new_session, run_concurrently


def payload(**overrides) -> AddressCreateRequest:
    values = dict(
        full_name="Asha Rao",
        phone_number="9876543210",
        address_line_1="12 MG Road",
        city="Pune",
        state="Maharashtra",
        postal_code="411001",
    )
    values.update(overrides)
    return AddressCreateRequest(**values)


class AddressSchemaTests(unittest.TestCase):
    def test_valid_payload_is_accepted_and_trimmed(self):
        p = payload(full_name="  Asha Rao  ", city=" Pune ")
        self.assertEqual((p.full_name, p.city), ("Asha Rao", "Pune"))
        self.assertFalse(p.is_default)

    def test_postal_code_must_be_a_six_digit_indian_pin(self):
        for bad in ["41100", "4110011", "011001", "41100a", "", "411 001"]:
            with self.subTest(pin=bad), self.assertRaises(ValidationError):
                payload(postal_code=bad)

    def test_phone_must_match_the_registration_rule(self):
        payload(phone_number="+919876543210")
        for bad in ["abc", "0123456789", "12345", "98765 43210"]:
            with self.subTest(phone=bad), self.assertRaises(ValidationError):
                payload(phone_number=bad)

    def test_required_fields_cannot_be_blank(self):
        for field in ["full_name", "address_line_1", "city", "state"]:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                payload(**{field: "   "})

    def test_over_long_values_are_rejected(self):
        with self.assertRaises(ValidationError):
            payload(full_name="x" * 151)
        with self.assertRaises(ValidationError):
            payload(address_line_1="x" * 256)

    def test_country_and_owner_are_not_client_controlled(self):
        # Extra keys are ignored by Pydantic; the point is they never reach the model.
        p = AddressCreateRequest.model_validate(
            dict(payload().model_dump(), country="Narnia", user_id="00000000-0000-0000-0000-000000000000")
        )
        self.assertFalse(hasattr(p, "country"))
        self.assertFalse(hasattr(p, "user_id"))


class AddressServiceTests(PostgresTestCase):
    def test_first_address_becomes_the_default(self):
        user = self.make_user()
        address = AddressService(self.db).create_address(user.id, payload())
        self.assertTrue(address.is_default)
        self.assertEqual(address.country, "India")
        self.assertEqual(address.user_id, user.id)

    def test_later_addresses_are_not_default_unless_asked(self):
        user = self.make_user()
        service = AddressService(self.db)
        first = service.create_address(user.id, payload())
        second = service.create_address(user.id, payload(address_line_1="Other"))
        self.assertTrue(first.is_default)
        self.assertFalse(second.is_default)

    def test_asking_for_default_moves_it(self):
        user = self.make_user()
        service = AddressService(self.db)
        first = service.create_address(user.id, payload())
        second = service.create_address(user.id, payload(address_line_1="Other", is_default=True))
        self.db.refresh(first)
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_list_puts_the_default_first_and_only_shows_own_addresses(self):
        mine, theirs = self.make_user(), self.make_user()
        service = AddressService(self.db)
        service.create_address(mine.id, payload(address_line_1="A"))
        service.create_address(mine.id, payload(address_line_1="B"))
        wanted = service.create_address(mine.id, payload(address_line_1="C", is_default=True))
        service.create_address(theirs.id, payload(address_line_1="Not mine"))

        listed = service.list_addresses(mine.id)
        self.assertEqual(len(listed), 3)
        self.assertEqual(listed[0].id, wanted.id)
        self.assertTrue(all(a.user_id == mine.id for a in listed))

    def test_default_is_per_user(self):
        a, b = self.make_user(), self.make_user()
        service = AddressService(self.db)
        self.assertTrue(service.create_address(a.id, payload()).is_default)
        self.assertTrue(service.create_address(b.id, payload()).is_default)

    def test_get_for_user_hides_other_peoples_addresses(self):
        mine, theirs = self.make_user(), self.make_user()
        address = self.make_address(theirs)
        service = AddressService(self.db)
        self.assertIsNone(service.repository.get_for_user(address.id, mine.id))
        self.assertIsNotNone(service.repository.get_for_user(address.id, theirs.id))

    def test_concurrent_default_requests_leave_exactly_one_default(self):
        user = self.make_user()
        user_id = user.id

        def job(n):
            def run():
                with new_session() as s:
                    return AddressService(s).create_address(user_id, payload(address_line_1=f"Line {n}", is_default=True)).id

            return run

        results = run_concurrently([job(n) for n in range(8)])
        self.assertEqual([r for r in results if r[0] == "err"], [])
        with new_session() as s:
            rows = s.query(Address).filter(Address.user_id == user_id).all()
            self.assertEqual(len(rows), 8)
            self.assertEqual(sum(1 for r in rows if r.is_default), 1)


if __name__ == "__main__":
    unittest.main()