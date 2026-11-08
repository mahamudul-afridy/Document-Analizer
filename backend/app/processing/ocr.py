"""OCR (Tesseract, English). Kept behind a tiny interface so other engines can be added later."""
import numpy as np
import pytesseract

from app.processing.types import PageText, Word


class OcrError(Exception):
    pass


def tesseract_available() -> bool:
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_image(img: np.ndarray, page_no: int, lang: str = "eng") -> PageText:
    """Run Tesseract on a preprocessed image, returning words with normalised boxes and confidences."""
    h, w = img.shape[:2]
    try:
        data = pytesseract.image_to_data(img, lang=lang, config="--oem 1 --psm 3",
                                         output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractNotFoundError as e:
        raise OcrError("Tesseract is not installed") from e
    except Exception as e:
        raise OcrError(f"OCR failed: {e}") from e

    words: list[Word] = []
    confs: list[float] = []
    lines: dict[tuple, list[str]] = {}
    for i, txt in enumerate(data["text"]):
        txt = (txt or "").strip()
        conf = float(data["conf"][i])
        if not txt or conf < 0:
            continue
        x, y, bw, bh = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        c = max(0.0, min(conf / 100.0, 1.0))
        words.append(Word(txt, x / w, y / h, (x + bw) / w, (y + bh) / h, c))
        confs.append(c)
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(txt)

    text = "\n".join(" ".join(v) for v in lines.values())
    return PageText(page_no=page_no, text=text, method="tesseract", words=words, width=float(w), height=float(h),
                    ocr_confidence=(sum(confs) / len(confs)) if confs else 0.0)
