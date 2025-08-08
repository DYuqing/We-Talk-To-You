"""
letter_analysis.py
===================

Utilities for analysing the content of letters or official documents
received from Work and Income.  These functions operate on plain text
strings and attempt to classify the document and extract salient
information for a human reader.

The analysis performed here is deliberately simple – it looks for
keywords that are commonly associated with sanctions, approvals or
rejections and summarises the document by taking a handful of sentences.
More sophisticated natural language processing (e.g. using NLTK or
transformer models) would improve accuracy but is beyond the scope of
this lightweight project.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple


KEYWORD_CLASSES: List[Tuple[str, List[str]]] = [
    ("Sanction or reduction notice", ["sanction", "reduced", "suspend", "suspension", "penalty"]),
    ("Approval or eligibility notice", ["approval", "approved", "granted", "eligible", "entitled"]),
    ("Rejection notice", ["rejection", "rejected", "declined", "not eligible", "denied"]),
]


def classify_letter(text: str) -> str:
    """Classify a letter based on the presence of certain keywords.

    Args:
        text: The letter contents as a single string.

    Returns:
        A classification string.  One of the keys from ``KEYWORD_CLASSES``
        or "General correspondence" if none of the keywords are found.
    """
    lower = text.lower()
    for label, keywords in KEYWORD_CLASSES:
        for kw in keywords:
            if kw in lower:
                return label
    return "General correspondence"


def summarise_letter(text: str, max_sentences: int = 3) -> str:
    """Return a brief summary consisting of up to ``max_sentences`` sentences.

    The summary simply takes the first few sentences from the document
    after stripping extra whitespace.  Sentences are detected by splitting
    on periods, exclamation marks and question marks.

    Args:
        text: Full text of the letter.
        max_sentences: Maximum number of sentences to include in the summary.

    Returns:
        A shortened string containing up to ``max_sentences`` sentences.
    """
    # Replace newlines with spaces and compress whitespace
    cleaned = re.sub(r"\s+", " ", text).strip()
    # Split on sentence terminators
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    selected = sentences[:max_sentences]
    return " ".join(selected)


def find_key_lines(text: str, keywords: List[str] | None = None, max_lines: int = 5) -> List[str]:
    """Find lines containing important keywords.

    Args:
        text: The full text of the letter.
        keywords: A list of keywords to search for.  If ``None``, a
            default set of benefit‑related words is used.
        max_lines: Maximum number of lines to return.

    Returns:
        A list of up to ``max_lines`` lines from the text that contain
        any of the supplied keywords.  Lines are de‑duplicated and
        returned in the order they appear in the original text.
    """
    if keywords is None:
        keywords = ["payment", "benefit", "date", "amount", "deadline", "evidence"]
    lower_keywords = [kw.lower() for kw in keywords]
    lines = []
    for line in text.splitlines():
        lower_line = line.lower()
        if any(kw in lower_line for kw in lower_keywords):
            stripped = line.strip()
            if stripped and stripped not in lines:
                lines.append(stripped)
        if len(lines) >= max_lines:
            break
    return lines


def analyse_letter(text: str) -> Dict[str, object]:
    """Analyse a letter and return a structured report.

    Args:
        text: The letter contents as a single string.

    Returns:
        A dictionary with the following keys:
            - ``classification``: A string classification of the letter.
            - ``summary``: A short summary of the contents.
            - ``key_lines``: A list of important lines containing keywords.
    """
    classification = classify_letter(text)
    summary = summarise_letter(text)
    key_lines = find_key_lines(text)
    return {
        "classification": classification,
        "summary": summary,
        "key_lines": key_lines,
    }