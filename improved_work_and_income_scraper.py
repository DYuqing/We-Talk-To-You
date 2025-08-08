"""
improved_work_and_income_scraper.py
===================================

This script provides a command‑line interface for downloading and
archiving the Work and Income website, extracting text from downloaded
PDFs, running a simple benefit diagnostic survey, and performing text
extraction on user‑supplied documents.  It improves upon the original
``work_and_income_scraper.py`` by fixing issues with PDF text extraction
and avoiding an always‑running scheduling loop.

Key features:

* Crawling and downloading of Work and Income pages and PDFs via the
  :class:`scraper.WorkAndIncomeScraper` class.  Extracted PDF text is
  stored under ``pdf_text/`` using ``pdftotext`` or OCR if available.
* A CLI diagnostic survey based on the logic in :mod:`diagnostic`.
* Ad‑hoc OCR of a supplied file (PDF or image) using functions in
  :mod:`ocr_utils`.
* Optional periodic scraping via a simple internal scheduler.  This
  avoids external dependencies like the ``schedule`` library.

Usage examples:

::

    python improved_work_and_income_scraper.py --scrape
    python improved_work_and_income_scraper.py --run-tool
    python improved_work_and_income_scraper.py --ocr path/to/file.pdf
    python improved_work_and_income_scraper.py --schedule --days 30

Note that periodic scraping runs indefinitely until interrupted.  To
run the interactive web interface instead, start ``python app.py``.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
import threading

from diagnostic import run_cli_survey
from ocr_utils import extract_text
from scraper import WorkAndIncomeScraper
from nav_scraper import NavScraper


def run_periodic_scrape(scraper: WorkAndIncomeScraper, interval_days: int) -> None:
    """Run the scraper periodically every ``interval_days`` days.

    This function runs indefinitely in the foreground.  Each cycle
    waits until the next scheduled run, checks whether the data is
    stale (older than the interval) and if so performs an update.

    Args:
        scraper: The scraper instance to run.
        interval_days: Number of days between scrapes.  A value of 30
            corresponds roughly to a monthly schedule.
    """
    logging.info(
        "Starting periodic scraping every %s days.  Press Ctrl+C to stop.",
        interval_days,
    )
    interval_seconds = interval_days * 24 * 3600
    while True:
        start = time.time()
        # Force update if needed (i.e. last scrape older than interval)
        if scraper.needs_update(days=interval_days):
            scraper.run_update(force=True)
        else:
            logging.info("Data is up to date; skipping scrape this cycle.")
        # Sleep until next run, adjusted for time taken by update
        elapsed = time.time() - start
        to_sleep = max(0, interval_seconds - elapsed)
        logging.info("Sleeping for %s seconds until next cycle.", int(to_sleep))
        try:
            time.sleep(to_sleep)
        except KeyboardInterrupt:
            logging.info("Periodic scraping interrupted by user.")
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Improved Work and Income scraper and tool")
    parser.add_argument(
        "--scrape", action="store_true", help="Download and archive the Work and Income website and extract PDF text."
    )
    parser.add_argument(
        "--run-tool", action="store_true", help="Run the interactive diagnostic survey in the command line."
    )
    parser.add_argument(
        "--ocr", type=str, help="Path to a scanned document or PDF to extract text from."
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data",
        help="Directory to store scraped data (default: data)",
    )
    parser.add_argument(
        "--nav-only",
        action="store_true",
        help="Only scrape the categories listed in the MAP navigation instead of the entire site."
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run periodic scraping indefinitely using the --days interval."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Interval in days for periodic scraping (default: 30)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    scraper = WorkAndIncomeScraper(output_dir=args.output)
    nav_scraper = NavScraper(start_url="https://www.workandincome.govt.nz/map/index.html", output_dir=args.output)

    if args.scrape:
        if args.nav_only:
            nav_scraper.scrape()
        else:
            scraper.run_update(force=True)

    if args.ocr:
        path = args.ocr
        if not os.path.exists(path):
            print(f"File not found: {path}")
        else:
            text = extract_text(path)
            if text:
                print(text)
            else:
                print("No text could be extracted.  Ensure the file contains selectable text or install OCR dependencies.")

    if args.run_tool:
        run_cli_survey()

    if args.schedule:
        try:
            if args.nav_only:
                # Periodic scraping for navigation categories
                def periodic_nav():
                    logging.info("Starting periodic navigation scrape every %s days.", args.days)
                    interval_seconds = args.days * 24 * 3600
                    while True:
                        start = time.time()
                        nav_scraper.scrape()
                        elapsed = time.time() - start
                        time.sleep(max(0, interval_seconds - elapsed))
                periodic_nav()
            else:
                run_periodic_scrape(scraper, args.days)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()