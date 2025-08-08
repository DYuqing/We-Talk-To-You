# We Talk To You—Work and Income Project

This repository contains a set of tools designed to help users interact with the New Zealand Work and Income website.  It aims to make it easier to download policy information for offline reading, run a benefit eligibility survey, and analyse official letters received from Work and Income. It also provides a web interface, so you can use these features through a browser without additional frameworks.

## Features

### 🔍 Website Scraper

- Recursively crawls the Work and Income MAP pages starting from
  `https://www.workandincome.govt.nz/map/index.html`.
- Downloads HTML pages and PDF documents while respecting domain boundaries.
- Stores downloaded content under a user‑specified directory (default: `data/`).
- Extracts text from downloaded PDFs using the system `pdftotext` package or falls back to image‑based OCR if Tesseract is available.
- Tracks the timestamp of the last crawl so that monthly updates can be scheduled.

### 📋 Diagnostic Survey

- A rule‑based questionnaire that asks for your age, income, living situation and other details.
- Suggests possible Work and Income benefits to explore, such as Jobseeker Support or Accommodation Supplement.
- Available via both a command‑line interface and the web interface.

### ✉️ Letter Analysis

- Extracts text from uploaded PDFs or images containing scanned letters.
- Classifies the letter into categories like “Sanction or reduction notice” or  “Approval or eligibility notice” based on keywords.
- Generates a brief summary and highlights key lines containing important information (dates, amounts, requests for evidence, etc.).

### 🌐 Web Interface

- Built on top of Python’s `http.server` module—no external web frameworks required.
- Exposes the scraper, diagnostic survey and letter analysis through a browser UI.
- Displays the list of downloaded documents and allows you to view extracted PDF text.
- Provides file upload for letter analysis.

## Directory Structure

```
├── app.py                    # Web server and UI (http.server)
├── diagnostic.py             # Diagnostic survey logic (CLI and web)
├── letter_analysis.py        # Letter classification and summarisation
├── ocr_utils.py              # PDF/image text extraction helpers
├── scraper.py                # WorkAndIncomeScraper class for crawling
├── improved_work_and_income_scraper.py  # CLI entry point
├── sample_letter.pdf         # Sample PDF for demonstration
└── data/                     # Default output directory (created at runtime)
    ├── html/                 # Saved HTML pages
    ├── pdfs/                 # Downloaded PDF files
    ├── pdf_text/             # Extracted text from PDFs
    └── uploads/              # Uploaded letters for analysis
```

## Installation

The tools are designed to work with minimal external dependencies.  At least one of the following methods for extracting PDF text must be available:

- **Poppler (`pdftotext`)** – recommended
- **Tesseract OCR** – optional fallback

### Installing Poppler

- **macOS (Homebrew)**

  ```python
  brew install poppler
  ```

- **Debian/Ubuntu**

  ```python
  sudo apt-get update
  sudo apt-get install poppler-utils
  ```

Poppler provides the `pdftotext` command used by the scraper to extract text from downloaded PDFs.  If `pdftotext` is not found on the system `PATH`, extraction will fall back to OCR.

### Optional: Installing OCR Dependencies

To perform OCR on scanned documents or images, install:

- `tesseract-ocr` – the Tesseract command line OCR engine
- `pytesseract` – Python bindings
- `pdf2image` and `Pillow` – to convert PDF pages to images

Example for macOS with Homebrew:

```python
brew install tesseract
pip install pytesseract pdf2image pillow
```

Example for Debian/Ubuntu:

```python
sudo apt-get install tesseract-ocr
pip install pytesseract pdf2image pillow
```

If neither Poppler nor Tesseract is available, the tools will warn that no text can be extracted from PDFs or images.

## Usage

### Command‑Line Interface

The file `improved_work_and_income_scraper.py` is the entry point for all
 command‑line operations.

**Crawl the Work and Income website and extract PDF text:**

```python
python improved_work_and_income_scraper.py --scrape --output data
```

This will save HTML pages to `data/html/`, PDFs to `data/pdfs/` and extracted PDF text to `data/pdf_text/`.  A timestamp is recorded in `data/last_scrape.txt` to determine when the next update is required.

**Run the diagnostic survey in the terminal:**

```python
python improved_work_and_income_scraper.py --run-tool
```

The survey will ask you for your age, income, living situation, etc., and then print suggested benefits and next steps.

**Extract text from a single file:**

```python
python improved_work_and_income_scraper.py --ocr path/to/document.pdf
```

If the file contains selectable text, it will be printed to the console.  For scanned documents, make sure OCR dependencies are installed.

**Periodic scraping:**

You can run the scraper on an interval without external scheduling tools:

```python
python improved_work_and_income_scraper.py --schedule --days 30
```

The script will loop indefinitely, checking once every 30 days whether the
 previous data is stale and running an update if needed.  Use Ctrl+C to stop.

### Web Interface

To use the interactive web UI, run:

```python
python app.py
```

By default the server listens on port **8000**.  Open `http://localhost:8000` in your browser to access the interface (note that some browsers block `localhost` pages when running inside certain sandboxed environments; run this on your own machine rather than in a restricted browser).  The interface provides:

- **Home** – shows when the last site update occurred and offers a button to refresh the data manually.
- **Diagnostic** – opens the same eligibility survey as the CLI, but in a friendly web form.
- **Documents** – lists the downloaded HTML pages and extracted PDF texts; you can click entries to view their content as plain text.
- **Upload Letter** – lets you upload a PDF or image of a letter and returns its classification, a short summary and key lines.  The full extracted text is also displayed.

### Demonstration Example

This repository includes a small PDF file, `sample_letter.pdf`  [sample_letter.pdf](https://files.oaiusercontent.com/file-4apCq1vaTeMFkgxEGTy3St?se=2025-08-08T22%3A02%3A42Z&sp=r&sv=2024-08-04&sr=b&rscc=max-age%3D299%2C immutable%2C private&rscd=attachment%3B filename%3Dsample_letter.pdf&sig=bwwYVhJ0ljlz/P4jx9bDr4NztLp7vWQXNuq4TqC2aQc%3D), that reads:

> Your benefit has been approved, please continue.

After installing Poppler, run:

```python
python improved_work_and_income_scraper.py --ocr sample_letter.pdf
```

The output should be the same as the sentence above.  You can also analyse the document programmatically:

```python
from ocr_utils import extract_text
from letter_analysis import analyse_letter

text = extract_text("sample_letter.pdf")
report = analyse_letter(text)
print(report)
```

The `analyse_letter` function returns a dictionary similar to:

```python
{
    'classification': 'Approval or eligibility notice',
    'summary': 'Your benefit has been approved, please continue.',
    'key_lines': ['Your benefit has been approved, please continue.']
}
```

## Troubleshooting

- **No text extracted / Poppler not found** – If you see warnings like `Unable to extract text... both pdftotext and OCR are unavailable`, it means neither Poppler nor Tesseract is installed.  Install one of them as described above.  On macOS you can use Homebrew: `brew install poppler`.
- **Poppler installation errors** – When attempting to install the `pdftotext` Python package you might see compiler errors.  You do not need this package; installing the Poppler utilities themselves (see installation section) is sufficient.
- **OCR fails on images** – Ensure you have installed `tesseract-ocr` as a  system package and `pytesseract`, `pdf2image` and `Pillow` via `pip`.
