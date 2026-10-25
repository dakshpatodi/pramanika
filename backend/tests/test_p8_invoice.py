"""
Phase 8 M3 - downloadable invoices (GET /api/invoices, GET /api/invoices/{id}).

  InvoiceFormatTests    money, dates, text clean-up (no database)
  InvoicePdfTests       the drawn document (no database)
  InvoiceSettingsTests  the optional seller settings and GSTIN check (no database)
  InvoiceServiceTests   who gets an invoice, and what is on it (PostgreSQL)
  InvoiceListTests      the paginated list (PostgreSQL)
  InvoiceApiTests       HTTP: authentication, ownership, headers (PostgreSQL)

Text is searched in PDFs made with compression off (`compress=False`), which
is a test-only switch on the renderer; real downloads are compressed.

See tests/pg_support.py for how to run the PostgreSQL ones.
"""

import random
import re
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import invoices as invoices_api
from app.core.config import Settings
from app.core.exceptions import DomainError, InvoiceNotAvailableError, OrderNotFoundError
from app.core.security import create_access_token
from app.database.session import get_db
from app.models import Address, Order, OrderPaymentStatus, OrderStatus, Payment, PaymentTransactionStatus, Product, User
from app.repositories.invoice_repository import InvoiceRepository
from app.services.invoice_data import (
    IST,
    InvoiceData,
    InvoiceLine,
    SellerDetails,
    format_date,
    format_inr,
    format_rate,
    invoice_filename,
    seller_from_settings,
)
from app.services.invoice_pdf import MAX_TEXT, pdf_text, render_invoice_pdf
from app.services.invoice_service import InvoiceService
from tests.pg_support import new_session
from tests.test_p6_checkout import CheckoutTestCase


def make_settings(**overrides) -> Settings:
    base = dict(SECRET_KEY="x" * 40, DATABASE_URL="postgresql://u:p@localhost/db_test")
    base.update(overrides)
    return Settings(**base)


def sample_data(**overrides) -> InvoiceData:
    values = dict(
        reference="PRM-2026-000042",
        order_date=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        paid_at=datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc),
        seller=SellerDetails(),
        bill_to=["Asha Rao", "Phone: 9876543210"],
        ship_to=["Asha Rao", "12 MG Road", "Pune Maharashtra - 411001", "India"],
        lines=[InvoiceLine(1, "Basmati Rice 5kg", "RICE-5", 2, Decimal("650.00"), Decimal("1300.00"))],
        subtotal=Decimal("1300.00"),
        discount=Decimal("0.00"),
        coupon_code=None,
        taxable_amount=Decimal("1300.00"),
        gst_rate=Decimal("0.05"),
        gst=Decimal("65.00"),
        delivery_charge=Decimal("0.00"),
        total=Decimal("1365.00"),
    )
    values.update(overrides)
    return InvoiceData(**values)


def pdf_pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type /Page(?![s\w])", pdf))


class InvoiceFormatTests(unittest.TestCase):
    def test_rupees_use_indian_grouping_and_two_decimals(self):
        cases = {
            "0": "Rs. 0.00", "5": "Rs. 5.00", "999.5": "Rs. 999.50", "1000": "Rs. 1,000.00",
            "99999": "Rs. 99,999.00", "100000": "Rs. 1,00,000.00", "123456.78": "Rs. 1,23,456.78",
            "1234567.8": "Rs. 12,34,567.80", "123456789": "Rs. 12,34,56,789.00", "-1234.5": "-Rs. 1,234.50",
        }
        for given, expected in cases.items():
            with self.subTest(value=given):
                self.assertEqual(format_inr(Decimal(given)), expected)

    def test_amounts_round_half_up_to_the_paisa(self):
        self.assertEqual(format_inr(Decimal("10.005")), "Rs. 10.01")
        self.assertEqual(format_inr(Decimal("10.004")), "Rs. 10.00")

    def test_gst_rates_read_as_percentages(self):
        for given, expected in [("0.0500", "5%"), ("0.18", "18%"), ("0.025", "2.5%"), ("0.0000", "0%")]:
            with self.subTest(rate=given):
                self.assertEqual(format_rate(Decimal(given)), expected)

    def test_dates_are_shown_in_indian_time(self):
        late_utc = datetime(2026, 10, 19, 20, 30, tzinfo=timezone.utc)  # 02:00 next day in India
        self.assertEqual(format_date(late_utc), "20 Oct 2026")
        self.assertEqual(format_date(datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)), "19 Oct 2026")
        self.assertEqual(format_date(datetime(2026, 10, 19, 22, 0, tzinfo=timezone(timedelta(hours=-5)))), "20 Oct 2026")

    def test_a_date_without_a_timezone_is_taken_as_utc(self):
        self.assertEqual(format_date(datetime(2026, 10, 19, 20, 30)), "20 Oct 2026")

    def test_the_ist_offset_is_five_thirty(self):
        self.assertEqual(IST.utcoffset(None), timedelta(hours=5, minutes=30))

    def test_text_the_font_cannot_draw_is_replaced_not_fatal(self):
        self.assertEqual(pdf_text("Price ₹100 – now"), "Price Rs.100 - now")
        self.assertEqual(pdf_text("‘quoted’ “double”"), "'quoted' \"double\"")
        self.assertEqual(pdf_text("café"), "café")  # Latin-1 passes through
        self.assertEqual(pdf_text("देसी"), "????")
        self.assertEqual(pdf_text("a\nb\tc\x00d"), "a b cd")
        self.assertEqual(pdf_text(None), "")

    def test_text_is_cut_to_a_maximum(self):
        self.assertEqual(len(pdf_text("x" * 5000)), MAX_TEXT)

    def test_any_text_at_all_can_be_rendered(self):
        rng = random.Random(8)
        for _ in range(40):
            text = "".join(chr(rng.choice([rng.randrange(32, 127), rng.randrange(128, 0x2FFF), rng.randrange(0x1F300, 0x1F600)])) for _ in range(60))
            with self.subTest(sample=text[:10]):
                clean = pdf_text(text)
                clean.encode("latin-1")  # must be drawable

    def test_the_download_name_is_safe(self):
        order = type("O", (), {"order_number": "PRM-2026-000042", "id": uuid.uuid4()})()
        self.assertEqual(invoice_filename(order), "invoice-PRM-2026-000042.pdf")
        order.order_number = '../../x";\r\nSet-Cookie: a=b'
        name = invoice_filename(order)
        self.assertRegex(name, r"^invoice-[A-Za-z0-9._-]+\.pdf$")
        order.order_number = None
        self.assertRegex(invoice_filename(order), r"^invoice-[0-9a-f]{12}\.pdf$")


class InvoicePdfTests(unittest.TestCase):
    def render(self, data=None, **kw):
        return render_invoice_pdf(data or sample_data(), compress=False, **kw)

    def test_the_output_is_a_pdf(self):
        pdf = self.render()
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertIn(b"%%EOF", pdf[-32:])
        self.assertEqual(pdf_pages(pdf), 1)

    def test_the_stored_figures_are_on_the_page(self):
        pdf = self.render()
        for text in [b"PRM-2026-000042", b"Basmati Rice 5kg", b"RICE-5", b"Rs. 650.00", b"Rs. 1,300.00",
                     b"GST @ 5%", b"Rs. 65.00", b"Rs. 1,365.00", b"01 Mar 2026", b"05 Mar 2026", b"12 MG Road"]:
            with self.subTest(text=text):
                self.assertIn(text, pdf)

    def test_a_discount_line_appears_only_when_there_was_a_discount(self):
        self.assertNotIn(b"Discount", self.render())
        with_discount = self.render(sample_data(discount=Decimal("100.00"), coupon_code="SAVE100",
                                                taxable_amount=Decimal("1200.00"), gst=Decimal("60.00"), total=Decimal("1260.00")))
        self.assertIn(rb"Discount \(SAVE100\)", with_discount)  # PDF strings escape parentheses
        self.assertIn(b"-Rs. 100.00", with_discount)

    def test_nothing_is_invented_for_the_seller(self):
        pdf = self.render()
        self.assertNotIn(b"GSTIN", pdf)
        self.assertNotIn(b"CIN", pdf)
        self.assertNotIn(b"Tax Invoice", pdf)
        self.assertNotIn(b"CGST", pdf)
        self.assertNotIn(b"SGST", pdf)

    def test_a_configured_seller_is_printed(self):
        seller = SellerDetails("Pramanika Foods LLP", ("12 Market Rd", "Pune 411001"), "27AAAAA0000A1Z5", "help@example.com")
        pdf = self.render(sample_data(seller=seller))
        for text in [b"Pramanika Foods LLP", b"12 Market Rd", b"Pune 411001", b"GSTIN: 27AAAAA0000A1Z5", b"help@example.com"]:
            with self.subTest(text=text):
                self.assertIn(text, pdf)

    def test_a_long_order_runs_onto_more_pages_and_keeps_every_line(self):
        lines = [InvoiceLine(i, f"Item number {i:03d}", f"SKU-{i:03d}", 1, Decimal("10.00"), Decimal("10.00")) for i in range(1, 101)]
        pdf = self.render(sample_data(lines=lines))
        self.assertGreaterEqual(pdf_pages(pdf), 3)
        for i in (1, 50, 100):
            self.assertIn(f"Item number {i:03d}".encode(), pdf)
        self.assertIn(b"Rs. 1,365.00", pdf)  # the total is still there

    def test_odd_text_does_not_stop_the_invoice(self):
        data = sample_data(
            lines=[InvoiceLine(1, "देसी आम ₹ – (50% off) \\ \U0001F600", "SK₹", 1, Decimal("1.00"), Decimal("1.00"))],
            ship_to=["अशोक", "x" * 400],
            bill_to=["", "Phone: "],
        )
        self.assertTrue(self.render(data).startswith(b"%PDF-"))

    def test_an_unbroken_very_long_word_does_not_break_the_layout(self):
        data = sample_data(lines=[InvoiceLine(1, "W" * 280, "S" * 280, 1, Decimal("1.00"), Decimal("1.00"))])
        self.assertTrue(self.render(data).startswith(b"%PDF-"))

    def test_compression_is_on_by_default(self):
        plain = render_invoice_pdf(sample_data(), compress=False)
        packed = render_invoice_pdf(sample_data())
        self.assertLess(len(packed), len(plain))
        self.assertNotIn(b"Rs. 1,365.00", packed)

    def test_no_payment_gateway_wording_is_printed(self):
        pdf = self.render().lower()
        for word in (b"razorpay", b"gateway", b"pay_", b"order_"):
            self.assertNotIn(word, pdf)


class InvoiceSettingsTests(unittest.TestCase):
    def test_all_seller_settings_are_optional_and_blank_by_default(self):
        s = make_settings()
        self.assertEqual((s.INVOICE_SELLER_NAME, s.INVOICE_SELLER_ADDRESS, s.INVOICE_SELLER_GSTIN, s.INVOICE_SELLER_EMAIL), ("", "", "", ""))
        self.assertTrue(seller_from_settings(s).is_empty)

    def test_a_gstin_is_trimmed_upper_cased_and_checked(self):
        self.assertEqual(make_settings(INVOICE_SELLER_GSTIN=" 22aaaaa0000a1z5 ").INVOICE_SELLER_GSTIN, "22AAAAA0000A1Z5")
        for bad in ["123", "22AAAAA0000A1Y5", "AAAAAAAAAAAAAAA", "22AAAAA0000A1Z", "22AAAAA0000A1Z55"]:
            with self.subTest(gstin=bad), self.assertRaises(ValidationError):
                make_settings(INVOICE_SELLER_GSTIN=bad)

    def test_the_address_setting_splits_on_a_bar(self):
        seller = seller_from_settings(make_settings(INVOICE_SELLER_ADDRESS="12 Market Rd | Pune 411001 | "))
        self.assertEqual(seller.address_lines, ("12 Market Rd", "Pune 411001"))

    def test_over_long_values_are_refused(self):
        with self.assertRaises(ValidationError):
            make_settings(INVOICE_SELLER_NAME="x" * 121)
        with self.assertRaises(ValidationError):
            make_settings(INVOICE_SELLER_ADDRESS="x" * 301)


# --- PostgreSQL ------------------------------------------------------------------


class InvoiceTestCase(CheckoutTestCase):
    def paid_order(self, user=None, *, price="650.00", qty=2, name="Basmati Rice 5kg", paid_at=None, created_at=None):
        """A real order from checkout, then marked paid the way a captured
        payment leaves it."""
        user = user or self.make_user()
        address = self.make_address(user)
        product = self.make_product(price=price, stock=50, name=name)
        self.fill_cart(user, [(product, qty)])
        order = self.checkout(user, address).order
        order_id = order.id
        self.mark_paid(order_id, paid_at=paid_at, created_at=created_at)
        return user, order_id, product, address

    def mark_paid(self, order_id, *, paid_at=None, created_at=None):
        with new_session() as s:
            o = s.get(Order, order_id)
            o.payment_status = OrderPaymentStatus.PAID
            o.status = OrderStatus.CONFIRMED
            if created_at is not None:
                o.created_at = created_at
            s.add(Payment(
                order_id=o.id, payment_gateway="razorpay", gateway_order_id=f"order_T{uuid.uuid4().hex[:10]}",
                gateway_payment_id=f"pay_T{uuid.uuid4().hex[:10]}", amount=o.total_amount, currency="INR",
                status=PaymentTransactionStatus.CAPTURED, paid_at=paid_at or datetime.now(timezone.utc),
            ))
            s.commit()

    def service(self, **kw):
        return InvoiceService(self.db, **dict(compress=False, **kw))

    def pdf(self, user, order_id, **kw) -> bytes:
        self.db.expire_all()
        return self.service(**kw).get_invoice_pdf(user, order_id).content


class InvoiceServiceTests(InvoiceTestCase):
    def test_a_paid_order_gets_an_invoice_with_its_stored_figures(self):
        user, order_id, product, _ = self.paid_order()
        with new_session() as s:
            o = s.get(Order, order_id)
            number, total, gst = o.order_number, o.total_amount, o.tax_amount
        pdf = self.pdf(user, order_id)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        for text in [number, "Basmati Rice 5kg", product.sku, "Rs. 650.00", "Rs. 1,300.00"]:
            self.assertIn(str(text).encode(), pdf)
        self.assertIn(f"Rs. {total:,.2f}".encode(), pdf)
        self.assertIn(f"Rs. {gst:,.2f}".encode(), pdf)

    def test_the_file_is_named_after_the_order(self):
        user, order_id, *_ = self.paid_order()
        self.db.expire_all()
        invoice = self.service().get_invoice_pdf(user, order_id)
        with new_session() as s:
            number = s.get(Order, order_id).order_number
        self.assertEqual(invoice.filename, f"invoice-{number}.pdf")

    def test_the_customer_is_the_account_holder_and_the_address_is_the_orders_copy(self):
        user, order_id, *_ = self.paid_order()
        pdf = self.pdf(user, order_id)
        self.assertIn(f"Email: {user.email}".encode(), pdf)
        self.assertIn(b"1 Test Street", pdf)
        self.assertIn(b"411001", pdf)

    def test_a_later_price_or_name_change_does_not_change_the_invoice(self):
        user, order_id, product, _ = self.paid_order(price="650.00", name="Basmati Rice 5kg")
        before = self.pdf(user, order_id)
        with new_session() as s:
            p = s.get(Product, product.id)
            p.price, p.name = Decimal("9999.00"), "Renamed Thing"
            s.commit()
        after = self.pdf(user, order_id)
        for pdf in (before, after):
            self.assertIn(b"Basmati Rice 5kg", pdf)
            self.assertIn(b"Rs. 650.00", pdf)
            self.assertNotIn(b"Renamed Thing", pdf)
            self.assertNotIn(b"9,999.00", pdf)

    def test_editing_or_deleting_the_saved_address_does_not_change_the_invoice(self):
        user, order_id, _, address = self.paid_order()
        with new_session() as s:
            a = s.get(Address, address.id)
            a.address_line_1, a.city = "99 Elsewhere Lane", "Delhi"
            s.commit()
        pdf = self.pdf(user, order_id)
        self.assertIn(b"1 Test Street", pdf)
        self.assertNotIn(b"Elsewhere", pdf)
        with new_session() as s:
            from sqlalchemy import delete
            s.execute(delete(Address).where(Address.id == address.id))
            s.commit()
        self.assertIn(b"1 Test Street", self.pdf(user, order_id))

    def test_an_order_that_is_not_paid_has_no_invoice(self):
        user = self.make_user()
        product = self.make_product()
        for payment_status in (OrderPaymentStatus.PENDING, OrderPaymentStatus.FAILED, OrderPaymentStatus.REFUNDED):
            with self.subTest(payment_status=payment_status):
                order = self.make_order(user, [(product, 1)], payment_status=payment_status)
                with self.assertRaises(InvoiceNotAvailableError):
                    self.service().get_invoice_pdf(user, order.id)

    def test_a_cancelled_unpaid_order_has_no_invoice(self):
        user = self.make_user()
        order = self.make_order(user, [(self.make_product(), 1)], status=OrderStatus.CANCELLED)
        with self.assertRaises(InvoiceNotAvailableError):
            self.service().get_invoice_pdf(user, order.id)

    def test_someone_elses_order_looks_like_a_missing_one(self):
        owner, order_id, *_ = self.paid_order()
        stranger = self.make_user()
        with self.assertRaises(OrderNotFoundError):
            self.service().get_invoice_pdf(stranger, order_id)
        with self.assertRaises(OrderNotFoundError):
            self.service().get_invoice_pdf(owner, uuid.uuid4())

    def test_someone_elses_unpaid_order_is_still_just_not_found(self):
        owner = self.make_user()
        order = self.make_order(owner, [(self.make_product(), 1)])
        with self.assertRaises(OrderNotFoundError):  # not 409: that would confirm the order exists
            self.service().get_invoice_pdf(self.make_user(), order.id)

    def test_the_paid_date_is_when_the_money_was_captured(self):
        user, order_id, *_ = self.paid_order(
            paid_at=datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc),
            created_at=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        )
        pdf = self.pdf(user, order_id)
        self.assertIn(b"01 Mar 2026", pdf)
        self.assertIn(b"05 Mar 2026", pdf)

    def test_a_capture_flagged_for_refund_is_not_the_paid_date(self):
        user, order_id, *_ = self.paid_order(
            paid_at=datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc),
            created_at=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        )
        with new_session() as s:
            s.add(Payment(
                order_id=order_id, payment_gateway="razorpay", gateway_order_id="order_Tlate",
                gateway_payment_id="pay_Tlate", amount=Decimal("1.00"), currency="INR",
                status=PaymentTransactionStatus.CAPTURED, paid_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                refund_required=True,
            ))
            s.commit()
        pdf = self.pdf(user, order_id)
        self.assertIn(b"05 Mar 2026", pdf)
        self.assertNotIn(b"01 Feb 2026", pdf)

    def test_without_a_payment_row_the_paid_date_falls_back_to_the_order_date(self):
        user, order_id, *_ = self.paid_order(created_at=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc))
        with new_session() as s:
            s.query(Payment).filter(Payment.order_id == order_id).delete()
            s.commit()
        pdf = self.pdf(user, order_id)
        self.assertEqual(pdf.count(b"01 Mar 2026"), 2)  # "Order date" and "Paid on" both read the order date
        self.assertIn(b"Paid on", pdf)

    def test_no_gateway_identifier_reaches_the_invoice(self):
        user, order_id, *_ = self.paid_order()
        with new_session() as s:
            payment = s.query(Payment).filter(Payment.order_id == order_id).one()
            ids = [payment.gateway_order_id, payment.gateway_payment_id]
        pdf = self.pdf(user, order_id)
        for value in ids:
            self.assertNotIn(value.encode(), pdf)
        self.assertNotIn(b"razorpay", pdf.lower())

    def test_the_configured_seller_appears_and_nothing_else_is_made_up(self):
        user, order_id, *_ = self.paid_order()
        blank = self.pdf(user, order_id)
        self.assertNotIn(b"GSTIN", blank)
        configured = make_settings(INVOICE_SELLER_NAME="Pramanika Foods LLP", INVOICE_SELLER_GSTIN="27AAAAA0000A1Z5")
        pdf = self.pdf(user, order_id, config=configured)
        self.assertIn(b"Pramanika Foods LLP", pdf)
        self.assertIn(b"GSTIN: 27AAAAA0000A1Z5", pdf)

    def test_asking_twice_reads_without_writing(self):
        user, order_id, *_ = self.paid_order()
        with new_session() as s:
            stamp = s.get(Order, order_id).updated_at
        self.pdf(user, order_id)
        self.pdf(user, order_id)
        with new_session() as s:
            self.assertEqual(s.get(Order, order_id).updated_at, stamp)

    def test_a_many_line_order_makes_a_multi_page_invoice(self):
        user = self.make_user()
        address = self.make_address(user)
        products = [self.make_product(price="10.00", stock=5, name=f"Bulk item {i:03d}") for i in range(60)]
        self.fill_cart(user, [(p, 1) for p in products])
        order_id = self.checkout(user, address).order.id
        self.mark_paid(order_id)
        pdf = self.pdf(user, order_id)
        self.assertGreaterEqual(pdf_pages(pdf), 2)
        for i in (0, 30, 59):
            self.assertIn(f"Bulk item {i:03d}".encode(), pdf)

    def test_lines_are_listed_in_a_stable_order(self):
        user = self.make_user()
        address = self.make_address(user)
        products = [self.make_product(price="10.00", stock=5, name=n) for n in ("Zebra nuts", "apple chips", "Mango pulp")]
        self.fill_cart(user, [(p, 1) for p in products])
        order_id = self.checkout(user, address).order.id
        self.mark_paid(order_id)
        pdf = self.pdf(user, order_id)
        positions = [pdf.index(n.encode()) for n in ("apple chips", "Mango pulp", "Zebra nuts")]
        self.assertEqual(positions, sorted(positions))


class InvoiceListTests(InvoiceTestCase):
    def test_only_the_users_own_paid_orders_are_listed_newest_first(self):
        user, first, *_ = self.paid_order(created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        _, second, *_ = self.paid_order(user, created_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
        self.make_order(user, [(self.make_product(), 1)])  # unpaid
        self.paid_order()  # someone else's
        result = InvoiceService(self.db).list_invoices(user.id, page=1, page_size=10)
        self.assertEqual([i.order_id for i in result.invoices], [second, first])
        self.assertEqual(result.pagination.total, 2)

    def test_summary_figures_come_from_the_order(self):
        user, order_id, *_ = self.paid_order(qty=3, price="100.00")
        item = InvoiceService(self.db).list_invoices(user.id, page=1, page_size=10).invoices[0]
        with new_session() as s:
            o = s.get(Order, order_id)
            self.assertEqual((item.order_number, item.total), (o.order_number, float(o.total_amount)))
        self.assertEqual((item.item_count, item.line_count), (3, 1))

    def test_pages_split_the_list(self):
        user, *_ = self.paid_order()
        for _ in range(4):
            self.paid_order(user)
        service = InvoiceService(self.db)
        p1 = service.list_invoices(user.id, page=1, page_size=2)
        p3 = service.list_invoices(user.id, page=3, page_size=2)
        p9 = service.list_invoices(user.id, page=9, page_size=2)
        self.assertEqual((len(p1.invoices), p1.pagination.total, p1.pagination.total_pages, p1.pagination.has_next), (2, 5, 3, True))
        self.assertEqual((len(p3.invoices), p3.pagination.has_next, p3.pagination.has_previous), (1, False, True))
        self.assertEqual(p9.invoices, [])
        ids = [i.order_id for i in service.list_invoices(user.id, page=1, page_size=10).invoices]
        self.assertEqual(len(set(ids)), 5)

    def test_a_user_with_no_paid_orders_gets_an_empty_page(self):
        user = self.make_user()
        result = InvoiceService(self.db).list_invoices(user.id, page=1, page_size=10)
        self.assertEqual((result.invoices, result.pagination.total, result.pagination.total_pages), ([], 0, 0))

    def test_the_repository_scopes_by_owner(self):
        user, order_id, *_ = self.paid_order()
        repo = InvoiceRepository(self.db)
        self.assertIsNotNone(repo.get_order_for_user(order_id, user.id))
        self.assertIsNone(repo.get_order_for_user(order_id, self.make_user().id))


def build_app(*, compress: bool = False, config=None) -> FastAPI:
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

    def override_service():
        session = new_session()
        try:
            kwargs = {"compress": compress}
            if config is not None:
                kwargs["config"] = config
            yield InvoiceService(session, **kwargs)
        finally:
            session.close()

    app.include_router(invoices_api.router)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[invoices_api.get_invoice_service] = override_service
    return app


class InvoiceApiTests(InvoiceTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(build_app())

    def auth(self, user):
        return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}

    def test_both_routes_need_a_login(self):
        _, order_id, *_ = self.paid_order()
        self.assertEqual(self.client.get("/api/invoices").status_code, 401)
        self.assertEqual(self.client.get(f"/api/invoices/{order_id}").status_code, 401)
        bad = {"Authorization": "Bearer nope"}
        self.assertEqual(self.client.get(f"/api/invoices/{order_id}", headers=bad).status_code, 401)

    def test_a_deactivated_account_is_refused(self):
        user, order_id, *_ = self.paid_order()
        with new_session() as s:
            s.get(User, user.id).is_active = False
            s.commit()
        self.assertEqual(self.client.get(f"/api/invoices/{order_id}", headers=self.auth(user)).status_code, 403)

    def test_the_download_is_a_pdf_attachment_that_is_not_cached(self):
        user, order_id, *_ = self.paid_order()
        with new_session() as s:
            number = s.get(Order, order_id).order_number
        r = self.client.get(f"/api/invoices/{order_id}", headers=self.auth(user))
        self.assertEqual(r.status_code, 200, r.text[:200])
        self.assertEqual(r.headers["content-type"], "application/pdf")
        self.assertEqual(r.headers["content-disposition"], f'attachment; filename="invoice-{number}.pdf"')
        self.assertEqual(r.headers["cache-control"], "no-store")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertTrue(r.content.startswith(b"%PDF-"))
        self.assertIn(number.encode(), r.content)

    def test_real_downloads_are_compressed(self):
        """Through the route's own dependency, exactly as production builds it."""
        user, order_id, *_ = self.paid_order()
        app = build_app()
        app.dependency_overrides.pop(invoices_api.get_invoice_service)
        r = TestClient(app).get(f"/api/invoices/{order_id}", headers=self.auth(user))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"%PDF-"))
        self.assertNotIn(b"Basmati Rice 5kg", r.content)
        self.assertIn(b"/FlateDecode", r.content)

    def test_another_users_invoice_is_404_with_no_pdf(self):
        _, order_id, *_ = self.paid_order()
        r = self.client.get(f"/api/invoices/{order_id}", headers=self.auth(self.make_user()))
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.json()["success"])
        self.assertNotIn(b"%PDF", r.content)

    def test_an_unknown_id_is_404_and_a_malformed_one_is_422(self):
        user = self.make_user()
        self.assertEqual(self.client.get(f"/api/invoices/{uuid.uuid4()}", headers=self.auth(user)).status_code, 404)
        self.assertEqual(self.client.get("/api/invoices/not-a-uuid", headers=self.auth(user)).status_code, 422)

    def test_an_unpaid_order_is_409_with_a_message(self):
        user = self.make_user()
        order = self.make_order(user, [(self.make_product(), 1)])
        r = self.client.get(f"/api/invoices/{order.id}", headers=self.auth(user))
        self.assertEqual(r.status_code, 409)
        self.assertIn("paid", r.json()["message"])

    def test_the_list_returns_the_envelope_and_obeys_its_bounds(self):
        user, order_id, *_ = self.paid_order()
        r = self.client.get("/api/invoices", headers=self.auth(user))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["success"])
        self.assertEqual([i["order_id"] for i in body["data"]["invoices"]], [str(order_id)])
        self.assertEqual(body["data"]["pagination"]["total"], 1)
        for query in ("page=0", "page_size=0", "page_size=51", "page=x"):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(f"/api/invoices?{query}", headers=self.auth(user)).status_code, 422)
        self.assertEqual(self.client.get("/api/invoices?page_size=50", headers=self.auth(user)).status_code, 200)

    def test_the_list_never_shows_another_users_orders(self):
        self.paid_order()
        r = self.client.get("/api/invoices", headers=self.auth(self.make_user()))
        self.assertEqual(r.json()["data"]["invoices"], [])

    def test_the_list_carries_no_payment_gateway_fields(self):
        user, *_ = self.paid_order()
        text = self.client.get("/api/invoices", headers=self.auth(user)).text.lower()
        for word in ("gateway", "razorpay", "pay_", "signature"):
            self.assertNotIn(word, text)

    def test_the_configured_seller_reaches_the_download(self):
        user, order_id, *_ = self.paid_order()
        client = TestClient(build_app(config=make_settings(INVOICE_SELLER_NAME="Pramanika Foods LLP")))
        r = client.get(f"/api/invoices/{order_id}", headers=self.auth(user))
        self.assertIn(b"Pramanika Foods LLP", r.content)


if __name__ == "__main__":
    unittest.main()
