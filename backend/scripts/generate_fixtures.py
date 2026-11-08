"""Generate synthetic English invoices with KNOWN ground truth for tests and evaluation.

Outputs (in --out):
  *.pdf            digital PDFs (3 layouts)
  *_scan.png/jpg/tiff, *_scan.pdf   rasterised, rotated, noisy copies (exercise OCR + preprocessing)
  *.xlsx / *.csv   spreadsheet versions (single invoice sheets + a CSV invoice register)
  manifest.json    ground truth per file, including deliberate errors

Usage: python -m scripts.generate_fixtures --out tests/fixtures/generated --count 12 --seed 7
"""
import argparse
import csv
import json
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

SUPPLIERS = ["ABC Corporation", "Northwind Traders Ltd", "Bluebird Office Supplies Inc", "Granite Peak Consulting LLC",
             "Summit Logistics Group", "Evergreen Software Solutions", "Harbor Point Industries", "Maple & Oak Trading Co."]
CUSTOMERS = ["XYZ Limited", "Riverside Medical Partners", "Atlas Engineering Ltd", "Brightline Retail Inc",
             "Oakwood Property Management", "Pioneer Analytics LLC"]
ITEMS = [("Consulting services", 150), ("Office chairs", 89.5), ("Laptop stand", 39.99), ("Cloud hosting (monthly)", 240),
         ("Printer paper A4 (box)", 24.75), ("Software licence", 499), ("Onsite support hours", 95),
         ("Network switch 24-port", 310.4), ("Delivery charge", 35), ("Training workshop", 1200)]
LAYOUTS = ["classic", "tax", "minimal"]
CURRENCIES = [("USD", "$"), ("GBP", "£"), ("EUR", "€")]


def q2(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(v: Decimal, sym: str) -> str:
    return f"{sym}{v:,.2f}"


def make_invoice(i: int, rnd: random.Random) -> dict:
    n_items = rnd.randint(2, 6)
    items = []
    for desc, price in rnd.sample(ITEMS, n_items):
        qty = rnd.randint(1, 12)
        unit = q2(price)
        items.append({"description": desc, "quantity": str(qty), "unit_price": str(unit),
                      "line_total": str(q2(unit * qty))})
    subtotal = sum(Decimal(it["line_total"]) for it in items)
    rate = rnd.choice([Decimal("0"), Decimal("5"), Decimal("10"), Decimal("15"), Decimal("20")])
    tax = q2(subtotal * rate / 100)
    total = subtotal + tax
    cur, sym = rnd.choice(CURRENCIES)
    d = date(2026, 1, 1) + timedelta(days=rnd.randint(0, 300))
    return {
        "invoice_number": f"INV-2026-{1000 + i}",
        "invoice_date": d.isoformat(),
        "supplier_name": rnd.choice(SUPPLIERS),
        "customer_name": rnd.choice(CUSTOMERS),
        "subtotal": str(q2(subtotal)),
        "tax": str(tax),
        "total": str(q2(total)),
        "currency": cur,
        "tax_rate": str(rate),
        "line_items": items,
        "_symbol": sym,
        "_layout": LAYOUTS[i % len(LAYOUTS)],
        "_errors": [],
    }


# ------------------------------------------------------------------ PDF rendering (reportlab)
def render_pdf(inv: dict, path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    W, H = A4
    sym = inv["_symbol"]
    layout = inv["_layout"]
    d = date.fromisoformat(inv["invoice_date"])
    printed_total = Decimal(inv["_printed_total"]) if "_printed_total" in inv else Decimal(inv["total"])
    printed_tax = Decimal(inv["_printed_tax"]) if "_printed_tax" in inv else Decimal(inv["tax"])

    def txt(x, y, s, size=10, bold=False, right=False):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        (c.drawRightString if right else c.drawString)(x, y, s)

    y = H - 60
    if layout == "classic":
        txt(50, y, inv["supplier_name"], 16, True)
        txt(50, y - 16, "120 Market Street, Springfield", 9)
        txt(W - 50, y, "INVOICE", 22, True, right=True)
        txt(W - 200, y - 40, "Invoice No:", 10, True); txt(W - 50, y - 40, inv["invoice_number"], right=True)
        txt(W - 200, y - 56, "Invoice Date:", 10, True); txt(W - 50, y - 56, d.strftime("%m/%d/%Y") if d.day > 12
                                                              else d.isoformat(), right=True)
        txt(W - 200, y - 72, "Due Date:", 10, True); txt(W - 50, y - 72, (d + timedelta(days=30)).isoformat(), right=True)
        txt(50, y - 100, "Bill To:", 10, True)
        txt(50, y - 116, inv["customer_name"])
        txt(50, y - 130, "45 Harbour Road, Riverside", 9)
        cols = [("Description", 50, False), ("Qty", 330, True), ("Unit Price", 430, True), ("Amount", W - 50, True)]
        tax_label, total_label, sub_label = f"Tax ({inv['tax_rate']}%)", "Total", "Subtotal"
    elif layout == "tax":
        txt(50, y, "TAX INVOICE", 20, True)
        txt(W - 50, y, f"Invoice # {inv['invoice_number']}", 11, True, right=True)
        txt(W - 50, y - 16, f"Date: {d.strftime('%d %b %Y')}", 10, right=True)
        txt(50, y - 50, "From:", 10, True); txt(320, y - 50, "To:", 10, True)
        txt(50, y - 66, inv["supplier_name"]); txt(320, y - 66, inv["customer_name"])
        txt(50, y - 80, "VAT No: GB123456789", 9); txt(320, y - 80, "Accounts Payable", 9)
        cols = [("Item", 50, False), ("Quantity", 330, True), ("Rate", 430, True), ("Line Total", W - 50, True)]
        tax_label, total_label, sub_label = f"VAT {inv['tax_rate']}%", "Amount Due", "Sub-total"
    else:  # minimal
        txt(50, y, f"Supplier: {inv['supplier_name']}", 12, True)
        txt(50, y - 20, f"Customer: {inv['customer_name']}", 11)
        txt(50, y - 40, f"Invoice Number: {inv['invoice_number']}", 11)
        txt(50, y - 56, f"Issue Date: {d.strftime('%B %d, %Y')}", 11)
        txt(50, y - 72, f"Currency: {inv['currency']}", 11)
        cols = [("Product", 50, False), ("Hours", 330, True), ("Rate", 430, True), ("Total", W - 50, True)]
        tax_label, total_label, sub_label = "Sales Tax", "Grand Total", "Net Amount"

    ty = y - 170
    for name, x, right in cols:
        txt(x, ty, name, 10, True, right=right)
    c.line(50, ty - 6, W - 50, ty - 6)
    ty -= 22
    for it in inv["line_items"]:
        txt(cols[0][1], ty, it["description"])
        txt(cols[1][1], ty, it["quantity"], right=True)
        txt(cols[2][1], ty, money(Decimal(it["unit_price"]), sym if layout != "minimal" else ""), right=True)
        txt(cols[3][1], ty, money(Decimal(it["line_total"]), sym if layout != "minimal" else ""), right=True)
        ty -= 18
    c.line(300, ty + 6, W - 50, ty + 6)
    ty -= 14
    for label, val in ((sub_label, Decimal(inv["subtotal"])), (tax_label, printed_tax),
                       (total_label, printed_total)):
        txt(380, ty, label, 10, label == total_label)
        txt(W - 50, ty, money(val, sym if layout != "minimal" else "") + (f" {inv['currency']}" if layout ==
                                                                              "minimal" else ""), 10,
            label == total_label, right=True)
        ty -= 18
    txt(50, 60, "Thank you for your business. Payment terms: 30 days.", 9)
    c.save()


def rasterise(pdf_path: Path, out_base: Path, rnd: random.Random) -> list[Path]:
    import cv2
    import fitz
    import numpy as np

    doc = fitz.open(pdf_path)
    pix = doc[0].get_pixmap(dpi=200)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR if pix.n == 3 else cv2.COLOR_RGBA2BGR)
    angle = rnd.uniform(-2.5, 2.5)
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    img = cv2.warpAffine(img, m, (w, h), borderValue=(255, 255, 255))
    noise = np.random.default_rng(rnd.randint(0, 9999)).normal(0, 12, img.shape)
    img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    outs = []
    ext = rnd.choice([".png", ".jpg", ".tiff"])
    p = out_base.with_name(out_base.name + "_scan" + ext)
    cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 85] if ext == ".jpg" else [])
    outs.append(p)
    # scanned PDF (image only, no text layer)
    ok, buf = cv2.imencode(".png", img)
    sdoc = fitz.open()
    page = sdoc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=buf.tobytes())
    sp = out_base.with_name(out_base.name + "_scan.pdf")
    sdoc.save(sp)
    outs.append(sp)
    return outs


def write_xlsx(inv: dict, path: Path, overrides: dict | None = None) -> None:
    from openpyxl import Workbook

    v = {**inv, **(overrides or {})}
    wb = Workbook()
    ws = wb.active
    ws.title = "Invoice"
    rows = [["Invoice Number", v["invoice_number"]], ["Invoice Date", v["invoice_date"]],
            ["Supplier", v["supplier_name"]], ["Customer", v["customer_name"]], ["Currency", v["currency"]], []]
    for r in rows:
        ws.append(r)
    ws.append(["Description", "Quantity", "Unit Price", "Line Total"])
    for it in v["line_items"]:
        ws.append([it["description"], int(it["quantity"]), float(it["unit_price"]), float(it["line_total"])])
    ws.append([])
    ws.append(["Subtotal", None, None, float(v["subtotal"])])
    ws.append(["Tax", None, None, float(v["tax"])])
    ws.append(["Total", None, None, float(v["total"])])
    wb.save(path)


def write_register_csv(invoices: list[dict], path: Path, mismatch: dict | None = None) -> list[dict]:
    rows = []
    for inv in invoices:
        row = {k: inv[k] for k in ("invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal",
                                   "tax", "total", "currency")}
        if mismatch and inv["invoice_number"] == mismatch["invoice_number"]:
            row.update(mismatch["changes"])
        rows.append(row)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Invoice No", "Invoice Date", "Supplier", "Customer", "Subtotal", "Tax",
                                          "Total", "Currency"])
        w.writeheader()
        for r in rows:
            w.writerow({"Invoice No": r["invoice_number"], "Invoice Date": r["invoice_date"],
                        "Supplier": r["supplier_name"], "Customer": r["customer_name"], "Subtotal": r["subtotal"],
                        "Tax": r["tax"], "Total": r["total"], "Currency": r["currency"]})
    return rows


def public(inv: dict) -> dict:
    return {k: v for k, v in inv.items() if not k.startswith("_")} | {"errors": inv["_errors"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tests/fixtures/generated")
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-scans", action="store_true")
    args = ap.parse_args()

    rnd = random.Random(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    invoices = [make_invoice(i, rnd) for i in range(args.count)]

    # deliberate errors (ground truth = what is PRINTED; errors list = what validation should catch)
    if len(invoices) > 3:
        invoices[1]["_printed_tax"] = str(Decimal(invoices[1]["tax"]) + Decimal("7.50"))
        invoices[1]["tax"] = invoices[1]["_printed_tax"]
        invoices[1]["total"] = str(Decimal(invoices[1]["subtotal"]) + Decimal(invoices[1]["tax"]))
        invoices[1]["_printed_total"] = invoices[1]["total"]
        invoices[1]["_errors"].append("tax_calculation")
        invoices[2]["_printed_total"] = str(Decimal(invoices[2]["total"]) + Decimal("100.00"))
        invoices[2]["total"] = invoices[2]["_printed_total"]
        invoices[2]["_errors"].append("total_mismatch")

    for i, inv in enumerate(invoices):
        base = out / f"invoice_{i:02d}_{inv['_layout']}"
        render_pdf(inv, base.with_suffix(".pdf"))
        manifest[base.with_suffix(".pdf").name] = public(inv)
        if not args.no_scans and i % 2 == 0:
            for p in rasterise(base.with_suffix(".pdf"), base, rnd):
                manifest[p.name] = public(inv) | {"scanned": True}

    # duplicate: same invoice re-issued as a separate PDF
    dup = dict(invoices[0])
    dup["_errors"] = ["duplicate"]
    render_pdf(dup, out / "invoice_00_duplicate.pdf")
    manifest["invoice_00_duplicate.pdf"] = public(dup)

    # spreadsheet versions for cross-document verification
    write_xlsx(invoices[0], out / "invoice_00.xlsx")
    manifest["invoice_00.xlsx"] = public(invoices[0])
    changed = {"total": str(Decimal(invoices[3]["total"]) + Decimal("50.00"))}
    write_xlsx(invoices[3], out / "invoice_03_mismatch.xlsx", changed)
    manifest["invoice_03_mismatch.xlsx"] = public(invoices[3] | changed) | {"errors": ["pdf_excel_mismatch",
                                                                                         "total_mismatch"]}
    rows = write_register_csv(invoices[:6], out / "register.csv",
                              mismatch={"invoice_number": invoices[4]["invoice_number"],
                                        "changes": {"tax": str(Decimal(invoices[4]["tax"]) + Decimal("1.00"))}})
    # ground truth = what is actually written in the CSV (including the planted mismatch)
    manifest["register.csv"] = {"register": rows, "errors": [f"{invoices[4]['invoice_number']}:tax_mismatch"]}

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {len(manifest)} fixture files to {out}")


if __name__ == "__main__":
    main()
