import os
import shutil
try:
    import pymupdf as fitz  # PyMuPDF (new import name)
except ImportError:
    import fitz  # older PyMuPDF
import config


def ocr_available():
    """OCR needs the Tesseract program. PyMuPDF finds its language data via TESSDATA_PREFIX."""
    return config.OCR_ENABLED and shutil.which("tesseract") is not None


def open_pdf(path):
    """Open and validate a PDF. Raises on corrupt/encrypted files."""
    doc = fitz.open(path)
    if doc.needs_pass:
        doc.close()
        raise ValueError("PDF is password protected")
    return doc


def page_count(path):
    doc = open_pdf(path)
    try:
        return len(doc)
    finally:
        doc.close()


def _ocr_page(page):
    try:
        tp = page.get_textpage_ocr(language=config.OCR_LANG, dpi=200, full=True)
        return page.get_text("text", textpage=tp) or ""
    except Exception as e:
        print(f"[ocr] page {page.number + 1} failed: {e}")
        return ""


def extract_pages(path):
    """Return ([(page_number, text), ...], empty_pages, ocr_pages).

    PyMuPDF page indexes are 0-based; they are converted to the 1-based numbers
    users see exactly once, here, so everything downstream is 1-based.
    Pages with almost no text are OCR'd when Tesseract is installed.
    """
    doc = open_pdf(path)
    use_ocr = ocr_available()
    pages, empty, ocr = [], 0, 0
    try:
        for idx, page in enumerate(doc):
            text = page.get_text("text") or ""
            if len(text.strip()) < 20:
                if use_ocr:
                    text = _ocr_page(page)
                    if len(text.strip()) >= 20:
                        ocr += 1
                if len(text.strip()) < 20:
                    empty += 1
            pages.append((idx + 1, text))
    finally:
        doc.close()
    return pages, empty, ocr
