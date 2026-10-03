"""
Money helpers.

All monetary arithmetic in the backend is done with `Decimal`, never
`float` - floats cannot represent values like 0.1 exactly, and the error
compounds across GST / discount / total calculations. Floats appear only at
the very edge: settings values that arrive as floats (GST_RATE, etc.) are
converted once with `to_decimal`, and response schemas convert the final
already-rounded amounts back to JSON numbers.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Union

Number = Union[int, float, str, Decimal]

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")


def to_decimal(value: Number) -> Decimal:
    """Convert to Decimal without inheriting float noise.

    `Decimal(0.05)` is 0.05000000000000000277..., whereas `Decimal("0.05")`
    is exactly 0.05 - so anything that is not already a Decimal goes
    through `str()` first.
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def to_money(value: Number) -> Decimal:
    """Round to 2 decimal places, halves rounding up (0.125 -> 0.13).

    ROUND_HALF_UP is what people expect from an invoice; Python's default
    (banker's rounding, ROUND_HALF_EVEN) would turn 0.125 into 0.12.
    """
    return to_decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def money_to_float(value: Number) -> float:
    """For the JSON boundary only - call this on an already-rounded amount."""
    return float(to_money(value))