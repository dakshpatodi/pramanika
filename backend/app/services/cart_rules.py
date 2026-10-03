"""
Stock rules for the cart - pure functions, no database.

Phase 5 decision C: the cart only VALIDATES against stock, it never
reserves it. Available = quantity - reserved_quantity; `reserved_quantity`
is still untouched until Phase 6 (checkout initiation), but reading it here
means the cart keeps working unchanged once reservation starts.
"""

from typing import Any, Optional


def available_stock(inventory: Optional[Any]) -> int:
    """Units that can be added to a cart right now.

    A product with no inventory row counts as 0 (cannot be sold), and the
    result is clamped at 0 so an over-reserved row never yields a
    negative number.
    """
    if inventory is None:
        return 0
    return max(inventory.quantity - inventory.reserved_quantity, 0)


def line_issue(is_active: bool, quantity: int, available: int) -> Optional[str]:
    """Why a cart line cannot be purchased as it stands, or None if fine.

    Lines with an issue are still shown to the customer (so they can fix or
    remove them) but are excluded from totals; quantities are never changed
    silently behind their back.
    """
    if not is_active:
        return "This product is no longer available."
    if available <= 0:
        return "This product is currently out of stock."
    if quantity > available:
        unit_word = "unit" if available == 1 else "units"
        return f"Only {available} {unit_word} available - please reduce the quantity."
    return None