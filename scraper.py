"""
scraper.py
==========

Classes and functions for downloading and archiving content from the
Work and Income website.  The `WorkAndIncomeScraper` class can crawl
pages starting from a given URL, download HTML pages and PDFs, and
optionally extract text from downloaded PDFs.

The scraper is conservative by design: it only follows links that
belong to the same domain as the starting URL and avoids infinite
loops by tracking visited URLs.  A configurable delay between
requests is provided to reduce load on the remote server.

In addition to the crawl functionality, the scraper stores metadata
about the last run so that it can decide whether a new scrape is
required.  This makes it suitable for automated periodic updates.
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ocr_utils import extract_text_from_pdf


@dataclass
class WorkAndIncomeScraper:
    """Crawl the Work and Income website and archive its contents locally."""

    start_url: str = "https://www.workandincome.govt.nz/map/index.html"
    output_dir: str = "data"
    delay: float = 0.3
    _visited: Set[str] = field(default_factory=set, init=False, repr=False)
    last_scrape_file: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # Create directories
        self.html_dir = os.path.join(self.output_dir, "html")
        self.pdf_dir = os.path.join(self.output_dir, "pdfs")
        self.text_dir = os.path.join(self.output_dir, "pdf_text")
        os.makedirs(self.html_dir, exist_ok=True)
        os.makedirs(self.pdf_dir, exist_ok=True)
        os.makedirs(self.text_dir, exist_ok=True)
        self.last_scrape_file = os.path.join(self.output_dir, "last_scrape.txt")

    def scrape(self) -> None:
        """Perform a depth‑first crawl of the website and download HTML and PDFs.

        All downloaded content is stored under the ``output_dir`` in
        subdirectories: HTML pages in ``html/`` and PDFs in ``pdfs/``.

        After crawling, ``extract_all_pdfs`` should be called to convert
        downloaded PDFs into text files in ``pdf_text/``.
        """
        parsed_start = urlparse(self.start_url)
        base_domain = parsed_start.netloc
        queue: deque[str] = deque([self.start_url])
        session = requests.Session()

        logging.info("Starting crawl from %s", self.start_url)

        while queue:
            current_url = queue.popleft()
            if current_url in self._visited:
                continue
            self._visited.add(current_url)
            try:
                response = session.get(current_url, timeout=30)
            except Exception as exc:
                logging.warning("Failed to fetch %s: %s", current_url, exc)
                continue
            if response.status_code != 200:
                logging.warning(
                    "Non‑200 status for %s: %s", current_url, response.status_code
                )
                continue
            content_type = response.headers.get("Content-Type", "").lower()
            # If PDF, save and skip further processing
            if "application/pdf" in content_type or current_url.lower().endswith(".pdf"):
                filename = re.sub(r"[<>:/\\|?*]", "_", os.path.basename(urlparse(current_url).path))
                if not filename.lower().endswith(".pdf"):
                    filename += ".pdf"
                pdf_path = os.path.join(self.pdf_dir, filename)
                # Avoid overwriting if file already exists
                if not os.path.exists(pdf_path):
                    with open(pdf_path, "wb") as f:
                        f.write(response.content)
                    logging.info("Downloaded PDF: %s", pdf_path)
                time.sleep(self.delay)
                continue
            # Otherwise assume HTML/text
            html_text = response.text
            # Determine relative path for saving
            parsed_url = urlparse(current_url)
            rel_path = parsed_url.path.lstrip("/")
            if not rel_path or rel_path.endswith("/"):
                rel_path = rel_path + "index.html"
            local_path = os.path.join(self.html_dir, rel_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(html_text)
            logging.info("Saved page: %s", local_path)
            # Parse links from the HTML and enqueue new URLs
            soup = BeautifulSoup(html_text, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                next_url = urljoin(current_url, href)
                parsed_next = urlparse(next_url)
                # Skip non-HTTP(S) schemes and external domains
                if parsed_next.scheme not in {"http", "https"}:
                    continue
                if parsed_next.netloc != base_domain:
                    continue
                # Normalise by removing fragment
                normalised = parsed_next._replace(fragment="").geturl()
                if normalised not in self._visited:
                    queue.append(normalised)
            time.sleep(self.delay)
        # Update last scrape time
        with open(self.last_scrape_file, "w") as f:
            f.write(str(int(time.time())))
        logging.info("Crawl complete.  HTML saved under %s, PDFs under %s", self.html_dir, self.pdf_dir)

    def extract_all_pdfs(self) -> None:
        """Iterate over all downloaded PDFs and extract their text.

        Extracted text is stored in files with the same relative path
        structure under ``pdf_text/``.
        """
        logging.info("Extracting text from downloaded PDFs...")
        for root, _, files in os.walk(self.pdf_dir):
            for name in files:
                if not name.lower().endswith(".pdf"):
                    continue
                pdf_path = os.path.join(root, name)
                rel_path = os.path.relpath(pdf_path, self.pdf_dir)
                txt_rel = os.path.splitext(rel_path)[0] + ".txt"
                txt_full = os.path.join(self.text_dir, txt_rel)
                os.makedirs(os.path.dirname(txt_full), exist_ok=True)
                # Skip extraction if the text file already exists and is non-empty
                if os.path.exists(txt_full):
                    try:
                        if os.path.getsize(txt_full) > 0:
                            continue
                    except OSError:
                        pass
                logging.info("Extracting %s", pdf_path)
                text = extract_text_from_pdf(pdf_path)
                with open(txt_full, "w", encoding="utf-8") as f:
                    f.write(text)
        logging.info("PDF text extraction complete.  Results stored under %s", self.text_dir)

    def needs_update(self, days: int = 30) -> bool:
        """Return True if the data should be refreshed based on age.

        Args:
            days: Maximum age of the scrape in days before a refresh is needed.

        Returns:
            True if the last scrape is older than ``days``, or if no previous
            scrape timestamp exists.  False otherwise.
        """
        try:
            with open(self.last_scrape_file, "r") as f:
                last_ts_str = f.read().strip()
                last_ts = int(last_ts_str)
        except Exception:
            return True
        age_seconds = time.time() - last_ts
        return age_seconds > days * 24 * 3600

    def run_update(self, force: bool = False) -> None:
        """Perform a scrape and PDF extraction if needed.

        Args:
            force: If True, run the update regardless of the age of the data.
        """
        if force or self.needs_update():
            logging.info("Starting site update...")
            self.scrape()
            self.extract_all_pdfs()
            logging.info("Site update complete.")
        else:
            logging.info("Site data is up to date; no update performed.")