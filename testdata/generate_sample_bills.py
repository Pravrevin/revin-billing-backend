"""
Generate sample supplier purchase bills (PDF) for testing the AI "Upload Bill"
feature on the Purchase Entry screen.

Run:  python testdata/generate_sample_bills.py

Produces in this folder:
  • sample_purchase_bill.pdf       — single-page bill, names match seeded masters
  • sample_purchase_bill_2page.pdf — two-page bill (tests multi-page merge)

The supplier ("MedPlus Distributors Pvt Ltd") and most medicines match the
seeded item/party masters, so extraction should auto-match them; a couple of
rows are deliberately unknown to show the "pick or create" flow.
"""

import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

HERE = os.path.dirname(os.path.abspath(__file__))
styles = getSampleStyleSheet()

COLUMNS = ["S.No", "Item Description", "HSN", "Batch No", "Qty", "Free",
           "P.Rate", "MRP", "Disc %", "GST %", "Exp. Date"]

# Rows whose item names match the seeded item_master will auto-match; the
# "Pantoprazole" / "Dolo" rows are intentionally unknown → manual pick/create.
PAGE1_ROWS = [
    ["1", "Paracetamol 500mg Tablet",    "30049099", "PCM2401", "100", "10", "1.20",  "2.50",  "5",  "12", "07/2027"],
    ["2", "Amoxicillin 250mg Capsule",   "30041010", "AMX5521", "50",  "5",  "3.80",  "7.00",  "10", "12", "11/2027"],
    ["3", "Ascoril Cough Syrup 100ml",   "30049011", "ASC7788", "40",  "4",  "62.00", "98.00", "8",  "12", "03/2028"],
    ["4", "Volini Pain Relief Gel 30g",  "30049087", "VOL1290", "25",  "2",  "78.50", "125.00","7",  "18", "05/2028"],
    ["5", "Pantoprazole 40mg Tablet",    "30049099", "PAN4502", "60",  "6",  "2.10",  "4.50",  "5",  "12", "01/2028"],
    ["6", "Dolo 650mg Tablet",           "30049099", "DOL9931", "150", "15", "1.65",  "3.00",  "5",  "12", "09/2027"],
]

PAGE2_ROWS = [
    ["7", "Cetirizine 10mg Tablet",      "30049099", "CTZ9012", "200", "20", "0.85",  "1.80",  "5",  "12", "03/2027"],
    ["8", "Azithromycin 500mg Tablet",   "30042039", "AZI3344", "30",  "3",  "9.50",  "18.00", "8",  "12", "09/2026"],
]


def _header(elems, invoice_no, page_label=None):
    title = "MedPlus Distributors Pvt Ltd"
    elems.append(Paragraph(f"<b>{title}</b>", styles["Title"]))
    elems.append(Paragraph(
        "45 Anna Salai, Chennai - 600002 &nbsp;&nbsp; "
        "GSTIN: 33AABCM1234K1Z9 &nbsp;&nbsp; DL No: TN-CH-20B-1234",
        styles["Normal"],
    ))
    elems.append(Spacer(1, 6))
    extra = f" &nbsp;&nbsp; (Page {page_label})" if page_label else ""
    elems.append(Paragraph(
        f"Tax Invoice No: <b>{invoice_no}</b> &nbsp;&nbsp; Date: <b>30/05/2026</b>{extra}",
        styles["Normal"],
    ))
    elems.append(Spacer(1, 10))


def _table(rows):
    t = Table([COLUMNS] + rows, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0e7490")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (4, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
    ]))
    return t


def _totals(elems, sub, cgst, sgst, total):
    elems.append(Spacer(1, 12))
    elems.append(Paragraph(
        f"Sub Total: {sub:.2f} &nbsp;&nbsp; CGST: {cgst:.2f} &nbsp;&nbsp; "
        f"SGST: {sgst:.2f} &nbsp;&nbsp; <b>Grand Total: {total:.2f}</b>",
        styles["Normal"],
    ))
    elems.append(Spacer(1, 6))
    elems.append(Paragraph("Bank: HDFC Bank A/c 50200012345678, IFSC HDFC0000123", styles["Normal"]))
    elems.append(Paragraph("Terms: Goods once sold will not be taken back. E.&O.E.", styles["Normal"]))


def build_single():
    out = os.path.join(HERE, "sample_purchase_bill.pdf")
    doc = SimpleDocTemplate(out, pagesize=A4, topMargin=15 * mm)
    elems = []
    _header(elems, "INV-2026-0512")
    elems.append(_table(PAGE1_ROWS))
    _totals(elems, 21487.50, 1418.78, 1418.78, 24325.06)
    doc.build(elems)
    print("WROTE", out)


def build_two_page():
    out = os.path.join(HERE, "sample_purchase_bill_2page.pdf")
    doc = SimpleDocTemplate(out, pagesize=A4, topMargin=15 * mm)
    elems = []
    _header(elems, "INV-2026-0513", page_label="1 of 2")
    elems.append(_table(PAGE1_ROWS))
    elems.append(PageBreak())
    _header(elems, "INV-2026-0513", page_label="2 of 2")
    elems.append(_table(PAGE2_ROWS))
    _totals(elems, 23105.00, 1539.30, 1539.30, 26183.60)
    doc.build(elems)
    print("WROTE", out)


if __name__ == "__main__":
    build_single()
    build_two_page()
    print("Done. Upload these on Purchase Entry -> Upload Bill (AI).")
