"""
What an invoice says, as plain data (Phase 8). No PDF library in here.

Every figure comes from the ORDER as it was stored when it was placed: the item
lines (name, SKU, unit price, quantity, line total) and the pricing snapshot
(subtotal, discount, taxable amount, GST rate and amount, delivery, total) and
the delivery address copy. Nothing is looked up from the live product catalogue,
so a later price change or a deleted product cannot change an old invoice, and
nothing is recalculated: the stored numbers are printed as they are.

Two things are NOT snapshots, because the order does not store them: the
customer's email address and phone number come from the account as it is now.
The delivery name, phone and address are the order's own copy.

The seller block prints only what the operator configured
(`INVOICE_SELLER_*`); nothing is invented.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

from app.core.config import Settings, settings as default_settings
from app.core.money import to_money
from app.models import Order, User

IST = timezone(timedelta(hours=5, minutes=30), "IST")
"""Dates on the invoice are shown in Indian Standard Time. A fixed offset, not a
timezone database: India has no daylight saving, and a database would need an
extra package on Windows."""


@dataclass(frozen=True)
class SellerDetails:
    name: str = ""
    address_lines: tuple = ()
    gstin: str = ""
    email: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.name or self.address_lines or self.gstin or self.email)


def seller_from_settings(config: Settings = default_settings) -> SellerDetails:
    lines = tuple(part.strip() for part in config.INVOICE_SELLER_ADDRESS.split("|") if part.strip())
    return SellerDetails(
        name=config.INVOICE_SELLER_NAME,
        address_lines=lines,
        gstin=config.INVOICE_SELLER_GSTIN,
        email=config.INVOICE_SELLER_EMAIL,
    )


@dataclass(frozen=True)
class InvoiceLine:
    number: int
    name: str
    sku: str
    quantity: int
    unit_price: Decimal
    amount: Decimal


@dataclass(frozen=True)
class InvoiceData:
    reference: str
    """The order number: this project has no separate invoice numbering."""
    order_date: datetime
    paid_at: Optional[datetime]
    seller: SellerDetails
    bill_to: List[str]
    ship_to: List[str]
    lines: List[InvoiceLine]
    subtotal: Decimal
    discount: Decimal
    coupon_code: Optional[str]
    taxable_amount: Decimal
    gst_rate: Decimal
    gst: Decimal
    delivery_charge: Decimal
    total: Decimal


# --- formatting (pure) -------------------------------------------------------


def format_inr(value: Decimal) -> str:
    """Rs. 1,23,456.78 - two decimals and Indian digit grouping (3, then 2, 2, ...)."""
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    whole, _, fraction = f"{abs(amount):.2f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}Rs. {whole}.{fraction}"


def format_date(value: datetime) -> str:
    """19 Oct 2026, in Indian Standard Time."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(IST).strftime("%d %b %Y")


def format_rate(rate: Decimal) -> str:
    """0.0500 -> '5%', 0.18 -> '18%', 0.025 -> '2.5%'."""
    percent = (Decimal(str(rate)) * 100).normalize()
    text = format(percent, "f")
    return f"{text}%"


def invoice_filename(order: Order) -> str:
    base = order.order_number or order.id.hex[:12]
    return "invoice-" + re.sub(r"[^A-Za-z0-9._-]", "_", base) + ".pdf"


# --- building ------------------------------------------------------------------


def _clean(parts) -> List[str]:
    return [p.strip() for p in parts if p and str(p).strip()]


def build_invoice_data(
    order: Order, user: User, *, paid_at: Optional[datetime], seller: SellerDetails
) -> InvoiceData:
    """Assemble the invoice for a PAID order. The caller has already checked
    eligibility and ownership."""
    delivery_name = order.shipping_full_name
    delivery_phone = order.shipping_phone_number
    city_line = " ".join(_clean([order.shipping_city, order.shipping_state])).strip()
    pin_line = " - ".join(_clean([city_line, order.shipping_postal_code])) if city_line else (order.shipping_postal_code or "")

    ship_to = _clean(
        [
            delivery_name,
            order.shipping_address_line_1,
            order.shipping_address_line_2,
            pin_line,
            order.shipping_country,
            f"Phone: {delivery_phone}" if delivery_phone else None,
        ]
    )
    bill_to = _clean(
        [
            delivery_name or f"{user.first_name} {user.last_name}",
            f"Phone: {delivery_phone}" if delivery_phone else None,
            f"Email: {user.email}" if user.email else None,
        ]
    )

    items = sorted(order.items, key=lambda i: (i.product_name_snapshot.lower(), str(i.id)))
    lines = [
        InvoiceLine(
            number=n,
            name=i.product_name_snapshot,
            sku=i.sku_snapshot,
            quantity=i.quantity,
            unit_price=to_money(i.unit_price),
            amount=to_money(i.subtotal),
        )
        for n, i in enumerate(items, start=1)
    ]
    return InvoiceData(
        reference=order.order_number or order.id.hex[:12].upper(),
        order_date=order.created_at,
        paid_at=paid_at,
        seller=seller,
        bill_to=bill_to,
        ship_to=ship_to,
        lines=lines,
        subtotal=to_money(order.subtotal),
        discount=to_money(order.discount_amount),
        coupon_code=order.coupon_code,
        taxable_amount=to_money(order.taxable_amount),
        gst_rate=Decimal(str(order.gst_rate)),
        gst=to_money(order.tax_amount),
        delivery_charge=to_money(order.delivery_charge),
        total=to_money(order.total_amount),
    )
