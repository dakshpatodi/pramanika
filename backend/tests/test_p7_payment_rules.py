"""Phase 7 / Milestone 2: payment state rules (pure - no database)."""

import unittest
from itertools import product

from app.models import PaymentTransactionStatus as S
from app.services.payment_rules import (
    ALLOWED_TRANSITIONS,
    OPEN_STATUSES,
    PAID_STATUSES,
    can_transition,
    is_open,
    is_paid,
)

LEGAL = {
    (S.INITIATED, S.AUTHORIZED), (S.INITIATED, S.CAPTURED), (S.INITIATED, S.FAILED), (S.INITIATED, S.EXPIRED),
    (S.AUTHORIZED, S.CAPTURED), (S.AUTHORIZED, S.FAILED), (S.AUTHORIZED, S.EXPIRED),
    (S.FAILED, S.CAPTURED),
    (S.EXPIRED, S.CAPTURED),
    (S.CAPTURED, S.REFUNDED),
}


class TransitionTableTests(unittest.TestCase):
    def test_every_status_has_an_entry(self):
        self.assertEqual(set(ALLOWED_TRANSITIONS), set(S))

    def test_exactly_the_documented_moves_are_legal(self):
        actual = {(a, b) for a, b in product(S, S) if can_transition(a, b)}
        self.assertEqual(actual, LEGAL)

    def test_staying_in_the_same_state_is_not_a_transition(self):
        for status in S:
            self.assertFalse(can_transition(status, status), status)

    def test_captured_is_never_reverted(self):
        """Success is terminal: no late failure/expiry event can undo it."""
        for bad in (S.INITIATED, S.AUTHORIZED, S.FAILED, S.EXPIRED):
            self.assertFalse(can_transition(S.CAPTURED, bad), bad)

    def test_only_a_refund_can_follow_a_capture(self):
        self.assertEqual(ALLOWED_TRANSITIONS[S.CAPTURED], {S.REFUNDED})
        self.assertEqual(ALLOWED_TRANSITIONS[S.REFUNDED], frozenset())

    def test_failed_and_expired_never_become_open_again(self):
        """A retry is a NEW payment row, not a revived one."""
        for status in (S.FAILED, S.EXPIRED):
            for bad in (S.INITIATED, S.AUTHORIZED):
                self.assertFalse(can_transition(status, bad), (status, bad))

    def test_failed_and_expired_can_still_be_captured(self):
        """Money that really arrived is recorded even after a failure/expiry."""
        self.assertTrue(can_transition(S.FAILED, S.CAPTURED))
        self.assertTrue(can_transition(S.EXPIRED, S.CAPTURED))

    def test_nothing_goes_backwards_to_initiated(self):
        for status in S:
            self.assertFalse(can_transition(status, S.INITIATED), status)


class GroupingTests(unittest.TestCase):
    def test_open_statuses(self):
        self.assertEqual(OPEN_STATUSES, {S.INITIATED, S.AUTHORIZED})
        self.assertTrue(is_open(S.INITIATED) and is_open(S.AUTHORIZED))
        for status in (S.CAPTURED, S.FAILED, S.EXPIRED, S.REFUNDED):
            self.assertFalse(is_open(status), status)

    def test_paid_statuses(self):
        self.assertEqual(PAID_STATUSES, {S.CAPTURED, S.REFUNDED})
        for status in (S.INITIATED, S.AUTHORIZED, S.FAILED, S.EXPIRED):
            self.assertFalse(is_paid(status), status)

    def test_open_and_paid_never_overlap(self):
        self.assertFalse(OPEN_STATUSES & PAID_STATUSES)


if __name__ == "__main__":
    unittest.main()
