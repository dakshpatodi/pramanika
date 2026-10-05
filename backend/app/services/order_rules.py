"""
Order rules that need no database - pure functions, easy to test.
"""

from app.models import OrderPaymentStatus, OrderStatus

ORDER_NUMBER_PREFIX = "PRM"


def format_order_number(year: int, sequence: int) -> str:
    """(2026, 123) -> 'PRM-2026-000123'. Wider numbers just grow past six
    digits; they are never truncated."""
    return f"{ORDER_NUMBER_PREFIX}-{year}-{sequence:06d}"


def can_cancel(status: OrderStatus, payment_status: OrderPaymentStatus) -> bool:
    """A customer may cancel only an order that has not been paid for and
    has not started moving. Paid orders go through refunds, which belong to
    the payment phase."""
    return status == OrderStatus.PENDING and payment_status == OrderPaymentStatus.PENDING