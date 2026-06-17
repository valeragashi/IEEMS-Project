from decimal import Decimal, ROUND_HALF_UP

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

def _money(x) -> Decimal:
    #Build a Decimal from a string/number and snap to 2 places.
    return Decimal(str(x)).quantize( Decimal("0.01") , rounding=ROUND_HALF_UP)

def make_receipt_pdf(
        path: str,
        vendor: str,
        date: str,                          # "YYYY-MM-DD"
        currency: str,                      # "EUR", "USD", "GBP", "CHF", "TRY"
        items: list[dict],                  # [{"description": str, "quantity": int, "unit_price": "12.50"}]
        country: str,                       # "DE", "FR", "SA", ... (per-diem truth)
        payment: str = "corporate_card",    # corporate_card | personal | cash
        vendor_address: str = "",           # street line; country gets appended to it
        receipt_no: str = "",               # printed top-right of the date row, e.g. "0042"
        font: str = "Helvetica",            # s08 passes an odd font to drop extraction confidence
        obscure_total: bool = False,        # s08 passes True to obscure total to reduce confidence
        ) -> None:

    bold = font if font.endswith(("-Bold","-Oblique","-Italic","-BoldOblique","-BoldItalic")) else font + "-Bold"
    W = 80 * mm                             # thermal-roll width
    M = 5                                  # side margin
    inner_l = M                             # left text edge
    inner_r = W - M                         # right text edge (totals align here)

    # vertical budget: find receipt height from item count, then draw
    pad_top, pad_bot = 16, 20
    h_vendor, h_addr, h_date, h_div, h_item, h_total, h_pay, h_thanks = 20, 13, 16, 12, 24, 22, 16, 18
    H = (pad_top + h_vendor + h_addr + h_date + h_div
         + len(items) * h_item + h_div + h_total + h_pay + h_thanks + pad_bot)

    c = canvas.Canvas(path, pagesize=(W, H))
    cx = W / 2
    y = H - pad_top

    def divider():
        nonlocal y
        c.setDash(1, 2)
        c.line(inner_l, y, inner_r, y)
        c.setDash()

    # header (centered)
    c.setFont(bold, 12)
    c.drawCentredString(cx, y, vendor)
    y -= 14
    c.setFont(font, 7)
    c.drawCentredString(cx, y, f"{vendor_address}, {country}")
    y -= h_addr

    # date
    c.setFont(font, 8)
    c.drawString(inner_l, y, f"Date: {date}")
    if receipt_no:
        c.drawRightString(inner_r, y, f"Receipt No: {receipt_no}")
    y -= 8
    divider(); y -= 10

    # line items, stacked: description + total on one row, qty x unit below
    total = Decimal("0.00")
    for item in items:
        quantity = Decimal(str(item.get("quantity", 1)))
        unit_price = _money(item["unit_price"])
        line = _money(quantity * unit_price)
        total += line
        c.setFont(font, 8)
        c.drawString(inner_l, y, str(item["description"]))
        c.setFont(bold, 8)
        c.drawRightString(inner_r, y, f"{line:.2f}")
        y -= 10
        c.setFont(font, 7)
        c.drawString(inner_l + 8, y, f"{quantity.normalize()} x {unit_price:.2f}")
        y -= 14

    total = _money(total)

    # total
    y -= 2
    divider()
    y -= 14
    c.setFont(bold, 10)
    c.drawString(inner_l, y, "TOTAL")
    amount = f"{total:.2f}"
    if obscure_total:
        amount = amount[:1] + "#" + amount[2:]          # 44.00 -> 4#.00 in the text layer too
    c.drawRightString(inner_r, y, f"{currency} {amount}")
    if obscure_total:
        c.setFillGray(0.45); c.rect(inner_r - 26, y - 3, 15, 13, fill=1, stroke=0); c.setFillGray(0)
    y -= h_pay

    # payment + footer
    c.setFont(font, 8)
    c.drawString(inner_l, y, f"Paid: {payment}")
    y -= h_thanks
    c.setFont(font, 7)
    c.drawCentredString(cx, y, "Thank you")

    c.showPage()
    c.save()

# if __name__ == "__main__":
#     make_receipt_pdf(
#         "sample_receipt.pdf",
#         vendor="Trattoria Roma",
#         date="2026-06-10",
#         currency="EUR",
#         items=[
#             {"description": "Margherita pizza", "quantity": 2, "unit_price": "11.50"},
#             {"description": "House red (glass)", "quantity": 2, "unit_price": "6.00"},
#             {"description": "Espresso", "quantity": 2, "unit_price": "2.50"},
#         ],
#         country="IT",
#         payment="personal",
#         vendor_address="Via del Corso 14, Rome",
#         receipt_no=2212
#     )
#     print("wrote sample_receipt.pdf")    