"""Digital PDF text extraction with PyMuPDF (text + word boxes) and page rasterisation for OCR."""
import fitz  # PyMuPDF

from app.processing.types import PageText, Word

MIN_CHARS_DIGITAL = 40  # fewer characters than this on a page -> treat page as scanned


class PdfError(Exception):
    pass


def open_pdf(data: bytes) -> fitz.Document:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as e:  # corrupt / not a PDF
        raise PdfError(f"Cannot open PDF: {e}") from e
    if doc.needs_pass:
        raise PdfError("PDF is password protected")
    if doc.page_count == 0:
        raise PdfError("PDF has no pages")
    return doc


def extract_page(page: fitz.Page, page_no: int) -> PageText:
    w, h = page.rect.width, page.rect.height
    words = [
        Word(t=txt, x0=x0 / w, y0=y0 / h, x1=x1 / w, y1=y1 / h, c=1.0)
        for (x0, y0, x1, y1, txt, *_rest) in page.get_text("words")
        if txt.strip()
    ]
    return PageText(page_no=page_no, text=page.get_text("text"), method="pdf_text", words=words, width=w, height=h)


def page_needs_ocr(pt: PageText) -> bool:
    return len(pt.text.strip()) < MIN_CHARS_DIGITAL


def render_page_png(page: fitz.Page, dpi: int = 300) -> bytes:
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    return pix.tobytes("png")
