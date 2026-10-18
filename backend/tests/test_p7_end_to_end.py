"""
Phase 7 / Milestone 10: the whole payment journey, end to end, over HTTP.

Every other Phase 7 suite tests one piece. This one drives the real routers
(checkout -> start payment -> verify / webhook / cancel / expiry) against a real
PostgreSQL with a mocked Razorpay (`FakeGateway`; nothing touches the network),
then audits the books. The scenarios are the ones real customers produce:

  A  the customer closes the tab / the popup, comes back, retries
  B  the browser's verify and Razorpay's webhook arrive together
  C  money arrives after the order closed (customer cancel, or expiry)
  D  duplicate deliveries of everything
  E  events out of order, wrong amounts, forged or foreign data
  F  cancel, expiry, verify and webhook all racing for one order
  G  seeded random mixes of all of the above on many orders

After every scenario `assert_books_balance` (Phase 6) and `assert_payment_books`
(Phase 7) must hold, and no response or log line may contain a secret, a
signature or the customer's contact details.
"""

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi.testclient import TestClient

from app.api import payments as payments_api
from app.core.security import create_access_token
from app.models import (
    Inventory,
    Order,
    OrderInventoryState,
    OrderPaymentStatus,
    OrderStatus,
    Payment,
    PaymentTransactionStatus as S,
    PaymentWebhookEvent,
)
from app.services.order_expiry_service import run_expiry_pass
from app.services.payment_rules import OPEN_STATUSES
from app.services.razorpay_signature import webhook_signature
from tests.payment_fakes import FAKE_SECRET, sign
from tests.payment_fakes import FakeGateway
from tests.pg_support import new_session, run_concurrently
from tests.test_p6_checkout_integration import AuditedTestCase
from tests.test_p6_order_api import build_app as phase6_app
from tests.test_p7_payment_webhook import EMAIL, SECRET as WEBHOOK_SECRET, make_body

PHONE = "+919999999999"  # make_body puts this in every payload


class _Collect(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        text = record.getMessage()
        if record.exc_info:
            text += " " + "".join(logging.Formatter().formatException(record.exc_info))
        self.lines.append(text)


def paise(amount) -> int:
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class Buyer:
    """Plain values only: threads must never touch ORM objects bound to the test's own session."""

    def __init__(self, user, address):
        self.user, self.address = user, address  # for the main thread (fill_cart)
        self.id, self.role, self.address_id = user.id, user.role.value, address.id


class JourneyCase(AuditedTestCase):
    """A real app with a fake Razorpay, plus helpers that speak HTTP like the
    browser (and like Razorpay's servers) do."""

    def setUp(self):
        super().setUp()
        self.gateway = FakeGateway()
        self.app = phase6_app()
        self.app.include_router(payments_api.router)
        self.app.dependency_overrides[payments_api.get_payment_gateway] = lambda: self.gateway
        self.app.dependency_overrides[payments_api.get_webhook_secret] = lambda: WEBHOOK_SECRET
        self.client = TestClient(self.app)
        self.transcript = []
        self.signatures = []
        self.initial_stock = {}
        self.logs = _Collect()
        root = logging.getLogger()
        old_level = root.level
        root.addHandler(self.logs)
        root.setLevel(logging.DEBUG)
        self.addCleanup(lambda: (root.removeHandler(self.logs), root.setLevel(old_level)))
        self._n = 0

    def tearDown(self):
        try:
            self.assert_nothing_leaked()
        finally:
            super().tearDown()

    # --- people and goods ---------------------------------------------------

    def product(self, *, price="250.00", stock=50):
        product = self.make_product(price=price, stock=stock)
        self.initial_stock[product.id] = stock
        return product

    def buyer(self) -> Buyer:
        user = self.make_user()
        return Buyer(user, self.make_address(user))

    def headers(self, buyer: Buyer):
        return {"Authorization": f"Bearer {create_access_token(buyer.id, buyer.role)}"}

    # --- HTTP, as the browser sees it ------------------------------------------

    def call(self, method, url, *, client=None, **kwargs):
        response = (client or self.client).request(method, url, **kwargs)
        self.transcript.append(response.text)
        self.transcript.append(str(dict(response.headers)))
        return response

    def place(self, buyer, product, qty=2, *, coupon=None, key=None, client=None, expected_total=None, fill=True):
        if fill:  # threads must not share self.db: fill the carts first, then place with fill=False
            self.fill_cart(buyer.user, [(product, qty)], coupon=coupon)
        body = {"shipping_address_id": str(buyer.address_id)}
        if expected_total is not None:
            body["expected_total"] = str(expected_total)
        return self.call("POST", "/api/orders", client=client, json=body,
                         headers={**self.headers(buyer), "Idempotency-Key": key or f"e2e-{uuid.uuid4()}"})

    def _next(self):
        self._n += 1
        return self._n

    def order(self, buyer, product, qty=2, **kwargs):
        """Place an order and return its JSON; it must have been created."""
        response = self.place(buyer, product, qty, **kwargs)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["data"]

    def get(self, buyer, order_id, client=None):
        response = self.call("GET", f"/api/orders/{order_id}", client=client, headers=self.headers(buyer))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def start(self, buyer, order_id, client=None, **kwargs):
        return self.call("POST", f"/api/orders/{order_id}/payment", client=client, headers=self.headers(buyer), **kwargs)

    def begin(self, buyer, order_id):
        """Start paying; returns the intent the browser would hand to Razorpay."""
        response = self.start(buyer, order_id)
        self.assertIn(response.status_code, (200, 201), response.text)
        return response.json()["data"]

    def card_pays(self, intent, pay_id, *, amount_paise=None, status="captured"):
        """Razorpay takes the money (as far as the fake gateway is concerned) and
        returns what Checkout reports to the browser."""
        self.gateway.register_payment(pay_id, order_id=intent["razorpay_order_id"],
                                      amount_paise=amount_paise or intent["amount_paise"], status=status)
        signature = sign(intent["razorpay_order_id"], pay_id)
        self.signatures.append(signature)
        return {"razorpay_order_id": intent["razorpay_order_id"], "razorpay_payment_id": pay_id, "razorpay_signature": signature}

    def verify(self, buyer, order_id, reported, client=None):
        return self.call("POST", f"/api/orders/{order_id}/payment/verify", client=client,
                         headers=self.headers(buyer), json=reported)

    def cancel(self, buyer, order_id, client=None):
        return self.call("POST", f"/api/orders/{order_id}/cancel", client=client, headers=self.headers(buyer))

    def webhook(self, intent, pay_id, *, event="payment.captured", event_id=None, amount_paise=None, currency="INR",
                client=None, signature=None):
        raw = make_body(event, pid=pay_id, rz=intent["razorpay_order_id"],
                        amount=amount_paise or intent["amount_paise"], currency=currency)
        sig = webhook_signature(WEBHOOK_SECRET, raw) if signature is None else signature
        self.signatures.append(sig)
        return self.call("POST", "/api/payments/webhook", client=client, content=raw, headers={
            "Content-Type": "application/json", "X-Razorpay-Signature": sig,
            "X-Razorpay-Event-Id": event_id or f"evt_{uuid.uuid4().hex}"})

    def expire(self, minutes=31):
        return run_expiry_pass(new_session, clock=lambda: datetime.now(timezone.utc) + timedelta(minutes=minutes))

    def thread_client(self):
        return TestClient(self.app)

    # --- fresh readers ----------------------------------------------------------

    def db_order(self, order_id):
        with new_session() as s:
            row = s.get(Order, uuid.UUID(str(order_id)))
            s.expunge(row)
            return row

    def payments_of(self, order_id):
        with new_session() as s:
            rows = s.query(Payment).filter(Payment.order_id == uuid.UUID(str(order_id))).order_by(Payment.created_at).all()
            s.expunge_all()
            return rows

    def event_count(self):
        with new_session() as s:
            return s.query(PaymentWebhookEvent).count()

    def order_count(self):
        with new_session() as s:
            return s.query(Order).count()

    # --- the books ----------------------------------------------------------------

    def assert_payment_books(self):
        """What must be true of every order and payment, whatever happened."""
        with new_session() as s:
            orders = s.query(Order).all()
            captured_money = Decimal("0")
            paid_money = Decimal("0")
            for o in orders:
                label = f"order {o.order_number}"
                pays = list(o.payments)
                paid = o.payment_status == OrderPaymentStatus.PAID
                self.assertFalse(paid and o.status == OrderStatus.CANCELLED, f"{label}: paid AND cancelled")
                self.assertEqual(paid, o.status == OrderStatus.CONFIRMED, f"{label}: paid / confirmed out of step")
                self.assertEqual(paid, o.inventory_state == OrderInventoryState.CONSUMED, f"{label}: paid / stock consumed out of step")
                for p in pays:
                    self.assertEqual(p.amount, o.total_amount, f"{label}: a payment for a different amount than the order's total")
                self.assertLessEqual(sum(1 for p in pays if p.status in OPEN_STATUSES), 1, f"{label}: two open payments")
                if o.status == OrderStatus.CANCELLED:
                    self.assertEqual(o.payment_status, OrderPaymentStatus.PENDING, f"{label}: a cancelled order claims a payment state")
                    self.assertEqual(o.inventory_state, OrderInventoryState.RELEASED)
                    self.assertFalse([p for p in pays if p.status in OPEN_STATUSES], f"{label}: cancelled but a payment is still open")
                counted = [p for p in pays if p.status in (S.CAPTURED, S.REFUNDED) and not p.refund_required]
                if paid:
                    self.assertEqual(len(counted), 1, f"{label}: a paid order needs exactly one payment that paid it")
                    paid_money += o.total_amount
                    captured_money += counted[0].amount
                else:
                    self.assertEqual(counted, [], f"{label}: money counted as paying an order that is not paid")
                for p in pays:
                    self.assertEqual(p.paid_at is not None, p.status in (S.CAPTURED, S.REFUNDED), f"{label}: paid_at out of step")
                    if p.refund_required:
                        self.assertEqual(p.status, S.CAPTURED, f"{label}: refund flag on a payment that took no money")
            self.assertEqual(captured_money, paid_money, "money counted != money owed by paid orders")
            # physical stock: only paid orders ever reduced it
            for pid, start in self.initial_stock.items():
                inv = s.query(Inventory).filter(Inventory.product_id == pid).one()
                sold = sum(i.quantity for o in orders if o.inventory_state == OrderInventoryState.CONSUMED
                           for i in o.items if i.product_id == pid)
                self.assertEqual(inv.quantity, start - sold, "physical stock != starting stock - units of paid orders")
                self.assertGreaterEqual(inv.quantity - inv.reserved_quantity, 0, "oversold")
            ids = [e.event_id for e in s.query(PaymentWebhookEvent).all()]
            self.assertEqual(len(ids), len(set(ids)), "a webhook event was recorded twice")

    def audit(self):
        self.assert_books_balance()
        self.assert_payment_books()

    def assert_nothing_leaked(self):
        needles = [FAKE_SECRET, WEBHOOK_SECRET, EMAIL, PHONE, *self.signatures]
        haystacks = [("a response", t) for t in self.transcript] + [("a log line", t) for t in self.logs.lines]
        for needle in needles:
            if len(needle.strip()) < 8:  # a blank/short test input is not a secret
                continue
            for where, text in haystacks:
                self.assertNotIn(needle, text, f"{needle[:12]}... leaked into {where}")

    def stock_of(self, product):
        return self.stock(product)


# ---------------------------------------------------------------------------
# A. the customer's own journey
# ---------------------------------------------------------------------------


class CustomerJourneyTests(JourneyCase):
    def test_checkout_then_pay_in_the_browser_is_the_happy_path(self):
        buyer, product = self.buyer(), self.product()
        order = self.order(buyer, product, 2)
        self.assertEqual((order["status"], order["payment_status"], order["can_pay"], order["can_cancel"]),
                         ("pending", "pending", True, True))
        self.assertIsNotNone(order["expires_at"])
        self.assertEqual(self.stock_of(product), (50, 2))  # reserved at checkout, not sold

        intent = self.begin(buyer, order["id"])
        self.assertEqual(intent["amount_paise"], paise(order["totals"]["total"]))  # the SERVER's amount, to the paisa
        self.assertEqual((intent["razorpay_key_id"], intent["currency"]), (self.gateway.key_id, "INR"))
        self.assertEqual(self.get(buyer, order["id"])["status"], "pending")  # starting is not paying

        reported = self.card_pays(intent, "pay_JRN1")
        response = self.verify(buyer, order["id"], reported)
        self.assertEqual(response.status_code, 200, response.text)

        paid = self.get(buyer, order["id"])
        self.assertEqual((paid["status"], paid["payment_status"], paid["can_pay"], paid["can_cancel"]), ("confirmed", "paid", False, False))
        self.assertEqual(paid["payment"], {"last_attempt": "captured", "refund_pending": False})
        self.assertEqual(self.stock_of(product), (48, 0))  # now sold
        self.audit()

    def test_a_tab_closed_after_paying_is_settled_by_the_webhook_alone(self):
        buyer, product = self.buyer(), self.product()
        order = self.order(buyer, product, 1)
        intent = self.begin(buyer, order["id"])
        self.card_pays(intent, "pay_JRN2")  # the customer paid, then closed the tab: no verify call ever comes

        self.assertEqual(self.webhook(intent, "pay_JRN2", event_id="evt_close_tab").status_code, 200)
        paid = self.get(buyer, order["id"])
        self.assertEqual((paid["status"], paid["payment_status"]), ("confirmed", "paid"))
        self.assertEqual(self.stock_of(product), (49, 0))

        # ...and when the browser's verify finally does arrive, it changes nothing
        again = self.verify(buyer, order["id"], self.card_pays(intent, "pay_JRN2"))
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["data"]["payment_status"], "paid")
        self.assertEqual(self.stock_of(product), (49, 0))
        self.assertEqual(len([p for p in self.payments_of(order["id"]) if p.status == S.CAPTURED]), 1)
        self.audit()

    def test_closing_the_popup_and_coming_back_resumes_the_same_payment_on_the_same_order(self):
        buyer, product = self.buyer(), self.product()
        order = self.order(buyer, product, 1)
        first = self.start(buyer, order["id"])
        self.assertEqual(first.status_code, 201)
        again = self.start(buyer, order["id"])  # "Try payment again"
        self.assertEqual(again.status_code, 200)
        self.assertEqual(first.json()["data"]["razorpay_order_id"], again.json()["data"]["razorpay_order_id"])
        self.assertEqual(len(self.gateway.calls), 1)  # one Razorpay order, not two
        self.assertEqual(self.order_count(), 1)  # never a second Pramanika order

        intent = again.json()["data"]
        self.assertEqual(self.verify(buyer, order["id"], self.card_pays(intent, "pay_JRN3")).status_code, 200)
        self.assertEqual(self.get(buyer, order["id"])["payment_status"], "paid")
        self.audit()

    def test_a_declined_card_leaves_the_order_payable_and_a_second_try_pays_it(self):
        buyer, product = self.buyer(), self.product()
        order = self.order(buyer, product, 1)
        intent = self.begin(buyer, order["id"])
        self.assertEqual(self.webhook(intent, "pay_JRN4F", event="payment.failed").status_code, 200)

        after = self.get(buyer, order["id"])
        self.assertEqual((after["status"], after["payment_status"], after["can_pay"], after["payment"]["last_attempt"]),
                         ("pending", "pending", True, "failed"))
        self.assertEqual(self.stock_of(product), (50, 1))  # the reservation is untouched by a failed card

        retry = self.begin(buyer, order["id"])  # a NEW Razorpay order for the failed attempt's replacement
        self.assertNotEqual(retry["razorpay_order_id"], intent["razorpay_order_id"])
        self.assertEqual(self.verify(buyer, order["id"], self.card_pays(retry, "pay_JRN4")).status_code, 200)
        self.assertEqual(sorted(p.status.value for p in self.payments_of(order["id"])), ["captured", "failed"])
        self.assertEqual(self.stock_of(product), (49, 0))
        self.audit()

    def test_razorpay_saying_success_without_a_captured_payment_does_not_pay_the_order(self):
        buyer, product = self.buyer(), self.product()
        order = self.order(buyer, product, 1)
        intent = self.begin(buyer, order["id"])
        reported = self.card_pays(intent, "pay_JRN5", status="authorized")  # the bank has not captured yet
        response = self.verify(buyer, order["id"], reported)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual((data["payment_status"], data["status"]), ("pending", "pending"))

        self.card_pays(intent, "pay_JRN5")  # ...and later the capture happens
        self.assertEqual(self.webhook(intent, "pay_JRN5").status_code, 200)
        self.assertEqual(self.get(buyer, order["id"])["payment_status"], "paid")
        self.audit()


# ---------------------------------------------------------------------------
# B / D. the same news arriving more than once, or all at once
# ---------------------------------------------------------------------------


class SimultaneousAndDuplicateTests(JourneyCase):
    def test_browser_verify_and_webhook_together_pay_the_order_exactly_once(self):
        buyer, product = self.buyer(), self.product()
        for n in range(6):
            with self.subTest(round=n):
                order = self.order(buyer, product, 1)
                intent = self.begin(buyer, order["id"])
                reported = self.card_pays(intent, f"pay_B{n}")
                results = run_concurrently([
                    lambda: self.verify(buyer, order["id"], reported, client=self.thread_client()).status_code,
                    lambda: self.webhook(intent, f"pay_B{n}", client=self.thread_client()).status_code,
                ])
                self.assertEqual([r[0] for r in results], ["ok", "ok"], results)
                self.assertEqual([r[1] for r in results], [200, 200])
                self.assertEqual(self.get(buyer, order["id"])["payment_status"], "paid")
                captured = [p for p in self.payments_of(order["id"]) if p.status == S.CAPTURED]
                self.assertEqual((len(captured), captured[0].refund_required), (1, False))
        self.assertEqual(self.stock_of(product), (44, 0))  # six units sold, none twice
        self.audit()

    def test_one_webhook_delivered_many_times_at_once_is_processed_once(self):
        buyer, product = self.buyer(), self.product()
        order = self.order(buyer, product, 3)
        intent = self.begin(buyer, order["id"])
        self.card_pays(intent, "pay_D1")
        results = run_concurrently([
            (lambda: self.webhook(intent, "pay_D1", event_id="evt_dup_same", client=self.thread_client()))
            for _ in range(8)
        ])
        self.assertEqual({r[0] for r in results}, {"ok"}, results)
        responses = [r[1] for r in results]
        self.assertEqual({r.status_code for r in responses}, {200})
        self.assertEqual(sorted(r.json()["message"] for r in responses).count("Event received."), 1)
        self.assertEqual(self.event_count(), 1)
        self.assertEqual(self.stock_of(product), (47, 0))
        self.audit()

    def test_the_same_capture_under_different_event_ids_and_event_types_pays_once(self):
        buyer, product = self.buyer(), self.product()
        order = self.order(buyer, product, 1)
        intent = self.begin(buyer, order["id"])
        self.card_pays(intent, "pay_D2")
        for event, event_id in (("payment.authorized", "e1"), ("payment.captured", "e2"), ("payment.captured", "e3"), ("order.paid", "e4")):
            self.assertEqual(self.webhook(intent, "pay_D2", event=event, event_id=event_id).status_code, 200)
        self.assertEqual(len(self.payments_of(order["id"])), 1)
        self.assertEqual(self.stock_of(product), (49, 0))
        self.audit()

    def test_the_browser_verifying_five_times_at_once_pays_once(self):
        buyer, product = self.buyer(), self.product()
        order = self.order(buyer, product, 1)
        intent = self.begin(buyer, order["id"])
        reported = self.card_pays(intent, "pay_D3")
        results = run_concurrently([
            (lambda: self.verify(buyer, order["id"], reported, client=self.thread_client()).status_code) for _ in range(5)
        ])
        self.assertEqual([r for r in results], [("ok", 200)] * 5)
        self.assertEqual(self.stock_of(product), (49, 0))
        self.audit()

    def test_a_double_click_on_pay_creates_one_razorpay_order(self):
        buyer, product = self.buyer(), self.product()
        order = self.order(buyer, product, 1)
        results = run_concurrently([
            (lambda: self.start(buyer, order["id"], client=self.thread_client()).status_code) for _ in range(6)
        ])
        self.assertEqual({r[0] for r in results}, {"ok"}, results)
        self.assertEqual(sorted(r[1] for r in results).count(201), 1)
        self.assertEqual(len(self.gateway.calls), 1)
        self.assertEqual(len(self.payments_of(order["id"])), 1)
        self.audit()

    def test_a_double_submit_of_checkout_makes_one_order_and_reserves_once(self):
        buyer, product = self.buyer(), self.product()
        self.fill_cart(buyer.user, [(product, 2)])
        key = "e2e-double-submit-key"
        results = run_concurrently([(lambda: self.place(buyer, product, 2, key=key, client=self.thread_client(), fill=False).status_code) for _ in range(5)])
        self.assertEqual({r[0] for r in results}, {"ok"}, results)
        self.assertEqual(sorted(r[1] for r in results), [200, 200, 200, 200, 201])
        self.assertEqual(self.order_count(), 1)
        self.assertEqual(self.stock_of(product), (50, 2))
        self.audit()


# ---------------------------------------------------------------------------
# C. money after the order closed
# ---------------------------------------------------------------------------


class LatePaymentTests(JourneyCase):
    def closed_order(self, how, *, coupon=None, pay_id="pay_C1"):
        buyer, product = self.buyer(), self.product()
        order = self.order(buyer, product, 2, coupon=coupon)
        intent = self.begin(buyer, order["id"])
        self.card_pays(intent, pay_id)  # the popup is still open in another tab
        if how == "customer":
            self.assertEqual(self.cancel(buyer, order["id"]).status_code, 200)
        else:
            self.expire()
        return buyer, product, order, intent

    def test_after_expiry_a_late_capture_is_recorded_and_flagged_but_never_pays_the_order(self):
        coupon = self.make_coupon(usage_limit=3)
        buyer, product, order, intent = self.closed_order("expiry", coupon=coupon)
        self.assertEqual(self.stock_of(product), (50, 0))  # stock went back when it expired
        self.assertEqual(self.used_count(coupon), 0)  # and so did the coupon use

        self.assertEqual(self.webhook(intent, "pay_C1").status_code, 200)  # a 2xx: retrying cannot change the answer
        view = self.get(buyer, order["id"])
        self.assertEqual((view["status"], view["payment_status"], view["cancellation_reason"], view["can_pay"]),
                         ("cancelled", "pending", "expired", False))
        self.assertTrue(view["payment"]["refund_pending"])
        payment = self.payments_of(order["id"])[0]
        self.assertEqual((payment.status, payment.refund_required), (S.CAPTURED, True))
        self.assertEqual(self.stock_of(product), (50, 0))  # not sold, not re-reserved
        self.assertEqual(self.used_count(coupon), 0)  # not restored a second time, not used again
        self.audit()

    def test_after_a_customer_cancel_a_late_capture_is_flagged_the_same_way(self):
        buyer, product, order, intent = self.closed_order("customer")
        self.assertEqual(self.webhook(intent, "pay_C1").status_code, 200)
        view = self.get(buyer, order["id"])
        self.assertEqual((view["status"], view["cancellation_reason"], view["payment"]["refund_pending"]), ("cancelled", "customer", True))
        self.assertEqual(self.stock_of(product), (50, 0))
        self.audit()

    def test_the_browser_verifying_a_late_payment_is_refused_and_changes_nothing_further(self):
        for how in ("customer", "expiry"):
            with self.subTest(how=how):
                buyer, product, order, intent = self.closed_order(how, pay_id="pay_C2" + how)
                reported = self.card_pays(intent, "pay_C2" + how)
                response = self.verify(buyer, order["id"], reported)
                self.assertEqual(response.status_code, 409, response.text)
                before = [(p.status, p.refund_required) for p in self.payments_of(order["id"])]
                self.assertEqual(before, [(S.CAPTURED, True)])  # the money is on record, flagged
                self.assertEqual(self.verify(buyer, order["id"], reported).status_code, 409)  # repeating is harmless
                self.assertEqual([(p.status, p.refund_required) for p in self.payments_of(order["id"])], before)
                self.assertEqual(self.get(buyer, order["id"])["payment_status"], "pending")
        self.audit()

    def test_a_late_capture_delivered_twice_is_recorded_once(self):
        buyer, product, order, intent = self.closed_order("expiry")
        self.webhook(intent, "pay_C1", event_id="evt_late")
        self.webhook(intent, "pay_C1", event_id="evt_late")
        self.webhook(intent, "pay_C1", event_id="evt_late_2")
        self.assertEqual([(p.status, p.refund_required) for p in self.payments_of(order["id"])], [(S.CAPTURED, True)])
        self.audit()

    def test_closed_orders_cannot_start_a_payment_and_running_expiry_again_does_nothing(self):
        buyer, product, order, intent = self.closed_order("expiry")
        self.assertEqual(self.start(buyer, order["id"]).status_code, 409)
        self.expire(60)
        self.assertEqual(self.stock_of(product), (50, 0))
        self.assertEqual(self.get(buyer, order["id"])["status"], "cancelled")
        self.audit()

    def test_a_paid_order_is_not_expired_and_not_cancellable(self):
        buyer, product = self.buyer(), self.product()
        order = self.order(buyer, product, 1)
        intent = self.begin(buyer, order["id"])
        self.verify(buyer, order["id"], self.card_pays(intent, "pay_C3"))
        self.expire(600)  # far past any deadline
        self.assertEqual(self.get(buyer, order["id"])["status"], "confirmed")
        self.assertEqual(self.cancel(buyer, order["id"]).status_code, 409)
        self.assertEqual(self.stock_of(product), (49, 0))
        self.audit()

    def test_a_second_payment_on_an_already_paid_order_is_flagged_not_counted(self):
        buyer, product = self.buyer(), self.product()
        order = self.order(buyer, product, 1)
        first = self.begin(buyer, order["id"])
        self.verify(buyer, order["id"], self.card_pays(first, "pay_C4a"))
        # the customer had a second tab open with its own Razorpay order, and paid there too
        with new_session() as s:
            o = s.get(Order, uuid.UUID(order["id"]))
            s.add(Payment(order_id=o.id, payment_gateway="razorpay", gateway_order_id="order_SECONDTAB1",
                          amount=o.total_amount, currency="INR", status=S.INITIATED))
            s.commit()
        second = {"razorpay_order_id": "order_SECONDTAB1", "amount_paise": first["amount_paise"]}
        self.card_pays(second, "pay_C4b")
        self.assertEqual(self.webhook(second, "pay_C4b").status_code, 200)
        flags = sorted((p.gateway_order_id == "order_SECONDTAB1", p.refund_required) for p in self.payments_of(order["id"]))
        self.assertEqual(flags, [(False, False), (True, True)])
        self.assertEqual(self.stock_of(product), (49, 0))  # sold once
        self.audit()


# ---------------------------------------------------------------------------
# E. out of order, wrong, forged, foreign
# ---------------------------------------------------------------------------


class MessyEventTests(JourneyCase):
    def setup_order(self, qty=1):
        buyer, product = self.buyer(), self.product()
        order = self.order(buyer, product, qty)
        return buyer, product, order, self.begin(buyer, order["id"])

    def test_a_late_failure_never_un_pays_a_captured_payment(self):
        buyer, product, order, intent = self.setup_order()
        self.webhook(intent, "pay_E1", event="payment.captured")
        self.webhook(intent, "pay_E1", event="payment.failed")
        self.webhook(intent, "pay_E1", event="payment.authorized")
        self.assertEqual(self.get(buyer, order["id"])["payment_status"], "paid")
        self.assertEqual(self.payments_of(order["id"])[0].status, S.CAPTURED)
        self.assertEqual(self.stock_of(product), (49, 0))
        self.audit()

    def test_a_capture_after_a_failure_on_the_same_razorpay_order_pays(self):
        buyer, product, order, intent = self.setup_order()
        self.webhook(intent, "pay_E2a", event="payment.failed")
        self.assertEqual(self.get(buyer, order["id"])["payment"]["last_attempt"], "failed")
        self.webhook(intent, "pay_E2b", event="payment.captured")  # the customer retried inside the same popup
        self.assertEqual(self.get(buyer, order["id"])["payment_status"], "paid")
        self.audit()

    def test_authorized_then_captured_pays_only_at_capture(self):
        buyer, product, order, intent = self.setup_order()
        self.webhook(intent, "pay_E3", event="payment.authorized")
        mid = self.get(buyer, order["id"])
        self.assertEqual((mid["payment_status"], mid["payment"]["last_attempt"], mid["can_pay"]), ("pending", "authorized", True))
        self.webhook(intent, "pay_E3", event="payment.captured")
        self.assertEqual(self.get(buyer, order["id"])["payment_status"], "paid")
        self.audit()

    def test_a_capture_for_the_wrong_amount_or_currency_never_pays_an_order(self):
        buyer, product, order, intent = self.setup_order(qty=2)
        for kwargs in (dict(amount_paise=100), dict(amount_paise=intent["amount_paise"] + 1), dict(currency="USD")):
            with self.subTest(**kwargs):
                self.assertEqual(self.webhook(intent, "pay_E4", **kwargs).status_code, 200)
                self.assertEqual(self.get(buyer, order["id"])["payment_status"], "pending")
        self.assertEqual(self.stock_of(product), (50, 2))
        self.audit()

    def test_the_browser_cannot_pay_for_a_different_amount_either(self):
        buyer, product, order, intent = self.setup_order(qty=2)
        reported = self.card_pays(intent, "pay_E5", amount_paise=100)  # Razorpay says only Rs 1 was taken
        self.assertNotEqual(self.verify(buyer, order["id"], reported).status_code, 200)
        self.assertEqual(self.get(buyer, order["id"])["payment_status"], "pending")
        self.audit()

    def test_forged_and_unsigned_webhooks_change_nothing(self):
        buyer, product, order, intent = self.setup_order()
        self.card_pays(intent, "pay_E6")
        for signature in ("0" * 64, "", "not-hex", webhook_signature("some-other-secret", make_body())):
            with self.subTest(signature=signature[:10]):
                self.assertEqual(self.webhook(intent, "pay_E6", signature=signature or " ").status_code, 400)
        self.assertEqual(self.get(buyer, order["id"])["payment_status"], "pending")
        self.assertEqual(self.event_count(), 0)
        self.audit()

    def test_a_tampered_checkout_signature_is_refused(self):
        buyer, product, order, intent = self.setup_order()
        reported = self.card_pays(intent, "pay_E7")
        reported["razorpay_signature"] = "0" * 64
        self.assertEqual(self.verify(buyer, order["id"], reported).status_code, 400)
        reported = self.card_pays(intent, "pay_E7")
        reported["razorpay_payment_id"] = "pay_E7other"  # a valid signature for a DIFFERENT payment id
        self.assertEqual(self.verify(buyer, order["id"], reported).status_code, 400)
        self.assertEqual(self.get(buyer, order["id"])["payment_status"], "pending")
        self.audit()

    def test_another_customer_cannot_see_start_verify_or_cancel_my_order(self):
        buyer, product, order, intent = self.setup_order()
        thief = self.buyer()
        reported = self.card_pays(intent, "pay_E8")
        self.assertEqual(self.call("GET", f"/api/orders/{order['id']}", headers=self.headers(thief)).status_code, 404)
        self.assertEqual(self.start(thief, order["id"]).status_code, 404)
        self.assertEqual(self.verify(thief, order["id"], reported).status_code, 404)
        self.assertEqual(self.cancel(thief, order["id"]).status_code, 404)
        self.assertEqual(self.get(buyer, order["id"])["status"], "pending")
        self.audit()

    def test_no_login_means_no_payment_endpoints_but_the_webhook_needs_none(self):
        buyer, product, order, intent = self.setup_order()
        self.assertEqual(self.call("POST", f"/api/orders/{order['id']}/payment").status_code, 401)
        self.assertEqual(self.call("POST", f"/api/orders/{order['id']}/payment/verify", json={}).status_code, 401)
        self.card_pays(intent, "pay_E9")
        self.assertEqual(self.webhook(intent, "pay_E9").status_code, 200)

    def test_events_for_razorpay_orders_we_never_created_are_acknowledged_and_ignored(self):
        buyer, product, order, intent = self.setup_order()
        stranger = {"razorpay_order_id": "order_NOTOURS9", "amount_paise": 100}
        self.assertEqual(self.webhook(stranger, "pay_E10").status_code, 200)
        self.assertEqual(self.get(buyer, order["id"])["payment_status"], "pending")
        self.assertEqual(self.order_count(), 1)

    def test_the_client_cannot_choose_the_amount_when_starting_a_payment(self):
        buyer, product = self.buyer(), self.product(price="333.33")
        order = self.order(buyer, product, 3)
        response = self.start(buyer, order["id"], json={"amount": 1, "amount_paise": 100, "currency": "USD"})
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()["data"]
        self.assertEqual((data["amount_paise"], data["currency"]), (paise(order["totals"]["total"]), "INR"))
        self.assertEqual(self.gateway.calls[0]["amount_paise"], paise(order["totals"]["total"]))


# ---------------------------------------------------------------------------
# Phase 6 behaviour, still intact with payments in the picture
# ---------------------------------------------------------------------------


class Phase6StillHoldsTests(JourneyCase):
    def test_checkout_replay_cancel_and_totals_behave_exactly_as_before(self):
        coupon = self.make_coupon(usage_limit=2)
        buyer, product = self.buyer(), self.product(price="333.33")
        first = self.place(buyer, product, 3, coupon=coupon, key="p6-replay-key-0001")
        self.assertEqual(first.status_code, 201)
        replay = self.place(buyer, product, 3, coupon=coupon, key="p6-replay-key-0001")
        self.assertEqual((replay.status_code, replay.json()["data"]["id"]), (200, first.json()["data"]["id"]))
        self.assertEqual(self.order_count(), 1)
        self.assertEqual(self.stock_of(product), (50, 3))
        self.assertEqual(self.used_count(coupon), 1)

        t = first.json()["data"]["totals"]
        d = lambda k: Decimal(str(t[k]))
        self.assertEqual(d("subtotal") - d("discount"), d("taxable_amount"))
        self.assertEqual(d("taxable_amount") + d("gst") + d("delivery_charge"), d("total"))
        self.assertEqual(Decimal(str(t["gst_rate"])), self.db_order(first.json()["data"]["id"]).gst_rate)

        oid = first.json()["data"]["id"]
        self.begin(buyer, oid)  # a payment was started, then the customer changes their mind
        cancelled = self.cancel(buyer, oid)
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(self.cancel(buyer, oid).status_code, 200)  # safe to repeat
        data = cancelled.json()["data"]
        self.assertEqual((data["status"], data["payment_status"], data["cancellation_reason"]), ("cancelled", "pending", "customer"))
        self.assertEqual(self.stock_of(product), (50, 0))
        self.assertEqual(self.used_count(coupon), 0)  # restored once, not twice
        self.assertEqual([p.status for p in self.payments_of(oid)], [S.EXPIRED])
        self.audit()

    def test_a_stale_expected_total_is_still_refused_with_nothing_reserved(self):
        buyer, product = self.buyer(), self.product()
        response = self.place(buyer, product, 2, expected_total="1.00")
        self.assertEqual(response.status_code, 409)
        self.assertEqual((self.order_count(), self.stock_of(product)), (0, (50, 0)))

    def test_order_snapshots_do_not_change_when_the_product_does(self):
        buyer, product = self.buyer(), self.product(price="100.00")
        order = self.order(buyer, product, 1)
        with new_session() as s:
            from app.models import Product

            s.query(Product).filter(Product.id == product.id).update({Product.price: Decimal("999.00"), Product.name: "Renamed"})
            s.commit()
        intent = self.begin(buyer, order["id"])
        self.assertEqual(intent["amount_paise"], paise(order["totals"]["total"]))  # the order's own total, not today's price
        shown = self.get(buyer, order["id"])
        self.assertEqual(shown["items"][0]["unit_price"], order["items"][0]["unit_price"])
        self.assertNotEqual(shown["items"][0]["product_name"], "Renamed")

    def test_scarce_stock_is_never_oversold_even_with_payments_racing_new_checkouts(self):
        product = self.product(price="100.00", stock=3)
        buyers = [self.buyer() for _ in range(6)]
        for b in buyers:
            self.fill_cart(b.user, [(product, 1)])
        results = run_concurrently([
            (lambda b=b: self.place(b, product, 1, client=self.thread_client(), fill=False).status_code) for b in buyers
        ])
        statuses = sorted(r[1] for r in results if r[0] == "ok")
        self.assertEqual(statuses.count(201), 3)
        self.assertEqual(self.stock_of(product), (3, 3))
        self.audit()


# ---------------------------------------------------------------------------
# F. everything racing for one order
# ---------------------------------------------------------------------------


class FourWayRaceTests(JourneyCase):
    def test_verify_webhook_cancel_and_expiry_together_leave_one_consistent_story(self):
        coupon = self.make_coupon(usage_limit=50)
        product = self.product(price="120.00", stock=200)
        outcomes = {"paid": 0, "closed": 0}
        for n in range(10):
            with self.subTest(round=n):
                buyer = self.buyer()
                order = self.order(buyer, product, 2, coupon=coupon)
                intent = self.begin(buyer, order["id"])
                reported = self.card_pays(intent, f"pay_F{n}")
                results = run_concurrently([
                    lambda: self.verify(buyer, order["id"], reported, client=self.thread_client()).status_code,
                    lambda: self.webhook(intent, f"pay_F{n}", client=self.thread_client()).status_code,
                    lambda: self.cancel(buyer, order["id"], client=self.thread_client()).status_code,
                    lambda: (self.expire(), None)[1],
                ])
                for kind, value in results:
                    self.assertEqual(kind, "ok", f"a racing request blew up: {value!r}")
                for status in (r[1] for r in results[:3]):
                    self.assertLess(status, 500)
                final = self.db_order(order["id"])
                self.assertTrue((final.payment_status == OrderPaymentStatus.PAID) != (final.status == OrderStatus.CANCELLED),
                                "an order must end up exactly one of paid / cancelled")
                outcomes["paid" if final.payment_status == OrderPaymentStatus.PAID else "closed"] += 1
                self.audit()
        self.assertEqual(sum(outcomes.values()), 10)

    def test_expiry_sweeps_racing_each_other_and_the_customer_release_each_order_once(self):
        product = self.product(price="80.00", stock=100)
        coupon = self.make_coupon(usage_limit=30)
        orders = []
        for _ in range(6):
            buyer = self.buyer()
            order = self.order(buyer, product, 2, coupon=coupon)
            self.begin(buyer, order["id"])
            orders.append((buyer, order))
        jobs = [lambda: self.expire() for _ in range(3)]
        jobs += [(lambda b=b, o=o: self.cancel(b, o["id"], client=self.thread_client()).status_code) for b, o in orders[:3]]
        results = run_concurrently(jobs)
        for kind, value in results:
            self.assertEqual(kind, "ok", repr(value))
        self.assertEqual(self.stock_of(product), (100, 0))
        self.assertEqual(self.used_count(coupon), 0)
        self.audit()


# ---------------------------------------------------------------------------
# G. seeded random mixes
# ---------------------------------------------------------------------------


class RandomisedJourneyTests(JourneyCase):
    ACTIONS = ("verify", "verify", "captured", "captured", "failed", "authorized", "paid_event", "cancel", "expire", "restart", "dup_captured")

    def run_seed(self, seed, orders=8):
        rng = random.Random(seed)
        coupon = self.make_coupon(usage_limit=orders - 2)
        products = [self.product(price=p, stock=60) for p in ("99.00", "249.50", "333.33")]
        plans = []
        for i in range(orders):
            buyer = self.buyer()
            product = rng.choice(products)
            order = self.order(buyer, product, rng.randint(1, 4), coupon=coupon if rng.random() < 0.6 else None)
            intent = self.begin(buyer, order["id"])
            reported = self.card_pays(intent, f"pay_G{seed}_{i}")
            plans.append((buyer, order, intent, reported, f"pay_G{seed}_{i}"))

        jobs = []
        for buyer, order, intent, reported, pay_id in plans:
            for action in rng.sample(self.ACTIONS, rng.randint(2, 4)):
                jobs.append(self.job(action, buyer, order, intent, reported, pay_id))
        rng.shuffle(jobs)
        results = run_concurrently(jobs, timeout=120)
        for kind, value in results:
            self.assertEqual(kind, "ok", f"seed {seed}: a request blew up: {value!r}")
            if value is not None:
                self.assertLess(value, 500, f"seed {seed}: a server error")
        self.audit()
        return plans

    def job(self, action, buyer, order, intent, reported, pay_id):
        oid = order["id"]
        client = self.thread_client
        return {
            "verify": lambda: self.verify(buyer, oid, reported, client=client()).status_code,
            "captured": lambda: self.webhook(intent, pay_id, client=client()).status_code,
            "dup_captured": lambda: self.webhook(intent, pay_id, event_id=f"evt_dup_{pay_id}", client=client()).status_code,
            "failed": lambda: self.webhook(intent, pay_id, event="payment.failed", client=client()).status_code,
            "authorized": lambda: self.webhook(intent, pay_id, event="payment.authorized", client=client()).status_code,
            "paid_event": lambda: self.webhook(intent, pay_id, event="order.paid", client=client()).status_code,
            "cancel": lambda: self.cancel(buyer, oid, client=client()).status_code,
            "restart": lambda: self.start(buyer, oid, client=client()).status_code,
            "expire": lambda: (self.expire(), None)[1],
        }[action]

    def test_seeded_mixes_never_break_the_books(self):
        for seed in (11, 23, 47):
            with self.subTest(seed=seed):
                self.run_seed(seed)

    def test_every_order_ends_in_a_state_the_customer_can_understand(self):
        plans = self.run_seed(101)
        for buyer, order, *_ in plans:
            view = self.get(buyer, order["id"])
            if view["payment_status"] == "paid":
                self.assertEqual((view["status"], view["can_pay"], view["can_cancel"]), ("confirmed", False, False))
            elif view["status"] == "cancelled":
                self.assertIn(view["cancellation_reason"], ("customer", "expired"))
                self.assertEqual((view["can_pay"], view["can_cancel"]), (False, False))
            else:
                self.assertEqual((view["status"], view["payment_status"]), ("pending", "pending"))
