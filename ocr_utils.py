"""
ocr_utils.py
================

Helper functions for extracting text from PDF documents and images.  The
environment in which this application runs may not have access to all
third‑party OCR libraries, so this module attempts to use whatever tools
are available.  The preferred method for PDFs is to invoke the
``pdftotext`` command from the Poppler suite; this produces reliable
output without any additional Python dependencies.  If ``pdftotext`` is
unavailable and ``pytesseract`` is installed, it falls back to using
Tesseract OCR on images produced via ``pdf2image``.

Functions in this module never throw exceptions – they catch errors and
return empty strings when text extraction fails.  Logging is used to
report problems to the caller.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import List

try:
    from pdf2image import convert_from_path  # type: ignore
except Exception:
    convert_from_path = None  # type: ignore

try:
    import pytesseract  # type: ignore
except Exception:
    pytesseract = None  # type: ignore

try:
    from PIL import Image  # type: ignore
except Exception:
    Image = None  # type: ignore


def _extract_text_pdftotext(pdf_path: str) -> str:
    """Use the ``pdftotext`` CLI tool to extract text from a PDF file.

    If ``pdftotext`` is not found on the system path or an error occurs
    while running it, an empty string is returned.

    Args:
        pdf_path: The absolute or relative path to the PDF file.

    Returns:
        The extracted text as a single string, or an empty string if the
        command fails.
    """
    pdftotext_path = shutil.which("pdftotext")
    if not pdftotext_path:
        return ""
    try:
        result = subprocess.run(
            [pdftotext_path, "-layout", "-enc", "UTF-8", "-nopgbrk", pdf_path, "-"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout.decode("utf-8", errors="ignore")
    except Exception as exc:
        logging.warning("pdftotext failed on %s: %s", pdf_path, exc)
        return ""


def _extract_text_pytesseract_image(image) -> str:
    """Use pytesseract on a PIL image object to extract text.

    If pytesseract is not installed, returns an empty string.
    """
    if pytesseract is None:
        return ""
    try:
        return pytesseract.image_to_string(image)
    except Exception as exc:
        logging.warning("pytesseract failed on image: %s", exc)
        return ""


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF by using the best available method.

    The extraction strategy is as follows:

    1. Try to use the ``pdftotext`` command.  This requires the Poppler
       utilities to be installed on the system.  If successful, the
       extracted text is returned.
    2. If ``pdftotext`` is unavailable or fails and both ``pdf2image`` and
       ``pytesseract`` are available, convert each page of the PDF into
       an image and run Tesseract OCR on it.  The resulting strings from
       all pages are concatenated.
    3. If none of the above methods are available, return an empty string.

    Args:
        pdf_path: Path to the PDF file to process.

    Returns:
        A string containing the extracted text.  If extraction fails,
        returns an empty string.
    """
    # First try pdftotext
    text = _extract_text_pdftotext(pdf_path)
    if text:
        return text

    # Fall back to OCR if possible
    if convert_from_path is None or pytesseract is None:
        logging.warning(
            "Unable to extract text from %s: both pdftotext and OCR are unavailable.",
            pdf_path,
        )
        return ""
    try:
        pages = convert_from_path(pdf_path)
    except Exception as exc:
        logging.error("Failed to convert PDF to images for OCR (%s): %s", pdf_path, exc)
        return ""
    extracted_pages: List[str] = []
    for idx, page in enumerate(pages, start=1):
        logging.info("OCR processing page %s of %s in %s", idx, len(pages), pdf_path)
        extracted_pages.append(_extract_text_pytesseract_image(page))
    return "\n".join(extracted_pages)


def extract_text_from_image(image_path: str) -> str:
    """Extract text from an image file using Tesseract OCR.

    Args:
        image_path: Path to the image file.

    Returns:
        A string containing the extracted text, or an empty string if
        extraction fails or Tesseract/Pillow are unavailable.
    """
    if Image is None or pytesseract is None:
        logging.warning(
            "Cannot extract text from image %s: Pillow or pytesseract is not available.",
            image_path,
        )
        return ""
    try:
        with Image.open(image_path) as img:
            return _extract_text_pytesseract_image(img)
    except Exception as exc:
        logging.error("Failed to extract text from image %s: %s", image_path, exc)
        return ""


def extract_text(file_path: str) -> str:
    """Dispatch extraction based on file extension.

    Args:
        file_path: Path to the file to process.  PDF files are
            forwarded to :func:`extract_text_from_pdf`.  Supported image
            formats (PNG, JPEG) are forwarded to
            :func:`extract_text_from_image`.  Unknown formats result in an
            empty string.

    Returns:
        Extracted text as a string, or an empty string if extraction is
        unsupported.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff"}:
        return extract_text_from_image(file_path)
    else:
        logging.warning("Unsupported file format for OCR: %s", file_path)
        return ""