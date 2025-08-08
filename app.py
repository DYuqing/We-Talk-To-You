"""
app.py
=======

A lightweight web application providing an interactive interface to the
Work and Income scraper and diagnostic tool.  This server uses only
Python's built‑in ``http.server`` module for maximum compatibility
without external dependencies.

Available pages include:

* ``/`` – Home page with links to the diagnostic survey, document browser
  and letter analysis upload.
* ``/diagnostic`` – Form for users to enter their circumstances; POST
  requests process the form and display benefit suggestions.
* ``/documents`` – List of downloaded HTML pages and PDF texts with
  links to view individual items.  Includes a manual update trigger.
* ``/documents/html/...`` – View a downloaded HTML page as plain text.
* ``/documents/pdf_text/...`` – View extracted text from a PDF.
* ``/upload`` – Form for uploading a scanned letter or PDF; POST
  requests run OCR and analyse the letter.

Run this script with ``python app.py``.  The server listens on port
8000 by default; change the constant at the bottom of the file as
required.
"""

from __future__ import annotations

import cgi
import html
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import diagnostic
import letter_analysis
from scraper import WorkAndIncomeScraper
from ocr_utils import extract_text

# Instantiate a global scraper.  It will create its data directories on
# initialisation.
SCRAPER = WorkAndIncomeScraper()

# Ensure uploads directory exists
UPLOAD_DIR = os.path.join(SCRAPER.output_dir, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


class WebHandler(BaseHTTPRequestHandler):
    """Handle HTTP requests for the Work and Income helper site."""

    def _render_page(self, title: str, body: str) -> None:
        """Helper to send a complete HTML page with basic styling."""
        content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }}
    header {{ background: #004d99; color: white; padding: 1rem; }}
    nav a {{ margin-right: 1rem; color: white; text-decoration: none; }}
    main {{ padding: 1rem; }}
    footer {{ margin-top: 2rem; padding: 1rem; font-size: 0.8rem; color: #666; text-align: center; }}
    .container {{ max-width: 800px; margin: auto; background: white; padding: 2rem; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
    form label {{ display: block; margin-top: 1rem; }}
    form input[type="text"], form input[type="number"], form select {{ width: 100%; padding: 0.5rem; }}
    form input[type="submit"] {{ margin-top: 1rem; padding: 0.5rem 1rem; background: #004d99; color: white; border: none; cursor: pointer; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
    table, th, td {{ border: 1px solid #ccc; }}
    th, td {{ padding: 0.5rem; text-align: left; }}
    pre {{ background: #f0f0f0; padding: 1rem; overflow-x: auto; }}
    .alert {{ background: #ffefc4; border-left: 4px solid #ffd42a; padding: 0.5rem 1rem; margin-bottom: 1rem; }}
  </style>
</head>
<body>
  <header>
    <nav>
      <a href="/">Home</a>
      <a href="/diagnostic">Diagnostic</a>
      <a href="/documents">Documents</a>
      <a href="/upload">Upload Letter</a>
    </nav>
  </header>
  <main>
    <div class="container">
    {body}
    </div>
  </main>
  <footer>
    &copy; Work and Income Helper
  </footer>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/":
            self._handle_home()
        elif path == "/diagnostic":
            self._handle_diagnostic_get()
        elif path == "/documents":
            # Optional manual update via ?update=1
            if query.get("update") == ["1"]:
                threading.Thread(target=SCRAPER.run_update, kwargs={"force": True}).start()
                message = "Update started in background.  Refresh the page shortly to see new documents."
            else:
                message = None
            self._handle_documents(message)
        elif path.startswith("/documents/html/"):
            rel = path[len("/documents/html/") :]
            self._serve_html_file(rel)
        elif path.startswith("/documents/pdf_text/"):
            rel = path[len("/documents/pdf_text/") :]
            self._serve_pdf_text_file(rel)
        elif path == "/upload":
            self._handle_upload_get()
        else:
            self.send_error(404, "Page not found")

    def do_POST(self) -> None:
        if self.path == "/diagnostic":
            self._handle_diagnostic_post()
        elif self.path == "/upload":
            self._handle_upload_post()
        else:
            self.send_error(404, "Page not found")

    # Handlers for specific routes

    def _handle_home(self) -> None:
        # Check if data is stale and show warning
        stale = SCRAPER.needs_update()
        try:
            with open(SCRAPER.last_scrape_file) as f:
                last_ts = int(f.read().strip())
                last_str = time.strftime("%Y-%m-%d", time.localtime(last_ts))
        except Exception:
            last_str = "Never"
        body_parts = []
        if stale:
            body_parts.append(
                f"<div class=\"alert\">Data is older than 30 days (last update: {last_str})."
                " <a href=\"/documents?update=1\">Click here</a> to run an update.</div>"
            )
        else:
            body_parts.append(f"<p>Last update: {html.escape(last_str)}. Data is up to date.</p>")
        body_parts.append(
            """
            <h2>Welcome</h2>
            <p>This tool helps you explore Work and Income information, suggests benefits based on your situation, and analyses official letters. Choose an option from the navigation bar.</p>
            """
        )
        self._render_page("Home", "\n".join(body_parts))

    def _handle_diagnostic_get(self) -> None:
        form_html = """
        <h2>Benefit Diagnostic Survey</h2>
        <form method="post" action="/diagnostic">
          <label>Age: <input type="number" name="age" min="0" required></label>
          <label>Do you have a partner or spouse?
            <select name="partner">
              <option value="yes">Yes</option>
              <option value="no" selected>No</option>
            </select>
          </label>
          <label>Do you care for any dependent children or disabled family members?
            <select name="dependents">
              <option value="yes">Yes</option>
              <option value="no" selected>No</option>
            </select>
          </label>
          <label>Approximate weekly income (NZD): <input type="number" name="income" min="0" step="0.01" required></label>
          <label>Employment status:
            <select name="employment">
              <option value="employed">Employed</option>
              <option value="unemployed">Unemployed</option>
              <option value="student">Student</option>
              <option value="retired">Retired</option>
            </select>
          </label>
          <label>Housing situation:
            <select name="housing">
              <option value="own">Own</option>
              <option value="rent" selected>Rent</option>
              <option value="social-housing">Social Housing</option>
              <option value="homeless">Homeless</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>Do you have valid NZ identification (passport or driver's licence)?
            <select name="id">
              <option value="yes">Yes</option>
              <option value="no" selected>No</option>
            </select>
          </label>
          <label>Do you have a bank account?
            <select name="bank">
              <option value="yes">Yes</option>
              <option value="no" selected>No</option>
            </select>
          </label>
          <input type="submit" value="Get Suggestions">
        </form>
        """
        self._render_page("Diagnostic Survey", form_html)

    def _handle_diagnostic_post(self) -> None:
        # Read and parse POST data
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length).decode("utf-8")
        params = parse_qs(data)
        try:
            age = int(params.get("age", ["0"])[0])
            weekly_income = float(params.get("income", ["0"])[0])
        except ValueError:
            self._render_page("Error", "<p>Invalid numeric input. Please go back and try again.</p>")
            return
        has_partner = params.get("partner", ["no"])[0].lower() == "yes"
        has_dependents = params.get("dependents", ["no"])[0].lower() == "yes"
        employment_status = params.get("employment", ["unemployed"])[0].lower()
        housing_status = params.get("housing", ["rent"])[0].lower()
        has_id = params.get("id", ["no"])[0].lower() == "yes"
        has_bank = params.get("bank", ["no"])[0].lower() == "yes"
        result = diagnostic.diagnose(
            age,
            has_partner,
            has_dependents,
            weekly_income,
            employment_status,
            housing_status,
            has_id,
            has_bank,
        )
        suggestions_html = "".join(f"<li>{html.escape(item)}</li>" for item in result["suggestions"])
        steps_html = "".join(f"<li>{html.escape(step)}</li>" for step in result["next_steps"])
        body = f"""
        <h2>Suggested Benefits</h2>
        <ul>{suggestions_html}</ul>
        <h3>General Next Steps</h3>
        <ul>{steps_html}</ul>
        <p><a href="/diagnostic">Back to survey</a></p>
        """
        self._render_page("Diagnostic Results", body)

    def _handle_documents(self, message: str | None = None) -> None:
        # Build lists of HTML and PDF text files
        html_files = []
        for root, _, files in os.walk(SCRAPER.html_dir):
            for f in files:
                if f.lower().endswith(".html"):
                    rel = os.path.relpath(os.path.join(root, f), SCRAPER.html_dir)
                    html_files.append(rel)
        pdf_text_files = []
        for root, _, files in os.walk(SCRAPER.text_dir):
            for f in files:
                if f.lower().endswith(".txt"):
                    rel = os.path.relpath(os.path.join(root, f), SCRAPER.text_dir)
                    pdf_text_files.append(rel)
        html_links = "".join(
            f"<li><a href='/documents/html/{html.escape(rel)}'>{html.escape(rel)}</a></li>"
            for rel in sorted(html_files)
        )
        pdf_links = "".join(
            f"<li><a href='/documents/pdf_text/{html.escape(rel)}'>{html.escape(rel)}</a></li>"
            for rel in sorted(pdf_text_files)
        )
        parts = ["<h2>Documents</h2>"]
        if message:
            parts.append(f"<div class=\"alert\">{html.escape(message)}</div>")
        parts.append(
            "<p>Use the lists below to browse downloaded pages and extracted PDF text. "
            "Click the update link to refresh the local archive.</p>"
        )
        parts.append(
            "<p><a href='/documents?update=1'>Run update now</a></p>"
        )
        parts.append("<h3>HTML Pages</h3><ul>" + html_links + "</ul>")
        parts.append("<h3>PDF Texts</h3><ul>" + pdf_links + "</ul>")
        self._render_page("Documents", "\n".join(parts))

    def _serve_html_file(self, rel_path: str) -> None:
        # Serve a downloaded HTML file as escaped text so it isn't executed
        local = os.path.join(SCRAPER.html_dir, rel_path)
        if not os.path.exists(local):
            self.send_error(404, "HTML file not found")
            return
        try:
            with open(local, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as exc:
            self.send_error(500, f"Error reading file: {exc}")
            return
        escaped = html.escape(content)
        body = f"<h2>{html.escape(rel_path)}</h2><pre>{escaped}</pre><p><a href='/documents'>Back to list</a></p>"
        self._render_page(rel_path, body)

    def _serve_pdf_text_file(self, rel_path: str) -> None:
        # Serve the extracted text from a PDF
        local = os.path.join(SCRAPER.text_dir, rel_path)
        if not os.path.exists(local):
            self.send_error(404, "Text file not found")
            return
        try:
            with open(local, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as exc:
            self.send_error(500, f"Error reading file: {exc}")
            return
        escaped = html.escape(content)
        body = f"<h2>{html.escape(rel_path)}</h2><pre>{escaped}</pre><p><a href='/documents'>Back to list</a></p>"
        self._render_page(rel_path, body)

    def _handle_upload_get(self) -> None:
        form = """
        <h2>Upload Letter for Analysis</h2>
        <p>Select a PDF or image file containing a letter from Work and Income. The text will be extracted (if possible) and analysed to highlight important information.</p>
        <form method="post" action="/upload" enctype="multipart/form-data">
          <input type="file" name="letter" accept=".pdf,.png,.jpg,.jpeg,.bmp,.gif,.tiff" required>
          <input type="submit" value="Analyse Letter">
        </form>
        """
        self._render_page("Upload Letter", form)

    def _handle_upload_post(self) -> None:
        # Parse multipart form data
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self.send_error(400, "Expected multipart form data")
            return
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers["Content-Type"],
            },
        )
        file_field = form.getfirst("letter")
        # FieldStorage returns the value string for text fields, and a FieldStorage
        # object for files; use the getfirst above to handle both
        if isinstance(file_field, cgi.FieldStorage):
            upload = file_field
        else:
            self._render_page("Error", "<p>No file uploaded. Please go back and try again.</p>")
            return
        filename = upload.filename
        if not filename:
            self._render_page("Error", "<p>Missing filename.</p>")
            return
        # Ensure safe filename
        safe_name = os.path.basename(filename).replace("..", "_")
        save_path = os.path.join(UPLOAD_DIR, safe_name)
        try:
            with open(save_path, "wb") as f:
                f.write(upload.file.read())
        except Exception as exc:
            self._render_page("Error", f"<p>Failed to save upload: {html.escape(str(exc))}</p>")
            return
        # Extract text
        extracted = extract_text(save_path)
        if not extracted:
            self._render_page(
                "Analysis Result",
                "<p>Unable to extract any text from the uploaded document. This may be because the file is scanned or unsupported. Try uploading a PDF containing selectable text or install OCR dependencies.</p>",
            )
            return
        analysis = letter_analysis.analyse_letter(extracted)
        key_lines_html = "".join(f"<li>{html.escape(line)}</li>" for line in analysis["key_lines"])
        body = f"""
        <h2>Letter Analysis Result</h2>
        <p><strong>Classification:</strong> {html.escape(analysis['classification'])}</p>
        <p><strong>Summary:</strong> {html.escape(analysis['summary'])}</p>
        <h3>Key Lines</h3>
        <ul>{key_lines_html or '<li>No key lines found.</li>'}</ul>
        <h3>Full Extracted Text</h3>
        <pre>{html.escape(extracted)}</pre>
        <p><a href="/upload">Analyse another letter</a></p>
        """
        self._render_page("Letter Analysis", body)


def run_server(port: int = 8000) -> None:
    """Start the HTTP server on the specified port."""
    server_address = ("", port)
    httpd = HTTPServer(server_address, WebHandler)
    print(f"Serving on http://localhost:{port} ...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopping.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    # Configure basic logging
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    # Start a background update if the data is stale
    if SCRAPER.needs_update():
        threading.Thread(target=SCRAPER.run_update, kwargs={"force": True}).start()
    run_server(port=8000)