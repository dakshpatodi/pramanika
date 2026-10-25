"""
Draws an InvoiceData as a PDF with fpdf2 (Phase 8). Pure: no database, no clock.

The built-in PDF fonts are used (no font file to ship), and they only cover
Latin-1. So all text goes through `pdf_text`, which keeps what the font can
draw and replaces the rest, instead of letting the library raise on a product
named in Devanagari. The rupee sign is also outside Latin-1, which is why
amounts read "Rs. 1,299.00".
"""

import unicodedata
from typing import Iterable, List

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos

from app.services.invoice_data import (
    InvoiceData,
    SellerDetails,
    format_date,
    format_inr,
    format_rate,
)

_TRANSLATE = {
    "‘": "'", "’": "'", "‚": ",", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", "•": "*", "…": "...",
    " ": " ", "₹": "Rs.",
}

MAX_TEXT = 300
"""One text value is cut here so a pathological name cannot run to many pages."""


def pdf_text(value) -> str:
    """Text the built-in fonts can draw. Never raises."""
    out: List[str] = []
    for ch in str(value or ""):
        if ch in _TRANSLATE:
            out.append(_TRANSLATE[ch])
        elif ch in "\n\r\t":
            out.append(" ")
        elif ord(ch) < 32 or ord(ch) == 127:
            continue
        elif ord(ch) < 256:
            out.append(ch)
        else:
            base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
            if base and all(ord(c) < 128 for c in base):
                out.append(base)
            elif unicodedata.combining(ch):
                continue
            else:
                out.append("?")
    return "".join(out)[:MAX_TEXT]


INK = (30, 30, 30)
MUTED = (110, 110, 110)
RULE = (200, 200, 200)
HEAD_FILL = (240, 240, 240)


class _InvoicePDF(FPDF):
    def __init__(self, reference: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.reference = pdf_text(reference)
        self.set_margins(15, 15, 15)
        self.set_auto_page_break(auto=True, margin=18)
        self.set_title(f"Invoice {self.reference}")
        self.set_creator("Pramanika")

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, f"Invoice {self.reference}", align=Align.L)
        self.set_x(15)
        self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align=Align.R)


def _block(pdf: FPDF, title: str, lines: Iterable[str], x: float, width: float) -> float:
    """A titled paragraph at (x, current y); returns the y where it ended."""
    y0 = pdf.get_y()
    pdf.set_xy(x, y0)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(width, 4, pdf_text(title).upper(), new_x=XPos.LEFT, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*INK)
    for line in lines:
        pdf.set_x(x)
        pdf.multi_cell(width, 5, pdf_text(line), new_x=XPos.LEFT, new_y=YPos.NEXT)
    return pdf.get_y()


def _seller_lines(seller: SellerDetails) -> List[str]:
    lines = list(seller.address_lines)
    if seller.gstin:
        lines.append(f"GSTIN: {seller.gstin}")
    if seller.email:
        lines.append(seller.email)
    return lines


def render_invoice_pdf(data: InvoiceData, *, compress: bool = True) -> bytes:
    pdf = _InvoicePDF(data.reference)
    pdf.set_compression(compress)
    pdf.alias_nb_pages()
    pdf.add_page()

    # --- header: seller on the left, title on the right ----------------------
    top = pdf.get_y()
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*INK)
    name = data.seller.name or "Pramanika"
    pdf.cell(110, 8, pdf_text(name), new_x=XPos.LEFT, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    for line in _seller_lines(data.seller):
        pdf.multi_cell(110, 4.5, pdf_text(line), new_x=XPos.LEFT, new_y=YPos.NEXT)
    left_end = pdf.get_y()

    pdf.set_xy(125, top)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*INK)
    pdf.cell(70, 9, "Invoice", align=Align.R, new_x=XPos.LEFT, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    meta = [("Invoice no.", data.reference), ("Order date", format_date(data.order_date))]
    if data.paid_at is not None:
        meta.append(("Paid on", format_date(data.paid_at)))
    for label, value in meta:
        pdf.set_x(125)
        pdf.cell(25, 5, label)
        pdf.set_text_color(*INK)
        pdf.cell(45, 5, pdf_text(value), align=Align.R, new_x=XPos.LEFT, new_y=YPos.NEXT)
        pdf.set_text_color(*MUTED)
    pdf.set_y(max(left_end, pdf.get_y()) + 4)
    pdf.set_draw_color(*RULE)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(5)

    # --- addresses -----------------------------------------------------------
    y = pdf.get_y()
    pdf.set_y(y)
    end_a = _block(pdf, "Bill to", data.bill_to, 15, 85)
    pdf.set_y(y)
    end_b = _block(pdf, "Ship to", data.ship_to, 110, 85)
    pdf.set_y(max(end_a, end_b) + 6)

    # --- items ---------------------------------------------------------------
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*INK)
    with pdf.table(
        col_widths=(8, 72, 30, 10, 30, 30),
        text_align=("RIGHT", "LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT"),
        headings_style=_head_style(),
        line_height=5,
        padding=1.2,
        borders_layout="HORIZONTAL_LINES",
    ) as table:
        head = table.row()
        for h in ("#", "Item", "SKU", "Qty", "Unit price", "Amount"):
            head.cell(h)
        for line in data.lines:
            row = table.row()
            row.cell(str(line.number))
            row.cell(pdf_text(line.name))
            row.cell(pdf_text(line.sku))
            row.cell(str(line.quantity))
            row.cell(format_inr(line.unit_price))
            row.cell(format_inr(line.amount))
    pdf.ln(4)

    # --- totals --------------------------------------------------------------
    rows = [("Subtotal", format_inr(data.subtotal))]
    if data.discount:
        label = "Discount" + (f" ({pdf_text(data.coupon_code)})" if data.coupon_code else "")
        rows.append((label, "-" + format_inr(data.discount)))
    rows.append(("Taxable amount", format_inr(data.taxable_amount)))
    rows.append((f"GST @ {format_rate(data.gst_rate)}", format_inr(data.gst)))
    rows.append(("Delivery", format_inr(data.delivery_charge)))

    _keep_together(pdf, height=6 * (len(rows) + 2))
    for label, value in rows:
        _total_row(pdf, label, value)
    pdf.set_draw_color(*INK)
    pdf.line(110, pdf.get_y() + 1, 195, pdf.get_y() + 1)
    pdf.ln(2)
    _total_row(pdf, "Total", format_inr(data.total), bold=True)

    pdf.ln(8)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(
        0,
        4,
        "Amounts are in Indian rupees and are shown as recorded when the order was placed. "
        "GST is shown for the whole order. This is a computer-generated invoice.",
        new_x=XPos.LEFT,
        new_y=YPos.NEXT,
    )
    return bytes(pdf.output())


def _head_style():
    from fpdf.fonts import FontFace

    return FontFace(emphasis="BOLD", color=INK, fill_color=HEAD_FILL)


def _keep_together(pdf: FPDF, *, height: float) -> None:
    """Start a new page rather than split the totals box across two."""
    if pdf.get_y() + height > pdf.h - pdf.b_margin:
        pdf.add_page()


def _total_row(pdf: FPDF, label: str, value: str, *, bold: bool = False) -> None:
    pdf.set_x(110)
    pdf.set_font("Helvetica", "B" if bold else "", 11 if bold else 10)
    pdf.set_text_color(*INK)
    pdf.cell(45, 6, pdf_text(label))
    pdf.cell(40, 6, value, align=Align.R, new_x=XPos.LEFT, new_y=YPos.NEXT)
