from decimal import Decimal

import cv2
import numpy as np
import pytest

from app.processing import image_preprocess as ip
from app.processing.spreadsheet import SpreadsheetError, load_frames, parse_spreadsheet
from app.services.documents import UploadError, detect_kind


# ---------------------------------------------------------------- Excel / CSV
def test_excel_single_invoice(fixtures_dir, manifest):
    gt = manifest["invoice_00.xlsx"]
    res = parse_spreadsheet(load_frames((fixtures_dir / "invoice_00.xlsx").read_bytes(), ".xlsx"))
    assert len(res) == 1
    r = res[0]
    assert r.invoice_number == gt["invoice_number"] and r.supplier_name == gt["supplier_name"]
    assert Decimal(r.total) == Decimal(gt["total"]) and Decimal(r.subtotal) == Decimal(gt["subtotal"])
    assert len(r.line_items) == len(gt["line_items"])


def test_csv_register(fixtures_dir, manifest):
    res = parse_spreadsheet(load_frames((fixtures_dir / "register.csv").read_bytes(), ".csv"))
    reg = manifest["register.csv"]["register"]
    assert len(res) == len(reg)
    assert [r.invoice_number for r in res] == [x["invoice_number"] for x in reg]
    assert res[0].source_ref == {"sheet": "CSV", "row": 2}


def test_bad_spreadsheet_raises():
    with pytest.raises(SpreadsheetError):
        load_frames(b"PK\x03\x04 not a real xlsx", ".xlsx")


# ---------------------------------------------------------------- image preprocessing
def _text_image(angle: float) -> np.ndarray:
    img = np.full((800, 1200), 255, np.uint8)
    for i in range(12):
        cv2.putText(img, "INVOICE TOTAL 1,234.56 USD", (60, 80 + i * 55), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 0, 2)
    m = cv2.getRotationMatrix2D((600, 400), angle, 1.0)
    return cv2.warpAffine(img, m, (1200, 800), borderValue=255)


def test_deskew_corrects_rotation():
    rotated = _text_image(4.0)
    assert abs(ip.estimate_skew(rotated)) > 2
    fixed, angle = ip.deskew(rotated)
    assert abs(ip.estimate_skew(fixed)) < 1.0


def test_preprocess_outputs_binary_image():
    out = ip.preprocess(cv2.cvtColor(_text_image(0), cv2.COLOR_GRAY2BGR))
    assert out.ndim == 2 and set(np.unique(out)) <= {0, 255}
    assert out.shape[1] >= 1600  # upscaled for OCR


def test_corrupt_image_raises():
    with pytest.raises(ip.ImageError):
        ip.decode_image(b"\x89PNG\r\n\x1a\n garbage")


def test_multipage_tiff(fixtures_dir):
    tif = next(fixtures_dir.glob("*.tiff"))
    frames = ip.load_multipage(tif.read_bytes())
    assert len(frames) >= 1 and frames[0].shape[0] > 100


# ---------------------------------------------------------------- upload validation
def test_upload_accepts_valid_files(fixtures_dir):
    assert detect_kind("a.pdf", (fixtures_dir / "invoice_00_classic.pdf").read_bytes())[0] == "pdf"
    assert detect_kind("a.xlsx", (fixtures_dir / "invoice_00.xlsx").read_bytes())[0] == "spreadsheet"
    assert detect_kind("a.csv", (fixtures_dir / "register.csv").read_bytes())[0] == "csv"


@pytest.mark.parametrize("name,data,msg", [
    ("virus.exe", b"MZ....", "Unsupported"),
    ("empty.pdf", b"", "empty"),
    ("fake.pdf", b"\x89PNG\r\n\x1a\nxxxx", "does not match"),
    ("fake.png", b"%PDF-1.4", "does not match"),
    ("bin.csv", b"a,b\x00c", "does not match"),
])
def test_upload_rejects_bad_files(name, data, msg):
    with pytest.raises(UploadError, match=msg):
        detect_kind(name, data)


def test_upload_size_limit(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_mb", 1)
    with pytest.raises(UploadError, match="larger"):
        detect_kind("big.pdf", b"%PDF-1.4" + b"0" * (2 * 1024 * 1024))
