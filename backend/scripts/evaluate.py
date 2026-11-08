"""Measure extraction accuracy, processing time and success/failure rates on a labelled dataset.

Uses the SAME processing code as the pipeline (PDF text, OpenCV preprocessing, Tesseract OCR, spreadsheet
parser, built-in or LLM extraction, validation rules). Writes docs/evaluation-report.md with measured numbers
only: anything that could not be run (e.g. OCR without Tesseract) is reported as "not measured".

Usage:
  python -m scripts.evaluate --data tests/fixtures/generated --out ../docs/evaluation-report.md
Add your own labelled files to a folder with a manifest.json in the same format to evaluate on real documents.
"""
import argparse
import json
import platform
import statistics
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.ai.builtin.invoice_parser import extract_invoice
from app.processing import image_preprocess, ocr, pdf, spreadsheet
from app.processing.types import ExtractionResult
from app.validation.rules import overall_status, run_rules, view_from_dict

FIELDS = ["invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total", "currency"]


def eq(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError):
        return str(a).strip().lower() == str(b).strip().lower()


def file_type(name: str, gt: dict) -> str:
    ext = Path(name).suffix.lower()
    if ext == ".pdf":
        return "scanned_pdf" if gt.get("scanned") else "digital_pdf"
    if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        return "image"
    return {"xlsx": "excel", "xls": "excel", "csv": "csv"}[ext.lstrip(".")]


def run_one(path: Path) -> list[ExtractionResult]:
    data = path.read_bytes()
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xls", ".csv"):
        return spreadsheet.parse_spreadsheet(spreadsheet.load_frames(data, ext))
    pages = []
    if ext == ".pdf":
        doc = pdf.open_pdf(data)
        for i, page in enumerate(doc, start=1):
            pt = pdf.extract_page(page, i)
            if pdf.page_needs_ocr(pt):
                img = image_preprocess.decode_image(pdf.render_page_png(page))
                pt = ocr.ocr_image(image_preprocess.preprocess(img), i)
            pages.append(pt)
    else:
        for i, img in enumerate(image_preprocess.load_multipage(data), start=1):
            pages.append(ocr.ocr_image(image_preprocess.preprocess(img), i))
    return [extract_invoice(pages)]


def pct(n, d) -> str:
    return f"{100 * n / d:.1f}%" if d else "n/a"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="tests/fixtures/generated")
    ap.add_argument("--out", default="../docs/evaluation-report.md")
    args = ap.parse_args()
    data_dir = Path(args.data)
    manifest = json.loads((data_dir / "manifest.json").read_text())
    has_ocr = ocr.tesseract_available()

    per_type = defaultdict(lambda: {"files": 0, "ok": 0, "failed": 0, "skipped": 0, "times": [],
                                    "field_hits": defaultdict(int), "field_total": defaultdict(int),
                                    "li_hits": 0, "li_total": 0})
    error_detection = {"expected": 0, "detected": 0, "false_alarms": 0, "clean": 0}
    failures = []

    for name, gt in manifest.items():
        path = data_dir / name
        ftype = file_type(name, gt)
        st = per_type[ftype]
        st["files"] += 1
        needs_ocr = ftype in ("scanned_pdf", "image")
        if needs_ocr and not has_ocr:
            st["skipped"] += 1
            continue
        t0 = time.perf_counter()
        try:
            results = run_one(path)
        except Exception as e:
            st["failed"] += 1
            failures.append((name, str(e)[:120]))
            continue
        st["times"].append(time.perf_counter() - t0)
        if not results:
            st["failed"] += 1
            failures.append((name, "no invoice extracted"))
            continue
        st["ok"] += 1

        truths = gt["register"] if "register" in gt else [gt]
        for res, truth in zip(results, truths):
            for f in FIELDS:
                st["field_total"][f] += 1
                st["field_hits"][f] += int(eq(getattr(res, f), truth.get(f)))
            want = truth.get("line_items") or []
            if want and ftype not in ("csv",):
                for i, w in enumerate(want):
                    st["li_total"] += 1
                    if i < len(res.line_items):
                        g = res.line_items[i]
                        st["li_hits"] += int(eq(g.quantity, w["quantity"]) and eq(g.unit_price, w["unit_price"])
                                             and eq(g.line_total, w["line_total"]))
            # validation: did rules flag the deliberately broken invoices (single-document errors only)?
            single_doc_errors = [e for e in truth.get("errors", []) if e in ("tax_calculation", "total_mismatch")]
            if "register" not in gt and not name.endswith(".xlsx"):
                status = overall_status(run_rules(view_from_dict(res.to_dict())))
                if single_doc_errors:
                    error_detection["expected"] += 1
                    error_detection["detected"] += int(status == "failed")
                else:
                    error_detection["clean"] += 1
                    error_detection["false_alarms"] += int(status == "failed")

    # ---------------------------------------------------------------- report
    lines = [
        "# DocuMind AI: Evaluation Report",
        "",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by `scripts/evaluate.py`. All numbers below were "
        f"measured on this run; nothing is estimated._",
        "",
        "## Setup",
        "",
        f"- **Dataset:** `{data_dir}`, {len(manifest)} files. **Synthetic** invoices generated by "
        "`scripts/generate_fixtures.py` with known ground truth (3 layouts, rotated/noisy scans, Excel/CSV, deliberate "
        "errors). Results on real-world documents will differ. Add labelled real samples to re-measure.",
        "- **Extraction engine:** built-in rule-based engine (no LLM / API key)",
        f"- **OCR:** {'Tesseract ' + str(ocr.pytesseract.get_tesseract_version()) if has_ocr else 'NOT AVAILABLE on this machine: OCR file types were not measured'}",
        f"- **Machine:** {platform.platform()}, Python {platform.python_version()}, {platform.processor() or 'CPU'}",
        "",
        "## Success / failure rate",
        "",
        "| File type | Files | Processed | Failed | Not measured | Success rate | Failure rate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    tot = {"files": 0, "ok": 0, "failed": 0, "skipped": 0}
    for t, s in sorted(per_type.items()):
        run = s["ok"] + s["failed"]
        lines.append(f"| {t} | {s['files']} | {s['ok']} | {s['failed']} | {s['skipped']} | {pct(s['ok'], run)} | "
                     f"{pct(s['failed'], run)} |")
        for k in tot:
            tot[k] += s[k]
    run = tot["ok"] + tot["failed"]
    lines.append(f"| **all measured** | {tot['files']} | {tot['ok']} | {tot['failed']} | {tot['skipped']} | "
                 f"**{pct(tot['ok'], run)}** | **{pct(tot['failed'], run)}** |")

    lines += ["", "## Field-level extraction accuracy (exact match)", "",
              "| File type | " + " | ".join(FIELDS) + " | **overall** | line items |",
              "|---|" + "---:|" * (len(FIELDS) + 2)]
    all_hits = all_total = 0
    for t, s in sorted(per_type.items()):
        if not s["field_total"]:
            continue
        cells = [pct(s["field_hits"][f], s["field_total"][f]) for f in FIELDS]
        h, n = sum(s["field_hits"].values()), sum(s["field_total"].values())
        all_hits, all_total = all_hits + h, all_total + n
        lines.append(f"| {t} | " + " | ".join(cells) + f" | **{pct(h, n)}** | {pct(s['li_hits'], s['li_total'])} |")
    lines += ["", f"**Overall field accuracy (measured files): {pct(all_hits, all_total)}** "
                  f"({all_hits}/{all_total} fields)", ""]

    lines += ["## Processing time (extraction only, per file)", "", "| File type | n | mean | p50 | p95 | max |",
              "|---|---:|---:|---:|---:|---:|"]
    for t, s in sorted(per_type.items()):
        ts = sorted(s["times"])
        if not ts:
            continue
        p95 = ts[min(len(ts) - 1, int(round(0.95 * (len(ts) - 1))))]
        lines.append(f"| {t} | {len(ts)} | {statistics.mean(ts):.3f}s | {statistics.median(ts):.3f}s | {p95:.3f}s | "
                     f"{ts[-1]:.3f}s |")

    lines += ["", "## Validation: detection of deliberately broken invoices", "",
              f"- Invoices with a planted tax/total error: {error_detection['expected']}, flagged as failed: "
              f"{error_detection['detected']} ({pct(error_detection['detected'], error_detection['expected'])})",
              f"- Clean invoices: {error_detection['clean']}, wrongly flagged as failed: "
              f"{error_detection['false_alarms']} ({pct(error_detection['false_alarms'], error_detection['clean'])})",
              "- Duplicate and cross-document checks need the database and are covered by the integration tests "
              "(`tests/integration`).", ""]
    if failures:
        lines += ["## Failures", ""] + [f"- `{n}`: {e}" for n, e in failures] + [""]
    lines += ["## How to reproduce", "", "```bash",
              "docker compose exec api python -m scripts.generate_fixtures --out /tmp/eval --count 30",
              "docker compose exec api python -m scripts.evaluate --data /tmp/eval --out /tmp/evaluation-report.md",
              "```", ""]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
