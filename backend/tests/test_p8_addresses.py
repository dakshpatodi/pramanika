"""
Phase 8 M1 - address edit, delete and set-default.

  AddressUpdateSchemaTests   what PATCH accepts and refuses (no database)
  AddressEditTests           editing, never touching orders
  AddressDefaultTests        set-default and the one-default rule
  AddressDeleteTests         delete, default promotion, orders keep their snapshot
  AddressInvariantTests      a long random run of operations never breaks the rule
  AddressConcurrencyTests    real threads: no two defaults, delete vs checkout
  AddressApiTests            HTTP: login, ownership, validation, shapes

See tests/pg_support.py for how to run the PostgreSQL ones.
"""

import random
import unittest
import uuid
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import addresses as addresses_api
from app.core.exceptions import AddressLimitReachedError, AddressNotFoundError, DomainError
from app.core.security import create_access_token
from app.database.session import get_db
from app.models import Address, Order
from app.schemas.address import AddressCreateRequest, AddressUpdateRequest
from app.services.address_service import MAX_ADDRESSES_PER_USER, AddressService
from app.services.checkout_service import CheckoutService
from tests.pg_support import new_session, run_concurrently
from tests.test_p6_checkout import CONFIG, CheckoutTestCase, new_key


def create(**overrides) -> AddressCreateRequest:
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


def update(**fields) -> AddressUpdateRequest:
    return AddressUpdateRequest(**fields)


class AddressUpdateSchemaTests(unittest.TestCase):
    def test_a_single_field_is_enough_and_values_are_trimmed(self):
        p = update(city="  Mumbai ")
        self.assertEqual(p.model_fields_set, {"city"})
        self.assertEqual(p.city, "Mumbai")

    def test_an_empty_request_is_refused(self):
        with self.assertRaises(ValidationError):
            AddressUpdateRequest()

    def test_owner_country_default_and_unknown_fields_are_refused(self):
        for key, value in [
            ("user_id", "00000000-0000-0000-0000-000000000000"),
            ("id", "00000000-0000-0000-0000-000000000000"),
            ("country", "Narnia"),
            ("is_default", True),
            ("created_at", "2020-01-01T00:00:00Z"),
            ("landmark", "x"),
        ]:
            with self.subTest(field=key), self.assertRaises(ValidationError):
                AddressUpdateRequest.model_validate({"city": "Pune", key: value})

    def test_required_fields_cannot_be_null_or_blank(self):
        for field in ["full_name", "phone_number", "address_line_1", "city", "state", "postal_code"]:
            for bad in [None, "", "   "]:
                with self.subTest(field=field, value=bad), self.assertRaises(ValidationError):
                    AddressUpdateRequest.model_validate({field: bad})

    def test_the_optional_second_line_may_be_cleared(self):
        for clear in [None, "", "   "]:
            with self.subTest(value=clear):
                p = AddressUpdateRequest.model_validate({"address_line_2": clear})
                self.assertIn("address_line_2", p.model_fields_set)

    def test_pin_and_phone_follow_the_creation_rules(self):
        update(postal_code="560001", phone_number="+919876543210")
        for bad in ["41100", "4110011", "011001", "41100a", "411 001"]:
            with self.subTest(pin=bad), self.assertRaises(ValidationError):
                update(postal_code=bad)
        for bad in ["abc", "0123456789", "12345", "98765 43210"]:
            with self.subTest(phone=bad), self.assertRaises(ValidationError):
                update(phone_number=bad)

    def test_over_long_values_are_refused(self):
        with self.assertRaises(ValidationError):
            update(full_name="x" * 151)
        with self.assertRaises(ValidationError):
            update(address_line_2="x" * 256)


class AddressTestCase(CheckoutTestCase):
    def add(self, user, **overrides) -> Address:
        return AddressService(self.db).create_address(user.id, create(**overrides))

    def rows(self, user_id):
        with new_session() as s:
            rows = s.query(Address).filter(Address.user_id == user_id).order_by(Address.created_at, Address.id).all()
            return [(r.id, r.address_line_1, r.is_default) for r in rows]

    def defaults(self, user_id):
        return [row for row in self.rows(user_id) if row[2]]

    def order_snapshot(self, order_id):
        with new_session() as s:
            o = s.get(Order, order_id)
            return dict(
                address_id=o.shipping_address_id,
                name=o.shipping_full_name,
                phone=o.shipping_phone_number,
                line1=o.shipping_address_line_1,
                line2=o.shipping_address_line_2,
                city=o.shipping_city,
                state=o.shipping_state,
                pin=o.shipping_postal_code,
                country=o.shipping_country,
                status=o.status,
                payment=o.payment_status,
                total=o.total_amount,
                updated_at=o.updated_at,
            )

    def place_order(self, user, address, price="100.00"):
        product = self.make_product(price=price, stock=50)
        self.fill_cart(user, [(product, 1)])
        return self.checkout(user, address).order


class AddressEditTests(AddressTestCase):
    def test_changes_only_the_fields_that_were_sent(self):
        user = self.make_user()
        a = self.add(user)
        edited = AddressService(self.db).update_address(user.id, a.id, update(city="Mumbai", postal_code="400001"))
        self.assertEqual((edited.city, edited.postal_code), ("Mumbai", "400001"))
        self.assertEqual(
            (edited.full_name, edited.phone_number, edited.address_line_1, edited.state, edited.country),
            ("Asha Rao", "9876543210", "12 MG Road", "Maharashtra", "India"),
        )

    def test_the_default_flag_and_owner_never_change_by_editing(self):
        user = self.make_user()
        first = self.add(user)
        second = self.add(user, address_line_1="Other")
        AddressService(self.db).update_address(user.id, second.id, update(city="Nashik"))
        self.assertEqual([(r[1], r[2]) for r in self.rows(user.id)], [("12 MG Road", True), ("Other", False)])
        self.assertEqual(first.user_id, user.id)

    def test_the_second_line_can_be_set_and_cleared(self):
        user = self.make_user()
        a = self.add(user, address_line_2="Flat 4")
        svc = AddressService(self.db)
        self.assertEqual(svc.update_address(user.id, a.id, update(address_line_2="Flat 9")).address_line_2, "Flat 9")
        self.assertIsNone(svc.update_address(user.id, a.id, update(address_line_2="")).address_line_2)
        svc.update_address(user.id, a.id, update(address_line_2="Back"))
        cleared = svc.update_address(user.id, a.id, AddressUpdateRequest.model_validate({"address_line_2": None}))
        self.assertIsNone(cleared.address_line_2)

    def test_someone_elses_or_a_missing_address_is_not_found_and_unchanged(self):
        mine, theirs = self.make_user(), self.make_user()
        a = self.add(theirs)
        before = self.rows(theirs.id)
        svc = AddressService(self.db)
        with self.assertRaises(AddressNotFoundError):
            svc.update_address(mine.id, a.id, update(city="Hijacked"))
        with self.assertRaises(AddressNotFoundError):
            svc.update_address(mine.id, uuid.uuid4(), update(city="Nope"))
        self.assertEqual(self.rows(theirs.id), before)
        with new_session() as s:
            self.assertEqual(s.get(Address, a.id).city, "Pune")

    def test_editing_never_changes_an_order_already_placed_with_the_address(self):
        user = self.make_user()
        a = self.add(user)
        order = self.place_order(user, a)
        before = self.order_snapshot(order.id)

        AddressService(self.db).update_address(
            user.id, a.id, update(full_name="New Name", address_line_1="99 New Road", city="Delhi", postal_code="110001")
        )

        after = self.order_snapshot(order.id)
        self.assertEqual(after, before)  # including updated_at: the order row was not written
        self.assertEqual((after["name"], after["line1"], after["city"], after["pin"]), ("Asha Rao", "12 MG Road", "Pune", "411001"))

    def test_the_next_checkout_uses_the_edited_details(self):
        user = self.make_user()
        a = self.add(user)
        first = self.place_order(user, a)
        AddressService(self.db).update_address(user.id, a.id, update(city="Delhi", postal_code="110001"))
        second = self.place_order(user, a)
        self.assertEqual(self.order_snapshot(first.id)["city"], "Pune")
        self.assertEqual((self.order_snapshot(second.id)["city"], self.order_snapshot(second.id)["pin"]), ("Delhi", "110001"))


class AddressDefaultTests(AddressTestCase):
    def test_makes_another_address_the_default(self):
        user = self.make_user()
        a, b = self.add(user), self.add(user, address_line_1="B")
        listed = AddressService(self.db).set_default(user.id, b.id)
        self.assertEqual([x.id for x in listed][0], b.id)
        self.assertEqual([(r[1], r[2]) for r in self.rows(user.id)], [("12 MG Road", False), ("B", True)])

    def test_the_current_default_stays_as_it_is(self):
        user = self.make_user()
        a = self.add(user)
        self.add(user, address_line_1="B")
        listed = AddressService(self.db).set_default(user.id, a.id)
        self.assertEqual(len(listed), 2)
        self.assertEqual(len(self.defaults(user.id)), 1)
        self.assertEqual(self.defaults(user.id)[0][0], a.id)

    def test_someone_elses_address_cannot_become_your_default_nor_disturb_theirs(self):
        mine, theirs = self.make_user(), self.make_user()
        self.add(mine)
        t1, t2 = self.add(theirs), self.add(theirs, address_line_1="T2")
        before_mine, before_theirs = self.rows(mine.id), self.rows(theirs.id)
        with self.assertRaises(AddressNotFoundError):
            AddressService(self.db).set_default(mine.id, t2.id)
        self.assertEqual(self.rows(mine.id), before_mine)
        self.assertEqual(self.rows(theirs.id), before_theirs)

    def test_each_user_has_their_own_default(self):
        a, b = self.make_user(), self.make_user()
        a1, a2 = self.add(a), self.add(a, address_line_1="A2")
        self.add(b)
        AddressService(self.db).set_default(a.id, a2.id)
        self.assertEqual(len(self.defaults(a.id)), 1)
        self.assertEqual(len(self.defaults(b.id)), 1)


class AddressDeleteTests(AddressTestCase):
    def test_deleting_a_non_default_address_keeps_the_default(self):
        user = self.make_user()
        a, b = self.add(user), self.add(user, address_line_1="B")
        remaining = AddressService(self.db).delete_address(user.id, b.id)
        self.assertEqual([x.id for x in remaining], [a.id])
        self.assertEqual([(r[0], r[2]) for r in self.rows(user.id)], [(a.id, True)])

    def test_deleting_the_default_promotes_the_newest_remaining_address(self):
        user = self.make_user()
        a = self.add(user)
        b = self.add(user, address_line_1="B")
        c = self.add(user, address_line_1="C")
        remaining = AddressService(self.db).delete_address(user.id, a.id)
        self.assertEqual(remaining[0].id, c.id)  # newest first, and it is the default
        self.assertEqual(self.defaults(user.id)[0][0], c.id)
        self.assertEqual(len(self.defaults(user.id)), 1)

    def test_deleting_the_only_address_leaves_an_empty_list(self):
        user = self.make_user()
        a = self.add(user)
        self.assertEqual(AddressService(self.db).delete_address(user.id, a.id), [])
        self.assertEqual(self.rows(user.id), [])

    def test_the_next_address_added_after_deleting_everything_is_the_default(self):
        user = self.make_user()
        a = self.add(user)
        AddressService(self.db).delete_address(user.id, a.id)
        self.assertTrue(self.add(user, address_line_1="Fresh").is_default)

    def test_someone_elses_or_a_missing_address_is_not_found_and_nothing_is_deleted(self):
        mine, theirs = self.make_user(), self.make_user()
        a = self.add(theirs)
        svc = AddressService(self.db)
        with self.assertRaises(AddressNotFoundError):
            svc.delete_address(mine.id, a.id)
        with self.assertRaises(AddressNotFoundError):
            svc.delete_address(mine.id, uuid.uuid4())
        self.assertEqual(len(self.rows(theirs.id)), 1)

    def test_deleting_twice_is_not_found_the_second_time(self):
        user = self.make_user()
        a = self.add(user)
        self.add(user, address_line_1="B")
        svc = AddressService(self.db)
        svc.delete_address(user.id, a.id)
        with self.assertRaises(AddressNotFoundError):
            svc.delete_address(user.id, a.id)
        self.assertEqual(len(self.defaults(user.id)), 1)

    def test_orders_placed_with_the_address_keep_their_delivery_details(self):
        user = self.make_user()
        a = self.add(user)
        self.add(user, address_line_1="B")
        paid = self.place_order(user, a)
        pending = self.place_order(user, a)
        before = {o.id: self.order_snapshot(o.id) for o in (paid, pending)}

        AddressService(self.db).delete_address(user.id, a.id)

        for order_id, snap in before.items():
            after = self.order_snapshot(order_id)
            self.assertEqual(snap["address_id"], a.id)
            self.assertIsNone(after["address_id"])  # only the optional link is cleared, by the database
            # everything else - delivery copy, status, total and updated_at - is untouched
            self.assertEqual(after, dict(snap, address_id=None))
            self.assertEqual((after["name"], after["line1"], after["city"]), ("Asha Rao", "12 MG Road", "Pune"))

    def test_checkout_with_a_deleted_address_is_refused_and_changes_nothing(self):
        user = self.make_user()
        a = self.add(user)
        self.add(user, address_line_1="B")
        product = self.make_product(price="100.00", stock=5)
        self.fill_cart(user, [(product, 1)])
        stock_before = self.stock(product)
        AddressService(self.db).delete_address(user.id, a.id)
        with self.assertRaises(AddressNotFoundError):
            self.checkout(user, a)
        self.assertEqual(self.order_count(), 0)
        self.assertEqual(self.stock(product), stock_before)

    def test_other_users_addresses_and_orders_are_untouched(self):
        mine, theirs = self.make_user(), self.make_user()
        a = self.add(mine)
        t = self.add(theirs)
        their_order = self.place_order(theirs, t)
        before = self.order_snapshot(their_order.id)
        AddressService(self.db).delete_address(mine.id, a.id)
        self.assertEqual(self.order_snapshot(their_order.id), before)
        self.assertEqual(len(self.rows(theirs.id)), 1)


class AddressLimitTests(AddressTestCase):
    def test_the_limit_is_enforced_and_nothing_is_added_past_it(self):
        user = self.make_user()
        svc = AddressService(self.db)
        for n in range(MAX_ADDRESSES_PER_USER):
            svc.create_address(user.id, create(address_line_1=f"Line {n}"))
        with self.assertRaises(AddressLimitReachedError):
            svc.create_address(user.id, create(address_line_1="One too many", is_default=True))
        rows = self.rows(user.id)
        self.assertEqual(len(rows), MAX_ADDRESSES_PER_USER)
        self.assertEqual(len(self.defaults(user.id)), 1)
        self.assertEqual(self.defaults(user.id)[0][1], "Line 0")  # the refused one did not steal the default

    def test_deleting_one_makes_room(self):
        user = self.make_user()
        svc = AddressService(self.db)
        made = [svc.create_address(user.id, create(address_line_1=f"L{n}")) for n in range(MAX_ADDRESSES_PER_USER)]
        svc.delete_address(user.id, made[-1].id)
        svc.create_address(user.id, create(address_line_1="Room again"))
        self.assertEqual(len(self.rows(user.id)), MAX_ADDRESSES_PER_USER)

    def test_the_limit_is_per_user(self):
        a, b = self.make_user(), self.make_user()
        svc = AddressService(self.db)
        for n in range(MAX_ADDRESSES_PER_USER):
            svc.create_address(a.id, create(address_line_1=f"L{n}"))
        svc.create_address(b.id, create())


class AddressInvariantTests(AddressTestCase):
    def test_a_long_random_run_always_leaves_exactly_one_default(self):
        rng = random.Random(8)
        user, other = self.make_user(), self.make_user()
        svc = AddressService(self.db)
        svc.create_address(other.id, create(address_line_1="Other user"))
        other_before = self.rows(other.id)
        ids = []
        for step in range(80):
            op = rng.choice(["add", "add", "default", "delete", "edit", "add_default"])
            if op in ("add", "add_default") and len(ids) < MAX_ADDRESSES_PER_USER:
                ids.append(svc.create_address(user.id, create(address_line_1=f"S{step}", is_default=(op == "add_default"))).id)
            elif ids and op == "default":
                svc.set_default(user.id, rng.choice(ids))
            elif ids and op == "delete":
                gone = rng.choice(ids)
                ids.remove(gone)
                svc.delete_address(user.id, gone)
            elif ids and op == "edit":
                svc.update_address(user.id, rng.choice(ids), update(city=f"City{step}"))
            rows = self.rows(user.id)
            self.assertEqual(len(rows), len(ids), f"step {step} ({op})")
            self.assertEqual(len(self.defaults(user.id)), 1 if rows else 0, f"step {step} ({op})")
        self.assertEqual(self.rows(other.id), other_before)


class AddressConcurrencyTests(AddressTestCase):
    def test_simultaneous_set_default_requests_leave_exactly_one_default(self):
        user = self.make_user()
        ids = [self.add(user, address_line_1=f"L{n}").id for n in range(6)]
        user_id = user.id

        def job(address_id):
            def run():
                with new_session() as s:
                    return [a.id for a in AddressService(s).set_default(user_id, address_id)]

            return run

        results = run_concurrently([job(i) for i in ids])
        self.assertEqual([r for r in results if r[0] == "err"], [])
        self.assertEqual(len(self.defaults(user_id)), 1)
        self.assertEqual(len(self.rows(user_id)), 6)

    def test_deleting_the_default_from_two_tabs_leaves_one_default_and_one_error(self):
        user = self.make_user()
        first = self.add(user)
        for n in range(3):
            self.add(user, address_line_1=f"L{n}")
        user_id, first_id = user.id, first.id

        def run():
            with new_session() as s:
                return len(AddressService(s).delete_address(user_id, first_id))

        results = run_concurrently([run, run])
        oks = [r for r in results if r[0] == "ok"]
        errs = [r for r in results if r[0] == "err"]
        self.assertEqual((len(oks), len(errs)), (1, 1))
        self.assertIsInstance(errs[0][1], AddressNotFoundError)
        self.assertEqual(len(self.rows(user_id)), 3)
        self.assertEqual(len(self.defaults(user_id)), 1)

    def test_delete_racing_with_checkout_never_breaks_the_checkout(self):
        """Either checkout wins (order saved with its own copy of the address,
        the saved address then disappears) or delete wins (checkout says
        'address not found'). Never an integrity error, never a half order."""
        outcomes = {"order": 0, "refused": 0}
        for round_ in range(12):
            user = self.make_user()
            address = self.add(user)
            self.add(user, address_line_1="Spare")
            product = self.make_product(price="100.00", stock=5)
            self.fill_cart(user, [(product, 1)])
            user_id, address_id, product_id = user.id, address.id, product.id

            def do_checkout():
                with new_session() as s:
                    return CheckoutService(s, config=CONFIG).place_order(
                        user_id, shipping_address_id=address_id, idempotency_key=new_key()
                    ).order.id

            def do_delete():
                with new_session() as s:
                    return len(AddressService(s).delete_address(user_id, address_id))

            checkout_result, delete_result = run_concurrently([do_checkout, do_delete])
            self.assertEqual(delete_result[0], "ok", f"round {round_}: {delete_result}")
            self.assertEqual(delete_result[1], 1)
            with new_session() as s:
                orders = s.query(Order).filter(Order.user_id == user_id).all()
            if checkout_result[0] == "ok":
                outcomes["order"] += 1
                self.assertEqual(len(orders), 1)
                self.assertEqual(orders[0].shipping_address_line_1, "12 MG Road")
                self.assertIsNone(orders[0].shipping_address_id)  # delete ran after the order was saved
                self.assertEqual(self.stock(self.db.get(type(product), product_id)), (5, 1))
            else:
                outcomes["refused"] += 1
                self.assertIsInstance(checkout_result[1], AddressNotFoundError, f"round {round_}: {checkout_result[1]!r}")
                self.assertEqual(orders, [])
                self.assertEqual(self.stock(self.db.get(type(product), product_id)), (5, 0))
            self.assertEqual(len(self.defaults(user_id)), 1)
        self.assertEqual(sum(outcomes.values()), 12)


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
    app.dependency_overrides[get_db] = override_get_db
    return app


class AddressApiTests(AddressTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(build_app())
        self.user = self.make_user()

    def auth(self, user=None):
        user = user or self.user
        return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}

    def post_address(self, user=None, **overrides):
        body = dict(
            full_name="Asha Rao", phone_number="9876543210", address_line_1="12 MG Road",
            city="Pune", state="Maharashtra", postal_code="411001",
        )
        body.update(overrides)
        r = self.client.post("/api/addresses", json=body, headers=self.auth(user))
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["data"]

    def test_every_new_endpoint_requires_a_login(self):
        some_id = uuid.uuid4()
        calls = [
            ("patch", f"/api/addresses/{some_id}", {"city": "X"}),
            ("delete", f"/api/addresses/{some_id}", None),
            ("post", f"/api/addresses/{some_id}/default", None),
        ]
        for method, url, body in calls:
            with self.subTest(call=f"{method} {url}"):
                r = getattr(self.client, method)(url, **({"json": body} if body is not None else {}))
                self.assertEqual(r.status_code, 401)

    def test_edit_returns_the_updated_address(self):
        a = self.post_address()
        r = self.client.patch(f"/api/addresses/{a['id']}", json={"city": "Mumbai", "address_line_2": "Flat 3"}, headers=self.auth())
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertEqual((data["city"], data["address_line_2"], data["is_default"], data["country"]), ("Mumbai", "Flat 3", True, "India"))

    def test_edit_refuses_protected_fields_empty_bodies_and_bad_values(self):
        a = self.post_address()
        url = f"/api/addresses/{a['id']}"
        for body in [
            {}, {"is_default": False}, {"country": "Narnia"}, {"user_id": str(uuid.uuid4())},
            {"postal_code": "41100"}, {"city": ""}, {"city": None}, {"phone_number": "12"},
        ]:
            with self.subTest(body=body):
                self.assertEqual(self.client.patch(url, json=body, headers=self.auth()).status_code, 422)
        self.assertEqual(self.client.get("/api/addresses", headers=self.auth()).json()["data"][0]["city"], "Pune")

    def test_someone_elses_address_is_404_for_edit_delete_and_default(self):
        other = self.make_user()
        theirs = self.post_address(other)
        url = f"/api/addresses/{theirs['id']}"
        self.assertEqual(self.client.patch(url, json={"city": "X"}, headers=self.auth()).status_code, 404)
        self.assertEqual(self.client.delete(url, headers=self.auth()).status_code, 404)
        self.assertEqual(self.client.post(url + "/default", headers=self.auth()).status_code, 404)
        self.assertEqual(self.client.get("/api/addresses", headers=self.auth(other)).json()["data"][0]["city"], "Pune")

    def test_a_malformed_id_is_422(self):
        self.assertEqual(self.client.delete("/api/addresses/not-a-uuid", headers=self.auth()).status_code, 422)

    def test_set_default_returns_the_list_with_the_new_default_first(self):
        a = self.post_address()
        b = self.post_address(address_line_1="Second")
        r = self.client.post(f"/api/addresses/{b['id']}/default", headers=self.auth())
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertEqual([x["id"] for x in data], [b["id"], a["id"]])
        self.assertEqual([x["is_default"] for x in data], [True, False])

    def test_delete_returns_the_remaining_addresses_with_a_promoted_default(self):
        a = self.post_address()
        b = self.post_address(address_line_1="Second")
        r = self.client.delete(f"/api/addresses/{a['id']}", headers=self.auth())
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertEqual([(x["id"], x["is_default"]) for x in data], [(b["id"], True)])
        self.assertEqual(self.client.delete(f"/api/addresses/{a['id']}", headers=self.auth()).status_code, 404)

    def test_the_21st_address_is_409(self):
        for n in range(MAX_ADDRESSES_PER_USER):
            self.post_address(address_line_1=f"L{n}")
        r = self.client.post(
            "/api/addresses",
            json=dict(full_name="A", phone_number="9876543210", address_line_1="x", city="Pune", state="MH", postal_code="411001"),
            headers=self.auth(),
        )
        self.assertEqual(r.status_code, 409)
        self.assertFalse(r.json()["success"])

    def test_the_phase_6_list_and_add_still_behave(self):
        self.assertEqual(self.client.get("/api/addresses", headers=self.auth()).json()["data"], [])
        a = self.post_address()
        self.assertTrue(a["is_default"])
        self.assertEqual(self.client.get("/api/addresses", headers=self.auth()).json()["data"][0]["id"], a["id"])


if __name__ == "__main__":
    unittest.main()
