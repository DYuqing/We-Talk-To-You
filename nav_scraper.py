"""
nav_scraper.py
===============

This module provides a specialised scraper for the Work and Income MAP
navigation panel.  Unlike the general crawler in `scraper.py`, which
follows every link within the MAP domain, the `NavScraper` focuses
exclusively on the categories listed in the left‑hand menu of
``map/index.html``.  Each category is crawled separately, and only
pages whose paths begin with the category’s base path are visited.

The result is a more targeted download of the policy information under
each heading (Card Services, Deskfile, Employment and Training, etc.)
without pulling in unrelated sections of the website.
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections import deque
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ocr_utils import extract_text_from_pdf


class NavScraper:
    """Scrape only the categories listed in the MAP left navigation."""

    def __init__(self, start_url: str = "https://www.workandincome.govt.nz/map/index.html", output_dir: str = "data", delay: float = 0.3) -> None:
        self.start_url = start_url
        self.output_dir = output_dir
        self.delay = delay
        self.html_dir = os.path.join(self.output_dir, "html")
        self.pdf_dir = os.path.join(self.output_dir, "pdfs")
        self.text_dir = os.path.join(self.output_dir, "pdf_text")
        os.makedirs(self.html_dir, exist_ok=True)
        os.makedirs(self.pdf_dir, exist_ok=True)
        os.makedirs(self.text_dir, exist_ok=True)
        self.last_scrape_file = os.path.join(self.output_dir, "last_nav_scrape.txt")

    def scrape(self) -> None:
        """Entry point for scraping the navigation categories."""
        logging.info("Fetching navigation page %s", self.start_url)
        resp = requests.get(self.start_url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Find potential category links.  A category link is typically one
        # directory deep under /map/, e.g. /map/card-services/index.html.
        nav_links_set = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("/map/"):
                continue
            # Normalise by stripping query and fragment
            href_parsed = urlparse(href)
            path = href_parsed.path
            # Split into path segments (discard leading empty segment)
            segments = [seg for seg in path.split("/") if seg]
            # Expect segments like ['map', 'card-services', 'index.html']
            if len(segments) <= 3:
                # Ignore the top index.html itself
                if segments == ['map', 'index.html']:
                    continue
                full = urljoin(self.start_url, href)
                nav_links_set.add(full)
        nav_links = sorted(nav_links_set)
        logging.info("Found %d category links in navigation", len(nav_links))
        for link in nav_links:
            self._crawl_category(link)
        # After crawling all categories, extract PDF text
        self._extract_all_pdfs()
        with open(self.last_scrape_file, "w") as f:
            f.write(str(int(time.time())))
        logging.info("Navigation scrape complete.")

    def _crawl_category(self, category_url: str) -> None:
        """Crawl pages only within a single navigation category."""
        parsed_start = urlparse(category_url)
        # Determine base directory of this category.  If the start URL
        # includes a file (e.g. index.html or map-changes.html), drop the
        # filename.  Otherwise treat the path itself as the directory.
        start_path = parsed_start.path
        if start_path.endswith(".html"):
            base_dir = start_path.rsplit("/", 1)[0] + "/"
        else:
            base_dir = start_path.rstrip("/") + "/"
        base_domain = parsed_start.netloc
        queue: deque[str] = deque([category_url])
        visited: set[str] = set()
        session = requests.Session()
        logging.info("Crawling category %s", category_url)
        while queue:
            current_url = queue.popleft()
            if current_url in visited:
                continue
            visited.add(current_url)
            try:
                r = session.get(current_url, timeout=30)
            except Exception as exc:
                logging.warning("Failed to fetch %s: %s", current_url, exc)
                continue
            if r.status_code != 200:
                logging.warning("Non‑200 status for %s: %s", current_url, r.status_code)
                continue
            ct = r.headers.get("Content-Type", "").lower()
            if "application/pdf" in ct or current_url.lower().endswith(".pdf"):
                filename = re.sub(r"[<>:/\\|?*]", "_", os.path.basename(urlparse(current_url).path))
                if not filename.lower().endswith(".pdf"):
                    filename += ".pdf"
                pdf_path = os.path.join(self.pdf_dir, filename)
                if not os.path.exists(pdf_path):
                    with open(pdf_path, "wb") as f:
                        f.write(r.content)
                    logging.info("Downloaded PDF: %s", pdf_path)
                time.sleep(self.delay)
                continue
            # Save HTML
            rel_path = urlparse(current_url).path.lstrip("/")
            if not rel_path or rel_path.endswith("/"):
                rel_path += "index.html"
            local_path = os.path.join(self.html_dir, rel_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(r.text)
            # Parse internal links within the same category
            page = BeautifulSoup(r.text, "html.parser")
            for a_tag in page.find_all("a", href=True):
                href = a_tag["href"]
                next_url = urljoin(current_url, href)
                parsed = urlparse(next_url)
                if parsed.scheme not in {"http", "https"}:
                    continue
                if parsed.netloc != base_domain:
                    continue
                # Only follow links that stay within this category path
                if parsed.path.startswith(base_dir):
                    # Remove fragment
                    norm = parsed._replace(fragment="").geturl()
                    if norm not in visited:
                        queue.append(norm)
            time.sleep(self.delay)

    def _extract_all_pdfs(self) -> None:
        """Extract text from downloaded PDFs in a navigation scrape."""
        for root, _, files in os.walk(self.pdf_dir):
            for name in files:
                if not name.lower().endswith(".pdf"):
                    continue
                pdf_path = os.path.join(root, name)
                rel = os.path.relpath(pdf_path, self.pdf_dir)
                txt_rel = os.path.splitext(rel)[0] + ".txt"
                txt_full = os.path.join(self.text_dir, txt_rel)
                if os.path.exists(txt_full) and os.path.getsize(txt_full) > 0:
                    continue
                logging.info("Extracting text from %s", pdf_path)
                text = extract_text_from_pdf(pdf_path)
                os.makedirs(os.path.dirname(txt_full), exist_ok=True)
                with open(txt_full, "w", encoding="utf-8") as f:
                    f.write(text)