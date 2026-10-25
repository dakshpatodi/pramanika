"""Phase 7 / Milestone 6: the payment state machine's single writer (`payment_state`)."""

import itertools
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from app.models import Payment, PaymentTransactionStatus as S
from app.services.payment_rules import ALLOWED_TRANSITIONS
from app.services.payment_state import (
    MAX_FAILURE_REASON,
    IllegalPaymentTransitionError,
    close_open_payments,
    transition,
)
from tests.pg_support import PostgresTestCase, new_session

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def payment(status: S, **extra) -> Payment:
    values = dict(payment_gateway="razorpay", gateway_order_id="order_X", amount=Decimal("10.00"), currency="INR", status=status)
    if status in (S.CAPTURED, S.REFUNDED):
        values.update(gateway_payment_id="pay_X", paid_at=NOW)
    values.update(extra)
    return Payment(**values)


def moves(allowed: bool):
    return [(a, b) for a, b in itertools.product(S, S) if a != b and (b in ALLOWED_TRANSITIONS[a]) == allowed]


class TransitionTests(unittest.TestCase):
    def test_every_legal_move_happens_and_says_so(self):
        for current, new in moves(True):
            with self.subTest(move=f"{current.value}->{new.value}"):
                p = payment(current)
                self.assertTrue(transition(p, new, now=NOW, gateway_payment_id="pay_X"))
                self.assertEqual(p.status, new)

    def test_every_forbidden_move_raises_and_changes_nothing(self):
        forbidden = moves(False)
        self.assertGreaterEqual(len(forbidden), 20)
        for current, new in forbidden:
            with self.subTest(move=f"{current.value}->{new.value}"):
                p = payment(current)
                before = (p.status, p.paid_at, p.failure_reason, p.gateway_payment_id, p.gateway_signature)
                with self.assertRaises(IllegalPaymentTransitionError):
                    transition(p, new, now=NOW, gateway_payment_id="pay_Y", gateway_signature="sig", failure_reason="x")
                self.assertEqual((p.status, p.paid_at, p.failure_reason, p.gateway_payment_id, p.gateway_signature), before)

    def test_moving_to_the_status_it_already_has_is_a_quiet_no_op(self):
        for status in S:
            with self.subTest(status=status):
                p = payment(status, failure_reason="old")
                self.assertFalse(transition(p, status, now=NOW, gateway_payment_id="pay_Z", failure_reason="new"))
                self.assertEqual((p.status, p.failure_reason), (status, "old"))
                self.assertNotEqual(p.gateway_payment_id, "pay_Z")

    def test_captured_is_terminal_apart_from_refunded(self):
        for new in (S.INITIATED, S.AUTHORIZED, S.FAILED, S.EXPIRED):
            with self.subTest(new=new):
                p = payment(S.CAPTURED)
                with self.assertRaises(IllegalPaymentTransitionError):
                    transition(p, new, failure_reason="a late failed webhook")
                self.assertEqual(p.status, S.CAPTURED)
                self.assertIsNone(p.failure_reason)
        p = payment(S.CAPTURED)
        self.assertTrue(transition(p, S.REFUNDED))
        self.assertEqual(p.paid_at, NOW)  # a refund does not erase when the money arrived

    def test_refunded_is_final(self):
        for new in S:
            if new != S.REFUNDED:
                with self.subTest(new=new), self.assertRaises(IllegalPaymentTransitionError):
                    transition(payment(S.REFUNDED), new, now=NOW, gateway_payment_id="pay_X")

    def test_failed_and_expired_payments_can_still_be_captured_because_real_money_wins(self):
        for status in (S.FAILED, S.EXPIRED):
            p = payment(status, failure_reason="declined")
            self.assertTrue(transition(p, S.CAPTURED, now=NOW, gateway_payment_id="pay_L", gateway_signature="sig"))
            self.assertEqual((p.status, p.paid_at, p.gateway_payment_id, p.gateway_signature), (S.CAPTURED, NOW, "pay_L", "sig"))
            self.assertIsNone(p.failure_reason)  # a captured payment carries no failure

    def test_capturing_needs_the_time_and_the_payment_id(self):
        for kwargs in (dict(), dict(now=NOW), dict(gateway_payment_id="pay_X"), dict(now=NOW, gateway_payment_id="")):
            with self.subTest(kwargs=sorted(kwargs)):
                p = payment(S.INITIATED)
                with self.assertRaises(ValueError):
                    transition(p, S.CAPTURED, **kwargs)
                self.assertEqual((p.status, p.paid_at, p.gateway_payment_id), (S.INITIATED, None, None))

    def test_failed_and_expired_remember_why(self):
        for new in (S.FAILED, S.EXPIRED):
            p = payment(S.INITIATED)
            transition(p, new, failure_reason="Card declined")
            self.assertEqual(p.failure_reason, "Card declined")
            self.assertIsNone(p.paid_at)

    def test_a_long_reason_is_cut_to_fit(self):
        p = payment(S.INITIATED)
        transition(p, S.FAILED, failure_reason="x" * 5000)
        self.assertEqual(len(p.failure_reason), MAX_FAILURE_REASON)

    def test_authorizing_records_the_payment_id_but_is_not_paid(self):
        p = payment(S.INITIATED)
        transition(p, S.AUTHORIZED, gateway_payment_id="pay_A", gateway_signature="sig")
        self.assertEqual((p.status, p.gateway_payment_id, p.gateway_signature, p.paid_at), (S.AUTHORIZED, "pay_A", "sig", None))


class CloseOpenPaymentsTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.product = self.make_product()
        self.order = self.make_order(self.user, [(self.product, 1)])

    def close(self, order=None, reason="closed for test"):
        from app.repositories.payment_repository import PaymentRepository

        with new_session() as s:
            n = close_open_payments(PaymentRepository(s), (order or self.order).id, reason=reason)
            s.commit()
            return n

    def statuses(self, order=None):
        with new_session() as s:
            return {p.gateway_order_id: (p.status, p.failure_reason, p.paid_at is not None)
                    for p in s.query(Payment).filter(Payment.order_id == (order or self.order).id).all()}

    def test_it_closes_an_initiated_payment_and_remembers_why(self):
        self.make_payment(self.order, gateway_order_id="order_A")
        self.assertEqual(self.close(reason="cancelled"), 1)
        self.assertEqual(self.statuses()["order_A"], (S.EXPIRED, "cancelled", False))

    def test_it_closes_an_authorized_payment_too(self):
        self.make_payment(self.order, gateway_order_id="order_A", status=S.AUTHORIZED)
        self.assertEqual(self.close(), 1)
        self.assertEqual(self.statuses()["order_A"][0], S.EXPIRED)

    def test_it_never_touches_payments_that_are_not_open(self):
        self.make_payment(self.order, gateway_order_id="order_CAP", status=S.CAPTURED)
        self.make_payment(self.order, gateway_order_id="order_FAIL", status=S.FAILED, failure_reason="declined")
        self.make_payment(self.order, gateway_order_id="order_EXP", status=S.EXPIRED, failure_reason="older")
        self.make_payment(self.order, gateway_order_id="order_REF", status=S.REFUNDED)
        before = self.statuses()
        self.assertEqual(self.close(), 0)
        self.assertEqual(self.statuses(), before)

    def test_it_never_touches_another_orders_payments(self):
        other = self.make_order(self.user, [(self.product, 1)])
        self.make_payment(other, gateway_order_id="order_OTHER")
        self.make_payment(self.order, gateway_order_id="order_MINE")
        self.close()
        self.assertEqual(self.statuses(other)["order_OTHER"][0], S.INITIATED)
        self.assertEqual(self.statuses()["order_MINE"][0], S.EXPIRED)

    def test_it_is_idempotent(self):
        self.make_payment(self.order, gateway_order_id="order_A")
        self.assertEqual(self.close(reason="first"), 1)
        self.assertEqual(self.close(reason="second"), 0)
        self.assertEqual(self.statuses()["order_A"], (S.EXPIRED, "first", False))

    def test_it_waits_for_a_capture_in_progress_and_then_leaves_the_paid_payment_alone(self):
        """The row lock is what stops 'cancel' overwriting a capture that is committing right now."""
        import threading
        import time

        from app.repositories.payment_repository import PaymentRepository

        payment = self.make_payment(self.order, gateway_order_id="order_RACE")
        order_id, payment_id = self.order.id, payment.id
        capturing = new_session()
        row = capturing.query(Payment).filter(Payment.id == payment_id).with_for_update().one()
        finished = threading.Event()
        outcome = {}

        def closer():
            with new_session() as s:
                outcome["closed"] = close_open_payments(PaymentRepository(s), order_id, reason="cancelled")
                s.commit()
            finished.set()

        thread = threading.Thread(target=closer, daemon=True)
        thread.start()
        try:
            time.sleep(0.5)
            self.assertFalse(finished.is_set(), "closing did not wait for the row lock")
            transition(row, S.CAPTURED, now=NOW, gateway_payment_id="pay_RACE")
            capturing.commit()
        finally:
            capturing.close()
        thread.join(30)
        self.assertTrue(finished.is_set())
        self.assertEqual(outcome["closed"], 0)
        self.assertEqual(self.statuses()["order_RACE"], (S.CAPTURED, None, True))

    def test_an_order_with_no_payments_is_fine(self):
        self.assertEqual(self.close(), 0)


class SingleWriterHygieneTests(unittest.TestCase):
    def test_no_application_code_assigns_a_payment_status_except_the_state_module(self):
        """Every status change must go through payment_state.transition, or the
        state machine is a suggestion rather than a rule."""
        import re
        from pathlib import Path

        app_dir = Path(__file__).resolve().parent.parent / "app"
        pattern = re.compile(r"\b(?:payment|pay|p)\.status\s*=(?!=)|Payment\.status\s*:|\"status\"\s*:\s*PaymentTransactionStatus|Payment\.status:\s*S\.")
        offenders = []
        for path in app_dir.rglob("*.py"):
            if path.name in ("payment_state.py",):
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line) and not line.lstrip().startswith("#"):
                    offenders.append(f"{path.relative_to(app_dir)}:{number}: {line.strip()}")
        self.assertEqual(offenders, [])

    def test_the_pattern_would_catch_a_direct_assignment(self):
        import re

        pattern = re.compile(r"\b(?:payment|pay|p)\.status\s*=(?!=)")
        self.assertTrue(pattern.search("    payment.status = PaymentTransactionStatus.FAILED"))
        self.assertFalse(pattern.search("    if payment.status == S.FAILED:"))


if __name__ == "__main__":
    unittest.main()
